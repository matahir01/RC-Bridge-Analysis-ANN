# RC Bridge Analysis & ANN

Deterministic reinforced-concrete bridge girder analysis and design with Eurocode and BS 5400 modules, plus dataset generation, ANN surrogate modelling, reliability analysis and RBDO.

## Project goals
- Manual/deterministic structural analysis and RC design
- Eurocode and BS 5400 calculation paths kept separate
- Transparent calculation traces suitable for hand-checking
- Dataset generation using deterministic solver outputs
- ANN training/validation/test pipeline
- Reliability and RBDO research modules
- Desktop-first architecture with future Windows packaging

## Current foundation
Implemented so far:
- Typed bridge geometry, material and design-code models
- Rectangular, T and I section geometric-property calculations
- Uniform and point-load primitives
- Tributary deck self-weight calculation
- Simply supported reactions, shear and bending moment response
- Numerical sagging-moment envelope for arbitrary point loads
- Moving axle-train solver kept independent of traffic-code definitions
- Code-neutral load-effect objects
- Configurable Eurocode persistent ULS combination starting point
- Separate BS 5400 combination interface with explicit project factors
- Preliminary EC2-style singly reinforced rectangular flexural resistance calculation
- Flexure/shear/deflection limit-state scaffolding
- Latin Hypercube Sampling utility
- Deterministic ANN training-record schema
- Pytest benchmark suite and GitHub Actions CI

## Initial verification bridge
The first benchmark is the 15 m RC girder research bridge:
- 15.0 m span
- 11.0 m overall deck width
- 7 girders at 1.70 m spacing
- 950 mm precast girder depth
- 250 mm structural deck/false-slab contribution
- C35/45 concrete and B500 reinforcement baseline

The reference project is stored in `examples/reference_bridge_15m.py`.

## Engineering verification policy
No module should be treated as production-ready merely because it executes. Each code-specific equation, load model, partial factor, resistance model and serviceability check must be verified against the applicable standard, hand calculations and independent benchmark cases before its output is admitted as ANN ground-truth training data.

BS 5400 is retained as a legacy/comparison path and is intentionally isolated from the Eurocode implementation.

## Near-term roadmap
1. Complete deterministic simply-supported beam analysis including UDL + point-load combinations and deflection.
2. Implement EN 1991-2 road traffic load models and lane-placement logic.
3. Implement Eurocode 2 bridge flexure, shear, torsion, cracking, deflection and fatigue checks.
4. Implement BS 5400 loading/design path separately.
5. Add transverse load distribution and grillage-result import.
6. Generate verified LHS/Monte Carlo datasets.
7. Train and validate ANN surrogates for limit-state functions.
8. Add reliability analysis and RBDO.
9. Build the desktop GUI and Windows installer.
