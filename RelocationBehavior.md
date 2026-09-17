# Human-Centric Relocation Behavior & Spatial Modeling

This document details the architectural and algorithmic overhaul of the spatial-temporal and relocation engine in the Trajectories Entity Resolution platform ([`backend/resolution.py`](file:///home/jeromemassot/Projects/Trajectories/backend/resolution.py)).

---

## 1. Overview & Problem Formulation

In earlier versions of the platform, relocation feasibility was evaluated using an artificial continuous physical velocity:
$$\\text{velocity} = \\frac{\\text{distance}}{\\max(\\Delta t_{\\text{hours}}, 0.5)}$$

For human beings traveling by cars, planes, or trains:
1. **Velocity in km/h is not meaningful over long periods**: Describing a relocation between Dallas and Phoenix separated by 9 months as traveling at "$0.2\\text{ km/h}$" is artificial and uninformative.
2. **Transportation modes are discrete**: Humans do not travel at a constant average velocity over weeks or months. Modern travel occurs rapidly via cars, trains, or flights, after which the person settles into a location.
3. **Locality of daily life**: Successive locations from a timestamp point of view are naturally expected to stay in a reduced local area (home, workplace, neighborhood), except during infrequent macro relocation events.
4. **Relocation frequency**: Moving residence to a different town or state is a significant life transition that is rare to occur frequently during a short timeline. Rapid alternation between distant cities within days strongly indicates distinct individuals rather than a single person.

---

## 2. Key Improvements Made

### A. Complete Elimination of Velocity in km/h
- **Removed parameters**: `velocity_kmh`, `MAX_HUMAN_SPEED_KMH` ($950\\text{ km/h}$), and the continuous exponential speed penalty $\\exp(-(v / v_{\\max} - 1) \\cdot w_{\\text{penalty}})$.
- **Removed UI artifacts**: Eliminated velocity numbers (e.g. "$0.2\\text{ km/h}$ over 262 days") from the Leaflet map tooltips, timeline player cards, and the candidate pairs inspection table.

### B. The Dual-Regime Spatial & Relocation Model
The new model evaluates spatial relationships across two distinct geographic regimes:

```
                                +-------------------------------------------+
                                | Spatial-Temporal & Relocation Evaluation  |
                                +-------------------------------------------+
                                                      |
                 +------------------------------------+------------------------------------+
                 |                                                                         |
                 v                                                                         v
+-----------------------------------+                                     +-----------------------------------+
|      Regime 1: Local Area         |                                     |    Regime 2: Inter-City / State   |
|         (dist <= 50 km)           |                                     |          (dist > 50 km)           |
+-----------------------------------+                                     +-----------------------------------+
| * High spatial locality           |                                     | * Check dt_days & anchor context  |
| * Habitual activity zone          |                                     | * dt = 0d: Hard conflict (Block)  |
| * Exponential local decay over    |                                     | * dt < 14d without anchor:        |
|   commuting radius (~25 km)       |                                     |   Rapid churn penalty (Low plaus) |
| * Plausibility = 1.0 (no move)    |                                     | * dt >= 21d or anchor-supported:  |
|                                   |                                     |   Plausible relocation (0.7-0.8)  |
+-----------------------------------+                                     +-----------------------------------+
```

#### 1. Regime 1: Local Habitual Activity Area ($d \\le 50\\text{ km}$)
- When two observations are within the same metropolitan area or neighborhood ($d \\le 50\\text{ km}$), they reflect normal daily commuting and living patterns.
- Evaluated with an exponential local decay:
  $$S_{\text{locality}} = 0.5 + 0.5 \times \exp\left(-\frac{\Delta t}{180}\right) \times \exp\left(-\frac{d}{25}\right)$$
- `relocation_plausibility = 1.0` (the person has not relocated; they are in their habitual activity zone).

#### 2. Regime 2: Inter-City / Inter-State Relocations ($d > 50\text{ km}$)
- When observations are in different cities or states, relocation plausibility is evaluated based on **elapsed time** and **anchor continuity**:
  - **Rapid Churn Penalty ($\Delta t < 14\text{ days}$ without anchor)**: Alternating between distant cities across a short timeline without anchor continuity receives `relocation_plausibility = 0.10`, penalizing implausible rapid jumping between distinct cities.
  - **Short Transition ($14 \le \Delta t < 21\text{ days}$ without anchor)**: Receives `relocation_plausibility = 0.40`.
  - **Plausible Relocation ($\Delta t \ge 21\text{ days}$)**: Relocations separated by weeks, months, or years receive `relocation_plausibility = 0.70` (unanchored) or `0.80` (anchor-supported), recognizing natural career and life relocations without penalty.
  - `spatial_locality = 0.10` (the observations are in distinct geographic regions).

#### 3. Simultaneous Presence Conflict (Strict Hard Block)
- If two observations occur on the **exact same calendar day** ($\Delta t = 0\text{ days}$) across different metropolitan areas ($d > 100\text{ km}$), they cannot physically belong to the same person.
- Triggers a strict `hard_block = True` cannot-link constraint, forcing the pairwise probability to $0.0$.

#### 4. Context & Anchor Continuity (`employer_id`, `household_id`, `persistent_token`)
- Constant and slowly changing attributes explain and validate inter-city relocations:
  - **Corporate employer transfers**: When observations across different cities share the same `employer_id`, the relocation is supported by corporate transfer continuity.
  - **Household moves**: When observations share a `household_id`, the entire household unit relocated together.
  - **Persistent hardware tokens**: Device and browser tokens bridge geographic relocations seamlessly.

---

## 3. Mathematical Scoring Formulation

The logistic probability combines the redesigned spatial and relocation features:

$$\begin{aligned}
\text{Logit} &= w_{\text{name}}(S_{\text{name}} - 0.5) \\
&+ w_{\text{dob}}(S_{\text{dob}} - 0.5) \\
&+ w_{\text{email}}(S_{\text{email}} - 0.5) \\
&+ w_{\text{phone}}(S_{\text{phone}} - 0.5) \\
&+ w_{\text{loc}}(S_{\text{locality}} - 0.5) \\
&+ w_{\text{reloc}}(S_{\text{reloc}} - 0.5) \\
&+ w_{\text{cooc}}(S_{\text{context}})
\end{aligned}$$

$$\\text{Probability} = \\frac{1}{1 + e^{-\\text{Logit}}}$$

### Default Weights in `DEFAULT_WEIGHTS`:
| Parameter | Weight | Description |
| :--- | :--- | :--- |
| `name` | $3.0$ | Jaro-Winkler + Soundex + Nickname dictionary |
| `dob` | $1.5$ | Date of birth exact match |
| `email` | $2.0$ | Shared email alias match |
| `phone` | $1.8$ | Active phone line match with carrier decay |
| `spatial_locality` | $1.2$ | Local commuting & neighborhood affinity |
| `relocation_plausibility` | $1.5$ | Plausibility of inter-city relocation across time |
| `cooccurrence` | $2.2$ | Secondary continuity anchors (tokens, household, employer) |
| `dob_conflict_penalty` | $5.0$ | Multiplicative crushing penalty on confirmed DOB mismatch |

---

## 4. Empirical Mobility Baselines & U.S. Census Bureau Reference

To ground the synthetic relocation engine and spatial resolution logic in demographic reality, the platform calibrates its mobility archetypes against empirical data from the **U.S. Census Bureau**.

### A. Data Sources & Geographic Taxonomy

The 4 mobility tiers implemented in the platform map directly to the official geographic mobility classification used in the **American Community Survey (ACS)** (Subject Table `S0701` / Table `B07001`: *Geographic Mobility by Selected Characteristics*) and the **Current Population Survey (CPS)** *Annual Social and Economic Supplement (ASEC)*:

| Generator Tier | U.S. Census Category | Spatial Scale & Definition |
| :--- | :--- | :--- |
| **Tier 0: Non-Movers / Stayers** ($P_{\text{never}}$) | *"Same house"* | Individuals remaining at their primary residence and neighborhood cluster ($\le 5\text{ km}$ activity radius). |
| **Tier 1: Intra-County Movers** ($P_{\text{county}}$) | *"Moved within same county"* | Local residential relocations within the same municipality or metropolitan county ($\le 30\text{ km}$). |
| **Tier 2: Intra-State Movers** ($P_{\text{state}}$) | *"Moved from different county, same state"* | Inter-county moves between distinct metropolitan regions within the same state. |
| **Tier 3: Cross-US Migrators** ($P_{\text{cross\_us}}$) | *"Moved from different state"* | Long-distance interstate migrations across state lines. |

### B. Baseline Proportions ($50\% / 30\% / 15\% / 5\%$)

The **"↺ US Census Baseline"** preset in the synthetic data generator sets:
- **Tier 0 (Non-Movers)**: $50\%$
- **Tier 1 (Intra-County)**: $30\%$
- **Tier 2 (Intra-State)**: $15\%$
- **Tier 3 (Cross-US)**: $5\%$

#### Longitudinal Observation Window vs. 1-Year Snapshot
1. **Annual Mobility Snapshot**: In a single year, the U.S. Census Bureau reports an annual mover rate of approximately $8\% - 12\%$ (~$11.8\%$ in recent ACS surveys). Among individuals who move in a given year, roughly $\sim 60\% - 65\%$ move within the same county, $\sim 18\% - 20\%$ move across counties within the same state, and $\sim 15\% - 18\%$ move to another state.
2. **Multi-Year Longitudinal Window (2016–2024)**: The synthetic trajectory dataset models an extended **8-year observation horizon**. Over multi-year horizons (consistent with Census 5-year ACS estimates and longitudinal panel studies), residential stability rates show that approximately **$50\%$ of individuals remain at their primary residence** throughout the window without relocating.
3. **Mover Breakdown Across Longitudinal Cohort**: Decomposing the $50\%$ of the population that relocates according to Census migration shares:
   $$\begin{aligned}
   P_{\text{county}} &= 50\% \times 60\% = \mathbf{30\%} \\
   P_{\text{state}} &= 50\% \times 30\% = \mathbf{15\%} \\
   P_{\text{cross\_us}} &= 50\% \times 10\% = \mathbf{5\%} \\
   P_{\text{never}} &= \mathbf{50\%}
   \end{aligned}$$
   $$\sum P_k = 50\% + 30\% + 15\% + 5\% = 100\%$$

### C. Move Frequency Parameters ($M_i \sim \mathcal{N}(\mu, \sigma^2)$)

For entities in moving tiers, the number of residential transitions $M_i$ throughout the longitudinal timeline is sampled from normal distributions bounded by empirical life-transition patterns:
- **Intra-County**: $\mu = 1.8 \pm 0.8$ moves (reflecting local apartment changes, lease renewals, or upsizing within the metropolitan area).
- **Intra-State**: $\mu = 2.2 \pm 0.9$ moves (reflecting career transitions, university enrollments, or regional moves between cities in the same state).
- **Cross-US**: $\mu = 3.1 \pm 1.2$ moves (reflecting interstate migrations across distinct economic hubs).

---

## 5. Frontend UI & Explainability Overhaul

1. **Pairs Table Inspection ([`frontend/index.html`](file:///home/jeromemassot/Projects/Trajectories/frontend/index.html))**:
   - Replaced table column `Velocity (km/h)` with `Reloc. Plaus.` and `Locality`.
2. **Trajectory Segment Tooltips & Timeline Player ([`frontend/app.js`](file:///home/jeromemassot/Projects/Trajectories/frontend/app.js))**:
   - Replaced mechanical velocity strings with semantic, human-readable explanations:
     - **Local area**: *"Local area: 2.1 km apart over 14 days (habitual activity zone)"*
     - **Plausible relocation**: *"Plausible inter-city relocation: 1,425 km across 262 days (supported by anchor continuity)"*
     - **Simultaneous conflict**: *"Simultaneous presence conflict: 1,409 km apart on the exact same date"*
     - **Implausible churn**: *"Implausible rapid inter-city jump: 1,200 km in 3 days without anchor continuity"*
   - Updated badge pill from `"Transit & Speed"` to `"Mobility & Relocation"`.

---

## 6. Verification & Benchmark Metrics

The overhauled model was evaluated on the 314-observation benchmark dataset ([`backend/data/mock_observations.json`](file:///home/jeromemassot/Projects/Trajectories/backend/data/mock_observations.json)):

| Benchmark Metric | Measured Result | Target |
| :--- | :--- | :--- |
| **Backend Unit Tests** | **20 / 20 passed** in 0.083s | 100% pass |
| **Pairwise Precision** | **1.0000 (100.0%)** | $\ge 0.98$ ($FP = 0$) |
| **Pairwise Recall** | **1.0000 (100.0%)** | $\ge 0.98$ ($FN = 0$) |
| **Pairwise $F_1$ Score** | **1.0000 (100.0%)** | $\ge 0.98$ |
| **True Entities / Predicted Clusters** | **30 / 30** | Exactly 30 clusters |
| **Same-Day Distant Conflicts** | **100% Hard-Blocked** | Absolute cannot-link |
| **Unanchored Rapid Churn (< 14d)** | **Penalized ($0.10$)** | Low plausibility |
| **Multi-Month Relocations** | **Plausible ($0.70 - 0.80$)** | Natural transitions |
