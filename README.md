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
- Automatic edge-aware gross composite longitudinal `A`, `J`, `Iy` and `Iz` derivation for every rectangular, T or I girder line, including participating deck concrete and physical overhang tributaries
- Physical longitudinal concrete layers preserve the actual 175 mm in-situ slab above the 75 mm precast false slab; the false slab contributes longitudinal stiffness only when its composite participation is explicitly enabled
- Gross precast-girder-only section properties are available separately for construction-stage analysis
- Automatic station-specific transverse deck-strip properties for native/verification grillages, with exact bridge-length recovery, explicit expert overrides and stiffness assumptions recorded in model metadata
- Native LM1 and FLM3 grillage searches can now consume those physical properties directly when explicit expert section overrides are omitted
- Explicit span-wise longitudinal and transverse effective-stiffness modifiers, plus a service helper that combines caller-justified cracked inertia ratios and creep without silently choosing them
- Edge-aware deck tributary widths and permanent-load protection against conflicting/double-counted explicit girder self-weight
- Physical-position-aware surfacing layers and barrier/service/other line actions with transverse allocation, explicit longitudinal extents, construction-stage tags/filters and category-level double-count protection
- Exact simple-span segmented permanent-load reactions, shear and zero-shear moment extrema; the same permanent moment field feeds native service-deflection curvature
- Incremental native permanent-action grillage analysis on an unchanged grid/support system, with three ordered stiffness stages, exact partial member UDLs, signed cumulative response and separate exact-model MIDAS/STAAD stage packages
- Separate 75 mm precast false slab and 175 mm in-situ slab construction model
- Uniform, point and moving axle-train load mechanics
- Simply supported reactions, shear/moment response and moving-load envelopes
- Multi-span continuous Euler-Bernoulli stiffness analysis with explicit span EI
- Continuous-beam reactions, rotations, moment/shear envelopes and influence lines
- Continuous moving axle-train moment, shear, reaction and vertical-deflection envelopes
- Code-neutral elastic T-section service-analysis mechanics
- Numerical simply-supported and continuous-span elastic deflection recovery
- Piecewise-linear simple-span M/EI deflection integration now solves interior zero-slope points analytically, so governing displacement is not restricted to stored moment stations
- Simple-span UDL-plus-axle load-pattern deflection with virtual-work curvature integration, span-wise maximum search and EC2 cracked/uncracked interpolation
- Benchmark-gated native LM1 service deflection using the exact governing girder/case moment field plus permanent response, with member-joint jumps, SLS factors and source trace retained
- EN 1991-2 LM1 lane/tandem/UDL loading including remaining carriageway area
- Continuous LM1 tandem placement and adverse influence-region UDL effects
- Lane-specific transverse-distribution interfaces
- Verification-only equal transverse shares and direct grillage-result import
- EN 1990 ULS and configurable SLS combinations, including signed continuous-section branches
- Continuous Eurocode project envelopes for sagging, hogging and shear
- Native continuous LM1 production envelope combining full-width transverse grillage traffic with the cumulative staged permanent-action grillage response, retaining both member sides at grid/support lines
- Native continuous service deflection combining cumulative staged permanent displacement with scaled full-width LM1 traffic fields and exact interior cubic-Hermite peak recovery
- Continuous matched native V-T interaction preserving co-located LM1 case/member-end/station-side actions and signed staged permanent shear/torsion
- Continuous native FLM3 fatigue section design with two physical reinforcement layers, signed staged permanent moment, sagging/hogging reversal handling and top/bottom concrete compression checks
- Continuous native reinforcement zoning with full-length minimum top/bottom cores, EC2 tension-force shifting, anchorage-extended extra-bar zones, link-spacing zones and optional matched-V-T torsion cage selection
- Continuous support hogging design with web/stem or actual I-girder bottom-flange compression
- Explicit critical shear-section workflows that do not assume support centreline equals the design section
- Layered continuous-support crack analysis with active/inactive construction layers
- Continuous deterministic and moving-train deflection serviceability checks with explicit limits
- Eurocode T-girder flexure, shear, torsion, cracking, deflection, fatigue and detailing kernels
- Generic positive-bending Eurocode layered-section ULS/SLS workflow for physical rectangular, T and I precast profiles, preserving participating deck layers and non-composite gaps
- Practical EC2 discrete longitudinal-bar and vertical-link selection, straight-bar anchorage/lap calculations, explicit durability-cover checks and congestion-aware web fit checks
- Native simple-span ULS envelope-driven detailing with co-located station M/V recovery, EC2 tension-force shifting, anchorage-extended longitudinal curtailment zones and constant-family link spacing zones
- Dedicated full-width native EN 1991-2 FLM3 moving-vehicle fatigue search with explicit transverse vehicle position and per-girder co-located moment ranges
- Native FLM3-to-EC2 T-girder fatigue workflow for longitudinal reinforcement stress range and concrete compression fatigue without substituting LM1 traffic effects
- Native FLM3 layered-section fatigue adapter for rectangular, T and I physical girder profiles, using the same cracked transformed section and non-composite gaps as the generic production workflow
- Optional native FLM3 fatigue results integrated into the benchmark-gated simple-span T-girder production result, sharing the exact project section and permanent-action inputs
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
- Unified Stage-5 final-service verification model for the completed simple-span bridge, assembling permanent actions, governing LM1, gr2 frequent LM1, LM2, pedestrian and vertical-wind cases onto one common final-composite grillage mesh
- Native verification load-combination schema with STAAD `LOAD COMB` and MIDAS `*LOADCOMB` export for gr1a/gr1b/gr2/gr3, vertical-wind ULS, characteristic/frequent SLS and quasi-permanent permanent-action checks
- Application construction verification now distinguishes pre-final load-only deck states from the completed hardened stage; the final construction-stage export contains the full longitudinal-girder plus transverse-deck grillage and does not reapply earlier girder/false-slab/wet-deck loads
- Stage-5 verification result import is available in the desktop workbench: STAAD.Pro `.ANL` files can be imported directly, while MIDAS Civil reaction/displacement/beam-force result tables can be imported from CSV/text tables and matched to the exact exported load-case/combination names
- Imported external results are normalized to the application result schema, checked for complete node/support/member-end coverage, compared with native Stage-5 expectations using explicit tolerances, and can be saved as comparison CSV + summary JSON evidence bundles
- Verification exporters now harden external identifiers: load-case/load-combination IDs cannot overlap, MIDAS names are deterministically de-duplicated after the 40-character export limit, and manifests record the exact STAAD/MIDAS result identities expected on re-import
- Application performance tracking now records operation duration and cache hits; unchanged LM1, extended-action, local-deck, design and fatigue results are reused instead of being recomputed, while repeated permanent-load audits, combination summaries and calculation traces are session-cached
- Heavy desktop work that previously blocked Tk — local-deck design, integrated design, HTML/PDF report generation, verification export and STAAD/MIDAS result import/comparison — now runs on worker threads so pages remain responsive while calculations or file processing continue
- Reporting now uses a shared worked-calculation trace model (`CalculationTrace` / `CalculationBlock` / `CalculationStep`) consumed by both HTML and PDF output. Calculation sheets show design reference, equation, numerical substitution, result and PASS/CHECK status for permanent actions, LM1 envelopes, ULS/SLS combinations, longitudinal RC design, construction stages, local deck checks and FLM3 fatigue where available
- MIDAS/STAAD governing-case result adapters, aggregate completeness checks and engineering benchmark reports
- Benchmark-gated simple-span Eurocode T-girder production path using native per-girder LM1 effects rather than equal-share traffic
- Benchmark-gated physical layered-section native-LM1 production adapter now runs common positive-bending flexure, shear, cracking, deflection and practical detailing for rectangular, T and I precast girder profiles
- Edge-aware permanent deck tributary widths for exterior as well as internal girders
- Matched co-located native LM1 shear-torsion interaction checks that do not combine unrelated V/T maxima
- The matched native V-T adapter now accepts the physical layered rectangular/T/I design input, deriving shear-web width from the actual girder profile while retaining explicit torsion-cell geometry
- Drawing-level detailing now includes an explicit full-span continuous longitudinal core, optional end-anchorage/lap-stagger constructability checks, cage-depth fit checks, and benchmark-gated closed-link/perimeter-bar torsion cage selection
- Local deck fatigue has an explicit dedicated-plate/verified-external stress-range workflow; the global girder grillage is intentionally not relabelled as a local slab fatigue model
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

## Construction-stage analysis boundary

`run_project_construction_grillage` applies each permanent action exactly once, in `PRECAST_GIRDER`, `DECK_CONSTRUCTION`, then `SUPERIMPOSED` order. The 75 mm precast false-slab weight is applied in the precast-only stiffness state before any explicitly verified false-slab composite participation is activated; the wet in-situ slab weight is then applied in the deck-construction state. Each increment uses its own section stiffness; earlier loads are not reapplied to the final composite section. Results retain the stage input, source-to-member load audit, exact analysed model, incremental response and signed cumulative node/member-end response. `build_construction_stage_verification_packages` exports each actual stage model separately, not a fictitious final-stiffness model of the sum.

This is an incremental linear-elastic, **unpropped**, unchanged-support/continuity workflow for one simple span or continuous spans. `ConstructionAnalysisAssumptions` makes that scope machine-readable. Requests for propping, support installation/removal, establishment of continuity during construction, creep/shrinkage redistribution, physical local transverse construction-action recovery, or non-stress-free layer activation fail explicitly instead of being silently approximated. The caller must document the unchanged support/continuity basis and each stage's stiffness basis. Pre-final stages require an explicit transverse section representing a cross-member at every supplied grid station, including supports; the software does not infer temporary diaphragms. Stiffness modifiers do not provide a time-dependent construction model.

Permanent actions retain the existing tributary-area/statical-line allocation. This does not recover physical local deck/overhang torsion. Load bounds are clipped exactly to members without adding fictitious cross-beams at load boundaries. Analytical reaction, moment, deflection, load-conservation and export tests are software/mechanics checks only. Project-specific construction validation and genuine independent comparison remain outstanding; production and ANN gates are unchanged.

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
1. **Construction-stage v1 scope is now explicit and fail-fast.** The incremental unpropped workflow separates girder/false-slab pre-deck loading, wet in-situ deck loading and final superimposed actions at their active stiffness states. Optional verified false-slab composite stiffness affects the later wet pour, not the false slab's own pre-activation weight. Propping, support changes, continuity establishment, creep/shrinkage redistribution, local transverse construction actions and layer stress-history modelling are explicitly rejected rather than approximated. Remaining construction work is project-specific assumption validation and final independent acceptance in Stage 7.
2. **Drawing-level detailing v1 is implemented.** Native simple-span section-by-section link spacing and anchorage-extended longitudinal curtailment retain a full-span minimum continuous-bar core. Explicit anchorage coefficient policies support project-approved straight/hooked/other geometries without inventing geometry factors; optional end-length checks, non-overlapping staggered lap groups and longitudinal cage-depth constructability checks are implemented. Benchmark-gated matched V-T results now generate a closed-link torsion cage family plus corner/perimeter longitudinal torsion bars. The cage enforces a conservative verified-cell `uk/8` longitudinal link-spacing cap and a 350 mm maximum nominal spacing of longitudinal torsion bars around the cell perimeter. Exact bar coordinates, bend shapes, couplers, stock-length optimisation and local end-block drawing review remain project/drawing tasks rather than silently assumed code checks.
3. **Fatigue v1 is implemented with explicit modelling boundaries.** Dedicated native full-width FLM3 envelopes auditable left/right-packed notional-lane centre candidates when no physical fatigue-lane centre is supplied, while preserving explicit project/NA lane selection when known. Per-girder co-located moment and shear ranges drive simple-span rectangular/T/I longitudinal-reinforcement and concrete-compression fatigue, plus optional vertical-link fatigue using the actual provided A_sw/s and an explicit link fatigue category; the link stress range uses a conservative full-truss cyclic-shear model. The desktop now connects the native FLM3 search directly to the selected simple-span girder cage for longitudinal-steel, concrete-compression and optional vertical-link fatigue checks; fatigue-category strengths and damage-equivalence factors remain explicit project inputs. A native continuous transverse slab-strip solver now provides local LM2 and barrier-wheel flexure/one-way-shear design for the present longitudinal-girder bridge, while a general two-way plate FE fatigue/stress solver remains a higher-fidelity optional verification route rather than being claimed by the beam/grillage model. A full-length continuous-grillage FLM3 traffic search retains signed station-by-station M/V ranges for every girder; the top/bottom continuous RC fatigue section design belongs to Stage 5 with the rest of the signed continuous workflow. Clause-by-clause verification and final independent acceptance remain Stage 7 obligations.
4. **Complete simple-span physical-profile acceptance.** Rectangular, T and I physical profiles now share benchmark-gated native-LM1 positive-bending ULS/SLS, envelope-driven bar/link zoning, practical detailing, matched co-located V-T interaction with explicit torsion-cell geometry, and dedicated FLM3 longitudinal/concrete fatigue adapters. Remaining work here is clause-by-clause verification, construction/drawing refinements and final independent external acceptance rather than a T-only production architecture.
5. **Continuous-span production v1 is implemented.** Native full-width LM1 transverse distribution is integrated with exact cumulative staged/nonuniform permanent actions to generate signed station-side sagging/hogging/shear ULS/SLS envelopes feeding continuous flexure, shear and support-crack checks. Service deflection combines staged permanent and scaled native-LM1 cubic displacement fields with interior peak recovery. Matched V-T keeps co-located LM1 case/member-end/station-side actions and signed permanent response. Full-length FLM3 supplies signed fatigue actions and a two-steel-layer cracked section retains top/bottom steel through sagging, hogging and reversal. Continuous detailing now provides full-length minimum top/bottom cores, tension-shifted anchorage-extended additional-bar zones, link-spacing zones and an optional conservative full-length torsion cage. Final clause/project verification and independent acceptance remain Stage 7 obligations.
6. **Desktop application workbench v2 is implemented.** The desktop is now organised around Project, Design Basis, Load Cases & Combinations, Additional Actions, Analysis, Design & Checks, Verification and Research workspaces rather than a single LM1 form. Project files persist the validated bridge model together with checksummed application preferences; editable inputs cover spans, deck/carriageway geometry, rectangular/T/I **precast** girder profiles, explicit false-slab/in-situ deck build-up and composite-participation switches, material density/stiffness, display/input length units and exposed Eurocode/National-Annex ULS/SLS parameters. Precast and final composite identities are kept distinct: for example, a 400 x 950 mm rectangular precast girder remains rectangular during the applicable construction stages and is explicitly reported as a final composite T-section once a participating deck flange becomes active; non-participating false-slab concrete remains weight-only. The Load Cases & Combinations workspace derives girder, false-slab and wet in-situ deck self-weight automatically from the physical project; it also persists user-defined surfacing, barrier and services actions, shows a per-girder permanent-load audit, and combines simple-span characteristic Gk with native LM1 Qk into exposed EN 1990 ULS/characteristic/frequent/quasi-permanent interpretation using the persisted project factors. The Additional Actions workspace implements braking/acceleration, thermal movement/gradient actions, pedestrian footway loading, LM2, safety-barrier accidental action, construction-stage actions and a static wind-action assessment. Wind speed, exposure and force coefficients are explicit project inputs; transverse wind feeds the support/bearing path and optional vertical wind enters the girder action envelope rather than being silently ignored. The design workspace builds mutually compatible road-traffic situations (gr1a LM1 + reduced footway, gr1b LM2, gr2 braking with a separately rerun frequent-LM1 vertical component, and gr3 pedestrian), envelopes the governing effects into EC2 girder checks, allows construction stages to govern automatic bar/link selection, and carries braking/thermal/wind demand into longitudinal/transverse bearing checks plus barrier impact into a separate accidental demand/capacity path. The new Deck & Fatigue workspace uses a native continuous transverse slab strip over the actual girder lines and edge cantilevers to design top/bottom transverse slab reinforcement and check one-way shear under permanent loads, dispersed LM2 wheels and the barrier-impact vertical wheel; nonparticipating false-slab concrete remains weight-only in slab resistance/stiffness. Native full-width FLM3 is also a desktop workflow tied to the selected girder reinforcement. Missing project wind/climate/footway inputs, verified bearing/barrier capacities or fatigue-category data remain explicit blockers rather than hidden defaults. Native full-width LM1 runs off the UI thread and reports governing M/V/T plus deflection traces. Repeated LM1 placements are grouped only when their exact load-generated grillage topology is identical; each unique topology is assembled/factorized once with a sparse solver and subsequent load cases reuse that factorization without changing the original structural discretization. Application runs retain only governing M/V/T/deflection case models, and the desktop provides case progress, percentage, elapsed time, ETA and cancellation. The same analysed model can generate standalone HTML reports, true PDF reports and browser print/preview output. HTML/PDF reports now share a worked-calculation trace so summary tables are backed by auditable equation/substitution/result sheets, and the trace API is also ready for the future GUI calculation-detail viewer. The default independent-verification export consolidates all unique governing LM1 placements onto one exact common mesh and writes one MIDAS `.mct` plus one STAAD `.std`, with every governing placement represented as a separate named static load case; the older one-folder-per-case packages remain available only as a detailed/debug export. A capability dashboard exposes the implemented simple/continuous ULS, SLS, fatigue and detailing engine without bypassing benchmark gates, while the Research workspace keeps ANN/reliability/RBDO generation visibly locked until the applicable verification manifest is complete. The CLI shares the persisted search settings and now writes HTML + PDF + verification outputs. Stage 6 application redevelopment is therefore substantially complete; independent external-result acceptance and any production-design unlock belong to Stage 7/8 rather than being silently treated as UI completion.
7. **Perform the final MIDAS/STAAD independent validation.** The application exports both action-family packages and a unified Stage-5 final-service model with static ULS/SLS combinations for the current simple-span profile. Run the exported file in installed STAAD.Pro or MIDAS Civil, then use the Verification tab to import the returned `.ANL` file or MIDAS reaction/displacement/beam-force tables. The application checks result coverage, normalizes axes/units through the verified adapters, compares node/support/member-end responses against the native solver with explicit tolerances, and can write the comparison evidence bundle. Engineering acceptance still requires confirmation that the external model/version/settings are equivalent. Continuous-span Stage-5 permanent-action combination remains intentionally blocked until construction-history effects can be carried into the external verification model without reapplying them to final stiffness.
8. **Complete verification manifests before ANN export.** Keep ANN ground-truth generation locked until the applicable solver profile has genuine evidence for traffic loading, combinations, flexure, shear, cracking, deflection, fatigue, detailing, transverse distribution, independent benchmarking and torsion when required.
9. **Define the research input space.** Establish justified ANN/RBDO random-variable distributions, bounds, correlations and feature schemas before large-scale dataset generation.
10. **Train and validate the research models.** Generate verified datasets, train/calibrate the ANN surrogate, then complete reliability analysis and RBDO.
