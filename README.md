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
- Independently editable deck width, girder count and girder spacing with linked geometry guidance
- Physical rectangular, T and I girder profiles with automatic precast-girder self-weight when a complete profile is defined
- Automatic gross composite longitudinal `A`, `J`, `Iy` and `Iz` derivation for physical rectangular, T and I girder profiles, including participating deck concrete
- Automatic physical transverse deck-strip properties for native/verification grillages, with explicit expert overrides retained and stiffness assumptions recorded in model metadata
- Edge-aware deck tributary widths and permanent-load protection against conflicting/double-counted explicit girder self-weight
- Physical-position-aware surfacing layers and barrier/service/other line actions, with conservative girder allocation and category-level double-count protection
- Separate 75 mm precast false slab and 175 mm in-situ slab construction model
- Uniform, point and moving axle-train load mechanics
- Simply supported reactions, shear/moment response and moving-load envelopes
- Multi-span continuous Euler-Bernoulli stiffness analysis with explicit span EI
- Continuous-beam reactions, rotations, moment/shear envelopes and influence lines
- Continuous moving axle-train moment, shear, reaction and vertical-deflection envelopes
- Code-neutral elastic T-section service-analysis mechanics
- Numerical simply-supported and continuous-span elastic deflection recovery
- Simple-span UDL-plus-axle load-pattern deflection with virtual-work curvature integration, span-wise maximum search and EC2 cracked/uncracked interpolation
- EN 1991-2 LM1 lane/tandem/UDL loading including remaining carriageway area
- Continuous LM1 tandem placement and adverse influence-region UDL effects
- Lane-specific transverse-distribution interfaces
- Verification-only equal transverse shares and direct grillage-result import
- EN 1990 ULS and configurable SLS combinations, including signed continuous-section branches
- Continuous Eurocode project envelopes for sagging, hogging and shear
- Continuous support hogging design with web/stem or actual I-girder bottom-flange compression
- Explicit critical shear-section workflows that do not assume support centreline equals the design section
- Layered continuous-support crack analysis with active/inactive construction layers
- Continuous deterministic and moving-train deflection serviceability checks with explicit limits
- Eurocode T-girder flexure, shear, torsion, cracking, deflection, fatigue and detailing kernels
- Practical EC2 discrete longitudinal-bar and vertical-link selection, straight-bar anchorage/lap calculations, explicit durability-cover checks and congestion-aware web fit checks
- Actual provided EC2 vertical-link shear resistance, using the lower of V_Rd,s and V_Rd,max
- BS 5400 / BD 37/01 HA loading plus Type HB moving-vehicle mechanics
- BS 5400 rectangular/T-section flexure, shear/link sizing, cracking, deflection, detailing and fatigue-scope mechanics
- Actual provided BS 5400 vertical-link shear resistance with minimum-link and web-resistance checks
- Code-specific consolidated project workflows for ULS and SLS verification
- MIDAS Civil `.mct` and STAAD.Pro `.std` longitudinal verification-model export
- Dynamic full-width grillage verification export driven by editable girder count, spacing and deck width
- Grillage deck-edge cantilevers, exact wheel stations and generic rectangular pressure-patch loading
- EN 1991-2 LM1 full-grillage snapshot generation with explicit lane, remaining-area and tandem placement
- Native vertical-grillage solver with automated LM1 transverse layouts, independent tandem positions and span-wise UDL search
- Independent per-girder native LM1 M/V/T envelopes with exact governing-case traceability
- Governing native LM1 case export to identical MIDAS Civil and STAAD.Pro benchmark models
- MIDAS/STAAD governing-case result adapters, aggregate completeness checks and engineering benchmark reports
- Benchmark-gated simple-span Eurocode T-girder production path using native per-girder LM1 effects rather than equal-share traffic
- Edge-aware permanent deck tributary widths for exterior as well as internal girders
- Matched co-located native LM1 shear-torsion interaction checks that do not combine unrelated V/T maxima
- Supplemental LM1 benchmark-case packaging when the governing V-T interaction case does not govern M, V or T individually
- Exact longitudinal member-end V/M/T magnitude comparisons for externally returned benchmark results, including local evidence gates for governing torsion and V-T interaction points
- Explicit provided EC2 shear-link resistance and detailing-adequacy checks in the girder workflow, with supplied A_sw/s carried into Eurocode ANN shear-resistance records
- Exact static moving-vehicle snapshot export at an internal governing axle position
- Longitudinal verification bundles with model files, manifest hashes and internal expected-results CSV
- Full-grillage model-only bundles with exact exported-load audit, requested-result map and normalized return template
- Direct STAAD `.ANL` parsing for reactions, displacements and GLOBAL member-end forces
- MIDAS global reaction/displacement table normalization and orientation-gated horizontal-grillage member-force mapping
- Normalized external-results completeness/comparison with explicit absolute/relative tolerances
- Independent verification campaigns requiring numerical agreement plus geometry, boundary, load and result-axis equivalence review
- Four controlled two-span line benchmark cases generated in one call for MIDAS/STAAD checking
- First-stage line round-trip comparison using globally unambiguous `FZ`, `DZ` and `RY` quantities
- Independent benchmark and imported-grillage comparison frameworks that do not self-certify the solver
- Latin Hypercube Sampling utilities
- Code-profile-specific deterministic verification manifests
- Separate locked Eurocode continuous-span verification profile
- Multi-limit ANN ground-truth records carrying g_M, g_V, g_crack and g_deflection for verified fixed-profile workflows
- Reproducible train/validation/test splitting with train-only standardization
- Optional TensorFlow/Keras four-output ANN surrogate trainer with early stopping and physical-unit metrics
- Pytest benchmark suite and GitHub Actions CI

## Initial verification bridge
The first project benchmark is the 15 m RC girder research bridge:
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

## Development sequence

The project is intentionally being completed in four stages:

1. **Finish the deterministic engineering engine.** Complete physical section/grillage properties, permanent actions, native traffic analysis, ULS/SLS design, load-pattern deflection, fatigue and practical detailing.
2. **Finish the usable application.** Provide project creation/saving, calculation reports, desktop-oriented workflows and application-driven MIDAS `.mct` / STAAD `.std` export from the exact model analysed by the program.
3. **Perform final independent structural validation.** Use the substantially complete application to generate the governing verification models, run those files in installed MIDAS Civil/STAAD.Pro, import the genuine results, confirm result axes/sign conventions and accept justified tolerances.
4. **Unlock research generation only after verification.** Complete the solver verification manifest before generating ANN ground truth, reliability datasets or RBDO results.

The external MIDAS/STAAD comparison is therefore a **final acceptance gate for the completed deterministic program**, not the next development task. Internal CI fixtures and native round trips remain software verification only and must never be presented as independent structural validation.

## ANN verification lock
Training-data export requires a `DeterministicSolverVerification` for the exact solver profile being used. A single Boolean cannot unlock ANN data. The manifest currently requires explicit verification of traffic loading, load combinations, flexure, shear, cracking, deflection, fatigue, detailing, transverse distribution and an independent benchmark; torsion is also required when it is in scope.

The simple-span Eurocode, continuous-span Eurocode and BS 5400 solver profiles are distinct. Verification of one profile cannot certify records generated by another. The continuous Eurocode profile remains locked until its complete deterministic verification programme, including an independent benchmark, is complete.

Eurocode rows preserve `fck_mpa`; BS 5400 rows preserve `fcu_mpa` rather than applying an implicit strength conversion.

If design shear exceeds concrete-only resistance, ANN export also requires the **actual provided shear reinforcement** so `g_V` is based on a real resistance rather than the quantity of reinforcement merely required by the design equation.

## Continuous-span verification boundary
The current continuous longitudinal solver has automated mechanics benchmarks for classical beam reactions/moments, influence-line response, support continuity, closed-form simply-supported deflection recovery and moving-load symmetry. These tests demonstrate internal numerical consistency but do **not** replace independent MIDAS/STAAD/grillage evidence.

A formal external verification campaign now sits above the numerical comparison layer. A benchmark case can count as independent evidence only when its requested numerical results pass the supplied tolerances **and** geometry, boundary conditions, loading and result-axis equivalence have been explicitly reviewed. A passing comparison cannot automatically mark unrelated solver-verification milestones complete.

Continuous service deflection keeps span EI explicit. The solver does not silently choose gross, cracked, composite, creep-adjusted or construction-stage stiffness. Likewise, moving-train deflection is code-neutral until a specific traffic/service combination and validated transverse-distribution treatment are supplied upstream.

The current project-level continuous traffic workflow uses supplied validated/imported transverse lane distributions. It does not treat equal-share distribution as production ground truth, and it does not assume that moment distribution factors are automatically valid for deflection.

## MIDAS Civil / STAAD.Pro verification workflow
The exporter is designed to remove manual recreation of benchmark models.

### Controlled longitudinal benchmark suite
A two-span project can generate four synthetic, code-neutral solver-isolation cases:

```text
continuous-2span-equal-udl
continuous-2span-asymmetric-udl
continuous-2span-point-load
continuous-2span-mixed-load
```

Each case produces:

```text
<case>.mct
<case>.std
<case>_manifest.json
<case>_expected_results.csv
<case>_external_expected_results.csv
```

The rich expected-results file preserves the internal solver trace. The first-stage external expected file deliberately uses only global quantities with already-explicit conventions: support `FZ`, node `DZ`, and node `RY`. Member-end `V/M/T` is intentionally excluded from the first acceptance gate until its end-force sign convention is calibrated against a real external-software run.

The external line model carries support-line geometry, beam connectivity, stabilized boundary conditions, explicit material stiffness, section properties derived to reproduce the caller-supplied span EI, UDLs and point/axle loads at the same locations used internally. A moving axle train can also be frozen at an exact lead-axle position so structural response is compared without mixing differences in moving-load search algorithms.

STAAD `.ANL` output can be parsed directly. The parser reads reported units, reactions and displacements and accepts member forces only when STAAD explicitly reports them in GLOBAL axes. MIDAS global reaction/displacement tables can be normalized directly. For horizontal beta-zero grillage members, MIDAS ECS `Shear-z`, `Moment-y` and `Torsion` have an orientation-gated mapping to semantic vertical shear, vertical-plane bending and torsion.

### Full bridge/grillage verification export
The full verification-grillage generator is dynamic: girder count, spacing, deck width, carriageway position and transverse load stations are project-driven rather than hard-coded to seven girders. Deck-edge cantilever strips are retained, wheel coordinates become exact grid stations, and rectangular lane/area pressures are converted to equilibrium-preserving grillage nodal loads.

An LM1 grillage snapshot can generate:

```text
<case>.mct
<case>.std
<case>_manifest.json
<case>_exported_loads.csv
<case>_result_requests.csv
<case>_external_results_template.csv
```

The model-only snapshot bundle still does not fabricate internal result files. In parallel, the project now contains a native vertical-grillage solver and an automated LM1 placement/envelope search. That native route identifies the governing per-girder M/V/T cases, packages the exact governing models for MIDAS/STAAD, and can add a supplemental benchmark case when the critical co-located V-T interaction comes from a different traffic placement.

The comparison layer can now check both per-girder envelope magnitudes and exact longitudinal member-end V/M/T magnitudes. The native torsion/V-T production check requires passing external evidence at the actual governing case/member/end, not merely an overall girder-envelope match.

The export/import/benchmark workflow and production-lock logic are covered by synthetic CI fixtures, but those fixtures are software tests—not independent structural validation. Genuine numerical agreement from installed MIDAS Civil/STAAD.Pro remains a final acceptance requirement. That external run is intentionally deferred until the deterministic application is substantially complete, so the verification files are generated by the same software/model path intended for actual use.

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
1. **Refine physical analysis properties.** Gross longitudinal composite and representative transverse deck-strip properties are now derived automatically from physical geometry, with explicit expert overrides retained. Complete station-specific transverse strip widths, edge-girder longitudinal slab widths and any validated cracked/creep/construction-stage stiffness selections required by production analysis.
2. **Complete simple-span service deflection integration.** The load-pattern/curvature engine now handles actual full-span UDL plus arbitrary axle patterns and searches the span maximum. Replace the compatibility equivalent-UDL adapter by tracing the governing co-located native traffic service pattern into this engine.
3. **Extend permanent-action modelling to staged/nonuniform longitudinal actions.** Girder and deck self-weight, transverse surfacing bands and positioned barrier/service/other line actions are automated with category-level double-count protection. Add longitudinally varying/staged actions when required by a project.
4. **Complete envelope-driven detailing.** Discrete longitudinal bars and closed links, web-fit/congestion, straight-bar anchorage/laps and explicit durability cover are implemented. Add section-by-section link spacing zones, longitudinal curtailment from the final design envelope, alternate anchorage geometries and drawing-level torsion-cage placement.
5. **Add the dedicated Eurocode fatigue traffic path.** Implement the appropriate fatigue-load-model moving analysis and integrate it into the simple-span production workflow rather than reusing LM1.
6. **Generalize the native simple-span production workflow.** Extend the benchmark-gated design path from its current T-girder adapter to the supported rectangular, T and I non-prestressed RC girder profiles.
7. **Complete the continuous-span production workflow.** Integrate native transverse distribution, signed sagging/hogging/shear envelopes, service traffic deflection, torsion, fatigue and detailing with the existing continuous analysis/design kernels.
8. **Finish the usable desktop-oriented program.** Add professional calculation reports, project persistence, application workflows/UI and Windows packaging, with MIDAS `.mct` and STAAD `.std` export generated directly from the exact analysed project/governing cases.
9. **Perform the final MIDAS/STAAD independent validation.** Run the application-generated governing and supplemental verification files in installed MIDAS Civil/STAAD.Pro, import genuine results, confirm axes/sign conventions and stiffness/model equivalence, and establish justified tolerances including exact member-end V/T evidence for torsion interaction.
10. **Complete verification manifests before ANN export.** Keep ANN ground-truth generation locked until the applicable solver profile has genuine evidence for traffic loading, combinations, flexure, shear, cracking, deflection, fatigue, detailing, transverse distribution, independent benchmarking and torsion when required.
11. **Define the research input space.** Establish justified ANN/RBDO random-variable distributions, bounds, correlations and feature schemas before large-scale dataset generation.
12. **Train and validate the research models.** Generate verified datasets, train/calibrate the ANN surrogate, then complete reliability analysis and RBDO.
