"""Start the voice node and the base_link -> respeaker_link transform.

    ros2 launch rover_voice_ros voice.launch.py input:=xiao
    ros2 launch rover_voice_ros voice.launch.py params_file:=/path/voice.yaml

Directions in the messages are already turned to the rover's frame by
the array calibration, so the transform only places the array (x, y, z).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    defaults = PathJoinSubstitution(
        [FindPackageShare("rover_voice_ros"), "config", "voice.yaml"]
    )
    args = [
        DeclareLaunchArgument("params_file", default_value=defaults),
        DeclareLaunchArgument("input", default_value="xiao"),
        DeclareLaunchArgument("speak", default_value="true"),
        DeclareLaunchArgument("use_llm", default_value="true"),
        DeclareLaunchArgument("namespace", default_value=""),
        DeclareLaunchArgument("frame_id", default_value="respeaker_link"),
        DeclareLaunchArgument("parent_frame", default_value="base_link"),
        DeclareLaunchArgument("publish_tf", default_value="true"),
        DeclareLaunchArgument("x", default_value="0.0"),
        DeclareLaunchArgument("y", default_value="0.0"),
        DeclareLaunchArgument("z", default_value="0.0"),
    ]
    voice = Node(
        package="rover_voice_ros",
        executable="voice_node",
        name="rover_voice",
        namespace=LaunchConfiguration("namespace"),
        output="screen",
        emulate_tty=True,
        # A lost USB link is handled inside the node; a crash restarts it.
        respawn=True,
        respawn_delay=5.0,
        parameters=[
            LaunchConfiguration("params_file"),
            {
                "input": LaunchConfiguration("input"),
                "speak": LaunchConfiguration("speak"),
                "use_llm": LaunchConfiguration("use_llm"),
                "frame_id": LaunchConfiguration("frame_id"),
            },
        ],
    )
    transform = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="respeaker_tf",
        namespace=LaunchConfiguration("namespace"),
        condition=IfCondition(LaunchConfiguration("publish_tf")),
        arguments=[
            "--x", LaunchConfiguration("x"),
            "--y", LaunchConfiguration("y"),
            "--z", LaunchConfiguration("z"),
            "--frame-id", LaunchConfiguration("parent_frame"),
            "--child-frame-id", LaunchConfiguration("frame_id"),
        ],
    )
    return LaunchDescription([*args, voice, transform])
