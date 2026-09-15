# Data Generation & Human Mobility Archetypes

This document details the synthetic data generation engine ([`backend/data_gen.py`](file:///home/jeromemassot/Projects/Trajectories/backend/data_gen.py)) used in the Trajectories Entity Resolution platform. It describes the design rationale, the three human mobility archetypes, confounder models, kinematic constraints, and benchmark verification metrics.

---

## 1. Overview & Motivation

In previous iterations of the generator, synthetic individuals frequently oscillated back and forth between only two geographic locations in an artificial ping-pong pattern. Furthermore, consecutive sightings often repeated the exact same coordinate pair.

Real-world human mobility exhibits clear spatial structures:
1. People do not jump back and forth between distant cities on alternating weeks.
2. Most moves are local (within the same neighborhood or city district).
3. Moves outside the local area follow distinct life patterns: either relocations within a home state or inter-state migrations over multi-year horizons.

The overhauled generator addresses these limitations by introducing **three human mobility archetypes**, a rich geographic database of authentic US street addresses across 33 cities, and an explicit **zero consecutive coordinate duplicate** guarantee.

---

## 2. The Three Human Mobility Archetypes

The 18 primary latent individuals are divided evenly into three representative categories:

```
                                  +---------------------------------------+
                                  |      Human Mobility Archetypes        |
                                  +---------------------------------------+
                                                      |
            +-----------------------------------------+-----------------------------------------+
            |                                         |                                         |
            v                                         v                                         v
+-----------------------+                 +-----------------------+                 +-----------------------+
|      Category 1       |                 |      Category 2       |                 |      Category 3       |
|  Neighborhood Stayers |                 |   Intra-State Movers  |                 | Inter-State Migrators |
|     (E001 - E006)     |                 |     (E007 - E012)     |                 |     (E013 - E018)     |
+-----------------------+                 +-----------------------+                 +-----------------------+
| * Single neighborhood |                 | * 2-3 cities within   |                 | * 2-4 states across   |
| * Relocations < 5 km  |                 |   same state          |                 |   sampling period     |
| * Local venue hops    |                 | * Area code updates   |                 | * Long-distance moves |
+-----------------------+                 +-----------------------+                 +-----------------------+
```

### Category 1: Neighborhood Stayers (`E001` -- `E006`)
- **Behavior**: Individuals who reside long-term within a specific neighborhood district. When they change residential address, they remain strictly within the same neighborhood cluster.
- **Neighborhood Bounding**: Across all chronological observations, their maximum geographic span remains strictly bounded under $5\text{ km}$ (empirically $1.69\text{ km} - 4.62\text{ km}$).
- **Assigned Neighborhoods & Cities**:
  - `E001`: Brickell, Miami, FL (Max span: $1.80\text{ km}$)
  - `E002`: Downtown / Uptown, Dallas, TX (Max span: $2.02\text{ km}$)
  - `E003`: Back Bay, Boston, MA (Max span: $1.69\text{ km}$)
  - `E004`: Lincoln Park, Chicago, IL (Max span: $4.62\text{ km}$)
  - `E005`: Mission District, San Francisco, CA (Max span: $2.29\text{ km}$)
  - `E006`: Midtown, New York, NY (Max span: $3.76\text{ km}$)
- **Sighting Dynamics**: Sightings rotate through local coffee shops, offices, grocery stores, and apartments without consecutive coordinate repeats.

### Category 2: Intra-State Movers (`E007` -- `E012`)
- **Behavior**: Individuals who relocate between 2 to 3 cities exclusively within their state of origin.
- **Telecom Realism**: When relocating to a new city, the individual acquires a local phone number matching the destination city's area code, while email addresses accumulate or persist.
- **State Routes**:
  - `E007` (Texas): Dallas $\to$ Austin $\to$ Houston
  - `E008` (California): San Francisco $\to$ Los Angeles
  - `E009` (Florida): Miami $\to$ Tampa $\to$ Orlando
  - `E010` (New York): New York City $\to$ Albany
  - `E011` (Washington): Seattle $\to$ Tacoma $\to$ Spokane
  - `E012` (Illinois): Chicago $\to$ Naperville

### Category 3: Inter-State Migrators (`E013` -- `E018`)
- **Behavior**: Individuals who undertake long-distance migrations across state lines, residing in 2 to 4 distinct states over the 2016--2024 observation sampling window.
- **Migration Routes**:
  - `E013`: Boston, MA $\to$ Washington, DC $\to$ Atlanta, GA $\to$ Miami, FL (4 states)
  - `E014`: New York, NY $\to$ Chicago, IL $\to$ Denver, CO $\to$ Seattle, WA (4 states)
  - `E015`: Philadelphia, PA $\to$ Dallas, TX $\to$ Phoenix, AZ $\to$ Los Angeles, CA (4 states)
  - `E016`: Minneapolis, MN $\to$ Chicago, IL $\to$ Austin, TX (3 states)
  - `E017`: Detroit, MI $\to$ Denver, CO $\to$ Portland, OR (3 states)
  - `E018`: Atlanta, GA $\to$ Dallas, TX $\to$ San Diego, CA (3 states)

---

## 3. Confounder Populations (`E019` -- `E030`)

To ensure the entity resolution algorithm does not overfit to naive heuristics, 12 confounder entities (40% of the population) are injected:

1. **Household Confounders (`E019` -- `E024`)**:
   - 3 pairs of siblings or domestic partners sharing a household ID, residential landline, and home address.
   - Differentiated by distinct dates of birth, first names, and independent mobile/email records.
2. **Name-Collision Confounders (`E025` -- `E028`)**:
   - 2 pairs of unrelated individuals sharing identical first and last names (e.g., 'James Smith').
   - Reside in distant states with distinct dates of birth and simultaneous/contemporaneous observation dates that trigger hard kinematic impossibility blocks.
3. **Carrier Phone Reallocation Confounders (`E029` -- `E030`)**:
   - Person A (`Marcus Vance` in Boston) drops phone `+1-555-0199` in 2018.
   - Person B (`Clara Oswald` in Denver) is allocated that recycled number in 2021 (after a 3-year quarantine window).
   - The temporal decay kernel discounts the shared phone score based on elapsed time, preventing false positive merges.

---

## 4. Spatial Locality, Relocation Plausibility & Anti-Oscillation Guarantees

### Non-Consecutive Venue Sampling
Rather than alternating between two fixed coordinates, `sample_venue_sequence()` selects candidates from a pool of authentic city addresses, guaranteeing $c_{t} \neq c_{t-1}$:

```python
def sample_venue_sequence(pool, n_samples):
    seq = []
    prev = None
    for _ in range(n_samples):
        candidates = [p for p in pool if p != prev]
        chosen = random.choice(candidates)
        seq.append(chosen)
        prev = chosen
    return seq
```

### Post-Processing Duplicate Elimination
Even when confounder common dates or life events inject specific addresses, a post-processing validation step iterates over each entity's chronological trajectory. If $c_{t} == c_{t-1}$, $c_t$ is reassigned to an alternative venue in that same city, ensuring **0.0% consecutive identical coordinates**.

### Human-Centric Spatial & Relocation Model
Rather than calculating an artificial continuous velocity in km/h, the resolution engine evaluates human mobility across two distinct spatial regimes:
1. **Local Habitual Activity Area ($d \le 50\text{ km}$)**:
   - Evaluates whether successive sightings stay within the same local metropolitan/neighborhood commuting zone, with decaying affinity over distance and elapsed time.
2. **Inter-City / Inter-State Relocation ($d > 50\text{ km}$)**:
   - Relocations to different towns/states are rare over short timeframes. Sightings across distant cities separated by $< 14\text{ days}$ without anchor continuity are penalized as implausible rapid churn.
   - Genuine relocations separated by adequate elapsed time ($\ge 21\text{ days}$, months, or years) or supported by anchor continuity (employer transfers, household moves, persistent device tokens) are recognized as plausible life transition events.
3. **Simultaneous Presence Conflict (Hard Anti-Reflexive Block)**:
   - Two sightings on the exact same date ($\Delta t = 0\text{ days}$) across different metropolitan areas ($d > 100\text{ km}$) cannot physically belong to the same person, triggering an absolute cannot-link constraint (`hard_block = True`).

---

## 5. Realistic Email Lifecycles & Logical Email Evolution

In real-world data collection, individuals do not dump an ever-growing historical list of every email address they have ever created. Instead:
- At any single observation, an individual surfaces:
  - **Personal only (~50%)**: Their current active personal email.
  - **Personal + Professional (~35%)**: Their active personal email and their current corporate work email.
  - **Professional only (~10%)**: Business or workplace transaction.
  - **None (~5%)**: Email unrecorded or dropped.
- **Constraints Enforced**:
  - Every observation has at most 1 personal email and at most 1 professional email ($\le 2$ emails total).
  - Never multiple personal emails or multiple corporate emails on a single observation.
  - High stability between successive sightings, with smooth multi-year evolution (e.g. personal email provider upgrade from Yahoo to Gmail, or surname update upon marriage).
- **Logical Email Evolution Scoring**:
  - Exact match ($e_1 \cap e_2 \neq \emptyset$): **1.00** (`exact_match`).
  - Personal $\leftrightarrow$ Corporate complementary pair with matching username: **0.88** (`personal_work_pair`).
  - Provider migration / upgrade (e.g. Yahoo $\to$ Gmail) with matching username: **0.85** (`provider_migration`).
  - Unrecorded on either record: **0.50** (`missing`).
  - Disjoint incompatible emails: **0.20** (`disjoint`).

---

## 6. Date of Birth (DOB) Realism Noise

In real-world public records, credit data, and digital observations, dates of birth exhibit characteristic noise patterns:
1. **Privacy Redaction / Year Only (`"YYYY"`)**: ~10% of observations contain only the birth year (e.g. `"1984"`).
2. **Coarse Recording / Year and Month (`"YYYY-MM"`)**: ~10% of observations contain only the birth year and month (e.g. `"1984-07"`).
3. **Transcription & Timezone Off-by-One Discrepancies**: ~12% of observations differ from the true birth date by $\pm 1$ day before or after (e.g. `"1984-07-14"` or `"1984-07-16"` for a true DOB of `"1984-07-15"`).
4. **Unrecorded / Missing**: ~6% of observations have `None`.
5. **Exact Full Date (`"YYYY-MM-DD"`)**: ~62% of observations have the exact full date.

### Resolution Engine Tolerance ([`backend/resolution.py`](file:///home/jeromemassot/Projects/Trajectories/backend/resolution.py))
`dob_score(o1, o2)` accommodates this noise without triggering false hard blocks:
- **Full exact match**: $1.00$, `conflict = False`.
- **Full dates, $\Delta t = 1$ day**: $0.88$, `conflict = False` (supports month/year boundaries e.g. Dec 31 $\leftrightarrow$ Jan 1).
- **Full dates, $\Delta t = 2$ days** (opposing $\pm 1$ shifts): $0.78$, `conflict = False`.
- **Compatible full vs. partial date**: $0.90$ (year+month) or $0.80$ (year only), `conflict = False`.
- **Incompatible dates** (different months/years, $\Delta t > 2$ days): $0.00$, `conflict = True` (disqualifying hard block).

---

## 7. Verification & Benchmark Metrics

The generated dataset ([`backend/data/mock_observations.json`](file:///home/jeromemassot/Projects/Trajectories/backend/data/mock_observations.json)) was evaluated against the resolution engine at a clustering threshold of $0.65$:

| Metric | Measured Value | Benchmark Target |
| :--- | :--- | :--- |
| **Total Observations** | **306** | Multi-year realistic sampling |
| **True Latent Entities** | **30** | Exactly 30 entities |
| **Predicted Entity Clusters** | **30** | Exactly 30 clusters |
| **Year-Only DOBs (`^\d{4}$`)** | **27 (8.8%)** | Present |
| **Year-Month DOBs (`^\d{4}-\d{2}$`)** | **26 (8.5%)** | Present |
| **1-Day Shifted Entities** | **15 / 30 entities** | Multi-day variation present |
| **Max Emails per Observation** | **$\le 2$ ($\le 1$ personal, $\le 1$ work)** | No accumulating dumps |
| **Consecutive Identical Coordinates** | **0 (0.0%)** | 0 duplicates |
| **Category 1 Max Spatial Span** | **1.69 -- 4.62 km** | $< 10\text{ km}$ (neighborhood) |
| **Category 2 State Boundary** | **100% within origin state** | Single state ($\ge 2$ cities) |
| **Category 3 State Span** | **2 -- 4 distinct states** | $\ge 2$ states |
| **Two-City Ping-Pong Loops** | **0** | None |
| **Pairwise Precision** | **1.0000 (100%)** | $\ge 0.98$ ($FP = 0$) |
| **Pairwise Recall** | **1.0000 (100%)** | $\ge 0.98$ ($FN = 0$) |
| **Pairwise $F_1$ Score** | **1.0000 (100%)** | $\ge 0.98$ |
| **Pairwise True Positives ($TP$)** | **1,551** | -- |
| **Pairwise True Negatives ($TN$)** | **45,114** | -- |
| **Backend Unit Tests** | **25 / 25 passed** | 100% pass |

---

## 8. How to Regenerate

To regenerate the dataset and re-verify resolution metrics:

```bash
# Run data generator (updates backend/data/mock_observations.json)
python3 backend/data_gen.py

# Execute full backend test suite
python3 -m unittest discover -s backend/tests
```
