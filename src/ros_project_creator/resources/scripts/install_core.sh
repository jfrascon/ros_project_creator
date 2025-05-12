#!/bin/bash

#set -e

# Run a command as a specific user.
as_user() {
    local target_user="${1}"
    shift

    if [ "${target_user}" = "root" ]; then
        "$@"
    else
        sudo -H -u "${target_user}" "$@"
    fi
}

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

log() {
    local message="${1}"
    local fd="${2:-1}" # default to 1 (stdout) if not provided

    # Validate that fd is either 1 (stdout) or 2 (stderr)
    if [[ "${fd}" != "1" && "${fd}" != "2" ]]; then
        fd=1
    fi

    printf "[%s] %s\n" "$(date --utc '+%Y-%m-%d_%H-%M-%S')" "${message}" >&"${fd}"
}

should_install_mesa() {
    if [ "${USE_NVIDIA_SUPPORT}" = "true" ]; then
        log "USE_NVIDIA_SUPPORT was explicitly set"
        return 1
    fi

    log "USE_NVIDIA_SUPPORT was not set, checking for NVIDIA libraries"

    if detect_nvidia_libraries; then
        log "Warning: NVIDIA libraries detected"
        log "Assuming NVIDIA runtime will be used"
        return 1
    fi

    return 0
}

# Requested user to be created in the image.
REQUESTED_USER="${1}"
USE_NVIDIA_SUPPORT="${2:-false}"
INSTALL_MESA_PACKAGES_SCRIPT="${3}"

requested_user_shell="/bin/bash"

if [ -z "${REQUESTED_USER}" ]; then
    log "Error: User not provided" 2
    exit 1
fi

if [ "${REQUESTED_USER}" != root ]; then
    requested_user_home="/home/${REQUESTED_USER}"
else
    requested_user_home="/root"
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
apt-get install --yes --no-install-recommends "apt-utils"

# Upgrade the system to ensure all packages are up to date, now that apt-utils is installed.
apt-get dist-upgrade --yes

# In a development environment, man pages are useful, so do not exclude them.
# Up to Ubuntu:22.04, the command 'unminimize' was already included in the Ubuntu base image
# provided by Docker Hub.
# Starting with Ubuntu:24.04, the 'unminimize' command is no longer included by default. However, it
# is available in the APT repositories and must be installed before it can be used.

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

. /etc/os-release

# Install core packages.
packages=(
    # Packages to handle users and groups
    bash
    coreutils
    grep
    login
    passwd
    procps
    sudo
    # basic packages
    apt-rdepends
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
    python3-dev
    python3-mypy
    python3-numpy
    python3-pip
    python3-pytest
    python3-setuptools
    rsync
    sed
    tree
    wget
    valgrind
    vim
)

valid_packages=()

for package in "${packages[@]}"; do
    if apt-cache policy "${package}" | grep --quiet 'Candidate:'; then
        valid_packages+=("${package}")
    else
        log "Warning: Package '${package}' is missing in system repositories"
    fi
done

if [ "${#valid_packages[@]}" -gt 0 ]; then
    log "Installing packages: ${valid_packages[*]}"
    apt-get install --yes --no-install-recommends "${valid_packages[@]}"
else
    log "No packages to install"
fi

if should_install_mesa; then
    if [ -s "${INSTALL_MESA_PACKAGES_SCRIPT}" ]; then
        bash "${INSTALL_MESA_PACKAGES_SCRIPT}"
    else
        log "Warning: File '${INSTALL_MESA_PACKAGES_SCRIPT}' not found or empty! Skipping installation of Mesa packages"
    fi
else
    log "Installation of Mesa packages skipped"
fi

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

# Starting with Ubuntu 24.04, a default non-root user named 'ubuntu' exists with UID 1000 and main group 'ubuntu' with
# GID 1000.
# Reference: https://bugs.launchpad.net/cloud-images/+bug/2005129

# Ensure '${requested_user_shell}' is listed in /etc/shells (required by chsh and login)

if ! grep --quiet "^${requested_user_shell}$" /etc/shells; then
    echo "${requested_user_shell}" >>/etc/shells
fi

# Check if the user '${REQUESTED_USER}' exists
if ! getent passwd "${REQUESTED_USER}" >/dev/null 2>&1; then

    if [ "${REQUESTED_USER}" = root ]; then
        log "Error: User '${REQUESTED_USER}' should already exist in the image"
        exit 1
    fi

    log "Creating user '${REQUESTED_USER}'"

    # Create the user with the specified home directory and shell. Home is created physically.
    useradd \
        --home-dir "${requested_user_home}" \
        --create-home \
        --shell "${requested_user_shell}" \
        "${REQUESTED_USER}"

    img_user="${REQUESTED_USER}"
    img_user_entry="$(getent passwd "${img_user}")"
    img_user_id="$(echo "${img_user_entry}" | cut -d: -f3)"
    img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
    img_user_pri_group="$(getent group "${img_user_pri_group_id}" | cut -d: -f1)"
    img_user_home="$(echo "${img_user_entry}" | cut -d: -f6)"
    img_user_shell="$(echo "${img_user_entry}" | cut -d: -f7)"

    log "User '${img_user}' (UID '${img_user_id}') with primary group '${img_user_pri_group}' (GID '${img_user_pri_group_id}') created successfully"
else
    img_user="${REQUESTED_USER}"
    img_user_entry="$(getent passwd "${img_user}")"
    img_user_id="$(echo "${img_user_entry}" | cut -d: -f3)"
    img_user_pri_group_id="$(echo "${img_user_entry}" | cut -d: -f4)"
    img_user_pri_group="$(getent group "${img_user_pri_group_id}" | cut -d: -f1)"
    img_user_home="$(echo "${img_user_entry}" | cut -d: -f6)"
    img_user_shell="$(echo "${img_user_entry}" | cut -d: -f7)"

    log "User '${img_user}' (UID '${img_user_id}') with primary group '${img_user_pri_group}' (GID '${img_user_pri_group_id}') already exists, verifying properties"

    if [ "${img_user_shell}" != "${requested_user_shell}" ]; then
        log "Updating shell of user '${img_user}' (UID '${img_user_id}') from '${img_user_shell}' to '${requested_user_shell}'"
        usermod --shell "${requested_user_shell}" "${img_user}"
        img_user_shell="${requested_user_shell}"
    fi

    if [ "${img_user_home}" != "${requested_user_home}" ]; then
        log "Updating home directory of user '${img_user}' (UID '${img_user_id}') from '${img_user_home}' to '${requested_user_home}'"
        usermod --home "${requested_user_home}" --move-home "${img_user}"
        img_user_home="${requested_user_home}"
    fi

    # Ensure the home directory exists.
    if [ ! -d "${img_user_home}" ]; then
        log "Creating home directory '${img_user_home}' for user '${img_user}' (UID '${img_user_id}')"
        mkdir --parents "${img_user_home}"
    fi

    # Ensure the home directory is owned by the user and group.
    chown "${img_user}:${img_user_pri_group}" "${img_user_home}"
fi

# Ensure user is member of secondary groups (if they exist).
# dialout group is used to access serial ports (devices like /dev/ttyusb<x>).
# video group is used to access video devices (like /dev/video<x>, /dev/dri/card<x>).
for grp in dialout sudo video; do
    grp_entry="$(getent group "${grp}")"

    if [ -z "${grp_entry}" ]; then
        log "Warning: group '${grp}' does not exist!"
    elif ! id -nG "${img_user}" | grep --quiet --word-regexp "${grp}"; then
        grp_id="$(echo "${grp_entry}" | cut -d: -f3)"
        log "Adding user '${img_user}' (UID '${img_user_id}') to group '${grp}' (GID '${grp_id}')"
        usermod --append --groups "${grp}" "${img_user}"
    else
        log "User '${img_user}' (UID '${img_user_id}') is already a member of group '${grp}' (GID '${grp_id}')"
    fi
done

if [ "${img_user}" != root ]; then
    # Set password equal to username
    log "Setting password for user '${img_user}' (UID '${img_user_id}') to '${img_user}'"
    password="${img_user}"
    echo "${img_user}:${password}" | chpasswd

    # Configure passwordless sudo.
    log "Configuring passwordless sudo for user '${img_user}' (UID '${img_user_id}')"
    sudoers_file="/etc/sudoers.d/${img_user}"
    echo "${img_user} ALL=(ALL) NOPASSWD:ALL" >"${sudoers_file}"
    chmod 0440 "${sudoers_file}"

    # Check if the sudoers file is valid.
    if ! visudo --check --file "${sudoers_file}" >/dev/null 2>&1; then
        log "Error: Invalid sudoers file '${sudoers_file}'!"
        exit 1
    fi
fi

# Create basic folders for configuration and binaries.
dirs_to_create=("${img_user_home}/.config" "${img_user_home}/.local/bin" "${img_user_home}/.local/lib" "${img_user_home}/.local/share")

for dir in "${dirs_to_create[@]}"; do
    if [ ! -d "${dir}" ]; then
        log "Creating directory '${dir}'"
        install --directory --mode 755 --owner "${img_user}" --group "${img_user_pri_group}" "${dir}"
    else
        log "Directory '${dir}' already exists"
    fi
done

# Install the Python packages, with pip, that are commonly used for development.
python_packages=(argcomplete black cmake-format pre-commit)

log "Installing Python packages for the user '${img_user}': ${python_packages[*]}"

# Asegurar permisos correctos sobre el home (solo si no es root)
if [ "${img_user}" != root ]; then
    # log "Fixing ownership of home directory for '${img_user}'"
    # chown -R "${img_user}:${img_user_pri_group}" "${img_user_home}"

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
    sudo -H -u "${img_user}" env PATH="${img_user_home}/.local/bin:${PATH}" \
        python3 -m pip install --no-cache-dir --user ${flag_break} ${python_packages}
else
    python3 -m pip install --no-cache-dir ${python_packages}
fi

if [ ! -s "${img_user_home}/.bashrc" ]; then
    log "File '${img_user_home}/.bashrc' does not exist. Copying file /etc/skel/.bashrc to '${img_user_home}/.bashrc'"
    as_user "${img_user}" cp --verbose /etc/skel/.bashrc "${img_user_home}/.bashrc"
fi

# Check if the ${env_line} exists in the file bashrc files.
env_line='[ -f "${HOME}/.environment.sh" ] && . "${HOME}/.environment.sh"'

if ! grep -Fxq "${env_line}" "${img_user_home}/.bashrc"; then
    log "Adding line '${env_line}' to file '${img_user_home}/.bashrc'"
    as_user "${img_user}" bash -c "echo '# --------------------------------------' >> \"${img_user_home}/.bashrc\""
    as_user "${img_user}" bash -c "echo \"${env_line}\" >> \"${img_user_home}/.bashrc\""

else
    log "Line '${env_line}' already exists in file '${img_user_home}/.bashrc'"
fi

# If the user is not root, we also want the .bahrc file and the .environment.sh file present for the root user.
# This is useful for the case when the user is not root, but the container is run as root for some reason.
if [ "${img_user}" != root ]; then
    if [ ! -s "/root/.bashrc" ]; then
        log "File '/root/.bashrc' does not exist. Copying file /etc/skel/.bashrc to /root/.bashrc"
        cp --verbose /etc/skel/.bashrc "/root/.bashrc"
    fi

    if ! grep -Fxq "${env_line}" "/root/.bashrc"; then
        log "Adding line '${env_line}' to file '/root/.bashrc'"
        echo '# --------------------------------------' >>"/root/.bashrc"
        echo "${env_line}" >>"/root/.bashrc"
    else
        log "Line '${env_line}' already exists in file '/root/.bashrc'"
    fi
fi

log "Removing installation residues from apt cache"
apt-get autoclean
apt-get autoremove --purge -y
apt-get clean
rm -rf /var/lib/apt/lists/* 1>/dev/null 2>&1
