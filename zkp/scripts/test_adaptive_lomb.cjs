// Use Mocha's API to also support Node versions affected by old yargs CLI
// resolution. This runs the new selector, integration, and legacy regression.
const path = require("path");
const Mocha = require("mocha");
const suite = new Mocha({ timeout: 3600000 });
for (const name of ["adaptive_lomb_input", "csi_motion_selector", "lomb_scargle_adaptive", "lomb_scargle_end_to_end"]) {
  suite.addFile(path.join(__dirname, "../test", `${name}.test.js`));
}
suite.run(failures => { process.exitCode = failures ? 1 : 0; });
