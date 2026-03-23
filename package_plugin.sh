#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_DIR="$SCRIPT_DIR/lageplaner"
DIST_DIR="$SCRIPT_DIR/dist"
ZIP_PATH="$DIST_DIR/lageplaner-qgis-plugin.zip"

mkdir -p "$DIST_DIR"
rm -f "$ZIP_PATH"
find "$PLUGIN_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$PLUGIN_DIR" -name '*.pyc' -delete
find "$SCRIPT_DIR" -name '.DS_Store' -delete

cd "$SCRIPT_DIR"
zip -r "$ZIP_PATH" "lageplaner" -x '*/__pycache__/*' -x '*.pyc' -x '*.DS_Store' >/dev/null

echo "Created: $ZIP_PATH"
