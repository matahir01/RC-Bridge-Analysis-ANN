# MSc Research Scope Lock and Input Space

This document freezes the research direction after deterministic Batch 6Q and prevents further standalone-application development from silently expanding the MSc scope.

## Fixed bridge context

The ANN/reliability/RBDO study is centred on the verified Eurocode simple-span bridge profile:

- analysis span: 15.00 m
- physical precast girder length: 14.95 m
- overall deck width: 11.00 m
- carriageway width: 7.00 m
- seven longitudinal girders at 1.70 m spacing
- baseline precast girder: 400 mm x 950 mm rectangular RC member
- 75 mm precast false slab: permanent weight only
- 175 mm in-situ deck slab: participating composite flange after hardening
- baseline concrete: C35/45
- baseline reinforcement: B500
- traffic model: EN 1991-2 LM1
- current deflection research criterion: L/250 = 60 mm for the 15 m span

L/250 is adopted from Eurocode worked-example/training material. It is retained as the MSc research serviceability criterion and is not described as a universal normative EN 1992-2 road-bridge limit.

## Core ANN / reliability / RBDO variables

| Variable | Symbol | Role | Baseline | First-pass probability family | Current status |
| --- | --- | --- | ---: | --- | --- |
| concrete compressive strength | f_ck | random | 35 MPa characteristic baseline | lognormal | family/COV evidence available; C35 mean mapping and ANN bounds not frozen |
| reinforcement yield strength | f_y | random | 500 MPa nominal baseline | normal | provisional JCSS mean about 560 MPa, sigma about 30 MPa; ANN bounds not frozen |
| precast girder width | b | design | 0.40 m | n/a | RBDO bounds not frozen |
| precast girder depth | h | design | 0.95 m | n/a | RBDO bounds not frozen |
| longitudinal tension steel area | A_s | design | baseline to be taken from deterministic design | n/a | feasible discrete-bar/design bounds not frozen |
| permanent-action multiplier | lambda_G | random | 1.0 | normal | family supported; complete bridge-action mean/COV not frozen |
| traffic-action multiplier | lambda_Q | random | 1.0 | extreme-value family | bridge-specific LM1 probabilistic parameters not frozen |

The distinction between **design** and **random** variables is deliberate. The ANN may accept both classes as inputs. RBDO changes the design variables, while reliability integration samples the random variables according to their probability models.

## Limit-state outputs

The current four deterministic targets are

- g_M = M_R - M_E
- g_V = V_R - V_E
- g_cr = w_lim - w_k
- g_delta = L/250 - delta

Positive values indicate reserve; zero is the limit-state surface; negative values indicate violation.

For shear, when V_Ed exceeds V_Rd,c, g_V must be based on the **actual provided** shear reinforcement and the resulting provided resistance, not on the reinforcement merely required by the design equation.

## Evidence used for the first pass

The numerical definitions remain provisional until they are explicitly frozen in the methodology.

1. JRC, *Reliability background of the Eurocodes* (2024): material properties may generally be modelled lognormally, dimensions Gaussian, permanent-action effects Gaussian, and maxima over a reference period may use extreme-value distributions.
   https://eurocodes.jrc.ec.europa.eu/publications/reliability-background-eurocodes

2. JCSS Probabilistic Model Code, reinforced-concrete example: concrete compression strength is illustrated as lognormal with COV 0.17; reinforcing yield strength is illustrated around mean 560 MPa and standard deviation 30 MPa.
   https://www.jcss-lc.org/publications/jcsspmc/examplesmodelcode2001.pdf

3. JCSS Probabilistic Model Code, reinforcing steel: for high-standard production, yield strength may be modelled normally with overall standard deviation about 30 MPa and mean approximately S_nom + 2 sigma.
   https://www.jcss-lc.org/publications/jcsspmc/rebar.pdf

4. JCSS Probabilistic Model Code, self weight: ordinary concrete weight density is reported with COV about 0.04. This supports only the self-weight component and is not yet adopted as the COV of the complete permanent-action multiplier.
   https://www.jcss-lc.org/publications/jcsspmc/self_weight.pdf

5. JRC Eurocode bridge worked example / training material uses L/250 in serviceability deflection verification.
   https://eurocodes.jrc.ec.europa.eu/sites/default/files/2021-12/handbook4.pdf

## What remains before pilot LHS generation

No large dataset is to be generated until the following are justified and frozen:

- lower/upper ANN training bounds for f_ck and f_y
- feasible RBDO bounds for b and h
- baseline and feasible/discrete design domain for A_s
- mean/COV (or equivalent parameters) for the complete permanent-action multiplier lambda_G
- bridge-specific probabilistic parameters and reference period for lambda_Q
- correlation assumptions
- treatment of resistance/load-effect model uncertainty, if included in the final reliability model

After those items are frozen, the next step is a small pilot LHS dataset (about 100-200 analyses), not the full production dataset.
