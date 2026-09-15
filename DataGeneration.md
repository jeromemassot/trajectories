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

## 4. Kinematic Constraints & Anti-Oscillation Guarantees

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

### Kinematic Feasibility
The resolution engine enforces physical feasibility checks:
- $v > 900\text{ km/h}$: Hard anti-reflexive block ($FP = 0$).
- Same-day observations in different metropolitan areas ($d > 50\text{ km}$ on $\Delta t = 0$ days) are blocked from merging.

---

## 5. Verification & Benchmark Metrics

The generated dataset ([`backend/data/mock_observations.json`](file:///home/jeromemassot/Projects/Trajectories/backend/data/mock_observations.json)) was evaluated against the resolution engine at a clustering threshold of $0.65$:

| Metric | Measured Value | Benchmark Target |
| :--- | :--- | :--- |
| **Total Observations** | **314** | Multi-year realistic sampling |
| **True Latent Entities** | **30** | Exactly 30 entities |
| **Predicted Entity Clusters** | **30** | Exactly 30 clusters |
| **Consecutive Identical Coordinates** | **0 (0.0%)** | 0 duplicates |
| **Category 1 Max Spatial Span** | **1.69 -- 4.62 km** | $< 10\text{ km}$ (neighborhood) |
| **Category 2 State Boundary** | **100% within origin state** | Single state ($\ge 2$ cities) |
| **Category 3 State Span** | **2 -- 4 distinct states** | $\ge 2$ states |
| **Two-City Ping-Pong Loops** | **0** | None |
| **Pairwise Precision** | **1.0000 (100%)** | $\ge 0.98$ ($FP = 0$) |
| **Pairwise Recall** | **1.0000 (100%)** | $\ge 0.98$ ($FN = 0$) |
| **Pairwise $F_1$ Score** | **1.0000 (100%)** | $\ge 0.98$ |
| **Pairwise True Positives ($TP$)** | **1,604** | -- |
| **Pairwise True Negatives ($TN$)** | **47,537** | -- |
| **Backend Unit Tests** | **19 / 19 passed** | 100% pass |

---

## 6. How to Regenerate

To regenerate the dataset and re-verify resolution metrics:

```bash
# Run data generator (updates backend/data/mock_observations.json)
python3 backend/data_gen.py

# Execute full backend test suite
python3 -m unittest discover -s backend/tests
```
