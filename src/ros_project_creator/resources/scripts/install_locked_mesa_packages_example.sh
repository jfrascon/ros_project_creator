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

log "Using system repositories to install locked versions of Mesa packages"
apt-get update

# Puedes editar las versiones concretas según las que hayan funcionado bien para tu caso de uso.
# Estas versiones son solo ejemplos y deben ser revisadas antes de usar.
packages=(
mesa-utils=8.4.0-1ubuntu1
mesa-vulkan-drivers:amd64=23.2.1-1ubuntu3.1~22.04.3
libgl1-mesa-dri:amd64=23.2.1-1ubuntu3.1~22.04.3
libgl1-mesa-glx:amd64=23.0.4-0ubuntu1~22.04.1
libegl1-mesa:amd64=23.0.4-0ubuntu1~22.04.1
)

log "Candidate versions will be forced:"

for entry in "${packages[@]}"; do
    pkg="${entry%%=*}"
    ver="${entry##*=}"

    log "Package: ${pkg}"
    log "    Version: ${ver}"
done

apt-get install --yes --no-install-recommends "${packages[@]}"
