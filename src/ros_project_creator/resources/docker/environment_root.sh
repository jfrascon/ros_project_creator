#!/bin/bash

# The script deduplicate_path.sh removes duplicates from path variables.
export PATH="$(deduplicate_path.sh "${HOME}/.local/bin:${PATH}")"
export CMAKE_PREFIX_PATH="$(deduplicate_path.sh "${CMAKE_PREFIX_PATH}")"
export LD_LIBRARY_PATH="$(deduplicate_path.sh "${LD_LIBRARY_PATH}")"
export PKG_CONFIG_PATH="$(deduplicate_path.sh "${PKG_CONFIG_PATH}")"
export PYTHONPATH="$(deduplicate_path.sh "${PYTHONPATH}")"