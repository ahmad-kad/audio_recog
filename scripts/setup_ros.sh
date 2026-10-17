#!/usr/bin/env bash
# Linux rover computer with ROS 2 Jazzy (Ubuntu 24.04): Python environment,
# then build the ROS packages in ros/ into build/ and install/.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${ROS_DISTRO:-}" ]]; then
  if [[ -f /opt/ros/jazzy/setup.bash ]]; then
    set +u; source /opt/ros/jazzy/setup.bash; set -u
  else
    echo "ROS 2 Jazzy not found. Install ros-jazzy-ros-base first." >&2
    exit 1
  fi
fi
missing=()
for program in espeak-ng ffmpeg; do
  command -v "$program" >/dev/null || missing+=("$program")
done
if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
  missing+=(libportaudio2)
fi
if (( ${#missing[@]} )); then
  echo "Missing system packages. Install them with:" >&2
  echo "  sudo apt install ${missing[*]}" >&2
  exit 1
fi
scripts/setup.sh
colcon build --base-paths ros
# The node must start with the venv's python3, which has the speech models.
node=install/rover_voice_ros/lib/rover_voice_ros/voice_node
if [[ "$(head -1 "$node")" != "#!/usr/bin/env python3" ]]; then
  echo "warning: $node does not start with #!/usr/bin/env python3." >&2
  echo "Run it with the venv instead: .venv/bin/python $node" >&2
fi
echo "ROS packages built. In each new shell: source scripts/ros_env.sh"
echo "Then: ros2 launch rover_voice_ros voice.launch.py input:=xiao"
