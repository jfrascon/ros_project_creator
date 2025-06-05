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

IMG_USER="${1}"

[ -z "${IMG_USER}" ] && {
    log "Error: IMG_USER is not set" 2
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

items=(metadata metadata_repositories.yaml mixin mixin_repositories.yaml)
colcon_src_dir="/root/.colcon"

for item in "${items[@]}"; do
    src_item="${colcon_src_dir}/${item}"

    if [ -e "${src_item}" ]; then
        bak_item="${src_item}.bak_$(date --utc '+%Y-%m-%d_%H-%M-%S')"
        log "Backing up item '${src_item}' to '${bak_item}'"
        mv --verbose "${src_item}" "${bak_item}"
    fi
done

# Download the colcon mixin and metadata repositories.
log "Executing colcon mixin and colcon metadata as root"
echo "colcon databases ownership will be fixed later "
colcon mixin add default https://raw.githubusercontent.com/colcon/colcon-mixin-repository/master/index.yaml
colcon mixin update default
colcon metadata add default https://raw.githubusercontent.com/colcon/colcon-metadata-repository/master/index.yaml
colcon metadata update default

# Move the colcon databases to the user home directory, if the IMG_USER is non root.
if [ "${IMG_USER}" != "root" ]; then
    img_user_id="$(echo "${img_user_entry}" | cut -d: -f3)"
    img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
    img_user_home="$(echo "${img_user_entry}" | cut -d: -f6)"
    colcon_dst_dir="${img_user_home}/.colcon"

    # Make sure the destination directory exists, just in case.
    sudo -H -u "${IMG_USER}" mkdir --verbose --parent "${colcon_dst_dir}"

    for item in "${items[@]}"; do
        src_item="${colcon_src_dir}/${item}"
        dst_item="${colcon_dst_dir}/${item}"

        if [ -e "${dst_item}" ]; then
            bak_item="${dst_item}.bak_$(date --utc '+%Y-%m-%d_%H-%M-%S')"
            log "Baking up item '${dst_item}' to '${bak_item}'"
            sudo -H -u "${IMG_USER}" mv --verbose "${dst_item}" "${bak_item}"
        fi

        log "Copying item '${src_item}' into '${dst_item}'"

        recursive=""

        if [ -d "${src_item}" ]; then
            recursive="--recursive"
        fi

        cp --verbose ${recursive} "${src_item}" "${dst_item}"
        chown ${recursive} "${img_user_id}:${img_user_pri_group_id}" "${dst_item}"

        log "Removing item '${src_item}'"
        rm --verbose --recursive --force "${src_item}"
    done
fi
