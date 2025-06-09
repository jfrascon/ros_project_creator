#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
# set -e

# Variables EXT_UID and EXT_UPGID are defined in CLI or docker-compose.yml file.

add_render_group_to_user() {
    local user="${1}"

    # Check if the user with name ${user} exist.
    if ! getent passwd "${user}" >/dev/null; then
        return 1
    fi

    # If the user (no root) wants to access the devices /dev/dri/renderD*, the user must be in the
    # group of that device.

    # Iterate over every render node present in /dev/dri.
    for dev in /dev/dri/renderD*; do
        [ -e "${dev}" ] || continue # glob might not expand

        gid="$(stat -c %g "${dev}")" # numeric GID of the device

        if getent group "${gid}" >/dev/null; then
            group="$(getent group "${gid}" | cut -d: -f1)"

            if [ "${group}" != "render" ]; then
                print_banner "Using existing group id '${gid}', named '${group}' (different from 'render') for '${dev}', no problem"
            fi
        else
            group="render_${gid}"
            print_banner "Creating group '${group}' (GID ${gid}) for device ${dev}..."
            groupadd --system --gid "${gid}" "${group}"
        fi

        # Add the group to the user ${user}.
        print_banner "Adding user '${user}' to group '${group}' (GID ${gid}) for ${dev}"
        usermod -aG "${gid}" "${user}"
    done
}

# Find first integer that can be used as uid and gid above >= 2000
find_free_id() {
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
    local border_char="${3:--}" # default to '=' if not provided

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

remember_message() {
    print_banner "Warning: The user-group adaptation is only possible if the selected user is 'root' (uid: 0) and both variables, EXT_UID and EXT_UPGID, are defined with a non-empty integer value greater than 1000" 2 "x"
}

#---------------------------------------------------------------------------------------------------
# Script execution
#---------------------------------------------------------------------------------------------------
img_user_id="$(id --user)"
img_user_entry="$(getent passwd "${img_user_id}" 2>/dev/null)"
img_user="$(echo "${img_user_entry}" | cut -d: -f1)"
img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
img_user_pri_group="$(getent group "${img_user_pri_group_id}" | cut -d: -f1)"
img_user_home="$(echo "${img_user_entry}" | cut -d: -f6)"

print_banner "Entrypoint running with user '${img_user}' (UID '${img_user_id}') and primary group '${img_user_pri_group}' (UPGID '${img_user_pri_group_id}')"

# If the variables EXT_UID and EXT_UPGID DO NOT EXIT (not talking about being empty), the container
# is started with the selected user. The selected user is the one provided either with the flag
# '--user' in the container run command or with the 'user' field in the docker-compose file or in
# case none of these methods is used, the active user is the last user activated in the Dockerfile.
# In this scenario, no user-group adaptation is possible, due to the lack of the mentioned
# variables.
if [ -z "${EXT_UID+x}" ] && [ -z "${EXT_UPGID+x}" ]; then
    if [ "${img_user_id}" -eq 0 ]; then
        # Because the user is root, we can add the render group to the root user.
        add_render_group_to_user "${img_user}"
    fi
    # When the session is started, if you add a user to a group, the id command will not show the group added to the
    # user until you start a new session by launching a login shell or using the commands newgrp or gosu. This is
    # because the session is not updated. However, the group is added to the user, and you can use it.So, no real need
    # to use gosu here.
    [ -s "${img_user_home}/.environment.sh" ] && . "${img_user_home}/.environment.sh"
    exec "$@"
# The allowed cases are: either both enviroment variables EXT_UID and EXT_UPGID are not defined, or
# both are defined with a non-emtpy value.
# Any other combination is not allowed.
# EXT_UID not defined and EXT_UPGID defined, no matter the value, empty or non-emtpy -> Error
# EXT_UPGID not defined and EXT_UID defined, no matter the value, empty or non-emtpy -> Error
elif [ -z "${EXT_UID+x}" ]; then
    print_banner "Error: EXT_UID variable does not exist. Either EXT_UID and EXT_UPGID are undefined or both are defined with non-empty integer values greater than 1000" 2 "x"

    if [ "${img_user_id}" -ne 0 ]; then
        remember_message
    fi

    exit 1
elif [ -z "${EXT_UPGID+x}" ]; then
    print_banner "Error: EXT_UPGID variable does not exit. Either EXT_UID and EXT_UPGID are undefined or both are defined with non-empty integer values greater than 1000" 2 "x"

    if [ "${img_user_id}" -ne 0 ]; then
        remember_message
    fi

    exit 1
# From here on, both enviroment variables, EXT_UID and EXT_UPGID, are defined and have a non-empty
# value.
# Check if both variables have an integer value.
elif ! [[ "${EXT_UID}" =~ ^-?[0-9]+$ ]]; then
    print_banner "Error: EXT_UID variable must be an integer greater than 1000, given '${EXT_UID}'" 2 "x"

    if [ "${img_user_id}" -ne 0 ]; then
        remember_message
    fi

    exit 1
elif ! [[ "${EXT_UPGID}" =~ ^-?[0-9]+$ ]]; then
    print_banner "Error: EXT_UPGID variable must be an integer greater than 1000, given '${EXT_UPGID}' " 2 "x"

    if [ "${img_user_id}" -ne 0 ]; then
        remember_message
    fi

    exit 1
# To exeute user-group adaptation it is required that the user in the host system, defined by
# the variables, EXT_UID and EXT_UPGID, has values greater than 1000 in these variables. Integer
# values lower than 1000 are reserve for the operating system.
elif [ "${EXT_UID}" -lt 1000 ] || [ "${EXT_UPGID}" -lt 1000 ]; then
    print_banner "Error: EXT_UPGID ('${EXT_UPGID}') and EXT_UID ('${EXT_UID}') must be greater than 1000" 2 "x"

    if [ "${img_user_id}" -ne 0 ]; then
        remember_message
    fi

    exit 1
else
    # Adapt the user ${IMG_USER} to use the id ${EXT_UID} and the primary group id ${EXT_UPGID}.
    print_banner "EXT_UID=${EXT_UID}, EXT_UPGID=${EXT_UPGID}"

    if [ "${img_user_id}" -ne 0 ]; then
        remember_message
        print_banner "To run the container without the user-group adaptation, do not include the variables EXT_UID and EXT_UPGID in your command" 2 "x"
        exit 1
    fi

    # From here onwards, the selected user is root and both variables, EXT_UID and EXT_UPGID, are
    # defined with an integer value greaer than 1000, so user-group adaptation is possible.

    # Check if the enviroment variable 'IMG_USER' exists and it is not empty.
    if [ -z "${IMG_USER}" ]; then
        print_banner "Error: IMG_USER variable not set" 2 "!"
        exit 1
    fi

    img_user_entry="$(getent passwd "${IMG_USER}" 2>/dev/null)"

    # Check if the user with name ${IMG_USER} exists in the image.
    if [ -z "${img_user_entry}" ]; then
        print_banner "Error: User '${IMG_USER}' does not exist" 2 "!"
        exit 1
    fi

    img_user_id="$(echo "${img_user_entry}" | cut -d: -f3)"
    img_user_home="$(echo "${img_user_entry}" | cut -d: -f6)"
    img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
    img_user_pri_group="$(getent group "${img_user_pri_group_id}" | cut -d: -f1)"

    if [ ! -d "${img_user_home}" ]; then
        print_banner "Error: The home directory '${img_user_home}' does no exist" 2 "!"
        exit 1
    fi

    # Check if the primary group id for the user '${IMG_USER}' exists in the system.
    if [ -z "${img_user_pri_group}" ]; then
        print_banner "Error: Group '${img_user_pri_group_id}' does not exist (Primary group of user '${IMG_USER}')" 2 "!"
        exit 1
    fi

    # If the user ${IMG_USER} is root, no need to adapt the user and group ids.
    if [ "${IMG_USER}" = "root" ]; then
        print_banner "The IMG_USER in the Docker image is root, no user-group adaption is possible. Variables EXT_UID and EXT_UPGID are discarded"
        add_render_group_to_user "${IMG_USER}"
        # When the session is started, if you add a user to a group, the id command will not show
        # the group added to the user until you start a new session by launching a login shell or
        # using the commands newgrp or gosu. This is because the session is not updated. However,
        # the group is added to the user, and you can use it. So, no real need to use gosu here.
        [ -s "${img_user_home}/.environment.sh" ] && . "${img_user_home}/.environment.sh"
        exec "$@"
    # The user ${IMG_USER} is not root, we need to adapt the id and pri_gid of this user to the
    # provided EXT_UID and EXT_UPGID.
    else
        print_banner "User '${IMG_USER}' (UID '${img_user_id}') has primary group '${img_user_pri_group}' (GID '${img_user_pri_group_id}') (${img_user_entry})"

        # Detect if a group in the Docker image is already using the id ${EXT_UPGID}.
        group_entry="$(getent group "${EXT_UPGID}")"

        # Check if the id ${EXT_UPGID} is not in use.
        if [ -z "${group_entry}" ]; then
            # Since the id ${EXT_UPGID} is not in use, we can assign it to the existing group in the
            # Docker image with name ${img_user_pri_group}.
            echo "> Group id '${EXT_UPGID}' is not in use"
            echo "> Setting id '${EXT_UPGID}' to group '${img_user_pri_group}'"
            groupmod --gid "${EXT_UPGID}" "${img_user_pri_group}"
            # Next, we need to set the primary group id of the user ${IMG_USER} to the
            # new group id ${EXT_UPGID}.
            # It is still pending to update the ownership of the home directory of the user
            # ${IMG_USER} to the new group id ${EXT_UPGID}.
            echo "> Setting primary group id '${EXT_UPGID}' to user '${IMG_USER}'"
            usermod --gid "${EXT_UPGID}" "${IMG_USER}"
            echo "($(getent passwd "${IMG_USER}"))"

            # Update the variable to reflect the new primary group id.
            img_user_pri_group_id="${EXT_UPGID}"
        # If the execution reaches this point, it means that the group id ${EXT_UPGID} is in use in
        # the Docker image.
        # We need to check if the group id ${EXT_UPGID} is the primary group id of the user
        # ${IMG_USER}.
        elif [ "${EXT_UPGID}" != "${img_user_pri_group_id}" ]; then
            # If the execution reaches this point, it means that the group id ${EXT_UPGID} is in use
            # in the Docker image, but it is not the primary group id of the user ${IMG_USER}.
            group="$(echo "${group_entry}" | cut -d: -f1)"
            print_banner "The group '${group}' is using the id '${EXT_UPGID}' (${group_entry})"

            # First, we need the name ${img_user_pri_group} to be available to be set to the group
            # with id ${EXT_UPGID}. To do this, we need to set a new unique name to the group with
            # id # ${img_user_pri_group_id}.
            new_group_name="$(generate_unique_name group "${img_user_pri_group}_")"
            echo "> Setting name '${new_group_name}' to group '${img_user_pri_group_id}'. Name '${img_user_pri_group}' will be available'"
            groupmod --new-name "${new_group_name}" "${img_user_pri_group}"
            echo "($(getent group "${new_group_name}"))"

            # Now, we can set the name ${img_user_pri_group} to the group with id ${EXT_UPGID}.
            echo "> Setting name '${img_user_pri_group}' to group '${EXT_UPGID}'"
            groupmod --new-name "${img_user_pri_group}" "${group}"
            echo "($(getent group "${img_user_pri_group}"))"

            echo "> Setting primary group id '${EXT_UPGID}' to user '${IMG_USER}'"
            usermod --gid "${EXT_UPGID}" "${IMG_USER}"
            echo "($(getent passwd "${IMG_USER}"))"

            # Update the variable to reflect the new primary group id.
            img_user_pri_group_id="${EXT_UPGID}"
        fi

        # The case where  "${EXT_UPGID}" = "${img_user_pri_group_id}" means that the primary group
        # id of the user ${IMG_USER} is already set to the group with id ${EXT_UPGID}, so no need
        # to change it.

        user_entry="$(getent passwd "${EXT_UID}")"

        # Check if the id ${EXT_UID} is available.
        if [ -z "${user_entry}" ]; then
            # If the execution reaches this point, it means that the id ${EXT_UID} is not in use.
            # We can set the id of the user ${IMG_USER} to ${EXT_UID}.
            echo "> Setting id '${EXT_UID}' to user '${IMG_USER}'"
            usermod --uid "${EXT_UID}" "${IMG_USER}"
            echo "($(getent passwd "${IMG_USER}"))"

            # Update the variable to reflect the new user id.
            img_user_id="${EXT_UID}"
        elif [ "${EXT_UID}" != "${img_user_id}" ]; then
            # If the execution reaches this point, it means that the id ${EXT_UID} is in use
            # in the Docker image, but it is not the id of the user ${IMG_USER}.
            # We need to set the id ${EXT_UID} to the user ${IMG_USER}.
            user="$(echo "${user_entry}" | cut -d: -f1)"
            user_pri_group_id="$(echo "${user_entry}" | cut -d: -f4)"
            user_home="$(echo "${user_entry}" | cut -d: -f6)"
            print_banner "The user '${user}' is using the id '${EXT_UID}' (${user_entry})"

            # To do this, first, we find a free id and assign it to the user ${user}, that currently
            # has the id ${EXT_UID}.
            # This way, the id ${EXT_UID} will be available to be set to the user ${IMG_USER}.
            new_user_id="$(find_free_id)"
            echo "> Setting id '${new_user_id}' to user '${user}'"
            usermod --uid "${new_user_id}" "${user}"
            echo "($(getent passwd "${user}"))"

            # Since the user ${user} has a different id now, just in case, we need to change the
            # ownership of the home directory of the user ${user} to reflect the new id.
            echo "> Setting ownership of home directory '${user_home}' to '${new_user_id}:${user_pri_group_id}'"
            chown -R "${new_user_id}":"${user_pri_group_id}" "${user_home}"

            # Now we can set the id ${EXT_UID} to the user ${IMG_USER}.
            echo "> Setting id '${EXT_UID}' to user '${IMG_USER}'"
            usermod --uid "${EXT_UID}" "${IMG_USER}"
            echo "($(getent passwd "${IMG_USER}"))"

            # Update the variable to reflect the new user id.
            img_user_id="${EXT_UID}"
        fi

        # Now, we set the ownership of the home directory of the user ${IMG_USER}, to be sure that,
        # independtly of the previous operations, the home directory of the user ${IMG_USER} is
        # owned by the user ${IMG_USER} and the primary group of the user ${IMG_USER}.
        # At this point, the user ${IMG_USER} has the id ${EXT_UID} and the primary group id
        # ${EXT_UPGID}, so we can use these values to set the ownership of the home directory.
        echo "> Setting ownership of home directory '${img_user_home}' to '${EXT_UID}:${EXT_UPGID}'"
        chown -R "${EXT_UID}":"${EXT_UPGID}" "${img_user_home}"

        add_render_group_to_user "${IMG_USER}"

        # We use gosu here to start a new session with the new user and group ids.
        exec gosu "${IMG_USER}" bash -c '
            [ -s "${HOME}/.environment.sh" ] && . "${HOME}/.environment.sh"
            exec "$@"
        ' bash "$@"
    fi
fi
