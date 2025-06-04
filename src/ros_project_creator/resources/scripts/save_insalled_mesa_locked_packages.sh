#!/bin/bash
set -e

log() {
    local message="${1}"
    local fd="${2:-1}" # default to 1 (stdout) if not provided

    # Validate that fd is either 1 (stdout) or 2 (stderr)
    if [[ "${fd}" != "1" && "${fd}" != "2" ]]; then
        fd=1
    fi

    printf "[%s] %s\n" "$(date --utc '+%Y-%m-%d_%H-%M-%S')" "${message}" >&"${fd}"
}

. /etc/os-release
lockedfile="/tmp/mesa_locked_packages_ubuntu_${VERSION_ID}_$(date +%Y%m%d_%H%M%S).txt"

log "Generating file with Mesa locked packages"

mesa_packages=(
    mesa-utils
    mesa-vulkan-drivers
    libgl1-mesa-dri
    libgl1-mesa-glx
    libegl1-mesa
)

for pkg in "${mesa_packages[@]}"; do
    pkg_full=$(dpkg -l | grep "^ii" | grep -E "^ii\s+${pkg}(:amd64)?\s" | awk '{print $2 "=" $3}')

    if [ -n "${pkg_full}" ]; then
        echo "${pkg_full}" >> "${lockedfile}"
    else
        log "Package '${pkg}' not found or not installed"
    fi
done

log "Package list saved to file '${lockedfile}'"
