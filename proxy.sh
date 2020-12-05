#!/bin/bash

# This script might be useful if you want to invoke the python script from
# outside the project directory.

PROJECT_DIR="${PWD}"
cd "$1"

shift
python "${PROJECT_DIR}/hitomila.py" "$@"