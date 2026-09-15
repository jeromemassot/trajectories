# Date of Birth Noise & Resolution Upgrades Implemented

The synthetic data generator and entity resolution engine have been updated to support realistic Date of Birth (DOB) noise and boundary-tolerant matching.

---

## 1. Noise Profiles in Data Generation ([`data_gen.py`](file:///home/jeromemassot/Projects/Trajectories/backend/data_gen.py))

The generator introduces three distinct noise modes across observations:

1. **Year Only (`"YYYY"`)**: ~8.8% of observations surface only the 4-digit birth year (e.g. `"1984"`).
2. **Year-Month (`"YYYY-MM"`)**: ~8.5% of observations provide year and month precision without the day (e.g. `"1984-06"`).
3. **$\pm 1$ Day Shift (`"YYYY-MM-DD"`)**: ~11.4% of observations introduce a $\pm 1$ day typographical or timezone shift (e.g., true DOB `"1984-06-15"` reported as `"1984-06-14"` or `"1984-06-16"`).

Across the generated dataset ([`mock_observations.json`](file:///home/jeromemassot/Projects/Trajectories/backend/data/mock_observations.json), 306 observations across 30 entities):
- **Full Dates**: 235 (76.8%)
- **Year-Only**: 27 (8.8%)
- **Year-Month**: 26 (8.5%)
- **Missing DOB**: 18 (5.9%)
- **Shifted $\pm 1$ Day**: 35 observations spread across 15 different entities.

---

## 2. Resolution Engine Upgrades ([`resolution.py`](file:///home/jeromemassot/Projects/Trajectories/backend/resolution.py))

To prevent false entity splitting while still detecting genuine cross-individual birthdate mismatches:

- **Opposing Shifts Tolerance**: When observation $A$ is shifted $-1$ day and observation $B$ is shifted $+1$ day, the pairwise difference is **2 days** ($1 - (-1) = 2$). The comparator tolerates up to $\Delta t \le 2$ days ($0.88$ for 1-day difference, $0.78$ for 2-day difference) without triggering a hard conflict block (`dob_conflict=True`).
- **Month and Year Boundary Crossing**: If an individual born on Jan 1 is reported as Dec 31 of the previous year (or Feb 28/29 $\leftrightarrow$ Mar 1), [`is_date_compatible_with_partial`](file:///home/jeromemassot/Projects/Trajectories/backend/resolution.py) checks compatibility with a 1-day boundary buffer against `"YYYY"` or `"YYYY-MM"` records.
- **Partial Date Scoring**:
  - Exact full date match: `1.0`
  - Year-Month compatibility: `0.90`
  - Year-Only compatibility: `0.80`
  - Off-by-1 day: `0.88`
  - Off-by-2 days: `0.78`
  - Discrepancy $> 2$ days or incompatible year/month: `0.0` with `dob_conflict = True` (hard block).

---

## 3. Verification & Benchmark

- **Unit Test Suite**: 25/25 unit tests pass (`python3 -m unittest discover -s backend/tests`), including tests for partial dates, boundary crossings, off-by-one tolerance, and noise diversity.
- **Entity Resolution Benchmark**:
  - **Precision**: 100.0%
  - **Recall**: 100.0%
  - **F1 Score**: 1.0000 across all 30 entities and 306 observations.
- Documented in [DataGeneration.md](file:///home/jeromemassot/Projects/Trajectories/DataGeneration.md).
