#!/bin/bash

# ros1build.sh - A wrapper for `catkin build` with enhanced defaults.
#
# Features:
# - Adds `-j <half_cores>` if not specified by the user.
# - Adds `--cmake-args -DCMAKE_CXX_FLAGS="..."` and/or -DCMAKE_BUILD_TYPE=Release unless already set.
# - Prints the final command before execution.
# - Merges compile_commands.json from all packages and rewrites system includes as -isystem.
# - Supports custom --help that explains injected defaults.
# - Mirrors the structure and style of ros2build.sh for consistency.

# Compute default parallelism: half the CPU cores (rounded up).
default_parallel_jobs=$(( ( $(nproc) + 1 ) / 2 ))

# Default C++ warning flags to inject via CMAKE_CXX_FLAGS.
# These are compatible with both GCC and Clang, and provide a good balance between safety and verbosity.
default_cxx_flags="-Wall -Wextra -Wpedantic -Wnon-virtual-dtor -Woverloaded-virtual -Wnull-dereference -Wunused-parameter"

# Stricter warnings (optional):
# -Wshadow             Detects variable shadowing.
# -Wconversion         Warns on implicit type conversions (can be noisy).
# -Wsign-conversion    Warns on signed/unsigned conversions.
# -Wold-style-cast     Disallows C-style casts.

# Default build type.
default_build_type="Release"

# Internal flags to control injection of defaults.
add_default_jobs=true         # Add -j <N> if user didn't set it.
add_default_cxx_flags=true    # Add -DCMAKE_CXX_FLAGS if user didn't define it.
add_default_build_type=true   # Add -DCMAKE_BUILD_TYPE if user didn't define it.

# Show custom help if requested.
if [[ "${1}" == "--help" || "${1}" == "-h" ]]; then
    echo "The following configuration is set by default, unless the user explicitely set other:"
    echo "  -j N, --jobs N        ${default_parallel_jobs}"
    echo "  -DCMAKE_CXX_FLAGS     ${default_cxx_flags}."
    echo "  -DCMAKE_BUILD_TYPE    ${default_build_type}"
    echo

    # Replace default job count description in the original help output.
    catkin build --help \
    | sed -E 's/usage: catkin build/usage: '"$(basename "${BASH_SOURCE[0]}")"' /' \
    | sed -E "s/(.*packages\.[[:space:]]*)\(default is cpu count\)/\1(default is ${default_parallel_jobs})/"
    exit 0
fi

# Parse input arguments.
args=()         # Final list of arguments to pass to catkin build.
cmake_args=()   # All collected cmake args across all --cmake-args blocks.

i=0
while [[ ${i} -lt ${#} ]]; do
  arg="${@:$((i+1)):1}"
  case "${arg}" in
    -j|--jobs)
      add_default_jobs=false
      args+=("${arg}")         # Add "-j" or "--jobs" to the final argument list.
      i=$((i + 1))             # Move to the next positional argument (potential job count).
      if [[ ${i} -lt ${#} ]]; then
        # If there is another argument after "-j"/"--jobs", treat it as the value.
        next_arg="${@:$((i+1)):1}"   # Get the argument in position i+1 (bash is 1-based here).
        args+=("${next_arg}")        # Add the job count (e.g. "8") to the final list.
        i=$((i + 1))                 # Advance index past the value.
      fi
      ;;
    --cmake-args)
      args+=("${arg}")
      i=$((i + 1))
      # Collect all cmake args until the next flag starting with "--".
      while [[ ${i} -lt ${#} ]]; do
        next_arg="${@:$((i+1)):1}"
        if [[ "${next_arg}" == --* ]]; then
          # Do not consume the next --flag, it belongs to outer arguments.
          break
        fi

        # Detect if user provided CXX flags or build type.
        if [[ "${next_arg}" == -DCMAKE_CXX_FLAGS=* ]]; then
          add_default_cxx_flags=false
        elif [[ "${next_arg}" == -DCMAKE_BUILD_TYPE=* ]]; then
          add_default_build_type=false
        fi

        cmake_args+=("${next_arg}")
        args+=("${next_arg}")
        i=$((i + 1))
      done
      ;;
    *)
      # Forward any other argument not explicitly handled by the wrapper.
      args+=("${arg}")
      i=$((i + 1))
      ;;
  esac
done

# Inject -j <default_parallel_jobs> if not set by user.
if ${add_default_jobs}; then
  args+=("-j" "${default_parallel_jobs}")
fi

# Inject missing defaults in separate --cmake-args blocks.
if ${add_default_build_type}; then
  args+=("--cmake-args" "-DCMAKE_BUILD_TYPE=${default_build_type}")
fi

if ${add_default_cxx_flags}; then
  args+=("--cmake-args" "-DCMAKE_CXX_FLAGS=${default_cxx_flags}")
fi

# Print the command being run (for transparency and debugging).
echo "+ catkin build ${args[*]}"

# Execute the final command.
catkin build "${args[@]}"

# Ensure the "build" directory exists.
[ ! -e build ] && exit 1

# Merge compile_commands.json files.
find "build" -iname "compile_commands.json" | xargs --no-run-if-empty jq -s 'map(.[])' > "build/compile_commands.json"

# Modify compile_commands.json for better compatibility with ROS and common system paths.
sed -i \
  -e 's@-I\s\?/opt/ros@-isystem /opt/ros@g' \
  -e 's@-I\s\?/usr/local@-isystem /usr/local@g' \
  -e 's@-I\s\?/usr@-isystem /usr@g' \
  "build/compile_commands.json"