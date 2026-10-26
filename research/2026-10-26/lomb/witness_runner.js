// Actual circuit WASM, with Circom sanity assertions enabled.
const fs=require('fs');
const {performance}=require('perf_hooks');
(async()=>{
  const [wasm,calculator,inputPath,outputPath]=process.argv.slice(2);
  const start=performance.now();
  const calc=await require(calculator)(fs.readFileSync(wasm));
  const input=JSON.parse(fs.readFileSync(inputPath,'utf8'));
  const before=performance.now();
  const wtns=Buffer.from(await calc.calculateWTNSBin(input,true));
  const finish=performance.now();
  let p=12,fieldBytes,values;
  for(let n=0;n<wtns.readUInt32LE(8);n++){
    const kind=wtns.readUInt32LE(p),length=Number(wtns.readBigUInt64LE(p+4));p+=12;
    if(kind===1)fieldBytes=wtns.readUInt32LE(p);
    if(kind===2){
      values=[];
      for(let i=0;i<6;i++){
        let value=0n;for(let j=fieldBytes-1;j>=0;j--)value=(value<<8n)+BigInt(wtns[p+i*fieldBytes+j]);
        values.push(value.toString());
      }
    }
    p+=length;
  }
  if(outputPath!=='-')fs.writeFileSync(outputPath,wtns);
  console.log(JSON.stringify({csiCommitment:values[1],isNormal:Number(values[2]),selectedSubcarrier:Number(values[3]),estimatedFrequencyBin:Number(values[4]),globalPeakFrequencyBin:Number(values[5]),witness_seconds:(finish-before)/1000,wasm_load_seconds:(before-start)/1000,max_rss_kib:process.resourceUsage().maxRSS}));
})().catch(e=>{console.error(e);process.exit(1)});
