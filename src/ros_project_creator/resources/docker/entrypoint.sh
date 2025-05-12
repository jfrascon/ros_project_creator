#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
# set -e

# Variables EXT_UID and EXT_UPGID are defined in CLI or docker-compose.yml file.

add_render_group_to_user() {
    local img_user="${1}"

    # Check if the user with name ${img_user} exist.
    if ! getent passwd "${img_user}" >/dev/null; then
        return 1
    fi

    # Iterate over every render node present in /dev/dri, in case there are GPU devices in the host system.
    for dev in /dev/dri/renderD*; do
        [ -e "${dev}" ] || continue # glob might not expand

        gid="$(stat -c %g "${dev}")" # numeric GID of the device

        if getent group "${gid}" >/dev/null; then
            grpname="$(getent group "${gid}" | cut -d: -f1)"

            if [ "${grpname}" != "render" ]; then
                print_banner "Using existing group id '${gid}', named '${grpname}' (different from 'render') for '${dev}', no problem"
            fi
        else
            grpname="render_${gid}"
            print_banner "Creating group '${grpname}' (GID ${gid}) for ${dev}..."
            groupadd --system --gid "${gid}" "${grpname}"
        fi

        # Add the group to the user ${img_user}.
        usermod -aG "${gid}" "${img_user}"
    done
}

create_group_w_name_and_id() {
    local group_name="${1}"
    local group_id="${2}"

    # Check if the group with name ${group_name} exist.
    if getent group "${group_name}" &>/dev/null; then
        print_banner "Error creating group: Group '${group_name}' already exists" 2 "!"
        exit 1
    fi

    # Check if the group with id ${group_id} exist.
    if getent group "${group_id}" &>/dev/null; then
        print_banner "Error creating group: Group with id '${group_id}' already exists" 2 "!"
        exit 1
    fi

    print_banner "Creating group group with name '${group_name}' and id '${group_id}'"

    # Create the group with name ${group_name} and id ${group_id}.
    if ! groupadd --gid "${group_id}" "${group_name}"; then
        print_banner "Error: Failed to create group with name '${group_name}' and id '${group_id}'" 2 "!"
        exit 1
    fi
}

# Find first unused UID >= 2000
find_free_user_id() {
    awk -F: '
        NR==FNR { uids[$3]=1; next }
        { uids[$3]=1 }
        END { for(i=2000;i<60000;++i) if(!(i in uids)) { print i; break } }
    ' /etc/passwd /etc/group
}

generate_unique_name() {
    local type="${1}"     # "user" or "group"
    local prefix="${2:-}" # optional prefix
    local getent_target
    local candidate

    case "${type}" in
    user)
        getent_target="passwd"
        ;;
    group)
        getent_target="group"
        ;;
    *)
        echo "Error: unknown type '${type}'. Use 'user' or 'group'." >&2
        return 1
        ;;
    esac

    while :; do
        candidate="${prefix}$(tr -dc 'a-z' </dev/urandom | head -c 8)"
        if ! getent "${getent_target}" "${candidate}" >/dev/null 2>&1; then
            echo "${candidate}"
            return
        fi
    done
}

print_banner() {
    local message="${1}"
    local fd="${2:-1}"          # default to 1 (stdout) if not provided
    local border_char="${3:-=}" # default to '=' if not provided

    # Validate that fd is either 1 (stdout) or 2 (stderr)
    if [[ "${fd}" != "1" && "${fd}" != "2" ]]; then
        fd=1
    fi

    local line=" ${message} "
    local len=${#line}

    printf "%s\n" "$(printf "%${len}s" | tr ' ' "${border_char}")" >&"${fd}"
    printf "%s\n" "${line}" >&"${fd}"
    printf "%s\n" "$(printf "%${len}s" | tr ' ' "${border_char}")" >&"${fd}"
}

set_name_to_group() {
    local group_name="${1}"
    local new_group_name="${2}"

    # Check if the group with name ${group_name} exist.
    if ! getent group "${group_name}" >/dev/null; then
        print_banner "Error setting name to group. Group '${group_name}' does not exist" 2 "!"
        exit 1
    fi

    if ! getent group "${new_group_name}" >/dev/null; then
        print_banner "Updating name for group from '${group_name}' to '${new_group_name}'..."

        # Update name of group ${group_name} to ${new_group_name}.
        if ! groupmod --new-name "${new_group_name}" "${group_name}"; then
            print_banner "Error setting name to group. Failed to update name of group '${group_name}' to '${new_group_name}'" 2 "!"
            exit 1
        fi
    elif [ "${group_name}" != "${new_group_name}" ]; then
        print_banner "Error setting name to group. Group '${new_group_name}' already exists" 2 "!"
        exit 1
    fi
}

set_id_to_user() {
    local img_user="${1}"
    local new_user_id="${2}"

    # Check if the user with name ${img_user} exist.
    if ! getent passwd "${img_user}" >/dev/null; then
        print_banner "Error setting id to user: User '${img_user}' does not exist" 2 "!"
        exit 1
    fi

    img_user_id="$(getent passwd "${img_user}" | cut -d: -f3)"

    if ! getent passwd "${new_user_id}" >/dev/null; then
        print_banner "Updating id for user '${img_user}' from '${img_user_id}' to '${new_user_id}'..."

        # Update id of user ${img_user} to ${new_user_id}.
        if ! usermod --uid "${new_user_id}" "${img_user}"; then
            print_banner "Error setting id to user: Failed to update id of user '${img_user}' from '${img_user_id}' to '${new_user_id}'" 2 "!"
            exit 1
        fi
    elif [ "${img_user_id}" != "${new_user_id}" ]; then
        print_banner "Error setting id to user: User with id '${new_user_id}' already exists" 2 "!"
        exit 1
    fi
}

set_path_ownership_to_user() {
    local path="${1}"
    local img_user="${2}"

    # Check if the path ${path} exist.
    if [ ! -e "${path}" ]; then
        print_banner "Error setting ownership to path: Path '${path}' does not exist" 2 "!"
        exit 1
    fi

    img_user_entry="$(getent passwd "${img_user}" 2>/dev/null)"

    if [ -z "${img_user_entry}" ]; then
        print_banner "Error setting ownership to path: User '${img_user}' does not exist" 2 "!"
        exit 1
    fi

    img_user_id="$(echo "${img_user_entry}" | cut -d: -f3)"
    img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
    img_user_pri_group="$(getent group "${img_user_pri_group_id}" | cut -d: -f1)"

    # Set ownership of the path ${path} to user ${img_user} and group ${img_user_pri_group_id}.
    if ! chown -R "${img_user_id}:${img_user_pri_group_id}" "${path}"; then
        print_banner "Error: Failed to set ownership of path '${path}' to user '${img_user}' and group '${img_user_pri_group}'" 2 "!"
        exit 1
    fi
}

set_primary_group_id_to_user() {
    local img_user="${1}"
    local new_gid="${2}"

    # Check if the user with name ${img_user} exist.
    if ! getent passwd "${img_user}" >/dev/null; then
        print_banner "Error: User '${img_user}' does not exist" 2 "!"
        exit 1
    fi

    # Check if the group with id ${new_gid} exist.
    if ! getent group "${new_gid}" >/dev/null; then
        print_banner "Error: Group with id '${new_gid}' does not exist" 2 "!"
        exit 1
    fi

    # Update primary group of user ${img_user} to ${new_gid}.
    if ! usermod --gid "${new_gid}" "${img_user}"; then
        print_banner "Error: Failed to update primary group of user '${img_user}' to '${new_gid}'" 2 "!"
        exit 1
    fi
}

set_unique_random_name_to_group() {
    set_name_to_group "${1}" "$(generate_unique_name group "${1}_")"
}

# =================
# Script execution
# =================

# If here, the user used in docker-compose file or docker run command is a user that exists in the image.
img_user_id="$(id --user)"
img_user_entry="$(getent passwd "${img_user_id}" 2>/dev/null)"
img_user_name="$(echo "${img_user_entry}" | cut -d: -f1)"
img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
img_user_pri_group="$(getent group "${img_user_pri_group_id}" | cut -d: -f1)"
img_user_home="$(echo "${img_user_entry}" | cut -d: -f6)"

print_banner "Entrypoint running with UID=${img_user_id} and UPGID=${img_user_pri_group_id}"

# Check if the selected user is a regular user.
if [ "${img_user_id}" -ne 0 ]; then
    [ -d "${img_user_home}" ] && cd "${img_user_home}"
    [ -s "${img_user_home}/.environment.sh" ] && . "${img_user_home}/.environment.sh"
    exec "$@"
# The selected user is root, from here onward.
# If EXT_UID and EXT_UPGID are not defined (do not exist), no user and group adaptation is possible, so the the user
# running the container wants to start the container as root.
elif [ -z "${EXT_UID+x}" ] && [ -z "${EXT_UPGID+x}" ]; then
    # Because the user is root, we can add the render group to the root user.
    add_render_group_to_user "${img_user_name}"
    [ -d "${img_user_home}" ] && cd "${img_user_home}"
    # When the session is started, if you add a user to a group, the id command will not show the group added to the
    # user until you start a new session by launching a login shell or using the commands newgrp or gosu. This is
    # because the session is not updated. However, the group is added to the user, and you can use it. So, no real need
    # to use gosu here.
    [ -s "${img_user_home}/.environment.sh" ] && . "${img_user_home}/.environment.sh"
    exec "$@"
elif [ -z "${EXT_UID+x}" ]; then
    print_banner "EXT_UID variable not defined. Either EXT_UID and EXT_UPGID must be defined, or none of them" 2 "!"
    exit 1
elif [ -z "${EXT_UPGID+x}" ]; then
    print_banner "EXT_UPGID variable not defined. Either EXT_UID and EXT_UPGID must be defined, or none of them" 2 "!"
    exit 1
elif [ -z "${EXT_UID}" ] || [ -z "${EXT_UPGID}" ]; then
    print_banner "EXT_UID and EXT_UPGID variables can't be empty" 2 "!"
    exit 1
elif ! [[ "${EXT_UID}" =~ ^-?[0-9]+$ ]]; then
    print_banner "EXT_UID variable must be an integer" 2 "!"
    exit 1
elif ! [[ "${EXT_UPGID}" =~ ^-?[0-9]+$ ]]; then
    print_banner "EXT_UPGID variable must be an integer" 2 "!"
    exit 1
elif [ "${EXT_UID}" -lt 1000 ] || [ "${EXT_UPGID}" -lt 1000 ]; then
    print_banner "EXT_UPGID ('${EXT_UPGID}') and EXT_UID ('${EXT_UID}') must be greater than 1000" 2 "!"
else
    # Adapt the user ${IMG_USER} to use the id ${EXT_UID} and the primary group id ${EXT_UPGID}.
    print_banner "EXT_UID=${EXT_UID}, EXT_UPGID=${EXT_UPGID}"

    if [ -z "${IMG_USER}" ]; then
        print_banner "Error: IMG_USER variable not set" 2 "!"
        exit 1
    fi

    img_user_entry="$(getent passwd "${IMG_USER}" 2>/dev/null)"

    # Check if the user with name ${IMG_USER} exist.
    if [ -z "${img_user_entry}" ]; then
        print_banner "Error: User '${IMG_USER}' does not exist" 2 "!"
        exit 1
    fi

    img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
    img_user_pri_group="$(getent group "${img_user_pri_group_id}" | cut -d: -f1)"

    if [ -z "${img_user_pri_group}" ]; then
        print_banner "Error: Group '${img_user_pri_group_id}' of user '${IMG_USER}' does not exist" 2 "!"
        exit 1
    fi

    # Get data associated with the user ${IMG_USER}.
    img_user_id="$(echo "${img_user_entry}" | cut -d: -f3)"
    img_user_home="$(echo "${img_user_entry}" | cut -d: -f6)"

    # If the user ${IMG_USER} is root, no need to adapt the user and group ids.
    if [ "${IMG_USER}" = "root" ]; then
        add_render_group_to_user "${IMG_USER}"
        [ -d "${img_user_home}" ] && cd "${img_user_home}"
        # When the session is started, if you add a user to a group, the id command will not show the group added to the
        # user until you start a new session by launching a login shell or using the commands newgrp or gosu. This is
        # because the session is not updated. However, the group is added to the user, and you can use it. So, no real
        # need to use gosu here.
        [ -s "${img_user_home}/.environment.sh" ] && . "${img_user_home}/.environment.sh"
        exec "$@"
    # The user ${IMG_USER} is not root, so we need to adapt the user and group ids.
    else
        # Detect if a group is already using the id ${EXT_UPGID}.
        conflicting_img_group="$(getent group "${EXT_UPGID}" | cut -d: -f1)"

        # Check if the id ${EXT_UPGID} is available.
        if [ -z "${conflicting_img_group}" ]; then
            set_unique_random_name_to_group "${img_user_pri_group}"
            create_group_w_name_and_id "${img_user_pri_group}" "${EXT_UPGID}"
            set_primary_group_id_to_user "${IMG_USER}" "${EXT_UPGID}"
        elif [ "${conflicting_img_group}" != "${img_user_pri_group}" ]; then
            set_unique_random_name_to_group "${img_user_pri_group}"
            set_name_to_group "${conflicting_img_group}" "${img_user_pri_group}"
            set_primary_group_id_to_user "${IMG_USER}" "${EXT_UPGID}"
        fi

        conflicting_img_user="$(getent passwd "${EXT_UID}" | cut -d: -f1)"

        # Check if the id ${EXT_UID} is available.
        if [ -z "${conflicting_img_user}" ]; then
            # We use this strategy so we don't have to mv the files in the home directory of the user ${IMG_USER}.
            set_id_to_user "${IMG_USER}" "${EXT_UID}"
        elif [ "${conflicting_img_user}" != "${IMG_USER}" ]; then
            # We use this strategy so we don't have to mv the files in the home directory of the user ${IMG_USER}.
            new_user_id="$(find_free_user_id)"
            set_id_to_user "${conflicting_img_user}" "${new_user_id}"
            conflicting_img_user_home="$(getent passwd "${conflicting_img_user}" | cut -d: -f6)"
            set_path_ownership_to_user "${conflicting_img_user_home}" "${conflicting_img_user}"
            set_id_to_user "${IMG_USER}" "${EXT_UID}"
        fi

        set_path_ownership_to_user "${img_user_home}" "${IMG_USER}"

        add_render_group_to_user "${IMG_USER}"
        [ -d "${img_user_home}" ] && cd "${img_user_home}"
        # We use gosu here to start a new session with the new user and group ids.
        exec gosu "${IMG_USER}" bash -c '
            [ -s "${HOME}/.environment.sh" ] && . "${HOME}/.environment.sh"
            exec "$@"
        ' bash "$@"
    fi
fi
