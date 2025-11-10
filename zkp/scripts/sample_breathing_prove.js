const snarkjs = require("snarkjs");
const fs = require("fs");
const path = require("path");

async function main() {
    console.log("🚀 Sample Breathing Proof Generation\n");

    const breathingRate = 15;
    const input = { breathingRate: breathingRate };

    const zKeyPath = path.join(__dirname, "../keys/sample_breathing.zkey");

    console.log("🔐 Generating proof...");

    // 証明生成
    const { proof, publicSignals } = await snarkjs.groth16.fullProve(
        input,
        path.join(__dirname, "../build/sample_breathing_js/sample_breathing.wasm"),
        zKeyPath
    );

    console.log("✅ Proof generated!\n");

    // 結果を保存
    fs.writeFileSync(
        path.join(__dirname, "../build/sample_breathing_proof.json"),
        JSON.stringify(proof, null, 2)
    );
    fs.writeFileSync(
        path.join(__dirname, "../build/sample_breathing_public.json"),
        JSON.stringify(publicSignals, null, 2)
    );

    console.log("📋 Public Signals:");
    console.log(`   isValid (output): ${publicSignals[0]}`);
    console.log(`   ${publicSignals[0] === "1" ? "✅ VALID - Within range!" : "❌ INVALID - Out of range!"}\n`);

    console.log("📄 Proof saved to: build/sample_breathing_proof.json");
    console.log("📄 Public signals saved to: build/sample_breathing_public.json\n");

    const calldata = await snarkjs.groth16.exportSolidityCallData(
        proof,
        publicSignals
    );

    fs.writeFileSync(
        path.join(__dirname, "../build/sample_breathing_calldata.txt"),
        calldata
    );

    console.log("📄 Solidity calldata saved to: build/sample_breathing_calldata.txt");
}

main()
.then(() => {
    process.exit(0);
})
.catch((err) => {
    console.error(err);
    process.exit(1);
});