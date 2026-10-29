/* Export only actual circuit public outputs; host references are assertions only. */
const fs = require('fs');
const path = require('path');
const {performance} = require('perf_hooks');
const HERE = __dirname;
function flatten(value) {return Array.isArray(value) ? value.flat(Infinity) : [value];}
function indices(shape, prefix=[]) {
  if (!shape.length) return [prefix];
  return Array.from({length:shape[0]},(_,i)=>indices(shape.slice(1),[...prefix,i])).flat();
}
(async()=>{
 const schema=JSON.parse(fs.readFileSync(path.join(HERE,'public_schema.json')));
 const input=JSON.parse(fs.readFileSync(path.join(HERE,'input.json')));
 const reference=JSON.parse(fs.readFileSync(path.join(HERE,'reference_for_validation.json')));
 const name=schema.circuit, build=path.join(HERE,'build');
 const builder=require(path.join(build,`${name}_js/witness_calculator.js`));
 const calculator=await builder(fs.readFileSync(path.join(build,`${name}_js/${name}.wasm`)));
 const start=performance.now();
 const witness=await calculator.calculateWitness(input,true);
 const elapsed=(performance.now()-start)/1000;
 const symbols=new Map(fs.readFileSync(path.join(build,`${name}.sym`),'utf8').trim().split('\n').map(line=>{const a=line.split(',');return [a[3],Number(a[1])];}));
 const prime=BigInt(schema.field_modulus);
 let outputCount=0,referenceCount=0,internalCount=0;
 const eliminatedInternalSymbols=[];
 for(const group of schema.groups) {
   const expected=Object.hasOwn(reference,group.name)?flatten(reference[group.name]):null;
   const ix=indices(group.shape);
   for(let n=0;n<ix.length;n++) {
     const suffix=ix[n].map(i=>`[${i}]`).join('');
     const publicIndex=group.public_start_index_zero_based+n;
     const symbol=`main.${group.name}${suffix}`;
     if(symbols.get(symbol)!==publicIndex+1) throw Error(`Public order mismatch: ${symbol}`);
     const value=witness[publicIndex+1];
     if(expected) {
       if(value!==(BigInt(expected[n])%prime+prime)%prime) throw Error(`Independent reference mismatch: ${symbol}`);
       referenceCount++;
     }
     const internal=`main.${group.actual_internal_source}${suffix}`;
     const internalIndex=symbols.get(internal);
     if(internalIndex>=0) {
       if(value!==witness[internalIndex]) throw Error(`Actual internal signal mismatch: ${symbol} / ${internal}`);
       internalCount++;
     } else eliminatedInternalSymbols.push(internal);
     outputCount++;
   }
 }
 const signals=witness.slice(1,schema.public_signal_count+1).map(String);
 fs.writeFileSync(path.join(HERE,'public.json'),JSON.stringify(signals,null,2));
 // WTNS is generated from the same input for optional Groth16 proof later.
 fs.writeFileSync(path.join(build,'witness.wtns'),Buffer.from(await calculator.calculateWTNSBin(input,true)));
 fs.writeFileSync(path.join(HERE,'witness_validation.json'),JSON.stringify({status:'witness_generated_and_checked',
   public_schema_entries_checked:outputCount,independent_reference_values_checked:referenceCount,
   actual_internal_values_checked:internalCount,eliminated_internal_symbols:eliminatedInternalSymbols,
   witness_seconds:elapsed,public_signal_count:signals.length,
   proof_generated:false,proof_verified:false,
   note:'Circuit public outputs validated; Groth16 status is recorded separately in proof_validation.json.'},null,2));
 console.log(JSON.stringify({publicSignals:signals.length,referenceCount,internalCount,witness_seconds:elapsed}));
})().catch(error=>{console.error(error);process.exit(1);});
