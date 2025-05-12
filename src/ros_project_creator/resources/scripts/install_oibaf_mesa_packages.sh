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

# This script is run by root when building the Docker image.
[ "$(id --user)" -ne 0 ] && {
    log "Error: root user must be active to run the script '$(basename "${BASH_SOURCE[0]}")'" 2
    exit 1
}

log "Adding Oibaf PPA to install Mesa packages"
add-apt-repository -y ppa:oibaf/graphics-drivers
apt-get update

log "Resolving candidate versions for Mesa packages"

packages=(
    mesa-utils
    mesa-vulkan-drivers
    libgl1-mesa-dri
    libgl1-mesa-glx
    libegl1-mesa
)

for pkg in "${packages[@]}"; do
    candidate=$(apt-cache policy "${pkg}" | grep Candidate | awk '{print $2}')
    installed=$(dpkg-query -W -f='${Version}' "${pkg}" 2>/dev/null || echo "none")

    log "Package: ${pkg}"
    log "    Installed: ${installed}"
    log "    Candidate: ${candidate}"
done

log "Installing Mesa packages from Oibaf PPA"
apt-get install --yes --no-install-recommends "${packages[@]}"
