//! Native Groth16 adapter for Circom's R1CS/wtns files. Selection remains in Circom.
//! Setup uses a local CSPRNG ceremony, intended for testing only, not an MPC ceremony.
use anyhow::{bail, ensure, Context, Result};
use ark_bn254::{Bn254, Fr, G1Affine, G2Affine};
use ark_ff::{BigInteger, One, PrimeField, Zero};
use ark_groth16::{prepare_verifying_key, Groth16, ProvingKey};
use ark_relations::r1cs::{
    ConstraintSynthesizer, ConstraintSystemRef, LinearCombination, OptimizationGoal,
    SynthesisError, Variable,
};
use ark_serialize::{CanonicalDeserialize, CanonicalSerialize};
use rand::rngs::OsRng;
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    fs::File,
    io::{BufReader, BufWriter, Read, Seek, SeekFrom, Write},
    path::Path,
    time::Instant,
};

fn u32le(r: &mut impl Read) -> Result<usize> {
    let mut b = [0; 4];
    r.read_exact(&mut b)?;
    Ok(u32::from_le_bytes(b) as usize)
}
fn u64le(r: &mut impl Read) -> Result<u64> {
    let mut b = [0; 8];
    r.read_exact(&mut b)?;
    Ok(u64::from_le_bytes(b))
}
type Reader = BufReader<File>;
fn sections(
    path: &Path,
    magic: &[u8; 4],
    version: usize,
) -> Result<(Reader, HashMap<usize, (u64, u64)>)> {
    let mut r = BufReader::new(File::open(path)?);
    let length = r.get_ref().metadata()?.len();
    let mut found = [0; 4];
    r.read_exact(&mut found)?;
    ensure!(&found == magic, "Wrong binary format");
    ensure!(u32le(&mut r)? == version, "Unsupported binary version");
    let n = u32le(&mut r)?;
    ensure!(n <= 32, "Too many sections");
    let mut map = HashMap::new();
    for _ in 0..n {
        let kind = u32le(&mut r)?;
        let size = u64le(&mut r)?;
        let start = r.stream_position()?;
        ensure!(size <= length.saturating_sub(start), "Truncated section");
        ensure!(
            map.insert(kind, (start, size)).is_none(),
            "Duplicate section"
        );
        r.seek(SeekFrom::Start(start + size))?;
    }
    ensure!(r.stream_position()? == length, "Trailing binary data");
    Ok((r, map))
}
fn field_header(r: &mut Reader) -> Result<()> {
    ensure!(u32le(r)? == 32, "Expected 32-byte field");
    let mut p = [0; 32];
    r.read_exact(&mut p)?;
    ensure!(
        p.as_slice() == Fr::MODULUS.to_bytes_le(),
        "Expected BN254 scalar field"
    );
    Ok(())
}
fn scalar(r: &mut Reader) -> Result<Fr> {
    let mut b = [0; 32];
    r.read_exact(&mut b)?;
    let f = Fr::from_le_bytes_mod_order(&b);
    ensure!(f.into_bigint().to_bytes_le() == b, "Noncanonical scalar");
    Ok(f)
}
#[derive(Clone)]
struct Circuit {
    path: std::path::PathBuf,
    wires: usize,
    inputs: usize,
    constraints: usize,
    start: u64,
    length: u64,
    witness: Option<std::sync::Arc<Vec<Fr>>>,
}
impl Circuit {
    fn read(path: &Path) -> Result<Self> {
        let (mut r, s) = sections(path, b"r1cs", 1)?;
        let &(head, hlen) = s.get(&1).context("Missing R1CS header")?;
        ensure!(hlen == 64, "Invalid R1CS header length");
        r.seek(SeekFrom::Start(head))?;
        field_header(&mut r)?;
        let wires = u32le(&mut r)?;
        let outputs = u32le(&mut r)?;
        let public = u32le(&mut r)?;
        let private = u32le(&mut r)?;
        let _labels = u64le(&mut r)?;
        let constraints = u32le(&mut r)?;
        let inputs = 1 + outputs + public;
        ensure!(
            inputs <= wires && inputs + private <= wires,
            "Invalid wire counts"
        );
        let &(start, length) = s.get(&2).context("Missing constraints")?;
        Ok(Self {
            path: path.into(),
            wires,
            inputs,
            constraints,
            start,
            length,
            witness: None,
        })
    }
    fn load_witness(&mut self, path: &Path) -> Result<()> {
        let (mut r, s) = sections(path, b"wtns", 2)?;
        let &(start, len) = s.get(&1).context("Missing witness header")?;
        ensure!(len == 40, "Invalid witness header");
        r.seek(SeekFrom::Start(start))?;
        field_header(&mut r)?;
        ensure!(u32le(&mut r)? == self.wires, "Witness wire count mismatch");
        let &(start, len) = s.get(&2).context("Missing witness values")?;
        ensure!(len == self.wires as u64 * 32, "Invalid witness length");
        r.seek(SeekFrom::Start(start))?;
        let mut values = Vec::with_capacity(self.wires);
        for _ in 0..self.wires {
            values.push(scalar(&mut r)?);
        }
        ensure!(values[0] == Fr::one(), "Invalid constant wire");
        self.witness = Some(std::sync::Arc::new(values));
        Ok(())
    }
    fn lc(&self, r: &mut Reader) -> Result<LinearCombination<Fr>> {
        let n = u32le(r)?;
        ensure!(n <= self.wires, "Invalid term count");
        let mut terms = Vec::with_capacity(n);
        for _ in 0..n {
            let i = u32le(r)?;
            ensure!(i < self.wires, "Invalid wire index");
            let coefficient = scalar(r)?;
            let variable = if i == 0 {
                Variable::One
            } else if i < self.inputs {
                Variable::Instance(i)
            } else {
                Variable::Witness(i - self.inputs)
            };
            terms.push((coefficient, variable));
        }
        Ok(LinearCombination(terms))
    }
    fn synthesize(&self, cs: ConstraintSystemRef<Fr>) -> Result<()> {
        cs.set_optimization_goal(OptimizationGoal::None);
        for i in 1..self.wires {
            let f = || {
                self.witness
                    .as_ref()
                    .map(|w| w[i])
                    .ok_or(SynthesisError::AssignmentMissing)
            };
            if i < self.inputs {
                cs.new_input_variable(f)?;
            } else {
                cs.new_witness_variable(f)?;
            }
        }
        let mut r = BufReader::new(File::open(&self.path)?);
        r.seek(SeekFrom::Start(self.start))?;
        for i in 0..self.constraints {
            let a = self.lc(&mut r)?;
            let b = self.lc(&mut r)?;
            let c = self.lc(&mut r)?;
            if let Some(w) = &self.witness {
                let eval = |lc: &LinearCombination<Fr>| {
                    lc.0.iter().fold(Fr::zero(), |sum, (coef, var)| {
                        let index = match var {
                            Variable::One => 0,
                            Variable::Instance(j) => *j,
                            Variable::Witness(j) => self.inputs + j,
                            _ => unreachable!(),
                        };
                        sum + *coef * w[index]
                    })
                };
                ensure!(
                    eval(&a) * eval(&b) == eval(&c),
                    "Unsatisfied R1CS constraint {i}"
                );
            }
            cs.enforce_constraint(a, b, c)?;
            if i % 1_000_000 == 0 {
                eprintln!("constraints {i}/{}", self.constraints);
            }
        }
        ensure!(
            r.stream_position()? == self.start + self.length,
            "Constraint section length mismatch"
        );
        Ok(())
    }
}
impl ConstraintSynthesizer<Fr> for Circuit {
    fn generate_constraints(
        self,
        cs: ConstraintSystemRef<Fr>,
    ) -> std::result::Result<(), SynthesisError> {
        self.synthesize(cs).map_err(|e| {
            eprintln!("{e:#}");
            SynthesisError::Unsatisfiable
        })
    }
}
fn g1(p: &G1Affine) -> Value {
    json!([
        p.x.to_string(),
        p.y.to_string(),
        if p.infinity { "0" } else { "1" }
    ])
}
fn g2(p: &G2Affine) -> Value {
    json!([
        [p.x.c0.to_string(), p.x.c1.to_string()],
        [p.y.c0.to_string(), p.y.c1.to_string()],
        [if p.infinity { "0" } else { "1" }, "0"]
    ])
}
fn main() -> Result<()> {
    let a: Vec<String> = std::env::args().collect();
    ensure!(a.len()==5 || a.len()==6,"Usage: csi-native-prover setup circuit.r1cs key.ark verification_key.json | prove circuit.r1cs key.ark witness.wtns bundle.json");
    let start = Instant::now();
    let mut circuit = Circuit::read(Path::new(&a[2]))?;
    eprintln!(
        "{} wires, {} public, {} constraints",
        circuit.wires,
        circuit.inputs - 1,
        circuit.constraints
    );
    if a[1] == "setup" && a.len() == 5 {
        let pk = Groth16::<Bn254>::generate_random_parameters_with_reduction(circuit, &mut OsRng)?;
        let mut out = BufWriter::new(File::create(&a[3])?);
        pk.serialize_uncompressed(&mut out)?;
        out.flush()?;
        let vk = &pk.vk;
        let value = json!({"protocol":"groth16","curve":"bn128","nPublic":vk.gamma_abc_g1.len()-1,
            "vk_alpha_1":g1(&vk.alpha_g1),"vk_beta_2":g2(&vk.beta_g2),"vk_gamma_2":g2(&vk.gamma_g2),"vk_delta_2":g2(&vk.delta_g2),"IC":vk.gamma_abc_g1.iter().map(g1).collect::<Vec<_>>()});
        std::fs::write(&a[4], serde_json::to_vec_pretty(&value)?)?;
    } else if a[1] == "prove" && a.len() == 6 {
        circuit.load_witness(Path::new(&a[4]))?;
        let signals = circuit.witness.as_ref().unwrap()[1..circuit.inputs].to_vec();
        // Only a SHA256-pinned, locally generated key may reach this entrypoint.
        // Uncompressed avoids millions of decompressions; group membership is checked.
        let mut reader = BufReader::new(File::open(&a[3])?);
        let pk = ProvingKey::<Bn254>::deserialize_uncompressed(&mut reader)?;
        ensure!(
            pk.vk.gamma_abc_g1.len() == circuit.inputs && pk.a_query.len() == circuit.wires,
            "Key dimensions mismatch"
        );
        let proof = Groth16::<Bn254>::create_random_proof_with_reduction(circuit, &pk, &mut OsRng)?;
        ensure!(
            Groth16::<Bn254>::verify_proof(&prepare_verifying_key(&pk.vk), &proof, &signals)?,
            "Native verification failed"
        );
        let value = json!({"proof":{"protocol":"groth16","curve":"bn128","pi_a":g1(&proof.a),"pi_b":g2(&proof.b),"pi_c":g1(&proof.c)},"publicSignals":signals.iter().map(ToString::to_string).collect::<Vec<_>>()});
        std::fs::write(&a[5], serde_json::to_vec_pretty(&value)?)?;
    } else {
        bail!("Invalid arguments");
    }
    eprintln!("completed in {:.3}s", start.elapsed().as_secs_f64());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use ark_relations::r1cs::ConstraintSystem;

    fn fixture() -> (std::path::PathBuf, Circuit) {
        let dir = std::env::temp_dir().join(format!(
            "csi-native-test-{}-{}",
            std::process::id(),
            rand::random::<u64>()
        ));
        std::fs::create_dir(&dir).unwrap();
        let path = dir.join("square.r1cs");
        let mut header = Vec::new();
        header.extend(32u32.to_le_bytes());
        header.extend(Fr::MODULUS.to_bytes_le());
        for n in [3u32, 1, 0, 1] {
            header.extend(n.to_le_bytes());
        }
        header.extend(3u64.to_le_bytes());
        header.extend(1u32.to_le_bytes());
        let mut constraints = Vec::new();
        for wire in [2u32, 2, 1] {
            constraints.extend(1u32.to_le_bytes());
            constraints.extend(wire.to_le_bytes());
            constraints.extend(Fr::one().into_bigint().to_bytes_le());
        }
        let mut bytes = b"r1cs".to_vec();
        bytes.extend(1u32.to_le_bytes());
        bytes.extend(2u32.to_le_bytes());
        for (kind, section) in [(1u32, header), (2, constraints)] {
            bytes.extend(kind.to_le_bytes());
            bytes.extend((section.len() as u64).to_le_bytes());
            bytes.extend(section);
        }
        std::fs::write(&path, bytes).unwrap();
        let circuit = Circuit::read(&path).unwrap();
        (dir, circuit)
    }
    #[test]
    fn enforces_original_r1cs_and_rejects_wrong_witness() {
        let (dir, mut circuit) = fixture();
        circuit.witness = Some(std::sync::Arc::new(vec![
            Fr::one(),
            Fr::from(9u64),
            Fr::from(3u64),
        ]));
        let cs = ConstraintSystem::new_ref();
        circuit.synthesize(cs.clone()).unwrap();
        assert!(cs.is_satisfied().unwrap());
        let pk = Groth16::<Bn254>::generate_random_parameters_with_reduction(
            circuit.clone(),
            &mut OsRng,
        )
        .unwrap();
        let proof =
            Groth16::<Bn254>::create_random_proof_with_reduction(circuit.clone(), &pk, &mut OsRng)
                .unwrap();
        assert!(Groth16::<Bn254>::verify_proof(
            &prepare_verifying_key(&pk.vk),
            &proof,
            &[Fr::from(9u64)]
        )
        .unwrap());
        assert!(!Groth16::<Bn254>::verify_proof(
            &prepare_verifying_key(&pk.vk),
            &proof,
            &[Fr::from(8u64)]
        )
        .unwrap());
        circuit.witness = Some(std::sync::Arc::new(vec![
            Fr::one(),
            Fr::from(8u64),
            Fr::from(3u64),
        ]));
        assert!(circuit.synthesize(ConstraintSystem::new_ref()).is_err());
        std::fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn rejects_truncation_and_noncanonical_scalars() {
        let (dir, circuit) = fixture();
        let mut bytes = std::fs::read(&circuit.path).unwrap();
        bytes.pop();
        std::fs::write(&circuit.path, bytes).unwrap();
        assert!(Circuit::read(&circuit.path).is_err());
        let path = dir.join("scalar");
        std::fs::write(&path, Fr::MODULUS.to_bytes_le()).unwrap();
        assert!(scalar(&mut BufReader::new(File::open(path).unwrap())).is_err());
        std::fs::remove_dir_all(dir).unwrap();
    }
}
