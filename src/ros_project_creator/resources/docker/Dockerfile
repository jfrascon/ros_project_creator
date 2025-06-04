# syntax=docker/dockerfile:1

# No default base_img is provided to ensure the build process fails if no base_img is specified.
# The warning 'InvalidDefaultArgInFrom: Default value for ARG ${base_img} results in empty or
# invalid base image name' can be safely ignored, as this behavior is intentional.
ARG BASE_IMG
FROM ${BASE_IMG}

# The following labels adhere to the OCI Image Specification for standardized metadata.
# Reference: https://github.com/opencontainers/image-spec/blob/main/annotations.md
LABEL org.opencontainers.image.title="Project Docker Image" \
    org.opencontainers.image.description="A Docker image for development and testing" \
    org.opencontainers.image.authors="anon"

ARG DEBIAN_FRONTEND=noninteractive
ARG REQUESTED_USER=non_root
ARG ROS_DISTRO=humble
ARG ROS_VERSION=2

USER root
WORKDIR /

# Using the pattern COPY+RUN we can benefit from Docker's build cache.
# The copied files are lightweight, therefore the size of the associated layer is small.
# The script install_core.sh is responsible for installing system dependencies.
COPY --chmod=775 docker/.resources/install_base_system.sh /tmp/
RUN /tmp/install_base_system.sh "${REQUESTED_USER}" && rm -rf /tmp/install_base_system.sh

COPY --chmod=775 docker/.resources/install_ros.sh /tmp/install_ros.sh
RUN /tmp/install_ros.sh "${ROS_DISTRO}" "${ROS_VERSION}" "${REQUESTED_USER}" && rm -rf /tmp/install_ros.sh

# The following block is always re-executed and is NOT cached intentionally.
# It uses the --mount=type=bind option to bind the current context to the container, since the context has, most of the
# time, a significant amount of files that do not need to be copied, and subsequently occupying space in the associated
# layer.
RUN --mount=type=bind,source=.,target=/tmp/context bash <<'EOF'
log() { echo "[$(date --utc '+%Y-%m-%d_%H-%M-%S')]" "$@"; }

img_user="${REQUESTED_USER}"
img_user_entry="$(getent passwd "${img_user}")"

[ -z "${img_user_entry}" ] && {
    log "Error: User '${img_user}' not found" >&2
    exit 1
}

[ ! -f /tmp/context/docker/entrypoint.sh ] && {
    log "Error: Script entrypoint.sh not provided" >&2
    exit 1
}

[ ! -f /tmp/context/docker/environment.sh ] && {
    log "Error: Script environment.sh not provided" >&2
    exit 1
}

[ ! -f /tmp/context/docker/.resources/deduplicate_path.sh ] && {
    log "Error: Script deduplicate_path.sh not provided" >&2
    exit 1
}

[ ! -f /tmp/context/docker/.resources/rosbuild.sh ] && {
    log "Error: Script rosbuild.sh not provided" >&2
    exit 1
}

[ ! -f /tmp/context/docker/.resources/rosdep_init_update.sh ] && {
    log "Error: Script rosdep_init_update.sh not provided" >&2
    exit 1
}

# Check if ${ROS_DISTRO} is installed properly, otherwise abort the installation.
ros_distro=$(dpkg --list | sed -nE 's/^ii\s+ros-([a-z]+)-ros-core.*$/\1/p' | tr '\n' ' ' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

num_distros=$(echo "${ros_distro}" | wc -w)

# If no ROS_DISTRO is found at this point, exit with an error.
if [ "${num_distros}" -eq 0 ]; then
    log "Error: No ROS distribution found" >&2
    exit 1
fi

if [ "${num_distros}" -gt 1 ]; then
    log "Error: More than one ROS_DISTRO found: ${ros_distro}" >&2
    exit 1
fi

if [ "${ROS_DISTRO}" != "${ros_distro}" ]; then
    log "Error: Found ROS_DISTRO '${ros_distro}', expected ROS_DISTRO '${ROS_DISTRO}'" >&2
    exit 1
fi

rosdep_ignored_key_file=/tmp/context/docker/.resources/rosdep_ignored_keys.yaml
cp /tmp/context/docker/.resources/rosdep_init_update.sh /tmp/rosdep_init_update.sh
chmod 775 /tmp/rosdep_init_update.sh

src_dir="/tmp/context/src"

if [ ! -d "${src_dir}" ]; then
    log "Error: Source directory '${src_dir}' does not exist" >&2
    exit 1
fi

/tmp/rosdep_init_update.sh "${ROS_DISTRO}" "${img_user}" "${rosdep_ignored_key_file}" "${src_dir}"
rm -f /tmp/rosdep_init_update.sh

if [ -s /tmp/context/docker/.resources/colcon_mixin_metadata.sh ]; then
    cp /tmp/context/docker/.resources/colcon_mixin_metadata.sh /tmp/colcon_mixin_metadata.sh
    chmod 775 /tmp/colcon_mixin_metadata.sh
    /tmp/colcon_mixin_metadata.sh "${img_user}"
    rm -f /tmp/colcon_mixin_metadata.sh
else
    log "Error: No colcon_mixin_metadata.sh script found, skipping colcon mixin metadata installation"
fi

# Execute the custom dependency install script for the project.
find "/tmp/context" -maxdepth 1 -type f -name 'install_deps.sh' -exec bash {} \;

img_user_id="$(echo "${img_user_entry}" | cut -d: -f3)"
img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
img_user_pri_group="$(getent group "${img_user_pri_group_id}" | cut -d: -f1)"
img_user_home="$(echo "${img_user_entry}" | cut -d: -f6)"

# Every file and folder in img_user_home must belong to the img_user.
log "Setting ownership of path '${img_user_home}' to user '${img_user}' (UID '${img_user_id}') and primary group '${img_user_pri_group}' (GID '${img_user_pri_group_id}')"
chown --recursive "${img_user}":"${img_user_pri_group}" "${img_user_home}"

# Install utility scripts and environment files system-wide or per-user.
log "Installing file '/usr/local/bin/entrypoint.sh'" >&2
install --owner root --group root --mode 775 /tmp/context/docker/entrypoint.sh /usr/local/bin/entrypoint.sh

log "Installing file '/usr/local/bin/deduplicate_path.sh'"
install --owner root --group root --mode 775 /tmp/context/docker/.resources/deduplicate_path.sh /usr/local/bin/deduplicate_path.sh

log "Installing file '/usr/local/bin/rosbuild.sh'"
install --owner root --group root --mode 775 /tmp/context/docker/.resources/rosbuild.sh /usr/local/bin/rosbuild.sh

# An environment script is installed in the home directory of the '${img_user}'.
log "Installing file '${img_user_home}/.environment.sh'"
install --owner "${img_user}" --group "${img_user_pri_group}" --mode 775 /tmp/context/docker/environment.sh "${img_user_home}/.environment.sh"

# Optional: install .bash_aliases if present
if [ -e /tmp/context/docker/.resources/dot_bash_aliases ]; then
    install --owner "${img_user}" --group "${img_user_pri_group}" --mode 775 /tmp/context/docker/.resources/dot_bash_aliases "${img_user_home}/.bash_aliases"
fi

log "Removing installation residues from apt cache"
apt-get autoclean
apt-get autoremove --purge -y
apt-get clean
rm -rf /var/lib/apt/lists/* &>/dev/null
EOF

# Re-declare ARGs to make their values available for expansion in ENV below.
# This is required even if they were already defined earlier after the FROM.
ARG DEBIAN_FRONTEND
ARG REQUESTED_USER

# Configure timezone and localization settings.
# - TZ: Set the timezone to UTC to ensure consistent time handling across environments.
# - LC_ALL, LANG, LANGUAGE: Configure localization to US English and UTF-8 encoding, which helps
#   avoiding issues with character encoding and ensures compatibility with most tools and libraries.
ENV IMG_USER="${REQUESTED_USER}" \
    TZ="Etc/UTC" \
    LC_ALL="en_US.UTF-8" \
    LANG="en_US.UTF-8" \
    LANGUAGE="en_US:en" \
    DEBIAN_FRONTEND="${DEBIAN_FRONTEND}"

USER "${IMG_USER}"
WORKDIR "/"
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
