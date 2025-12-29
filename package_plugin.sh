#!/bin/bash
# Package GEE Data Catalogs plugin for QGIS repository upload
#
# Usage:
#   ./package_plugin.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run the Python package script
python3 "$SCRIPT_DIR/package_plugin.py" "$@"
