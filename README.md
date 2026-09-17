# RC Bridge Analysis & ANN

Deterministic reinforced-concrete bridge-girder analysis/design with separate Eurocode and BS 5400 calculation paths, verified dataset generation, ANN surrogate modelling, reliability analysis and RBDO.

## Project goals
- Manual/deterministic structural analysis and RC design
- Eurocode and BS 5400 calculation paths kept separate
- Transparent calculation traces suitable for hand checking
- Dataset generation from verified deterministic solver outputs
- ANN train/validation/test workflow with auditable solver provenance
- Reliability and RBDO research modules
- Desktop-first architecture with future Windows packaging

## Current engineering foundation
Implemented so far:
- Typed bridge geometry, materials, deck construction and design-code models
- Physical rectangular, T and I girder profiles with self-weight support
- Separate 75 mm precast false slab and 175 mm in-situ slab construction model
- Uniform, point and moving axle-train load mechanics
- Simply supported reactions, shear/moment response and moving-load envelopes
- Code-neutral elastic T-section service-analysis mechanics
- Numerical simply-supported elastic deflection integration
- EN 1991-2 LM1 lane/tandem/UDL loading including remaining carriageway area
- Lane-specific transverse-distribution interfaces
- Verification-only equal transverse shares and direct grillage-result import
- EN 1990 ULS and configurable SLS combinations
- Eurocode T-girder flexure, shear, torsion, cracking, deflection, fatigue and detailing kernels
- Actual provided EC2 vertical-link shear resistance, using the lower of V_Rd,s and V_Rd,max
- BS 5400 / BD 37/01 HA loading plus Type HB moving-vehicle mechanics
- BS 5400 rectangular/T-section flexure, shear/link sizing, cracking, deflection, detailing and fatigue-scope mechanics
- Actual provided BS 5400 vertical-link shear resistance with minimum-link and web-resistance checks
- Code-specific consolidated project workflows for ULS and SLS verification
- Latin Hypercube Sampling utilities
- Code-profile-specific deterministic verification manifests
- Multi-limit ANN ground-truth records carrying g_M, g_V, g_crack and g_deflection
- Reproducible train/validation/test splitting with train-only standardization
- Optional TensorFlow/Keras four-output ANN surrogate trainer with early stopping and physical-unit metrics
- Pytest benchmark suite and GitHub Actions CI

## Initial verification bridge
The first benchmark is the 15 m RC girder research bridge:
- 15.0 m span
- 11.0 m overall deck width
- 7.0 m carriageway
- 7 girders at 1.70 m spacing
- 950 mm precast girder depth
- 75 mm precast false slab + 175 mm in-situ slab = 250 mm physical deck depth
- 175 mm default composite compression-flange contribution unless false-slab participation is explicitly justified
- C35/45 concrete and B500 reinforcement baseline for the Eurocode case

The reference project is stored in `examples/reference_bridge_15m.py`.

## Deterministic-to-ANN research pipeline

```text
Latin Hypercube / Monte Carlo samples
              ↓
Code-specific deterministic bridge solver
              ↓
Analysis + ULS + SLS checks
              ↓
Verified limit-state reserves
 g_M, g_V, g_crack, g_deflection
              ↓
MultiLimitTrainingRecord
              ↓
Profile-safe dataset matrix
(Eurocode fck or BS 5400 fcu, never silently converted)
              ↓
Deterministic train / validation / test split
              ↓
Standardization fitted on training data only
              ↓
Optional Keras dense surrogate
              ↓
RMSE / MAE / R² in physical engineering units
              ↓
Reliability analysis / RBDO
```

The ANN is a surrogate for verified deterministic calculations; it is not the source of the bridge-design rules.

## ANN verification lock
Training-data export requires a `DeterministicSolverVerification` for the exact solver profile being used. A single Boolean cannot unlock ANN data. The manifest currently requires explicit verification of traffic loading, load combinations, flexure, shear, cracking, deflection, fatigue, detailing, transverse distribution and an independent benchmark; torsion is also required when it is in scope.

Eurocode verification cannot certify a BS 5400 dataset and BS 5400 verification cannot certify a Eurocode dataset. Eurocode rows preserve `fck_mpa`; BS 5400 rows preserve `fcu_mpa` rather than applying an implicit strength conversion.

If design shear exceeds concrete-only resistance, ANN export also requires the **actual provided shear reinforcement** so `g_V` is based on a real resistance rather than the quantity of reinforcement merely required by the design equation.

## Installing research/ANN dependencies
The deterministic bridge solver remains lightweight. TensorFlow is an optional research dependency:

```bash
pip install -e '.[research]'
```

The core package and CI do not require TensorFlow just to perform deterministic bridge calculations.

## Engineering verification policy
No module should be treated as production-ready merely because it executes. Each code-specific equation, load model, partial factor, resistance model and serviceability check must be verified against the applicable standard, hand calculations and independent benchmark cases before its output is admitted as ANN ground-truth training data.

The current equal-share transverse-distribution route is explicitly **verification-only**. Production design and ANN ground truth require a validated analytical distribution method or verified grillage-derived effects/factors.

BS 5400 is retained as a legacy/comparison path and remains isolated from the Eurocode implementation.

## Remaining major work
1. Independently verify transverse load distribution and benchmark against grillage/established structural software.
2. Add edge-girder tributary permanent loading and validated edge-girder traffic effects.
3. Add continuous-span matrix/grillage analysis and negative-moment RC design.
4. Replace remaining equivalent-UDL service approximations with general curvature/load integration where required.
5. Complete construction-stage, shrinkage/creep and additional bridge actions.
6. Define justified random-variable distributions/bounds and generate the research dataset.
7. Train, validate and calibrate ANN surrogate models.
8. Add reliability analysis and RBDO.
9. Build calculation reports, desktop GUI and Windows installer.
