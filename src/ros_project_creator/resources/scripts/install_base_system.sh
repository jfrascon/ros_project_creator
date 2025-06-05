#!/bin/bash

#set -e

#-----------------------------------------------------------------------------------------------------------------------
# Functions
#-----------------------------------------------------------------------------------------------------------------------

detect_nvidia_libraries() {
    log "Checking for NVIDIA-related user-space libraries"

    local nvidia_signatures=(
        "libcudart.so"
        "libcublas.so"
        "libcudnn.so"
        "libnvrtc.so"
        "libnvinfer.so"
        "libnvonnxparser.so"
        "libnpp.*.so"
        "libnvcuvid.so"
        "libnvidia-ml.so"
        "libGLX_nvidia.so"
        "libEGL_nvidia.so"
        "libGLESv2_nvidia.so"
        "nvcc"
        "libdevice.10.bc"
    )

    for pattern in "${nvidia_signatures[@]}"; do
        if find /usr /opt /lib /lib64 /usr/local -type f -name "${pattern}" 2>/dev/null | grep -q .; then
            log "Detected NVIDIA-related file: '${pattern}'"
            return 0
        fi
    done

    log "No NVIDIA libraries found"
    return 1
}

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
    if [[ "${fd}" != "1" && "${fd}" != "2" ]]; then
        fd=1
    fi

    printf "[%s] %s\n" "$(date --utc '+%Y-%m-%d_%H-%M-%S')" "${message}" >&"${fd}"
}

#-----------------------------------------------------------------------------------------------------------------------
# Start execution of the script
#-----------------------------------------------------------------------------------------------------------------------
# Requested user to be created in the image.
REQUESTED_USER="${1}"
requested_user_shell="/bin/bash"

if [ -z "${REQUESTED_USER}" ]; then
    log "Error: User not provided" 2
    exit 1
fi

if [ "${REQUESTED_USER}" == root ]; then
    requested_user_home="/root"
else
    requested_user_home="/home/${REQUESTED_USER}"
fi

# This script is run by root when building the Docker image.
[ "$(id --user)" -ne 0 ] && {
    log "Error: root user must be active to run the script '$(basename "${BASH_SOURCE[0]}")'" 2
    exit 1
}

# Update the package list and upgrade all packages to their latest versions.
apt-get update

# Install the apt-utils package first, to avoid warnings when installing packages if this package
# is not installed previously.
apt-get install --yes --no-install-recommends apt-utils

# Upgrade the system to ensure all packages are up to date, now that apt-utils is installed.
apt-get dist-upgrade --yes

#-----------------------------------------------------------------------------------------------------------------------
# Unminimize the system
#-----------------------------------------------------------------------------------------------------------------------
# In a development environment, man pages are useful for understanding commands and their options, so we install them.
# Up to Ubuntu:22.04, the command 'unminimize' was already included in the Ubuntu base image provided by Docker Hub.
# Starting with Ubuntu:24.04, the 'unminimize' command is no longer included by default. However, it is available in the
# system repositories and must be installed before it can be used.

# Check if the command exists; if not, install it if available in apt sources.
if ! command -v unminimize &>/dev/null; then
    if apt-cache policy unminimize | grep --quiet 'Candidate:'; then
        apt-get install --yes --no-install-recommends unminimize
    else
        log "Warning: Package 'unminimize' is missing in apt sources! Skipping installation"
    fi
fi

# Unminimize the system if the command unminimize is available.
if command -v unminimize &>/dev/null; then
    echo y | unminimize
fi

# Install the package that allow us to add repositories.
apt-get install --yes --no-install-recommends python3-software-properties software-properties-common
apt-get -f install --yes
dpkg --configure -a

# Now add-apt-repository is available, and we can add the universe repository that contains many
# of the packages we need. Next, the index is updated, and the system is upgraded to ensure all packages are up to date.
add-apt-repository --yes universe
apt-get update
apt-get dist-upgrade --yes

#-----------------------------------------------------------------------------------------------------------------------
# Install system packages
#-----------------------------------------------------------------------------------------------------------------------
. /etc/os-release

# Install core packages.
packages=(
    # basic packages
    apt-rdepends
    apt-utils
    automake
    bash-completion
    build-essential
    clang
    clang-format
    clang-tidy
    cmake
    cmake-data
    cppcheck
    curl
    gawk
    gdb
    git
    gnupg2
    gosu
    htop
    iproute2
    iputils-ping
    jq
    lcov
    less
    libcppunit-dev
    libtool-bin
    lldb
    man
    man-db
    manpages-dev
    manpages-posix-dev
    nano
    net-tools
    openssh-client
    procps
    python3-dev
    python3-mypy
    python3-numpy
    python3-pip
    python3-pytest
    python3-setuptools
    rsync
    sed
    sudo
    tree
    wget
    valgrind
    vim
)

install_packages "${packages[@]}"

# Since Ubuntu 18.04 onwards, python3 is the default python command.
update-alternatives --install /usr/bin/python python /usr/bin/python3 100

# Set the system timezone to UTC to ensure consistent timekeeping across environments.
# Handle timezone configuration explicitly and separately from the main package installation to avoid tzdata's
# interactive prompts. Even with DEBIAN_FRONTEND=noninteractive, tzdata might still try to launch its dialog if the
# timezone config files are missing or improperly set.
# The /etc/timezone file and the /etc/localtime symlink must be created before installing tzdata.
# The file /etc/localtime must point to a valid file under /usr/share/zoneinfo/, which is provided by the tzdata
# package.

package="tzdata"

if ! dpkg --status "${package}" &>/dev/null; then
    if apt-cache policy "${package}" | grep --quiet 'Candidate:'; then
        # IT is mandatory to set the timezone to utc and the /etc/localtime symlink before
        # installing tzdata to avoid tzdata's interactive prompts.
        echo "Etc/UTC" >/etc/timezone
        ln --symbolic --force --no-dereference "/usr/share/zoneinfo/etc/utc" /etc/localtime
        apt-get install --yes --no-install-recommends tzdata
    else
        log "Warning: package '${package}' is missing in system repositories"
    fi
else
    # If tzdata is already installed, set the timezone to UTC.
    echo "Etc/UTC" >/etc/timezone
    ln --symbolic --force --no-dereference "/usr/share/zoneinfo/etc/utc" /etc/localtime
    dpkg-reconfigure --frontend noninteractive tzdata
fi

# Install the locales package to enable language and regional settings.
# Then, uncomment the en_us.utf-8 locale in /etc/locale.gen to make it available.
# Finally, generate the selected locale to ensure proper language support in the system.
apt-get install --yes --no-install-recommends locales
sed -i 's/^# *\(en_US.UTF-8 UTF-8\)/\1/' /etc/locale.gen
locale-gen en_US.UTF-8

#-----------------------------------------------------------------------------------------------------------------------
# Create the requested user
#-----------------------------------------------------------------------------------------------------------------------
# Starting with Ubuntu 24.04, a default non-root user named 'ubuntu' exists with UID 1000 and primary group 'ubuntu'
# with GID 1000.
# Reference: https://bugs.launchpad.net/cloud-images/+bug/2005129

# Check if the user '${REQUESTED_USER}' exists
if ! getent passwd "${REQUESTED_USER}" >/dev/null 2>&1; then
    if [ "${REQUESTED_USER}" = root ]; then
        log "Error: User '${REQUESTED_USER}' should already exist in the image"
        exit 1
    fi

    # Create the user with the specified home directory and shell. Home is created physically.
    useradd --home-dir "${requested_user_home}" --create-home --shell "${requested_user_shell}" "${REQUESTED_USER}"

    img_user_entry="$(getent passwd "${REQUESTED_USER}")"
    img_user_id="$(echo "${img_user_entry}" | cut -d: -f3)"
    img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
    img_user_pri_group="$(getent group "${img_user_pri_group_id}" | cut -d: -f1)"

    log "Created user '${REQUESTED_USER}' (UID '${img_user_id}') with primary group '${img_user_pri_group}' (GID '${img_user_pri_group_id}')"
else
    # If the user already exists, check if the home directory and shell match the requested ones.
    img_user_entry="$(getent passwd "${REQUESTED_USER}")"
    img_user_id="$(echo "${img_user_entry}" | cut -d: -f3)"
    img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
    img_user_pri_group="$(getent group "${img_user_pri_group_id}" | cut -d: -f1)"

    img_user_home="$(echo "${img_user_entry}" | cut -d: -f6)"
    img_user_shell="$(echo "${img_user_entry}" | cut -d: -f7)"

    log "User '${REQUESTED_USER}' (UID '${img_user_id}') with primary group '${img_user_pri_group}' (GID '${img_user_pri_group_id}') already exists, verifying properties"

    if [ "${requested_user_shell}" != "${img_user_shell}" ]; then
        log "Updating shell of user '${REQUESTED_USER}' (UID '${img_user_id}') from '${img_user_shell}' to '${requested_user_shell}'"
        usermod --shell "${requested_user_shell}" "${REQUESTED_USER}"
    fi

    if [ "${requested_user_home}" != "${img_user_home}" ]; then
        log "Updating home directory of user '${REQUESTED_USER}' (UID '${img_user_id}') from '${img_user_home}' to '${requested_user_home}'"
        mkdir --parents "${requested_user_home}" # Create the home directory if it does not exist. If it exists, it will not be modified.
        usermod --home "${requested_user_home}" --move-home "${REQUESTED_USER}"
        # Ensure the home directory is owned by the user and group.
        chown "${REQUESTED_USER}:${img_user_pri_group}" "${requested_user_home}"
    fi
fi

# Ensure user is member of secondary groups dialout, sudo and video.
# dialout group is used to access serial ports (devices like /dev/ttyusb<x>).
# video group is used to access video devices (like /dev/video<x>, /dev/dri/card<x>).
for group in dialout sudo video; do
    group_entry="$(getent group "${group}")"

    if [ -z "${group_entry}" ]; then
        log "Warning: group '${group}' does not exist!"
    elif ! id -nG "${REQUESTED_USER}" | grep --quiet --word-regexp "${group}"; then
        group_id="$(echo "${group_entry}" | cut -d: -f3)"
        log "Adding user '${REQUESTED_USER}' (UID '${img_user_id}') to group '${group}' (GID '${group_id}')"
        usermod --append --groups "${group}" "${REQUESTED_USER}"
    else
        log "User '${REQUESTED_USER}' (UID '${img_user_id}') is already a member of group '${group}' (GID '${group_id}')"
    fi
done

# Set password for the non-root user.
# The non-root user can run commands with sudo without a password.
if [ "${REQUESTED_USER}" != root ]; then
    # Set password equal to username
    log "Setting password for user '${REQUESTED_USER}' (UID '${img_user_id}') to '${REQUESTED_USER}'"
    password="${REQUESTED_USER}"
    echo "${REQUESTED_USER}:${password}" | chpasswd

    # The following block is disabled and is left here for reference.
    # It is not recommended to configure passwordless sudo in a Docker image, as it can lead to
    # security issues.

    # Configure passwordless sudo.
    # log "Configuring passwordless sudo for user '${REQUESTED_USER}' (UID '${img_user_id}')"
    # sudoers_file="/etc/sudoers.d/${REQUESTED_USER}"
    # echo "${REQUESTED_USER} ALL=(ALL) NOPASSWD:ALL" >"${sudoers_file}"
    # chmod 0440 "${sudoers_file}"

    # # Check if the sudoers file is valid.
    # if ! visudo --check --file "${sudoers_file}" >/dev/null 2>&1; then
    #     log "Error: Invalid sudoers file '${sudoers_file}'!"
    #     exit 1
    # fi
fi

# Create basic folders for configuration and binaries.
dirs_to_create=(
    "${requested_user_home}/.config"
    "${requested_user_home}/.local/bin"
    "${requested_user_home}/.local/lib"
    "${requested_user_home}/.local/share"
)

for dir in "${dirs_to_create[@]}"; do
    if [ ! -d "${dir}" ]; then
        log "Creating directory '${dir}'"
        install --directory --mode 755 --owner "${REQUESTED_USER}" --group "${img_user_pri_group}" "${dir}"
    else
        log "Directory '${dir}' already exists"
    fi
done

# Create the .bashrc file if it does not exist.
if [ ! -s "${requested_user_home}/.bashrc" ]; then
    log "File '${requested_user_home}/.bashrc' does not exist. Copying file /etc/skel/.bashrc to '${requested_user_home}/.bashrc'"
    sudo -H -u "${REQUESTED_USER}" cp --verbose /etc/skel/.bashrc "${requested_user_home}/.bashrc"
fi

#-----------------------------------------------------------------------------------------------------------------------
# Install Python packages for the user that are commonly used for development
#-----------------------------------------------------------------------------------------------------------------------
python_packages=(argcomplete black cmake-format pre-commit)

log "Installing Python packages for the user '${REQUESTED_USER}': ${python_packages[*]}"

# Asegurar permisos correctos sobre el home (solo si no es root)
if [ "${REQUESTED_USER}" != root ]; then
    # The '--break-system-packages', described in PEP 668, was introduced in Python 3.11+ from Debian Bookworm and
    # Ubuntu 24.04 (Noble Numbat), onwards. PEP 668 prevents installing packages with  'pip install --user' in
    # system-managed environments. To work around this, the '--break-system-packages' flag is used to allow the
    # installation of packages in user-managed environments.
    # Ubuntu 22.04 (Jammy), and below, does NOT have this restriction, so 'pip install --user' should work fine.
    if python3 -m pip install --help | grep --quiet 'break-system-packages'; then
        flag_break="--break-system-packages"
    else
        flag_break=""
    fi

    # -H flag is used to set the HOME environment variable to the home directory of the target user.
    # The HOME environment variable is used by pip to determine the location of the user's home directory.
    # The --no-cache-dir flag is used to avoid caching the downloaded packages.
    # The --user flag is used to install the packages in the user's home directory.
    # To avoid warning messages when installing packages we set the environment variable PATH to include
    # the user's local bin directory. Next, an ENV variable is set to include the user's local bin
    # directory in the PATH variable, in the Dockerfile.
    sudo -H -u "${REQUESTED_USER}" env PATH="${requested_user_home}/.local/bin:${PATH}" \
        python3 -m pip install --no-cache-dir --user ${flag_break} ${python_packages}
else
    python3 -m pip install --no-cache-dir ${python_packages}
fi

#-----------------------------------------------------------------------------------------------------------------------
# Cleanup
#-----------------------------------------------------------------------------------------------------------------------
log "Removing installation residues from apt cache"
apt-get autoclean
apt-get autoremove --purge -y
apt-get clean
rm -rf /var/lib/apt/lists/* 1>/dev/null 2>&1
