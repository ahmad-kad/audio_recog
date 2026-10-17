#!/usr/bin/env bash
# Python environment with the pinned versions in requirements.txt.
# Works on an Apple Silicon Mac and on Linux. On Linux, source ROS 2 first
# (scripts/setup_ros.sh does) so the venv can also see rclpy's dependencies.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v python3.12 >/dev/null; then
  if [[ "$(uname)" == "Darwin" ]]; then
    echo "python3.12 not found. Install it with: brew install python@3.12" >&2
  else
    echo "python3.12 not found. On Ubuntu 24.04: sudo apt install python3.12-venv" >&2
  fi
  exit 1
fi
if [[ ! -d .venv ]]; then
  if [[ -n "${ROS_DISTRO:-}" ]]; then
    # rclpy runs in this venv; it needs PyYAML and friends from apt.
    python3.12 -m venv --system-site-packages .venv
  else
    python3.12 -m venv .venv
  fi
fi
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/pip install -q --no-deps -e .
echo "Setup complete. Run the tests with: scripts/test"
echo "Start listening with: scripts/run"
