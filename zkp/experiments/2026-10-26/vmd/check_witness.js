const fs = require('fs');
const path = require('path');
(async () => {
 const [dir, name, inputPath, referencePath] = process.argv.slice(2);
 const ref = JSON.parse(fs.readFileSync(referencePath));
 const input = JSON.parse(fs.readFileSync(inputPath));
 const builder = require(path.resolve(dir, `${name}_js/witness_calculator.js`));
 const calc = await builder(fs.readFileSync(path.join(dir, `${name}_js/${name}.wasm`)));
 const times=[];let witness;
 for(let i=0;i<3;i++) {const t=performance.now();witness=await calc.calculateWitness(input, true);times.push((performance.now()-t)/1000);}
 const symbols = new Map(fs.readFileSync(path.join(dir, `${name}.sym`),'utf8').trim().split('\n').map(line=>{const a=line.split(',');return [a[3],Number(a[1])];}));
 const P=21888242871839275222246405745257275088548364400416034343698204186575808495617n;
 const read = name=>witness[symbols.get(`main.${name}`)];
 const assert = (name,value)=> {if(read(name)!==(BigInt(value)%P+P)%P)throw new Error(`${name} mismatch ${read(name)} != ${value}`);};
 assert('estimatedFrequencyBin',ref.peak_bin);assert('selectedMode0based',ref.selected_mode);assert('isNormal',Number(ref.is_normal));
 for(let k=0;k<ref.centers.length;k++) {assert(`center[${ref.iterations}][${k}]`,ref.centers[k]);for(let j=0;j<63;j++){assert(`ur[${ref.iterations-1}][${k}][${j}]`,ref.spectra[k][j][0]);assert(`ui[${ref.iterations-1}][${k}][${j}]`,ref.spectra[k][j][1]);}}
 console.log(JSON.stringify({name,input:inputPath,peak_bin:ref.peak_bin,bpm:ref.bpm,all_final_spectra_and_centers_match:true,witness_seconds:times,public_signals:witness.slice(1,6).map(String)}));
})();
