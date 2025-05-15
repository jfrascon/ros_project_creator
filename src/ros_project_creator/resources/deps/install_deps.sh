#!/bin/bash

install_packages() {
    local packages=("$@")
    local sim_out
    local sim_rc
    local valid_packages=()
    local bad_packages=()
    local pkg

    sim_out="$(apt-get --simulate --quiet --quiet --no-install-recommends -o Dpkg::Use-Pty=0 install "${packages[@]}" 2>&1)"
    sim_rc=$?

    if [ "${sim_rc}" -ne 0 ] && [ "${sim_rc}" -ne 100 ]; then
        log "Error: apt-get simulation failed unexpectedly (rc=${sim_rc})" 2
        exit 1
    fi

    if [ "${sim_rc}" -eq 0 ]; then
        valid_packages=("${packages[@]}")
    else
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

apt-get update # Required to load the cache in the build container
apt-get install --yes --no-install-recommends python3-software-properties software-properties-common
apt-get -f install --yes
dpkg --configure -a

# Now add-apt-repository is available, and we can add the universe repository that contains many
# of the packages we need. Next, the index is updated, and the system is upgraded to ensure all packages are up to date.
add-apt-repository --yes universe
apt-get update
apt-get dist-upgrade --yes

. /etc/os-release

apt-get install --yes --no-install-recommends curl gpg

# + ------------------------+
# | Install system packages |
# + ------------------------+

# IT IS STRONGLY ADVISED TO DECLARE REQUIRED SYSTEM DEPENDENCIES IN THE APPROPRIATE
# PACKAGE'S package.xml FILE UNDER THE <depend> OR <build_depend> OR <exec_depend> TAGS.
# THIS ENSURES PROPER DEPENDENCY MANAGEMENT AND COMPATIBILITY ACROSS DIFFERENT ENVIRONMENTS.

# IF YOU ABSOLUTELY NEED TO INSTALL SYSTEM PACKAGES MANUALLY, ENSURE THAT THEY ARE
# NECESSARY AND CANNOT BE RESOLVED VIA rosdep. IMPROPER USE OF THIS SCRIPT FOR
# SYSTEM PACKAGE INSTALLATION MAY LEAD TO INCONSISTENCIES IN DEPENDENCY RESOLUTION.

# install_packages "pkg1" "pkg2" "pkg3"

# + ---------------------+
# | Install ROS packages |
# + ---------------------+

# IT IS STRONGLY ADVISED TO DECLARE REQUIRED ROS DEPENDENCIES IN THE APPROPRIATE PACKAGE'S
# package.xml FILE UNDER THE <depend>, <build_depend>, OR <exec_depend> TAGS.
# THIS ENSURES PROPER DEPENDENCY MANAGEMENT, AUTOMATIC RESOLUTION VIA rosdep,
# AND COMPATIBILITY ACROSS DIFFERENT ENVIRONMENTS.

# Check if ${ROS_DISTRO} is installed properly, otherwise abort the installation.
# ros_distro=$(dpkg --list | sed -nE 's/^ii\s+ros-([a-z]+)-ros-core.*$/\1/p' | tr '\n' ' ' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

# num_distros=$(echo "${ros_distro}" | wc -w)

# if [ "${num_distros}" -eq 0 ]; then
#     log "No ROS distribution found. Please install a ROS distribution before running the script '$(basename "${BASH_SOURCE[0]}")'"
#     exit 1
# elif [ "${num_distros}" -eq 1 ]; then
#     install_packages ros-"${ros_distro}"-<package>
# else # multiple distributions found
#     log "Warning: Multiple ROS distributions detected"
#     exit 1
# fi

# +--------------------------------------------------------------------------------------------------------------------+
# FOR EXAMPLE, IN CASE YOU WANT TO INSTALL PACKAGES FROM GAZEBO CLASSIC, UNCOMMENT THE LINES BELOW
# AND ADD THE REQUIRED GAZEBO-CLASSIC PACKAGES INTO THE PROPER package.xml FILE OF THE NECESSARY PACKAGE.
# curl -fsSL https://packages.osrfoundation.org/gazebo.key | gpg --dearmor -o /etc/apt/keyrings/gazebo_classic.gpg
# echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/gazebo_classic.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable ${VERSION_CODENAME} main" | tee /etc/apt/sources.list.d/gazebo_classic.list >/dev/null
# apt-get update
# +--------------------------------------------------------------------------------------------------------------------+

# +---------------------+
# | Custom instructions |
# +---------------------+

apt-get clean autoclean
apt-get autoremove --yes
rm -rf /var/lib/apt/lists/*
