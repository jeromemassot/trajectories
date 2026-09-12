"""
Core entity-resolution engine for the Trajectories prototype.

Implements, in pure Python (no third-party dependencies, by design - see
README for why), a simplified version of the four-stage pipeline from the
project brief:

  1. Blocking            -> candidate_pairs()
  2. Pairwise scoring     -> score_pair() / score_all_pairs()
  3. Clustering           -> cluster_pairs()   (constrained union-find,
                                                 not full HMM/community
                                                 detection - see README)
  4. Evaluation           -> evaluate() against the hidden ground truth

Every score returned to the caller carries its per-dimension breakdown so
the UI can explain *why* two observations were or weren't linked - this
is the single most important property for a system whose output is a
probability, not a fact.
"""

import math
import itertools
from collections import defaultdict
from datetime import date


# ---------------------------------------------------------------------------
# 1. String / phonetic similarity  (pure-python Jaro-Winkler + Soundex)
# ---------------------------------------------------------------------------

def jaro_similarity(s1, s2):
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    match_distance = max(len1, len2) // 2 - 1
    match_distance = max(match_distance, 0)

    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    return (matches / len1 + matches / len2 +
            (matches - transpositions) / matches) / 3.0


def jaro_winkler(s1, s2, prefix_weight=0.1, max_prefix=4):
    if not s1 or not s2:
        return 0.0
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    jaro = jaro_similarity(s1, s2)
    prefix = 0
    for a, b in zip(s1[:max_prefix], s2[:max_prefix]):
        if a != b:
            break
        prefix += 1
    return jaro + prefix * prefix_weight * (1 - jaro)


_SOUNDEX_MAP = {
    **{c: "1" for c in "bfpv"}, **{c: "2" for c in "cgjkqsxz"},
    **{c: "3" for c in "dt"}, "l": "4", **{c: "5" for c in "mn"}, "r": "6",
}


def soundex(name):
    if not name:
        return ""
    name = name.lower()
    letters = [c for c in name if c.isalpha()]
    if not letters:
        return ""
    first = letters[0].upper()
    result = [first]
    prev = _SOUNDEX_MAP.get(letters[0], "")
    for c in letters[1:]:
        if c in "hw":
            continue
        code = _SOUNDEX_MAP.get(c, "")
        if code:
            if code != prev:
                result.append(code)
            prev = code
        else:
            prev = ""  # vowel separator resets consecutive consonants
    result = "".join(result) + "000"
    return result[:4]


NICKNAME_GROUPS = [
    {"robert", "rob", "bob", "bobby"}, {"william", "bill", "will", "billy"},
    {"james", "jim", "jimmy"}, {"elizabeth", "liz", "beth", "eliza"},
    {"jennifer", "jen", "jenny"}, {"michael", "mike", "mikey"},
    {"daniel", "dan", "danny"}, {"susan", "sue", "susie"},
    {"anthony", "tony"}, {"thomas", "tom", "tommy"}, {"matthew", "matt"},
    {"jessica", "jess"}, {"kevin", "kev"}, {"sarah", "sara"},
]
_NICKNAME_LOOKUP = {}
for group in NICKNAME_GROUPS:
    for n in group:
        _NICKNAME_LOOKUP[n] = group


def name_similarity(a, b):
    """Blend of exact/nickname/phonetic/edit-distance signal, in [0, 1]."""
    if not a or not b:
        return 0.5  # missing -> uninformative, not a penalty
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return 1.0
    if b in _NICKNAME_LOOKUP.get(a, set()) or a in _NICKNAME_LOOKUP.get(b, set()):
        return 0.95
    jw = jaro_winkler(a, b)
    phonetic_bonus = 0.15 if soundex(a) == soundex(b) and soundex(a) else 0.0
    return min(1.0, jw + phonetic_bonus)


# ---------------------------------------------------------------------------
# 2. Spatio-temporal features
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0
MAX_HUMAN_SPEED_KMH = 950.0   # ~ commercial flight cruise speed
TAU_DAYS = 365.0              # temporal decay time-constant
SIGMA_KM = 80.0               # spatial decay length-constant


def haversine_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def days_between(d1, d2):
    return abs((date.fromisoformat(d1) - date.fromisoformat(d2)).days)


def kinematic_check(o1, o2):
    """Returns (feasible: bool, velocity_kmh: float|None, hard_block: bool).

    hard_block=True is the 'anti-reflexive' constraint from the brief: two
    observations essentially simultaneous but far apart CANNOT belong to the
    same person, regardless of how similar their attributes look. This is
    injected as a permanent cannot-link, not just a low score.
    """
    if o1["lat"] is None or o2["lat"] is None:
        return True, None, False
    dist_km = haversine_km(o1["lat"], o1["lon"], o2["lat"], o2["lon"])
    dt_days = days_between(o1["timestamp"], o2["timestamp"])
    dt_hours = max(dt_days * 24.0, 0.5)  # floor to avoid div-by-zero for same-day
    velocity = dist_km / dt_hours
    if dist_km < 5:
        return True, velocity, False
    # Anti-reflexive constraint: same calendar day, different city (>150km) is impossible.
    # For dt_days >= 1, velocity check ensures travel feasibility based on elapsed time.
    hard_block = dt_days == 0 and dist_km > 150
    feasible = velocity <= MAX_HUMAN_SPEED_KMH
    return feasible, velocity, hard_block


def spatiotemporal_kernel(o1, o2):
    """Exponential decay over (time, distance) - rewards habitual anchors.
    When location is unknown, returns an uninformative neutral score (0.4)
    scaled by temporal decay, so it does not add an unjustified spatial bonus.
    """
    dt_days = days_between(o1["timestamp"], o2["timestamp"])
    time_factor = math.exp(-dt_days / TAU_DAYS)
    if o1["lat"] is None or o2["lat"] is None:
        return 0.4 * time_factor  # neutral baseline (aligns with the 0.4 logistic offset)
    dist_km = haversine_km(o1["lat"], o1["lon"], o2["lat"], o2["lon"])
    return time_factor * math.exp(-dist_km / SIGMA_KM)


# ---------------------------------------------------------------------------
# 3. Co-occurrence / shared-context features
# ---------------------------------------------------------------------------

def cooccurrence_score(o1, o2):
    """Shared household / employer / persistent token = strong continuity
    anchors, exactly the 'secondary anchors' the brief calls for to survive
    simultaneous name+address discontinuities."""
    score = 0.0
    if o1.get("persistent_token") and o1["persistent_token"] == o2.get("persistent_token"):
        score = max(score, 0.98)
    if o1.get("household_id") and o1["household_id"] == o2.get("household_id"):
        score = max(score, 0.35)
    if o1.get("employer_id") and o1["employer_id"] == o2.get("employer_id"):
        score = max(score, 0.3)
    return score


def dob_score(o1, o2):
    if not o1.get("dob") or not o2.get("dob"):
        return 0.5, False  # unknown -> neutral, no conflict
    if o1["dob"] == o2["dob"]:
        return 1.0, False
    return 0.0, True  # DOB is (near) immutable: a confirmed mismatch is disqualifying,
                       # not merely "a vote against" - handled like kinematic infeasibility


# ---------------------------------------------------------------------------
# 4. Blocking
# ---------------------------------------------------------------------------

def blocking_keys(o):
    keys = set()
    keys.add(("soundex", soundex(o["first_name"]), soundex(o["last_name"])))
    if o.get("persistent_token"):
        keys.add(("token", o["persistent_token"]))
    if o.get("household_id"):
        keys.add(("household", o["household_id"]))
    if o.get("dob"):
        keys.add(("dob_soundex", o["dob"][:4], soundex(o["first_name"])))  # birth year + first-name phoneme
    return keys


def candidate_pairs(observations):
    """LSH-style blocking: union candidates found under ANY shared key,
    rather than requiring one perfect key - this is what gives recall
    across a simultaneous name+address change."""
    buckets = defaultdict(list)
    for i, o in enumerate(observations):
        for k in blocking_keys(o):
            buckets[k].append(i)
    pairs = set()
    for members in buckets.values():
        if len(members) < 2 or len(members) > 60:
            continue  # skip mega-buckets (would defeat the point of blocking)
        for i, j in itertools.combinations(members, 2):
            pairs.add((min(i, j), max(i, j)))
    return pairs


# ---------------------------------------------------------------------------
# 5. Pairwise scoring
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "name": 3.0,
    "dob": 1.5,
    "spatiotemporal": 1.2,
    "cooccurrence": 2.5,
    "kinematic_penalty": 4.0,      # multiplies down the combined score, not additive
    "dob_conflict_penalty": 5.0,   # ditto, for a confirmed DOB mismatch
}


def extract_pair_features(o1, o2):
    """Extract invariant features for a pair of observations."""
    first_sim = name_similarity(o1["first_name"], o2["first_name"])
    last_sim = name_similarity(o1["last_name"], o2["last_name"])
    name_sim = 0.7 * first_sim + 0.3 * last_sim
    dob_sim, dob_conflict = dob_score(o1, o2)
    st_kernel = spatiotemporal_kernel(o1, o2)
    cooc = cooccurrence_score(o1, o2)
    feasible, velocity, hard_block = kinematic_check(o1, o2)

    return {
        "first_name_sim": round(first_sim, 3),
        "last_name_sim": round(last_sim, 3),
        "name_sim": round(name_sim, 4),
        "dob_sim": round(dob_sim, 3),
        "dob_conflict": dob_conflict,
        "spatiotemporal_kernel": round(st_kernel, 3),
        "cooccurrence": round(cooc, 3),
        "kinematic_feasible": feasible,
        "velocity_kmh": None if velocity is None else round(velocity, 1),
        "hard_block": hard_block,
    }


def compute_pair_score(features, weights=None):
    """Compute link probability from extracted features and given weights."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    name_sim = features["name_sim"]
    dob_sim = features["dob_sim"]
    dob_conflict = features["dob_conflict"]
    st_kernel = features["spatiotemporal_kernel"]
    cooc = features["cooccurrence"]
    feasible = features["kinematic_feasible"]
    velocity = features["velocity_kmh"]
    hard_block = features["hard_block"]

    # weighted linear combination -> logistic squashing, as in the brief's
    # P(O_i <-> O_j) = sigma(w_s Sim + w_t f_kinematic + w_c Context)
    linear = (w["name"] * (name_sim - 0.5) +
              w["dob"] * (dob_sim - 0.5) +
              w["spatiotemporal"] * (st_kernel - 0.4) +
              w["cooccurrence"] * cooc)
    prob = 1.0 / (1.0 + math.exp(-linear))

    # Near-immutable attributes are disqualifying signals, not just one vote
    # among many: a confirmed DOB mismatch or a kinematically impossible jump
    # crushes the score multiplicatively.
    if dob_conflict:
        prob *= math.exp(-w["dob_conflict_penalty"])
    if not feasible and velocity is not None:
        # smoothly crush (not a step function), so "slightly too fast" != "teleportation"
        overshoot = max(velocity / MAX_HUMAN_SPEED_KMH, 1.0)
        prob *= math.exp(-(overshoot - 1.0) * w["kinematic_penalty"])

    return {
        "score": max(0.0, min(1.0, prob)),
        "hard_block": hard_block,
        "features": {
            "first_name_sim": features["first_name_sim"],
            "last_name_sim": features["last_name_sim"],
            "dob_sim": features["dob_sim"],
            "dob_conflict": features["dob_conflict"],
            "spatiotemporal_kernel": features["spatiotemporal_kernel"],
            "cooccurrence": features["cooccurrence"],
            "kinematic_feasible": features["kinematic_feasible"],
            "velocity_kmh": features["velocity_kmh"],
        },
    }


def score_pair(o1, o2, weights=None):
    feats = extract_pair_features(o1, o2)
    return compute_pair_score(feats, weights)


def extract_all_candidate_features(observations):
    """Extract invariant features for all candidate pairs in a dataset once."""
    pairs = candidate_pairs(observations)
    candidate_features = []
    for i, j in sorted(pairs):
        f = extract_pair_features(observations[i], observations[j])
        candidate_features.append({"i": i, "j": j, "features": f})
    return candidate_features


def score_all_pairs(observations, weights=None, precomputed_features=None):
    if precomputed_features is not None:
        results = []
        for item in precomputed_features:
            r = compute_pair_score(item["features"], weights)
            r["i"], r["j"] = item["i"], item["j"]
            results.append(r)
        return results

    results = []
    for i, j in sorted(candidate_pairs(observations)):
        r = score_pair(observations[i], observations[j], weights)
        r["i"], r["j"] = i, j
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# 6. Clustering: constrained union-find
# ---------------------------------------------------------------------------

class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))
        self.members = [{i} for i in range(n)]

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if len(self.members[rx]) < len(self.members[ry]):
            rx, ry = ry, rx
        self.parent[ry] = rx
        self.members[rx] |= self.members[ry]
        self.members[ry] = None


def cluster_pairs(n, pair_scores, threshold):
    """Greedy agglomerative clustering: process edges by descending score,
    union unless doing so would merge two clusters that contain a hard
    cannot-link pair (anti-reflexive kinematic constraint or confirmed
    DOB mismatch), enforced transitively at the cluster level."""
    hard_blocks = defaultdict(set)
    for r in pair_scores:
        # Both anti-reflexive spatial teleportation and confirmed DOB conflicts
        # are absolute cannot-link constraints.
        if r["hard_block"] or r["features"]["dob_conflict"]:
            hard_blocks[r["i"]].add(r["j"])
            hard_blocks[r["j"]].add(r["i"])

    uf = UnionFind(n)
    # Exclude edges that are hard-blocked or have confirmed DOB conflict
    edges = [
        r for r in pair_scores
        if r["score"] >= threshold and not r["hard_block"] and not r["features"]["dob_conflict"]
    ]
    edges.sort(key=lambda r: -r["score"])

    accepted, rejected = [], []
    accepted_set = set()
    for r in edges:
        ra, rb = uf.find(r["i"]), uf.find(r["j"])
        if ra == rb:
            accepted.append(r)
            accepted_set.add((r["i"], r["j"]))
            continue
        members_a, members_b = uf.members[ra], uf.members[rb]
        conflict = any(b in hard_blocks[a] for a in members_a for b in members_b)
        if conflict:
            rejected.append(r)
            continue
        uf.union(r["i"], r["j"])
        accepted.append(r)
        accepted_set.add((r["i"], r["j"]))

    clusters = defaultdict(list)
    for idx in range(n):
        clusters[uf.find(idx)].append(idx)
    return list(clusters.values()), accepted, rejected, accepted_set


# ---------------------------------------------------------------------------
# 7. Evaluation against hidden ground truth
# ---------------------------------------------------------------------------

def evaluate(observations, clusters):
    """Pairwise evaluation computed in O(N) via contingency table."""
    truth = [o["entity_id_truth"] for o in observations]
    n = len(observations)
    total_pairs = n * (n - 1) // 2

    truth_counts = defaultdict(int)
    for t in truth:
        truth_counts[t] += 1

    cluster_counts = defaultdict(lambda: defaultdict(int))
    for cid, members in enumerate(clusters):
        for m in members:
            cluster_counts[cid][truth[m]] += 1

    tp = 0
    tp_fp = 0
    for cid, members in enumerate(clusters):
        size = len(members)
        tp_fp += size * (size - 1) // 2
        for count in cluster_counts[cid].values():
            tp += count * (count - 1) // 2

    tp_fn = sum(cnt * (cnt - 1) // 2 for cnt in truth_counts.values())
    fp = tp_fp - tp
    fn = tp_fn - tp
    tn = total_pairs - tp - fp - fn

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "n_observations": n,
        "n_true_entities": len(set(truth)),
        "n_predicted_clusters": len(clusters),
        "pairwise_precision": round(precision, 4),
        "pairwise_recall": round(recall, 4),
        "pairwise_f1": round(f1, 4),
        "pairwise_tp": tp, "pairwise_fp": fp, "pairwise_fn": fn, "pairwise_tn": tn,
    }


# ---------------------------------------------------------------------------
# 8. Orchestration
# ---------------------------------------------------------------------------

def resolve(observations, weights=None, threshold=0.5, precomputed_features=None):
    pair_scores = score_all_pairs(observations, weights, precomputed_features=precomputed_features)
    clusters, accepted, rejected, accepted_set = cluster_pairs(len(observations), pair_scores, threshold)
    metrics = evaluate(observations, clusters)

    entities = []
    for cid, members in enumerate(clusters):
        members_sorted = sorted(members, key=lambda m: observations[m]["timestamp"])
        obs_list = [observations[m] for m in members_sorted]
        truths = {o["entity_id_truth"] for o in obs_list}
        entities.append({
            "cluster_id": f"C{cid:03d}",
            "size": len(obs_list),
            "observation_ids": [o["observation_id"] for o in obs_list],
            "is_pure": len(truths) == 1,
            "ground_truth_entities": sorted(truths),
            "date_span": [obs_list[0]["timestamp"], obs_list[-1]["timestamp"]],
            "names_seen": sorted({f'{o["first_name"]} {o["last_name"]}' for o in obs_list}),
            "cities_seen": sorted({o["city"] for o in obs_list}),
        })
    entities.sort(key=lambda e: -e["size"])

    return {
        "metrics": metrics,
        "entities": entities,
        "pairs": [
            {
                "i": r["i"], "j": r["j"],
                "observation_id_i": observations[r["i"]]["observation_id"],
                "observation_id_j": observations[r["j"]]["observation_id"],
                "score": round(r["score"], 4),
                "hard_block": r["hard_block"],
                "features": r["features"],
                "linked": (r["i"], r["j"]) in accepted_set,
            }
            for r in pair_scores
        ],
        "threshold": threshold,
        "weights": {**DEFAULT_WEIGHTS, **(weights or {})},
    }
