from glob import glob

from setuptools import find_packages, setup

package_name = "rover_voice_ros"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Ahmad Kaddoura",
    maintainer_email="kaddoura.ahmad@gmail.com",
    description="ROS 2 node for the rover voice loop.",
    license="TODO: License declaration",
    entry_points={
        "console_scripts": [
            "voice_node = rover_voice_ros.node:main",
        ],
    },
)
