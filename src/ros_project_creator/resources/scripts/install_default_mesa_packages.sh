#!/bin/bash
set -e

install_packages() {
    local packages=("$@")
    local sim_out
    local sim_rc
    local valid_packages=()
    local bad_packages=()
    local pkg

    apt-get update # Ensure the package index is up to date before simulating installation
    sim_out="$(apt-get --simulate --quiet --quiet --no-install-recommends -o Dpkg::Use-Pty=0 install "${packages[@]}" 2>&1)"
    sim_rc=$?

    if [ "${sim_rc}" -ne 0 ] && [ "${sim_rc}" -ne 100 ]; then
        log "Error: apt-get simulation failed unexpectedly (rc=${sim_rc})" 2
        exit 1
    fi

    if [ "${sim_rc}" -eq 0 ]; then
        valid_packages=("${packages[@]}") # All packages are valid, install all of them
    else                                  # exit_code is 100, which means some packages are not installable
        mapfile -t bad_packages < <(
            grep -oP 'Unable to locate package \K\S+' <<<"${sim_out}"
        )

        for pkg in "${packages[@]}"; do
            if ! echo " ${bad_packages[*]} " | grep -q " ${pkg} "; then
                valid_packages+=("${pkg}")
            fi
        done
    fi

    if [ "${#bad_packages[@]}" -gt 0 ]; then
        log "Packages not installable: ${bad_packages[*]}" 2
    fi

    if [ "${#valid_packages[@]}" -gt 0 ]; then
        log "Installing packages: ${valid_packages[*]}"

        if ! apt-get install --yes --no-install-recommends "${valid_packages[@]}"; then
            log "Error: Failed to install some packages: ${valid_packages[*]}" 2
            exit 1
        fi
    fi
}

log() {
    local message="${1}"
    local fd="${2:-1}" # default to 1 (stdout) if not provided

    # Validate that fd is either 1 (stdout) or 2 (stderr)
    if [ "${fd}" != "1" ] && [ "${fd}" != "2" ]; then
        fd=1
    fi

    printf "[%s] %s\n" "$(date --utc '+%Y-%m-%d_%H-%M-%S')" "${message}" >&"${fd}"
}

#-----------------------------------------------------------------------------------------------------------------------
# Start execution of the script
#-----------------------------------------------------------------------------------------------------------------------

# This script is run by root when building the Docker image.
[ "$(id --user)" -ne 0 ] && {
    log "Error: root user must be active to run the script '$(basename "${BASH_SOURCE[0]}")'" 2
    exit 1
}

log "Using system repositories to install Mesa packages"
apt-get update

log "Resolving candidate versions for Mesa packages"

packages=(
libgl1
libgl1-mesa-dri
mesa-utils
x11-xserver-utils
)

for pkg in "${packages[@]}"; do
    candidate=$(apt-cache policy "${pkg}" | grep Candidate | awk '{print $2}')
    installed=$(dpkg-query -W -f='${Version}' "${pkg}" 2>/dev/null || echo "none")

    log "Package: ${pkg}"
    log "    Installed: ${installed}"
    log "    Candidate: ${candidate}"
done

install_packages "${packages[@]}"
