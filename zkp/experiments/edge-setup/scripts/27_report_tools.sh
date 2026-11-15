set -euxo pipefail
# This step runs on the operator Mac, not on the edge PC.
npm install --prefix zkp/experiments/edge-setup/artifacts/report-renderer --no-audit --no-fund playwright@1.56.1
export PLAYWRIGHT_BROWSERS_PATH="$PWD/zkp/experiments/edge-setup/artifacts/report-renderer/browsers"
node zkp/experiments/edge-setup/artifacts/report-renderer/node_modules/playwright/cli.js install chromium --only-shell
node zkp/experiments/edge-setup/artifacts/report-renderer/node_modules/playwright/cli.js --version
