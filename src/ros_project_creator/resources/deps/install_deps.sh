#!/bin/bash

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

# + --------------------------------------------+
# | Install system dependencies for the project |
# + --------------------------------------------+

# WARNING: INSTALLING SYSTEM PACKAGES THROUGH THIS SCRIPT IS NOT RECOMMENDED!

# IT IS STRONGLY ADVISED TO DECLARE REQUIRED SYSTEM DEPENDENCIES IN THE APPROPRIATE
# PACKAGE'S package.xml FILE UNDER THE <depend> OR <build_depend> OR <exec_depend> TAGS.
# THIS ENSURES PROPER DEPENDENCY MANAGEMENT AND COMPATIBILITY ACROSS DIFFERENT ENVIRONMENTS.

# IF YOU ABSOLUTELY NEED TO INSTALL SYSTEM PACKAGES MANUALLY, ENSURE THAT THEY ARE
# NECESSARY AND CANNOT BE RESOLVED VIA rosdep. IMPROPER USE OF THIS SCRIPT FOR
# SYSTEM PACKAGE INSTALLATION MAY LEAD TO INCONSISTENCIES IN DEPENDENCY RESOLUTION.

# Fill in the array, either adding packages directly into the array system_deps, separated by spaces, or new lines
system_packages=()

valid_system_packages=() # DO NOT FILL THIS ARRAY MANUALLY

for system_package in "${system_packages[@]}"; do
    if apt-cache policy "${system_package}" | grep --quiet 'Candidate:'; then
        valid_system_packages+=("${system_package}")
    else
        log "Warning: Package '${package}' is missing in system repositories"
    fi
done

if [ "${#valid_system_packages[@]}" -gt 0 ]; then
    echo "Installing packages: ${valid_system_packages[@]}"
    apt-get install --yes --no-install-recommends "${valid_system_packages[@]}"
fi

# WARNING: INSTALLING ROS PACKAGES THROUGH THIS SCRIPT IS NOT RECOMMENDED!
#
# IT IS STRONGLY ADVISED TO DECLARE REQUIRED ROS DEPENDENCIES IN THE APPROPRIATE
# PACKAGE'S package.xml FILE UNDER THE <depend>, <build_depend>, OR <exec_depend> TAGS.
# THIS ENSURES PROPER DEPENDENCY MANAGEMENT, AUTOMATIC RESOLUTION VIA rosdep,
# AND COMPATIBILITY ACROSS DIFFERENT ENVIRONMENTS.

# FOR THIS REASON THE SKELETON TO INSTALL ROS PACKAGES IS NOT PROVIDED LIKE FOR SYSTEM PACKAGES, TO
# PERSUADE YOU TO USE THE PROPER WAY OF DECLARING DEPENDENCIES IN THE package.xml FILES.

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
