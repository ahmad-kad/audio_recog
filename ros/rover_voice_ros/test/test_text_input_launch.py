"""Integration test: text on ~/text_in comes back as a VoiceCommand.

Runs with `colcon test --packages-select rover_voice_ros`. It needs no
microphone or speech model (input:=none).
"""

import time
import unittest

import launch
import launch_ros.actions
import launch_testing.actions
import pytest
import rclpy
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from rover_voice_msgs.msg import VoiceCommand


@pytest.mark.launch_test
def generate_test_description():
    node = launch_ros.actions.Node(
        package="rover_voice_ros",
        executable="voice_node",
        name="rover_voice",
        parameters=[
            {"input": "none", "speak": False, "use_llm": False, "log_dir": ""}
        ],
    )
    return launch.LaunchDescription([node, launch_testing.actions.ReadyToTest()])


class TestTextInput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node("rover_voice_test")

    @classmethod
    def tearDownClass(cls):
        cls.node.destroy_node()
        rclpy.shutdown()

    def _collect(self, msg_type, topic, qos, send=None, timeout=20.0):
        received = []
        self.node.create_subscription(msg_type, topic, received.append, qos)
        deadline = time.monotonic() + timeout
        while not received and time.monotonic() < deadline:
            if send is not None:
                send()
            rclpy.spin_once(self.node, timeout_sec=0.5)
        return received

    def test_follow_is_published_as_a_command(self):
        reliable = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        text = self.node.create_publisher(String, "/rover_voice/text_in", reliable)
        sent = []

        def send():
            # Resend until the node is up; the first command stops the loop.
            if text.get_subscription_count() > 0 and len(sent) < 3:
                text.publish(String(data="follow me"))
                sent.append(1)

        commands = self._collect(VoiceCommand, "/rover_voice/command", reliable, send)
        self.assertTrue(commands, "no VoiceCommand received")
        self.assertEqual(commands[0].intent, VoiceCommand.FOLLOW)
        self.assertEqual(commands[0].transcript, "follow me")
        self.assertFalse(commands[0].has_direction)

    def test_state_is_latched(self):
        latched = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        states = self._collect(String, "/rover_voice/state", latched)
        self.assertTrue(states, "no state received")
