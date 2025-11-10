const snarkjs = require("snarkjs");
const path = require("path");

async function testValue(breathingRate) {
    console.log(`\n🧪 Testing breathingRate = ${breathingRate} bpm`);
    
    try {
        const { proof, publicSignals } = await snarkjs.groth16.fullProve(
            { breathingRate: breathingRate },
            path.join(__dirname, "../build/sample_breathing_js/sample_breathing.wasm"),
            path.join(__dirname, "../keys/sample_breathing.zkey")
        );
        
        console.log(`   isValid output: ${publicSignals[0]}`);
        if (publicSignals[0] === "1") {
            console.log("   ✅ VALID - Within range (10-30 bpm)");
        } else {
            console.log("   ❌ INVALID - Out of range");
        }
    } catch (error) {
        console.log("   ❌ Error generating proof:", error.message);
    }
}

async function main() {
    console.log("🚀 Testing Sample Breathing Circuit\n");
    console.log("=" .repeat(50));
    
    await testValue(5);   // 範囲外（低すぎる）
    await testValue(10);  // 境界値（最小）
    await testValue(15);  // 範囲内（中央）
    await testValue(30);  // 境界値（最大）
    await testValue(35);  // 範囲外（高すぎる）
    
    console.log("\n" + "=".repeat(50));
    console.log("\n💡 Note: The circuit outputs 1 for valid range (10-30 bpm)");
    console.log("         and 0 for out of range values.\n");
}

main().catch(console.error);
