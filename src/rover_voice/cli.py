"""Command-line entry point: parse flags and start one mode."""

import argparse
import logging
import sys

from rover_voice.events import ConsoleView, EventBus, JsonView, Status
from rover_voice.session import RoverSession


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # Library warnings (bridge disconnects, model failures) go to stderr, so
    # --json keeps stdout to one event per line.
    logging.basicConfig(
        level=logging.WARNING, stream=sys.stderr, format="%(levelname)s: %(message)s"
    )
    if not args.json:
        _print_banner()

    if args.doa or args.doa_calibrate or args.check_array:
        from rover_voice.doa_tools import (
            run_array_check,
            run_doa_calibrate,
            run_doa_monitor,
        )

        device = args.input or "xiao"
        if args.check_array:
            return run_array_check(device)
        if args.doa_calibrate:
            return run_doa_calibrate(device)
        return run_doa_monitor(device)
    if args.self_test:
        from rover_voice.selftest import run_self_test

        return run_self_test(speak=not args.no_speak, use_llm=not args.no_llm)
    if args.script:
        from rover_voice.script_test import run_script

        return run_script(
            speak=not args.no_speak,
            use_llm=not args.no_llm,
            text_mode=args.text,
            debug=args.debug,
            input_device=args.input,
        )

    events = EventBus(JsonView() if args.json else ConsoleView())
    session = RoverSession(speak=not args.no_speak, use_llm=not args.no_llm, events=events)
    if args.text:
        return run_text(session)
    from rover_voice.runtime import run_live

    return run_live(session, debug=args.debug, input_device=args.input)


def run_text(session: RoverSession) -> int:
    session.events.emit(Status("Type a command or a question. Enter quit to exit."))
    prompt = "> " if sys.stdin.isatty() else ""
    while True:
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            break
        if not session.handle_text(line):
            session.speaker.wait()
            break
        session.speaker.wait()
    return 0


def _print_banner() -> None:
    print("Rover voice prototype")
    print("Commands: follow, stay, fetch, come, give")
    print("Exact phrases and other wording with the same meaning are both accepted.")
    print("A recognized command is printed and spoken. Rover motion is not run from here.")
    print("Other speech is answered by a small local 4-bit chat model.")
    print()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rover voice command prototype for Mac")
    parser.add_argument(
        "--text",
        action="store_true",
        help="Type utterances instead of using the microphone",
    )
    parser.add_argument(
        "--no-speak",
        action="store_true",
        help="Print replies without using the speakers",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Use a fixed reply instead of the local chat model",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Transcribe synthesized speech and check the five commands",
    )
    parser.add_argument(
        "--input",
        help=(
            "Microphone name or index, or xiao for the reSpeaker Flex via the "
            "XIAO. Default is the Mac's current input"
        ),
    )
    parser.add_argument(
        "--script",
        action="store_true",
        help="Walk through scripts/test_lines.txt, one phrase at a time",
    )
    parser.add_argument("--debug", action="store_true", help="Print microphone levels")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write events as JSON lines on stdout, for a rover controller",
    )
    parser.add_argument(
        "--doa",
        action="store_true",
        help="Show the live direction of speech from the reSpeaker Flex",
    )
    parser.add_argument(
        "--check-array",
        action="store_true",
        help="Check that the reSpeaker Flex bridge streams audio and direction",
    )
    parser.add_argument(
        "--doa-calibrate",
        action="store_true",
        help="Teach the reSpeaker Flex which way is the rover's front",
    )
    return parser
