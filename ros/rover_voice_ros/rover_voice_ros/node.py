"""ROS 2 node around the rover voice loop.

The voice loop runs on the main thread, as it does from the terminal.
rclpy spins on a background thread: incoming requests go through
LoopControl, and outgoing events are published as they are emitted.
"""

import os
import signal
import threading
import time
from pathlib import Path

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String
from std_srvs.srv import SetBool

from rover_voice.audio.base import Microphone
from rover_voice.audio.direction import DirectionSample
from rover_voice.control import LoopControl, Say, SetListening, TextInput
from rover_voice.events import (
    CommandAccepted,
    ConsoleView,
    Event,
    EventBus,
    Heard,
    Reply,
    StateChanged,
    to_json,
)
from rover_voice.runtime import load_asr, run_headless, run_live
from rover_voice.session import RoverSession
from rover_voice_msgs.msg import SoundDirection, Utterance, VoiceCommand
from rover_voice_ros import mapping

_LEVELS = {
    "ok": DiagnosticStatus.OK,
    "warn": DiagnosticStatus.WARN,
    "error": DiagnosticStatus.ERROR,
}
# No microphone or speech model: text arrives on ~/text_in.
_TEXT_ONLY = {"none", "topic"}


class VoiceNode(Node):
    def __init__(self, control: LoopControl) -> None:
        super().__init__("rover_voice")
        self.control = control
        self.voice_input = str(self.declare_parameter("input", "xiao").value)
        self.speak = bool(self.declare_parameter("speak", True).value)
        self.use_llm = bool(self.declare_parameter("use_llm", True).value)
        self.frame_id = str(self.declare_parameter("frame_id", "respeaker_link").value)
        self.asr_backend = str(self.declare_parameter("asr_backend", "").value)
        self.asr_model = str(self.declare_parameter("asr_model", "").value)
        self.log_dir = str(self.declare_parameter("log_dir", "~/.ros/rover_voice").value)

        # A late subscriber must not act on an old command, so commands are
        # volatile. The current state is latched for controllers that start later.
        reliable = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        latched = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.command_pub = self.create_publisher(VoiceCommand, "~/command", reliable)
        self.state_pub = self.create_publisher(String, "~/state", latched)
        self.utterance_pub = self.create_publisher(Utterance, "~/utterance", reliable)
        self.reply_pub = self.create_publisher(String, "~/reply", reliable)
        self.events_pub = self.create_publisher(
            String, "~/events", QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE)
        )
        self.direction_pub = self.create_publisher(
            SoundDirection, "~/sound_direction", qos_profile_sensor_data
        )
        self.diagnostics_pub = self.create_publisher(DiagnosticArray, "/diagnostics", 10)

        self.create_subscription(String, "~/say", self._on_say, reliable)
        self.create_subscription(String, "~/text_in", self._on_text, reliable)
        self.create_service(SetBool, "~/set_listening", self._on_set_listening)
        self.create_timer(1.0, self._publish_diagnostics)

        self._microphone: Microphone | None = None
        self._input_name: str | None = None
        self._failed: str | None = None

    # Voice loop -> ROS

    def run(self) -> int:
        """Run the voice loop on this thread until shutdown."""
        events = EventBus(self._on_event)
        log_dir = Path(os.path.expanduser(self.log_dir)) if self.log_dir else None
        session = RoverSession(
            speak=self.speak,
            use_llm=self.use_llm,
            log_dir=log_dir,
            events=events,
            allow_quit=False,
        )
        self.state_pub.publish(String(data=session.state.command))
        if self.voice_input in _TEXT_ONLY:
            self._input_name = "text on ~/text_in"
            return run_headless(session, self.control)

        kwargs = {}
        if self.asr_backend:
            kwargs["backend"] = self.asr_backend
        asr = load_asr(events, model_id=self.asr_model, **kwargs)
        if asr is None:
            self._failed = "The speech model did not load."
            return 1
        device = None if self.voice_input in {"", "default"} else self.voice_input
        code = run_live(
            session,
            input_device=device,
            control=self.control,
            asr=asr,
            on_open=self._on_open,
        )
        if self._input_name is None:
            self._failed = f"Could not open the input {self.voice_input!r}."
        return code

    def _on_open(self, microphone: Microphone) -> None:
        self._microphone = microphone
        self._input_name = self.voice_input
        if microphone.directions is not None:
            microphone.directions.subscribe(self._on_direction)

    def _on_event(self, event: Event) -> None:
        line = ConsoleView.format(event)
        if line:
            self.get_logger().info(line)
        self.events_pub.publish(String(data=to_json(event)))
        match event:
            case CommandAccepted():
                msg = VoiceCommand(**mapping.command_fields(event))
                self._stamp(msg, event.started_at)
                self.command_pub.publish(msg)
            case Heard():
                msg = Utterance(**mapping.utterance_fields(event))
                self._stamp(msg, event.started_at)
                self.utterance_pub.publish(msg)
            case Reply(speech):
                self.reply_pub.publish(String(data=speech))
            case StateChanged(command):
                self.state_pub.publish(String(data=command))

    def _on_direction(self, sample: DirectionSample) -> None:
        directions = self._microphone.directions if self._microphone else None
        calibration = directions.calibration if directions is not None else None
        msg = SoundDirection(**mapping.direction_fields(sample, calibration))
        self._stamp(msg, None)
        self.direction_pub.publish(msg)

    def _stamp(self, msg, wall_time: float | None) -> None:
        sec, nanosec = mapping.stamp(wall_time, time.time())
        msg.header.stamp.sec = sec
        msg.header.stamp.nanosec = nanosec
        msg.header.frame_id = self.frame_id

    def _publish_diagnostics(self) -> None:
        microphone = self._microphone
        directions = microphone.directions if microphone is not None else None
        health = getattr(microphone, "health", None)
        report = health.report() if health is not None else None
        level, message, values = mapping.diagnostic(
            self._input_name,
            self.control.listening,
            directions is not None and directions.calibration is not None,
            int(getattr(microphone, "reconnects", 0)),
            self._failed,
            audio_level="ok" if report is None else report.level,
            audio_message="Audio ok." if report is None else report.message,
            audio_rms=0.0 if report is None else report.rms,
            audio_peak=0.0 if report is None else report.peak,
        )
        status = DiagnosticStatus(
            level=_LEVELS[level],
            name=f"{self.get_name()}: voice input",
            message=message,
            hardware_id=self.voice_input,
            values=[KeyValue(key=key, value=value) for key, value in values],
        )
        array = DiagnosticArray(status=[status])
        array.header.stamp = self.get_clock().now().to_msg()
        self.diagnostics_pub.publish(array)

    # ROS -> voice loop

    def _on_say(self, msg: String) -> None:
        self.control.submit(Say(msg.data))

    def _on_text(self, msg: String) -> None:
        self.control.submit(TextInput(msg.data))

    def _on_set_listening(self, request, response):
        self.control.submit(SetListening(bool(request.data)))
        response.success = True
        response.message = "listening" if request.data else "paused"
        return response


def main(args: list[str] | None = None) -> int:
    # Python's own SIGINT handling raises KeyboardInterrupt in the voice
    # loop, which then closes the microphone cleanly. SIGTERM does the same.
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    control = LoopControl()
    signal.signal(signal.SIGTERM, lambda *_: control.stop())
    node = VoiceNode(control)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    spinner = threading.Thread(target=executor.spin, daemon=True)
    spinner.start()
    try:
        code = node.run()
    except KeyboardInterrupt:
        code = 0
    finally:
        control.stop()
        executor.shutdown()
        node.destroy_node()
        rclpy.try_shutdown()
        spinner.join(timeout=1.0)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
