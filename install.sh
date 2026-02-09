#!/bin/bash
# Install GEE Data Catalogs plugin for QGIS
#
# Usage:
#   ./install.sh          # Install the plugin
#   ./install.sh --remove # Remove the plugin
#

set -e
set -u
set -o pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PLUGIN_NAME="gee_data_catalogs"
readonly INSTALLER_PYTHON="$SCRIPT_DIR/install.py"

help_message() {
  echo "GEE Data Catalogs Plugin Installer for QGIS"
  echo
  echo "Usage: $0 [options]"
  echo
  echo "Options:"
  echo " [no args]    Install plugin"
  echo " --remove     Remove plugin"
  echo " -h, --help   Show this help message"
  echo
  echo "Example: $0 --remove # to remove"
  echo "         $0          # to install"
}

data_check() {
  echo "Check for python"
  if ! command -v python3 &> /dev/null; then
    echo "Python is not install or not in your PATH, install it to continue"
  fi
  echo "Python ready"
}

main() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    help_message
    exit 0
  fi

  echo "proceed to install $PLUGIN_NAME"
  data_check

  if [[ ! -f "$INSTALLER_PYTHON" ]]; then
    echo "Installer script not found at: $INSTALLER_PYTHON"
  fi

  python3 "$INSTALLER_PYTHON" "$@"
}

main "$@"
