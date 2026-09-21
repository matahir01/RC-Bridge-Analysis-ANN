# RC Bridge Analysis & ANN

Deterministic reinforced-concrete bridge-girder analysis/design with separate Eurocode and BS 5400 calculation paths, verified dataset generation, ANN surrogate modelling, reliability analysis and RBDO.

## Project goals
- Manual/deterministic structural analysis and RC design
- Eurocode and BS 5400 calculation paths kept separate
- Transparent calculation traces suitable for hand checking
- Dataset generation from verified deterministic solver outputs
- ANN train/validation/test workflow with auditable solver provenance
- Reliability and RBDO research modules
- Desktop-first architecture with CI-built standalone Windows EXE packaging

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
- Reporting now uses a shared worked-calculation trace model (`CalculationTrace` / `CalculationBlock` / `CalculationStep`) consumed by both HTML and PDF output. Calculation sheets expose the actual analysis/design path as **formula → numerical substitution → result → reference/check**, including native grillage stiffness/solution mechanics, permanent actions, LM1 envelopes, ULS/SLS combinations, layered EC2 flexure, shear, cracking, deflection, construction stages, local deck checks and FLM3 fatigue. HTML uses native MathML and PDF uses a dedicated engineering-math renderer with stacked fractions, radicals, superscripts/subscripts and Greek symbols rather than monospaced text approximations. Road-bridge deflection reporting now distinguishes the calculated deformation from its acceptance criterion: no PASS/CHECK is shown unless a project/client limit has actually been entered
- The desktop/engine integration is now versioned and contract-checked: deterministic entry points and the application-session operations consumed by presentation layers are frozen under explicit interface version 1.0, with regression tests guarding accidental breaking changes
- The desktop GUI now uses a professional sidebar workspace shell with persistent project/workspace header, quick Open/Save/Run actions, an Overview control centre, performance diagnostics and a dedicated worked-calculation navigator that displays the same equation/substitution/result records used by reports
- The desktop now also exposes a grouped ribbon command surface for fast engineering setup. Ribbon commands open secondary scrollable input editors for Project & Geometry, Materials & Section, Permanent Loads, Additional Actions, Design Basis, Analysis Settings, Design Settings and Deck/Fatigue, reducing dependence on long embedded input pages while preserving the same underlying application state
- STAAD `.ANL` import now adds an engineering-envelope comparison layer above the raw result diagnostics: each native governing LM1 source case is mapped to its exported Stage-5 case, then per-girder moment, shear, torsion and service deflection are compared against STAAD on the same governing case; permanent-action global equilibrium is checked separately
- The STAAD parser now reads **all primary load cases and all load combinations in one pass**, preserves joint/member context across paginated STAAD output, and normalizes reactions, displacements and global member-end V/M/T for every result ID. The Verification workspace mirrors the exported model with a complete native load-case/load-combination catalogue showing IDs, categories, names and combination factors
- Verification acceptance now uses one shared **relative + quantity-specific absolute tolerance** policy for detailed result checks and governing envelopes. The deterministic-v1 Stage-5 defaults are finalized from the genuine STAAD evidence at **0.1% relative**, with absolute floors of **0.01 kN**, **0.01 kNm** and **0.001 mm** (one STAAD print increment for the reviewed ANL). Near-zero quantities are therefore judged by the print-resolution floor rather than receiving an automatic PASS when percentage error is undefined
- Imported-result status is separated into **import coverage**, **detailed numerical agreement**, **governing-envelope agreement** and **engineering acceptance**. Numerical agreement cannot hide failed detailed checks, and engineering acceptance remains pending until source/model-equivalence review is completed
- Ribbon input dialogs are transactional: text, choice and Boolean controls edit temporary dialog variables; Apply commits only after validation, while Cancel/Escape/window close discard the staged edits
- STAAD verification import now builds one indexed normalized-result database from the single ANL parse and reuses it for detailed comparisons and governing-envelope checks. Import progress and cancellation are exposed through the application session for large result files
- Governing Stage-5 ULS/SLS load-combination envelopes are independently recovered by girder for M/V/T and SLS deflection. The verifier checks both the external response on the native governing combination and the external solver's own governing combination envelope, recording governing-combination changes without treating a numerically equivalent switch as an automatic failure
- Engineering acceptance is now an explicit **auditable review gate** rather than a permanent placeholder. A Stage-5 import can be accepted only after numerical agreement plus recorded external source/run reference, solver version, exported-model identity, geometry, section/material properties, supports, loading, combinations and result-axis equivalence; incomplete reviews remain PENDING and completed reviews cannot override numerical failure
- Verification export manifests now include a structured model audit of nodes, member connectivity/assignments, materials, sections and support restraint codes together with acceptance-review requirements, so external-model equivalence can be checked against explicit exported data
- **First genuine Stage-5 STAAD benchmark completed (19 Sep 2026):** STAAD.Pro CONNECT 22.09.00.115 returned 63 primary cases and 141 combinations for the 540-node / 749-member final-service model. All 204 result sets and 1,029,792 detailed comparisons passed the original provisional policy and have now been rechecked against the tighter accepted-v1 policy (0.1% + 0.01 kN/kNm + 0.001 mm). All 203 ULS/SLS combination-envelope checks and all 28 LM1 governing-envelope checks pass, with the same governing combination/source case recovered in every envelope item. Sanitized evidence is stored in `verification_evidence/staad_stage5_2026-09-19.json`; the 36 MB raw ANL is identified by SHA-256 rather than committed
- **STAAD Stage-5 engineering source review closed (20 Sep 2026):** the supplied `application_verification_final_service.std` was checked against the genuine ANL input echo. Model title, all 540 node coordinates, all 749 member incidences, all 14 supports, the 63 primary-case structure, all 141 combinations and the complete GLOBAL member-force/reaction/displacement output scope agree. The supplied STD is a STAAD-resaved normalized copy rather than the byte-identical pre-analysis export: STAAD rounded section/material values by at most about 0.000256% and 56 nodal loads by at most 0.0005 kN. The ANL echo therefore remains the authoritative higher-precision analysed input, while the reviewed STD confirms semantic source/model equivalence. This benchmark's engineering acceptance is now **ACCEPTED**
- The genuine STAAD run exposed 20 parser warnings caused by overlong `MEMBER PROPERTY` commands. The numerical results were unaffected, but the exporter now explicitly wraps long PRIS property definitions with STAAD continuation markers so future verification files do not depend on STAAD's automatic line splitting
- Batch 6 now has a machine-readable **v1 acceptance matrix** (`rc_bridge.research.acceptance_matrix`) that explicitly separates external structural-analysis evidence from code-loading and RC design acceptance. The accepted STAAD run may promote the final-service structural benchmark and transverse-distribution mechanics, but it cannot by itself unlock EN 1991-2 LM1 generation, EN 1990 combination interpretation, EC2 flexure/shear/torsion/cracking/deflection, fatigue or detailing. MIDAS remains recorded as a V2-only cross-check rather than a v1 gate
- Published-reference code checks have started under `rc_bridge.research.code_reference_benchmarks`. The current independent JRC cases reproduce (a) the Handbook 2 Annex-B rectangular flexure example, matching the published **933 mm²** tension-steel result for **62.78 kNm**, and (b) the JRC Beam A2-B2-C2 EC2 link-spacing example, reproducing **0.75d = 265.5 mm** against the published rounded **266 mm**. These are recorded as externally accepted **sub-component reference cases only**; the broad EC2 flexure and detailing milestones remain locked pending representative T/I/layered and remaining detailing checks
- Batch 6I expands the published-reference suite with three more JRC checks: **EN 1991-2 LM1 characteristic values** (300/200/100 kN tandem axle loads, 9.0/2.5/2.5 kN/m² lane UDLs, 2.5 kN/m² remaining area and 1.2 m axle spacing), **road-bridge EN 1990/EN 1991 factors** (gamma_Q,traffic = 1.35 and split frequent LM1 TS/UDL factors 0.75/0.40), and the **EC2 concrete shear V_Rd,c** slab example (fck=35 MPa, d=360 mm, Asl=1848 mm², bw=1 m, published V_Rd,c≈198 kN/m). These are scoped sub-component evidence; LM1 placement, the full bridge combination matrix and link-governed shear remain locked
- Batch 6K adds three more JRC checks, bringing the published-reference suite to **eight** cases: **EN 1991-2 Table 3.5 notional-lane subdivision** (including the thesis 7.0 m carriageway -> two 3.0 m lanes + 1.0 m remaining area), **EN 1992-2 reinforcement fatigue** (88 MPa reference stress range, lambda_s=0.89 -> 78.32 MPa equivalent range; 162.5/1.15 -> 141.30 MPa resistance), and **EN 1992-2 concrete compression fatigue** (native f_cd,fat=15.95..17.40 MPa reproduces the published rounded 16..17.5 MPa range and the cited 11.9/3.5 MPa stress pair fails Expression 6.77 as reported). These remain scoped sub-component evidence: LM1 response-maximising placement and the FLM3 structural stress-range path are still independent-verification gates
- Batch 6L adds two further JRC checks, bringing the suite to **ten** published-reference cases. The Davaine LM1 transverse-distribution example is reproduced for the 11.0 m carriageway / two-girder reference: **R1=471.43 kN, R2=128.57 kN** versus published **471.4/128.6 kN**. The same source also verifies the MSc permanent+LM1 combination core: **ULS 1.35G+1.35(TS+UDL)**, characteristic **G+TS+UDL**, frequent **G+0.75TS+0.40UDL**, and zero quasi-permanent LM1 contribution. Broad LM1 remains locked only for the independent longitudinal governing-placement/envelope check; the standalone application's wider thermal/wind/pedestrian/braking/LM2 combination matrix remains a separate general-v1 verification item
- Batch 6M adds two independent **link-governed EC2 shear** references, bringing the suite to **twelve** published cases. The Concrete Centre support-B example is reproduced for **VEd=164.5 kN**, **d=392 mm**, **bw=300 mm**, **cot(theta)=2.5**: required **Asw/s=0.42897 mm²/mm** versus published **0.429**, minimum **0.26291** versus **0.263**, maximum link spacing **294 mm**, and a two-leg **H8@200** provides **0.50265 mm²/mm** versus published **0.50**. European Concrete Platform Example 6.4 independently verifies the provided-link equation with native **V_Rd,s=380.27 kN** versus published **380 kN**. The remaining broad shear gap is now explicitly **V_Rd,max / concrete-strut reduction-factor convention** plus final link-zoning review; no silent convention change has been made
- Batch 6N raises the suite to **fifteen** published-reference checks. The JRC EN 1992-2 bridge guidance confirms the deterministic-v1 recommended **nu1=0.6(1-fck/250)** basis, and the Concrete Centre fck=30 MPa / cot(theta)=2.5 example is reproduced at **v_Rd,max=3.641 MPa** versus published **3.64 MPa**. This closes the simple-span research **shear equation milestone**; drawing-level link zoning stays under detailing. European Concrete Platform Examples 6.6/6.7 also reproduce torsion **Asw/s=0.34830 mm²/mm**, longitudinal **Asl=6858.9 mm²** (published 6855), **T_Rd,max=65.86 kNm** (published 66), and the published **V=350 kN / T≈20 kNm** high-stress interaction point. The torsion formulas are therefore independently supported, while the broad torsion gate remains locked only until the actual bridge torsion-cell **Ak/uk/tef** basis is made traceable
- Batch 6O adds the independent **longitudinal LM1 governing-search** benchmark, bringing the suite to **sixteen** published/reference checks. The native simple-span search reproduces the independent 18 m hand calculation for two 300 kN axles at 1.2 m spacing: the governing section is **x=L/2-0.3=8.7 m**, the leading axle is at **9.9 m**, and **Mmax=2523 kNm**. Together with the already accepted LM1 constants, lane subdivision and transverse placement/distribution references, this closes the **simple-span MSc LM1 loading gate**. Continuous-span LM1 remains a separate locked solver profile rather than being silently promoted
- Batch 6J corrects the road-bridge serviceability basis exposed during report QA: the application no longer invents **L/1000** as a universal Eurocode deflection limit. Deflection is still calculated using the selected SLS path (frequent by default), but PASS/CHECK is assigned only when a positive **client/project span-ratio criterion** is supplied. A blank criterion is reported as **NOT ASSESSED / REVIEW** and remains an explicit design blocker; previously saved explicit ratios such as L/1000 remain loadable as project inputs rather than being silently rewritten
- The JRC road-bridge benchmark exposed a design-basis correction: the previous new-project traffic ULS default was **gamma_Q = 1.50**; deterministic v1 now defaults to **gamma_Q = 1.35** for road traffic while keeping the value editable for National Annex/project bases. The genuine 19 Sep STAAD benchmark used 1.50 and remains valid structural/model-response evidence for that recorded factor set; its direct 141 combination comparisons are not relabelled as validation of the corrected 1.35 code factor
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

## Authoritative development roadmap

The repository now follows one roadmap. Earlier references to numbered “Stages” were useful during rapid development but became ambiguous as the application, verification and research tracks evolved. **Batch** labels refer only to implementation increments; the engineering maturity sequence is the roadmap below.

1. **Deterministic engineering foundation — substantially implemented.** Physical rectangular/T/I sections, staged permanent actions, native LM1/LM2/FLM3 analysis, simple- and continuous-span ULS/SLS design, fatigue, local deck checks and practical detailing are in place with explicit modelling boundaries.
2. **Application, reporting and verification backbone — implemented.** Project persistence, exposed design-basis settings, full analysis/design workflows, shared step-by-step calculation traces, HTML/PDF reports, Stage-5 verification export, STAAD/MIDAS result import, evidence bundles, performance caching and Windows EXE packaging are implemented.
3. **Professional GUI v1 — implemented.** The versioned engine/application interface remains frozen at v1.0 while the desktop now provides the professional sidebar shell, overview control centre, graphical bridge plan/section preview, permanent-load distribution chart, exact governing LM1 M/V/T/deflection diagrams by girder, design-utilization dashboard, selected-girder reinforcement schematic, construction-stage review, deck/fatigue response visualisation, contextual worked-calculation navigation and external-verification comparison dashboard.
4. **Independent structural validation — in progress.** The primary Stage-5 simple-span benchmark now has genuine STAAD `.ANL` numerical evidence, an accepted source/model-equivalence review, a finalized evidence-based numerical tolerance policy and an explicit acceptance matrix separating structural-analysis evidence from code/design evidence. The remaining work is now concrete: independently check EN 1991-2 loading, EN 1990 combinations, construction-stage/local-deck response and the EN 1992 flexure, shear, torsion, cracking, deflection, fatigue and detailing paths before those research/profile milestones can be unlocked. **MIDAS cross-verification is explicitly deferred to V2 and is not a v1 release gate.**
5. **Deterministic application v1.0 release hardening — pending.** Complete end-to-end workflow QA, input/error handling, report pagination/polish, project-file compatibility, GUI consistency, packaging/versioning and final Windows release checks.
6. **Verification-manifest unlock — pending.** Keep ANN ground-truth generation locked until the applicable simple-span Eurocode, continuous-span Eurocode or BS 5400 solver profile has the required genuine verification evidence.
7. **Research input-space definition — pending.** Establish justified probability distributions, bounds, correlations, limit-state definitions and feature schemas for ANN/reliability/RBDO work.
8. **Verified dataset, ANN, reliability and RBDO programme — pending.** Generate verified deterministic datasets, train/validate the surrogate, perform reliability analysis and complete RBDO only after the preceding verification gates are satisfied.

Installed independent-software comparison remains an engineering acceptance gate, not a substitute for internal mechanics/software tests. For deterministic v1.0, the accepted genuine **STAAD** Stage-5 path is the external solver evidence used for the current simple-span verification profile; **MIDAS cross-verification is deferred to V2**. Synthetic CI fixtures and native round trips remain software verification only and must never be presented as independent structural validation.

## ANN verification lock
Training-data export requires a `DeterministicSolverVerification` for the exact solver profile being used. A single Boolean cannot unlock ANN data. The manifest currently requires explicit verification of traffic loading, load combinations, flexure, shear, cracking, deflection, fatigue, detailing, transverse distribution and an independent benchmark; torsion is also required when it is in scope. The v1 acceptance matrix maps only independently accepted evidence into that manifest, so the genuine STAAD analysis PASS cannot silently mark design-code milestones complete.

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

The export/import/benchmark workflow and production-lock logic are covered by synthetic CI fixtures, but those fixtures are software tests—not independent structural validation. The current simple-span Stage-5 profile now has genuine installed **STAAD.Pro** agreement and accepted source/model review. MIDAS remains fully supported by the exporter/importer but its second-solver cross-check is deferred to V2 rather than blocking deterministic v1.0.

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

## Implemented scope and acceptance boundaries

1. **Construction-stage v1 is implemented with explicit limits.** The incremental unpropped workflow separates girder/false-slab pre-deck loading, wet in-situ deck loading and final superimposed actions at their active stiffness states. Optional verified false-slab composite stiffness affects the later wet pour, not the false slab's own pre-activation weight. Propping, support changes, continuity establishment, creep/shrinkage redistribution, local transverse construction actions and layer stress-history modelling are rejected rather than silently approximated. Remaining work is project-specific assumption validation and independent acceptance.
2. **Drawing-level detailing v1 is implemented.** Native simple-span link spacing, anchorage-extended longitudinal curtailment, full-span minimum continuous-bar cores, anchorage policies, end-length checks, staggered lap groups, cage-depth checks and torsion cage selection are implemented. Exact bar coordinates, bend shapes, couplers, stock-length optimisation and local end-block drawing review remain project/drawing tasks.
3. **Fatigue v1 is implemented with explicit modelling boundaries.** Native full-width FLM3 envelopes feed simple-span rectangular/T/I longitudinal-reinforcement and concrete-compression fatigue, with optional provided-link fatigue. Continuous FLM3 retains signed station-by-station M/V ranges and the continuous RC fatigue section workflow is implemented. A general two-way plate FE fatigue/stress model remains an optional higher-fidelity route rather than being claimed by the present beam/grillage engine. Clause-by-clause verification and independent acceptance remain outstanding.
4. **Simple-span rectangular/T/I production paths are implemented.** Native LM1 ULS/SLS, envelope-driven bar/link zoning, practical detailing, matched co-located V-T interaction, explicit torsion-cell geometry and dedicated FLM3 adapters share the physical-profile architecture. Remaining work is clause/project verification, construction/drawing refinement and independent acceptance.
5. **Continuous-span production v1 is implemented.** Signed staged permanent actions, native LM1 transverse distribution, sagging/hogging/shear ULS/SLS envelopes, service deflection, matched V-T, FLM3 fatigue and continuous detailing are integrated. Final clause/project verification and independent acceptance remain outstanding.
6. **Desktop application workbench and professional GUI v1 are implemented.** Project persistence, design-basis settings, load/action workspaces, native analysis, design/deck/fatigue workflows, shared calculation traces, HTML/PDF reports, performance caching, Stage-5 verification export/import, evidence generation and the frozen engine/application interface v1.0 remain the application backbone. The GUI now adds graphical bridge/section previews, permanent-load charts, exact governing LM1 longitudinal M/V/T/deflection diagrams, design-utilization summaries, selected-girder reinforcement and construction-stage review, deck/fatigue diagrams, contextual calculation navigation and external-result comparison visualisation without moving engineering formulas into the presentation layer.

## Remaining major work

1. **Batch 6 — close independent structural verification and engineering QA (in progress).** The genuine Stage-5 STAAD benchmark, engineering source/model review, finalized v1 tolerances and the analysis-vs-design acceptance matrix are implemented. The published/reference suite now contains **sixteen scoped independent checks**. The **simple-span MSc LM1 loading gate** and the **simple-span EC2 shear equation milestone** are externally accepted; the permanent+LM1 ULS/SLS research combination core is also independently supported. The remaining MSc-critical gates are representative T/I/layered flexure, actual bridge torsion-cell Ak/uk/tef traceability, cracking, deflection, FLM3 structural stress-range generation and remaining detailing rules. The standalone application's wider EN 1990 thermal/wind/pedestrian/braking/LM2 matrix, construction-stage and local-deck structural checks remain general-v1 verification items; MIDAS cross-verification is deferred to V2.
2. **Batch 7 — harden and release deterministic application v1.0.** Finish end-to-end workflow testing, any GUI consistency issues revealed by real use, remaining performance issues, validation/error handling, project-file compatibility, documentation/help, EXE versioning and the final Windows release build. Reporting hardening now includes professional worked-calculation sheets with proper mathematical typography and step-by-step analysis/design equations rather than summary-only output.
3. **Complete verification manifests before ANN export.** Keep ANN ground-truth generation locked until the exact solver profile has genuine evidence for traffic loading, combinations, flexure, shear, cracking, deflection, fatigue, detailing, transverse distribution, independent benchmarking and torsion where required.
4. **Define the research input space.** Establish justified ANN/RBDO random-variable distributions, bounds, correlations, sampling assumptions, limit-state targets and feature schemas before large-scale dataset generation.
5. **Generate and validate the research models.** Produce verified deterministic datasets, train/validate the ANN surrogate, then complete reliability analysis and RBDO.

### Higher-fidelity work that does not block deterministic v1.0

General shell/plate deck FE, creep/shrinkage construction redistribution, propping/support installation-removal, non-stress-free layer activation, exact reinforcement bend/coupler/stock optimisation and other project-specific high-detail modelling remain future or specialist extensions unless independent verification identifies one as necessary for the current bridge scope.

