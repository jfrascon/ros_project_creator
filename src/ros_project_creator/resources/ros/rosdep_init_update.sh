#!/usr/bin/env bash

log() {
    local message="${1}"
    local fd="${2:-1}" # default to 1 (stdout) if not provided

    # Validate that fd is either 1 (stdout) or 2 (stderr)
    if [[ "${fd}" != "1" && "${fd}" != "2" ]]; then
        fd=1
    fi

    printf "[%s] %s\n" "$(date --utc '+%Y-%m-%d_%H-%M-%S')" "${message}" >&"${fd}"
}

ROS_DISTRO="${1}"
IMG_USER="${2}"
SRC_ROSDEP_IGNORED_KEY_FILE="${3}"
PROJECT_SRC_DIR="${4}"

[ -z "${ROS_DISTRO}" ] && {
    log "Error: ROS_DISTRO is not set" 2
    exit 1
}

[ -z "${IMG_USER}" ] && {
    log "Error: IMG_USER is not set" 2
    exit 1
}

[ ! -d "${PROJECT_SRC_DIR}" ] && {
    log "Error: PROJECT_SRC_DIR '${PROJECT_SRC_DIR}' does not exist" 2
    exit 1
}

img_user_entry="$(getent passwd "${IMG_USER}")"

[ -z "${img_user_entry}" ] && {
    log "Error: User '${IMG_USER}' does not exist" 2
    exit 1
}

# This script is run by root when building the Docker image.
[ "$(id --user)" -ne 0 ] && {
    log "Error: root user must be active to run the script '$(basename "${BASH_SOURCE[0]}")'" 2
    exit 1
}

rosdep_root_dir="/etc/ros/rosdep"
rosdep_sources_dir="${rosdep_root_dir}/sources.list.d"

if [ ! -d "${rosdep_sources_dir}" ]; then
    log "Creating path ${rosdep_sources_dir}"
    mkdir --verbose --parent "${rosdep_sources_dir}"
elif [ -f "${rosdep_sources_dir}/20-default.list" ]; then
    log "File '${rosdep_sources_dir}/20-default.list' already exists, removing it"
    rm --verbose --force "${rosdep_sources_dir}/20-default.list"
fi

# Check if there are keys to ignore for rosdep.
if [ -s "${SRC_ROSDEP_IGNORED_KEY_FILE}" ]; then
    dst_rosdep_ignored_key_file="${rosdep_root_dir}/rosdep_ignored_keys.yaml"
    rosdep_ignored_keys_list_file="${rosdep_sources_dir}/00-rosdep-ignored-key-file-list.list"

    log "rosdep ignored keys provided in the file "${SRC_ROSDEP_IGNORED_KEY_FILE}""

    # Check if there is no file with exclusions for rosdep yet.
    if [ ! -s "${dst_rosdep_ignored_key_file}" ]; then
        log "Copying file '"${SRC_ROSDEP_IGNORED_KEY_FILE}"' file to '${dst_rosdep_ignored_key_file}'"
        cp --verbose "${SRC_ROSDEP_IGNORED_KEY_FILE}" "${dst_rosdep_ignored_key_file}"
    # Check if the rosdep exclusions file present in the image and the provided one are different.
    elif ! cmp --silent "${SRC_ROSDEP_IGNORED_KEY_FILE}" "${dst_rosdep_ignored_key_file}"; then
        bak_file="${dst_rosdep_ignored_key_file}.bak_$(date +%Y%m%d_%H%M%S)"
        log "File '${dst_rosdep_ignored_key_file}' already exists, backing it up to file '${bak_file}'"
        mv --verbose "${dst_rosdep_ignored_key_file}" "${bak_file}"

        log "Copying file '"${SRC_ROSDEP_IGNORED_KEY_FILE}"' file to '${dst_rosdep_ignored_key_file}'"
        cp --verbose "${SRC_ROSDEP_IGNORED_KEY_FILE}" "${dst_rosdep_ignored_key_file}"
    else
        log "File with rosdep ignored keys already present in the image"
    fi

    # Check if the rosdep ignored keys file is already included in the list file.
    if ! grep --quiet --extended-regexp "yaml file://${dst_rosdep_ignored_key_file}" "${rosdep_ignored_keys_list_file}" &>/dev/null; then
        log "Adding file '${dst_rosdep_ignored_key_file}' to the list file '${rosdep_ignored_keys_list_file}'"
        echo "yaml file://${dst_rosdep_ignored_key_file}" >>"${rosdep_ignored_keys_list_file}"
    else
        log "File '${dst_rosdep_ignored_key_file}' already present in the file '${rosdep_ignored_keys_list_file}'"
    fi
else
    log "No rosdep exclusions to consider"
fi

log "Executing rosdep init"

if ! rosdep init; then
    log "Error: rosdep init failed" 2
    exit 1
fi

# If the command 'rosdep update' is run as root, the rosdep database is located at /root/.ros/rosdep.
# Ref: rosdep --help
items=(meta.cache sources.cache)
# Path where the rosdep databases are located when the command rosdep update is executed as root.
rosdep_src_dir="/root/.ros/rosdep"

# Check if the databases already exists in the proper path.
for item in "${items[@]}"; do
    src_item="${rosdep_src_dir}/${item}"

    if [ -e "${src_item}" ]; then
        bak_item="${src_item}.bak_$(date --utc '+%Y-%m-%d_%H-%M-%S')"
        log "Baking up item '${bak_item}'"
        mv --verbose "${src_item}" "${bak_item}"
    fi
done

log "Executing rosdep update as root. Ignore the warning about running as root"
log "rosdep database ownership will be fixed later"
rosdep update --rosdistro "${ROS_DISTRO}"

log "Installing dependencies for packages in the paths '${PROJECT_SRC_DIR}' and '/opt/ros/${ROS_DISTRO}/share/'"
# Update cache to ensure the latest package information is available.
apt-get update
rosdep install -y --rosdistro "${ROS_DISTRO}" --from-paths "${PROJECT_SRC_DIR}" "/opt/ros/${ROS_DISTRO}/share/" --ignore-src

# Move the rosdep databases to the user home directory, if the IMG_USER is non root.
if [ "${IMG_USER}" != "root" ]; then
    img_user_id="$(echo "${img_user_entry}" | cut -d: -f3)"
    img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
    img_user_home="$(echo "${img_user_entry}" | cut -d: -f6)"
    rosdep_dst_dir="${img_user_home}/.ros/rosdep"

    # Make sure the destination directory exists, just in case.
    sudo -H -u "${IMG_USER}" mkdir --verbose --parent "${rosdep_dst_dir}"

    for item in "${items[@]}"; do
        src_item="${rosdep_src_dir}/${item}"
        dst_item="${rosdep_dst_dir}/${item}"

        if [ -e "${dst_item}" ]; then
            bak_item="${dst_item}.bak_$(date --utc '+%Y-%m-%d_%H-%M-%S')"
            log "Baking up item '${bak_item}'"
            sudo -H -u "${IMG_USER}" mv --verbose "${dst_item}" "${bak_item}"
        fi

        log "Copying item '${src_item}' into '${dst_item}'"
        cp --verbose --recursive "${src_item}" "${dst_item}"
        chown --recursive "${img_user_id}:${img_user_pri_group_id}" "${dst_item}"

        log "Removing item '${src_item}'"
        rm --verbose --recursive --force "${src_item}"
    done
fi
