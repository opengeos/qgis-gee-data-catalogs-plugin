#!/bin/bash
# Install GEE Data Catalogs plugin for QGIS
#
# Usage:
#   ./install.sh          # Install the plugin
#   ./install.sh --remove # Remove the plugin

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_NAME="gee_data_catalogs"

# Run the Python install script
python3 "$SCRIPT_DIR/install.py" "$@"
