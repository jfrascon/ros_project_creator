# shellcheck shell=bash

# This file is sourced by code-devcont and devcont. Keeping image inspection in
# one place prevents the two launchers from interpreting the robotics-dockers
# image contract differently.

load_robotics_dockers_image_identity() {
    local image_name="${1}"
    local identity_helper="${2}"
    local image_environment
    local variable_name
    local variable_value

    if [ ! -f "${identity_helper}" ]; then
        log "ERROR: Image identity helper not found: ${identity_helper}"
        return 1
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        log 'ERROR: Python 3 is required to inspect the robotics-dockers image identity.'
        return 1
    fi

    # robotics_dockers_user_env.py is the canonical parser and validator for
    # the ROBOTICS_DOCKERS_* metadata stored in the selected Docker image.
    # Keep that logic out of these shell launchers so contract changes have a
    # single implementation.
    image_environment="$(python3 "${identity_helper}" "${image_name}")" || return 1

    ROBOTICS_DOCKERS_USER_ID=''
    ROBOTICS_DOCKERS_USER_PRIMARY_GROUP_ID=''
    while IFS='=' read -r variable_name variable_value; do
        case "${variable_name}" in
        ROBOTICS_DOCKERS_USER_ID)
            ROBOTICS_DOCKERS_USER_ID="${variable_value}"
            ;;
        ROBOTICS_DOCKERS_USER_PRIMARY_GROUP_ID)
            ROBOTICS_DOCKERS_USER_PRIMARY_GROUP_ID="${variable_value}"
            ;;
        esac
    done <<<"${image_environment}"

    # The Python helper guarantees decimal values in the supported range. The
    # shell only verifies that its expected output fields were received.
    if [ -z "${ROBOTICS_DOCKERS_USER_ID}" ]; then
        log 'ERROR: Image identity helper returned no ROBOTICS_DOCKERS_USER_ID value.'
        return 1
    fi

    if [ -z "${ROBOTICS_DOCKERS_USER_PRIMARY_GROUP_ID}" ]; then
        log 'ERROR: Image identity helper returned no ROBOTICS_DOCKERS_USER_PRIMARY_GROUP_ID value.'
        return 1
    fi

    export ROBOTICS_DOCKERS_USER_ID
    export ROBOTICS_DOCKERS_USER_PRIMARY_GROUP_ID
}
