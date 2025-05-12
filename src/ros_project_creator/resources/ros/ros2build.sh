#!/bin/bash

# ros2build.sh - Wrapper for colcon build with inverted defaults.
# - Enables --merge-install and --symlink-install by default.
# - Allows disabling them with --no-merge-install and --no-symlink-install.
# - Sets --parallel-workers to half of the available CPU cores (rounded up) if not provided.
# - Adds --mixin release by default unless the user explicitly passes debug or rel-with-deb-info.
# - Adds --mixin compile-commands by default unless explicitly passed.
# - Adds CMAKE_CXX_FLAGS with common warnings unless user already provides it.
# - Requires --mixin and --cmake-args to be space-separated. Disallows --mixin=... and --cmake-args=....
# - Prints the final colcon build command before executing.

# Initialize.
args=()
add_merge_install=true
add_symlink_install=true
add_default_parallel_workers=true
add_default_release_mixin=true
add_default_compile_commands=true
add_default_cxx_flags=true
mixin_args=()
show_help=false

# Compute default value for --parallel-workers.
default_parallel_workers=$(( ( $(nproc) + 1 ) / 2 ))

# Default C++ warning flags to inject via CMAKE_CXX_FLAGS.
# These are compatible with both GCC and Clang, and provide a good balance between safety and verbosity.
default_cxx_flags="-Wall -Wextra -Wpedantic -Wnon-virtual-dtor -Woverloaded-virtual -Wnull-dereference -Wunused-parameter"

# Stricter warnings (optional):
# -Wshadow             Detects variable shadowing.
# -Wconversion         Warns on implicit type conversions (can be noisy).
# -Wsign-conversion    Warns on signed/unsigned conversions.
# -Wold-style-cast     Disallows C-style casts.

# Parse arguments.
i=0
while [[ $i -lt $# ]]; do
    arg="${@:$((i+1)):1}"

    case "${arg}" in
        --no-merge-install)
            add_merge_install=false
            ;;
        --no-symlink-install)
            add_symlink_install=false
            ;;
        --merge-install)
            echo "ERROR: Unrecognized option '--merge-install'."
            exit 1
            ;;
        --symlink-install)
            echo "ERROR: Unrecognized option '--symlink-install'."
            exit 1
            ;;
        --parallel-workers|--parallel-workers=*)
            add_default_parallel_workers=false
            args+=("${arg}")
            ;;
        --cmake-args=*)
            # Disallow --cmake-args=value syntax to prevent confusion.
            # CMake arguments must be passed as space-separated values.
            # --cmake-args=... would not be parsed correctly and breaks internal detection logic.
            echo "ERROR: Invalid syntax '${arg}'. Use '--cmake-args val1 val2' with arguments as separate values."
            exit 1
            ;;
        --cmake-args)
            args+=("${arg}")
            j=$((i+1))
            # Collect all cmake arguments until the next flag (starting with --).
            # Also detect if user manually sets CMAKE_CXX_FLAGS to avoid injecting defaults.
            while [[ $j -lt $# ]]; do
                next_arg="${@:$((j+1)):1}"
                if [[ "${next_arg}" == --* ]]; then
                    break
                fi
                if [[ "${next_arg}" == *CMAKE_CXX_FLAGS* ]]; then
                    add_default_cxx_flags=false
                fi
                args+=("${next_arg}")
                j=$((j+1))
            done
            i=$((j))
            ;;
        --mixin=*)
            # Disallow --mixin=value syntax to prevent confusion.
            # --mixin=value1 is technically valid in colcon,
            # but --mixin=value1 value2 is NOT, while --mixin value1 value2 IS.
            # This wrapper disables --mixin=... entirely to avoid error-prone usage.
            echo "ERROR: Invalid syntax '${arg}'. Use '--mixin val1 val2' with mixins as separate arguments."
            exit 1
            ;;
        --mixin)
            args+=("${arg}")
            j=$((i+1))
            # Collect all mixin values following --mixin (until the next flag).
            # Also decide whether to skip default mixins based on user input.
            while [[ $j -lt $# ]]; do
                next_arg="${@:$((j+1)):1}"
                if [[ "${next_arg}" == --* ]]; then
                    break
                fi
                mixin_args+=("${next_arg}")
                args+=("${next_arg}")
                if [[ "${next_arg}" == "debug" || "${next_arg}" == "rel-with-deb-info" ]]; then
                    add_default_release_mixin=false
                elif [[ "${next_arg}" == "compile-commands" ]]; then
                    add_default_compile_commands=false
                fi
                j=$((j+1))
            done
            i=$((j))
            ;;
        --help|-h)
            show_help=true
            ;;
        *)
            args+=("${arg}")
            ;;
    esac

    i=$((i+1))
done

# Show modified help output.
if ${show_help}; then
    echo "The following configuration is set by default, unless the user explicitely set other:"
    echo "  --merge-install              Use --no-merge-install to disable"
    echo "  --symlink-install            Use --no-symlink-install to disable"
    echo "  --parallel-workers           ${default_parallel_workers}"
    echo "  --mixin release              Added unless debug or rel-with-deb-info is specified"
    echo "  --mixin compile-commands     Always used"
    echo "  -DCMAKE_CXX_FLAGS            ${default_cxx_flags}"
    echo

    colcon build --help \
    | sed -E 's/usage: colcon build/usage: '"$(basename "${BASH_SOURCE[0]}")"' /' \
    | sed -E 's/\[--merge-install\]/[--no-merge-install]/g' \
    | sed -E 's/\[--symlink-install\]/[--no-symlink-install]/g' \
    | sed -E 's/(.*)--merge-install[[:space:]]*Merge all.*$/\1--no-merge-install    Do not merge all install prefixes; keep them isolated per package/' \
    | sed -E 's/(.*)--symlink-install[[:space:]]*Use.*$/\1--no-symlink-install  Do not use symlinks; copy files during installation/' \
    | sed -E "s/(.*no limit[[:space:]]*)\(default:.*\)/\1(default: ${default_parallel_workers})/"
    exit 0
fi

# Add default flags unless explicitly disabled.
${add_merge_install} && args+=("--merge-install")
${add_symlink_install} && args+=("--symlink-install")
${add_default_parallel_workers} && args+=("--parallel-workers" "${default_parallel_workers}")
${add_default_release_mixin} && args+=("--mixin" "release")
${add_default_compile_commands} && args+=("--mixin" "compile-commands")
${add_default_cxx_flags} && args+=("--cmake-args" "-DCMAKE_CXX_FLAGS=${default_cxx_flags}")

# Trace command before execution.
echo "+ colcon build $(printf '%q ' "${args[@]}")"

# Execute.
colcon build "${args[@]}"