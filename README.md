# Trajectories — Temporal Entity Resolution Prototype

A proof-of-concept for estimating the probability that two independently
timestamped observations belong to the same real person, using name,
date-of-birth, location, timestamp, and shared-context (household/employer/
persistent-token) evidence — and clustering observations into reconstructed
"entities" (trajectories) accordingly.

This implements a **deliberately simplified** version of the pipeline
described in the project brief. See "What changed from the draft" below for
the reasoning.

## Quick start

No third-party packages required — everything is pure Python 3 standard
library plus vanilla HTML/CSS/JS (see "Why no dependencies" below).

```bash
cd backend
python3 data_gen.py     # (re)generates backend/data/mock_observations.json — already included
python3 server.py       # serves the API + frontend on http://localhost:8000
```

Then open **http://localhost:8000/** in a browser.

## What you're looking at

- **Pipeline controls** — the match threshold and per-dimension weights are
  live; every change re-runs resolution over the full dataset and re-renders
  the UI. This is meant to be played with, not just looked at.
- **Resolved entities** — the clusters the pipeline produced. A red card
  mixes more than one true person (over-merge); a banner above the list
  flags any true person the pipeline split into multiple clusters
  (under-merge). Ground truth is shown because this is a demo dataset — a
  real system obviously would not have it, which is exactly why the metrics
  panel exists: it's the stand-in for the labeled evaluation set you'd need
  in production.
- **Trajectory map** — a simple equirectangular scatter/path plot (no map
  tiles, no internet dependency) showing one entity's reconstructed
  chronological path across observed locations.
- **Candidate pairs** — every pair blocking produced, with its full feature
  breakdown (name/DOB/spatio-temporal/co-occurrence/velocity) and whether it
  was linked, rejected, or hard-blocked. This is the audit trail — for a
  system whose output is a probability, "why did it decide that" has to be
  answerable, and this tab is the answer.
- **Raw observations** — the actual input feed.

## Mock dataset

`backend/data_gen.py` generates ~290 synthetic observations for ~28 ground
truth individuals (seeded, reproducible), specifically constructed to
exercise the failure modes named in the brief:

| Scenario | What it tests |
|---|---|
| Maiden → married surname change | attribute mutation over time |
| Relocation to a new city | spatio-temporal continuity across a real gap |
| **Simultaneous** name change + relocation | the "discontinuity" case — no single attribute survives, so the pipeline must lean on household/token continuity |
| Siblings/spouses sharing surname + address + household id | entity chimerism risk (over-merging) |
| Two unrelated people with the identical full name in different cities | blocking/kinematic rejection of a name collision |
| Two people under the same name observed **on the same day, far apart** | the anti-reflexive / kinematic-impossibility hard constraint |
| Missing DOB / missing address on ~10-12% of observations | robustness to partial data |
| Nicknames, typos, OCR-style character transpositions on ~15-35% of name fields | string-similarity robustness |

Ground truth (`entity_id_truth`) is carried in the JSON purely for the
metrics panel; `resolution.py` never reads that field.

## Architecture

```
backend/
  data_gen.py     mock data generator
  resolution.py   the actual algorithm: blocking -> scoring -> clustering -> eval
  server.py       stdlib HTTP server: 3 JSON routes + static file serving
  data/mock_observations.json
frontend/
  index.html, styles.css, app.js    vanilla JS single-page app, no build step
```

`resolution.py` is the only file that matters algorithmically; everything
else is plumbing. It has zero dependency on `server.py`, so it's directly
unit-testable and directly portable into a different serving layer.

### Pipeline stages (mirroring the brief's 4-stage architecture)

1. **Blocking** (`candidate_pairs`) — LSH-style: each observation is hashed
   into several buckets (soundex(first)+soundex(last); birth-year +
   soundex(first); persistent token; household id) and any two observations
   sharing *any* bucket become a candidate pair. This is what gives recall
   across a simultaneous name+address change — the persistent-token and
   household buckets don't care that the name changed.
2. **Pairwise scoring** (`score_pair`) — a weighted linear combination of
   name similarity (Jaro-Winkler + phonetic + nickname table), DOB
   agreement, a spatio-temporal exponential-decay kernel, and a
   co-occurrence score (shared household/employer/persistent-token),
   squashed through a logistic function, exactly as
   `sigma(w_s·Sim + w_t·kinematic + w_c·Context)` in the brief. Two
   near-immutable signals — a **confirmed DOB mismatch** and a
   **kinematically impossible velocity** — are applied as *multiplicative*
   crushes on top of that score rather than additive votes, because "the
   birthdate doesn't match" should not be something enough co-occurring
   evidence can out-vote.
3. **Clustering** (`cluster_pairs`) — a constrained greedy union-find:
   candidate edges above threshold are unioned in descending score order,
   *unless* doing so would merge two clusters that contain a hard
   cannot-link pair. That cannot-link set is exactly the brief's
   anti-reflexive constraint: two observations within a day of each other
   but >150km apart are permanently forbidden from ending up in the same
   cluster, however similar everything else about them looks.
4. **Evaluation** (`evaluate`) — pairwise precision/recall/F1 against the
   hidden ground truth, purely for this demo.

### Default operating point

At the shipped defaults (threshold 0.65), with the transitive cannot-link
propagation for confirmed DOB mismatches, the pipeline reaches
**precision = 1.000, recall = 1.000, F1 = 1.000 (28/28 clusters)** on the mock
dataset out of the box (0 false merges, 0 false splits).

Crucially, confirmed DOB mismatches are enforced as **transitive cannot-link constraints**
in agglomerative clustering (alongside the anti-reflexive kinematic impossibility
constraint). This prevents intermediate observations with missing DOBs from
acting as transitive bridges between individuals with conflicting birthdates
(resolving the Amanda Brown name collision confounder).

Candidate pair features are also precomputed and cached on server startup, allowing
live threshold and weight slider adjustments to re-cluster in **<15 ms** for
instantaneous UI feedback.

### Running tests

An automated test suite covering phonetic matching, kinematics, spatio-temporal
decay, constraint propagation, and end-to-end resolution is included:

```bash
python3 -m unittest discover -s backend/tests -v
```

## Why no third-party dependencies

This prototype was built in a sandboxed environment with package
installation blocked (pip/apt egress was refused end-to-end while building
this). Rather than write code that could not be tested, everything was
implemented in the Python standard library (a hand-rolled Jaro-Winkler,
Soundex, haversine distance, and union-find) and vanilla JS (no CDN
libraries, no build step). This turned out to be a reasonable place to land
for a POC anyway: `git clone && python3 server.py` with no install step at
all. If you take this further, the natural real upgrade path is:

- `resolution.py` stays almost unchanged; swap the hand-rolled string
  metrics for `jellyfish` (Jaro-Winkler/Damerau-Levenshtein/Double
  Metaphone) and character-level learned edit distances.
- `server.py` becomes a thin FastAPI app exposing the same 3 routes
  (`GET /api/dataset`, `POST /api/resolve`, `GET /api/health`) — the
  handler bodies barely change.
- Union-find clustering is replaced with the brief's temporal community
  detection (Louvain/Infomap on the weighted observation graph) once cluster
  sizes and pairwise ambiguity make greedy agglomeration too crude — see the
  scoping notes below.

## What changed from the draft, and why

See the accompanying write-up (delivered alongside this code, and saved to
the project) for the full review. In short, for this first POC:

- **HMM / Multi-Hypothesis Tracking is deferred.** It's the right long-run
  answer for resolving long-term drift the pairwise scores can't settle on
  their own, but it needs a working baseline and labeled data to tune
  transition probabilities against first. Constrained greedy clustering is
  the honest MVP substitute and is what's implemented here.
- **Temporal Louvain/Infomap is deferred** for the same reason — community
  detection tuning needs a corpus large enough for its parameters to mean
  something; at POC scale (dozens to low hundreds of entities) it would
  mostly reproduce what union-find already gives you, at much higher
  implementation cost.
- **LSH blocking is real but simplified**: bucket-based (soundex + geohash-
  like birth-year/household/token keys) rather than true locality-sensitive
  hashing over continuous embeddings. At POC scale it doesn't need to be
  more than that; at production scale (millions of observations) it would.
- **The "learned edit distance via character-level Transformers" line from
  the draft is out of scope for a POC** — Jaro-Winkler + phonetic + a
  nickname table is the appropriate starting point; a learned model needs
  labeled transition pairs this project doesn't have yet.
- **DOB mismatch is treated as a near-hard constraint**, not merely a scored
  feature, because it isn't actually a "vote" in the same sense mutable
  attributes are — see the multiplicative-crush note above. This was found
  by testing: the original purely-additive scoring let the sibling/spouse
  confounder over-merge because shared household + same surname could
  out-vote a *known, confirmed* DOB mismatch. That's a correctness bug in a
  purely-additive design, not a modeling nuance.
