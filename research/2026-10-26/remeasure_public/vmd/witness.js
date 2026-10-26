// One witness calculation per measured run; public extraction reads that same WTNS.
const fs=require('fs'),path=require('path');
(async()=>{
 const [configDir,runDir]=process.argv.slice(2).map(p=>path.resolve(p));
 const schema=JSON.parse(fs.readFileSync(path.join(configDir,'schema.json'))),name=schema.circuit.replace('.circom','');
 const builder=require(path.join(configDir,'build',`${name}_js/witness_calculator.js`));
 const calculator=await builder(fs.readFileSync(path.join(configDir,'build',`${name}_js/${name}.wasm`)));
 const input=JSON.parse(fs.readFileSync(path.join(runDir,'input.json')));
 const t=performance.now();const bytes=Buffer.from(await calculator.calculateWTNSBin(input,true));const seconds=(performance.now()-t)/1000;
 fs.writeFileSync(path.join(runDir,'witness.wtns'),bytes);
 let pos=12,section2=-1;
 for(let s=0;s<bytes.readUInt32LE(8);s++) {
   const type=bytes.readUInt32LE(pos),size=Number(bytes.readBigUInt64LE(pos+4));pos+=12;
   if(type===2)section2=pos;pos+=size;
 }
 if(section2<0)throw Error('Missing WTNS values');
 const read=i=>{let v=0n;for(let j=7;j>=0;j--)v=(v<<32n)+BigInt(bytes.readUInt32LE(section2+i*32+j*4));return v.toString();};
 const symbols=new Map(fs.readFileSync(path.join(configDir,'build',`${name}.sym`),'utf8').trim().split('\n').map(line=>{const p=line.split(',');return [p[3],Number(p[1])];}));
 function ix(shape,prefix=[]){if(!shape.length)return[prefix];return Array.from({length:shape[0]},(_,i)=>ix(shape.slice(1),[...prefix,i])).flat();}
 for(const g of schema.groups)for(const [j,index] of ix(g.shape).entries()) {
   const symbol=`main.${g.name}${index.map(i=>`[${i}]`).join('')}`;
   if(symbols.get(symbol)!==g.public_start_index_zero_based+j+1)throw Error(`Public schema mismatch: ${symbol}`);
 }
 const pub=Array.from({length:schema.public_signal_count},(_,i)=>read(i+1));
 fs.writeFileSync(path.join(runDir,'witness_public.json'),JSON.stringify(pub));
 fs.writeFileSync(path.join(runDir,'witness_timing.json'),JSON.stringify({calculation_seconds:seconds,public_schema_checked:true,public_count:pub.length},null,2));
})().catch(e=>{console.error(e);process.exit(1)});
