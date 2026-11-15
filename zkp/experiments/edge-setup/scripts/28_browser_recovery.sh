set -euxo pipefail
# Step 27 downloaded the complete ZIP but its extraction stopped making progress.
# Before stopping only that installer, the archive was preserved under artifacts.
RENDER_ROOT="$PWD/zkp/experiments/edge-setup/artifacts/report-renderer"
ARCHIVE="$RENDER_ROOT/chromium-headless-shell-mac15-1194.zip"
DEST="$RENDER_ROOT/browsers/manual-chromium-1194"
test -f "$ARCHIVE"
test ! -e "$DEST"
shasum -a 256 "$ARCHIVE"
unzip -t "$ARCHIVE"
mkdir -p "$DEST"
unzip -q "$ARCHIVE" -d "$DEST"
"$DEST/chrome-mac/headless_shell" --version
node "$RENDER_ROOT/node_modules/playwright/cli.js" --version
