#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_DIR="$SCRIPT_DIR/lageplaner"
DIST_DIR="$SCRIPT_DIR/dist"
ZIP_PATH="$DIST_DIR/lageplaner-qgis-plugin.zip"
TMP_DIR=$(mktemp -d)

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

mkdir -p "$DIST_DIR"
rm -f "$ZIP_PATH"
find "$PLUGIN_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$PLUGIN_DIR" -name '*.pyc' -delete
find "$SCRIPT_DIR" -name '.DS_Store' -delete

cp -R "$PLUGIN_DIR" "$TMP_DIR/lageplaner"
cp "$SCRIPT_DIR/LICENSE" "$TMP_DIR/lageplaner/LICENSE"

if [ -f "$SCRIPT_DIR/THIRD_PARTY_NOTICES.md" ]; then
  cp "$SCRIPT_DIR/THIRD_PARTY_NOTICES.md" "$TMP_DIR/lageplaner/THIRD_PARTY_NOTICES.md"
fi

if [ -f "$SCRIPT_DIR/README.md" ]; then
  cp "$SCRIPT_DIR/README.md" "$TMP_DIR/lageplaner/README.md"
fi

cd "$TMP_DIR"
zip -r "$ZIP_PATH" "lageplaner" -x '*/__pycache__/*' -x '*.pyc' -x '*.DS_Store' >/dev/null

echo "Created: $ZIP_PATH"
