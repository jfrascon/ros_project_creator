#!/bin/bash

export ROS_HOME="${ROS_HOME:-${HOME}/.ros}"
export ROS_LOG_DIR="${ROS_LOG_DIR:-${HOME}/.ros/logs}"
export ROS_TEST_RESULTS_DIR="${ROS_TEST_RESULTS_DIR:-${HOME}/.ros/tests}"
export ROS_CONFIG_HOME="${ROS_CONFIG_HOME:-${HOME}/.config/ros.org}"
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://localhost:11311}"
export ROS_HOSTNAME="${ROS_HOSTNAME:-localhost}"
export ROSCONSOLE_CONFIG_FILE="${ROSCONSOLE_CONFIG_FILE:-/opt/ros/{{ ros_distro }}/share/ros/config/rosconsole.config}"
export ROSCONSOLE_STDOUT_LINE_BUFFERED="${ROSCONSOLE_STDOUT_LINE_BUFFERED:-1}"
export ROSCONSOLE_FORMAT="${ROSCONSOLE_FORMAT:-'[\${severity}] [\${time}] \${message}'}"

# Format: ${file}, ${function}, ${line}, ${logger}, ${message}, ${node}, ${severity}, ${thread},
#         ${time}, ${walltime}.

# Check if workspace setup exists
if [ -s "${HOME}/workspace/install/setup.bash" ]; then
    . "${HOME}/workspace/install/setup.bash"
elif [ -s "${HOME}/workspace/devel/setup.bash" ]; then
    . "${HOME}/workspace/devel/setup.bash"
elif [ -s "/opt/ros/{{ ros_distro }}/setup.bash" ]; then
    . "/opt/ros/{{ ros_distro }}/setup.bash"
else
    echo "No ROS workspace found"
    exit 1
fi

[ -s /usr/share/gazebo/setup.sh ] && . /usr/share/gazebo/setup.sh

export PATH="$(deduplicate_path.sh "${HOME}/.local/bin:${PATH}")"
export CMAKE_PREFIX_PATH="$(deduplicate_path.sh "${CMAKE_PREFIX_PATH}")"
export LD_LIBRARY_PATH="$(deduplicate_path.sh "${LD_LIBRARY_PATH}")"
export PKG_CONFIG_PATH="$(deduplicate_path.sh "${PKG_CONFIG_PATH}")"
export PYTHONPATH="$(deduplicate_path.sh "${PYTHONPATH}")"
export ROS_PACKAGE_PATH="$(deduplicate_path.sh "${ROS_PACKAGE_PATH}")"
