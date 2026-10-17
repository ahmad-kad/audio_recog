# Source this in each shell that runs the ROS node:
#   source scripts/ros_env.sh
# ROS 2 first, then this workspace, then the repo's venv, so `python3` is
# the venv (speech models) and rclpy and the messages are on PYTHONPATH.
_rover_root="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
source "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"
source "$_rover_root/install/setup.bash"
source "$_rover_root/.venv/bin/activate"
export ROVER_DOA_CALIBRATION="${ROVER_DOA_CALIBRATION:-$_rover_root/.doa_calibration.json}"
unset _rover_root
