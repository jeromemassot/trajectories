"""
Unit and integration tests for Trajectories resolution engine.
"""

import json
import math
import unittest
from pathlib import Path

import sys
TESTS_DIR = Path(__file__).parent
BACKEND_DIR = TESTS_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from resolution import (
    jaro_similarity,
    jaro_winkler,
    soundex,
    name_similarity,
    haversine_km,
    days_between,
    evaluate_spatial_and_relocation,
    kinematic_check,
    spatiotemporal_kernel,
    dob_score,
    email_score,
    phone_score,
    blocking_keys,
    cooccurrence_score,
    UnionFind,
    cluster_pairs,
    evaluate,
    resolve,
    extract_all_candidate_features,
)


class TestStringSimilarity(unittest.TestCase):
    def test_jaro_similarity_identical_and_empty(self):
        self.assertEqual(jaro_similarity("test", "test"), 1.0)
        self.assertEqual(jaro_similarity("", "test"), 0.0)
        self.assertEqual(jaro_similarity("test", ""), 0.0)
        self.assertEqual(jaro_similarity("", ""), 1.0)

    def test_jaro_winkler_prefix(self):
        # Common prefix gives boost
        jw = jaro_winkler("martha", "marhta")
        self.assertGreater(jw, 0.90)
        self.assertLessEqual(jw, 1.0)

    def test_soundex(self):
        self.assertEqual(soundex("Robert"), "R163")
        self.assertEqual(soundex("Rupert"), "R163")
        self.assertEqual(soundex("Ashcraft"), "A261")
        self.assertEqual(soundex(""), "")

    def test_name_similarity_nicknames_and_phonetics(self):
        # Nicknames
        self.assertEqual(name_similarity("Robert", "Bob"), 0.95)
        self.assertEqual(name_similarity("Liz", "Elizabeth"), 0.95)
        self.assertEqual(name_similarity("William", "Bill"), 0.95)
        # Exact match
        self.assertEqual(name_similarity("Amanda", "Amanda"), 1.0)
        # Missing
        self.assertEqual(name_similarity(None, "Smith"), 0.5)
        self.assertEqual(name_similarity("Smith", ""), 0.5)


class TestSpatioTemporalAndKinematics(unittest.TestCase):
    def test_haversine_known_distance(self):
        # NYC (40.7128, -74.0060) to Boston (42.3601, -71.0589) ~ 306 km
        dist = haversine_km(40.7128, -74.0060, 42.3601, -71.0589)
        self.assertAlmostEqual(dist, 306.0, delta=10.0)
        # Identical
        self.assertAlmostEqual(haversine_km(40.0, -74.0, 40.0, -74.0), 0.0, places=3)
        # None
        self.assertIsNone(haversine_km(None, -74.0, 40.0, -74.0))

    def test_days_between(self):
        self.assertEqual(days_between("2020-01-01", "2020-01-05"), 4)
        self.assertEqual(days_between("2020-01-05", "2020-01-01"), 4)

    def test_simultaneous_presence_conflict(self):
        # Same day, different cities (NYC and Boston ~306km) -> hard block!
        o1 = {"lat": 40.7128, "lon": -74.0060, "timestamp": "2020-06-01"}
        o2 = {"lat": 42.3601, "lon": -71.0589, "timestamp": "2020-06-01"}
        locality, reloc, hard_block, expl = evaluate_spatial_and_relocation(o1, o2)
        self.assertTrue(hard_block)
        self.assertEqual(locality, 0.0)
        self.assertEqual(reloc, 0.0)
        self.assertIn("Simultaneous presence conflict", expl)

    def test_local_habitual_activity_area(self):
        # Same neighborhood / metro area (< 50 km) -> high locality, plausibility 1.0, not blocked
        o1 = {"lat": 40.7128, "lon": -74.0060, "timestamp": "2020-06-01"}
        o2 = {"lat": 40.7484, "lon": -73.9857, "timestamp": "2020-06-05"}
        locality, reloc, hard_block, expl = evaluate_spatial_and_relocation(o1, o2)
        self.assertFalse(hard_block)
        self.assertEqual(reloc, 1.0)
        self.assertGreater(locality, 0.70)
        self.assertIn("Local area", expl)

    def test_relocation_plausibility_short_vs_long_timeline(self):
        # NYC to Boston (~306 km) across 3 days without anchor -> implausible rapid jump
        o1 = {"lat": 40.7128, "lon": -74.0060, "timestamp": "2020-06-01"}
        o2 = {"lat": 42.3601, "lon": -71.0589, "timestamp": "2020-06-04"}
        _, reloc_short, hard_block_short, expl_short = evaluate_spatial_and_relocation(o1, o2)
        self.assertFalse(hard_block_short)
        self.assertEqual(reloc_short, 0.10)
        self.assertIn("Implausible rapid inter-city jump", expl_short)

        # NYC to Boston across 90 days -> plausible macro relocation
        o3 = {"lat": 42.3601, "lon": -71.0589, "timestamp": "2020-09-01"}
        _, reloc_long, hard_block_long, expl_long = evaluate_spatial_and_relocation(o1, o3)
        self.assertFalse(hard_block_long)
        self.assertEqual(reloc_long, 0.70)
        self.assertIn("Plausible inter-city relocation", expl_long)

        # NYC to Boston with shared employer or device token across 10 days -> supported by anchor
        o4 = {"lat": 42.3601, "lon": -71.0589, "timestamp": "2020-06-11", "employer_id": "EMP-1"}
        o1_emp = {**o1, "employer_id": "EMP-1"}
        _, reloc_anchor, _, expl_anchor = evaluate_spatial_and_relocation(o1_emp, o4)
        self.assertEqual(reloc_anchor, 0.80)
        self.assertIn("supported by anchor continuity", expl_anchor)

    def test_spatial_missing_coordinates(self):
        # Missing coordinates return neutral baseline
        o1 = {"lat": None, "lon": None, "timestamp": "2020-01-01"}
        o2 = {"lat": 40.7128, "lon": -74.0060, "timestamp": "2020-01-01"}
        locality, reloc, hard_block, _ = evaluate_spatial_and_relocation(o1, o2)
        self.assertFalse(hard_block)
        self.assertEqual(locality, 0.5)
        self.assertEqual(reloc, 0.7)


class TestCooccurrenceAndDOB(unittest.TestCase):
    def test_dob_score(self):
        # Exact full match
        score, conflict = dob_score({"dob": "1990-05-15"}, {"dob": "1990-05-15"})
        self.assertEqual(score, 1.0)
        self.assertFalse(conflict)

        # 1-day off (timezone or recording shift)
        score, conflict = dob_score({"dob": "1990-05-15"}, {"dob": "1990-05-14"})
        self.assertEqual(score, 0.88)
        self.assertFalse(conflict)

        score, conflict = dob_score({"dob": "1990-05-15"}, {"dob": "1990-05-16"})
        self.assertEqual(score, 0.88)
        self.assertFalse(conflict)

        # 1-day off across month/year boundary (Dec 31 vs Jan 1)
        score, conflict = dob_score({"dob": "1989-12-31"}, {"dob": "1990-01-01"})
        self.assertEqual(score, 0.88)
        self.assertFalse(conflict)

        # 2-days off (opposing shifts +/- 1 day from true date)
        score, conflict = dob_score({"dob": "1990-05-14"}, {"dob": "1990-05-16"})
        self.assertEqual(score, 0.78)
        self.assertFalse(conflict)

        # Partial date: year and month
        score, conflict = dob_score({"dob": "1990-05-15"}, {"dob": "1990-05"})
        self.assertEqual(score, 0.90)
        self.assertFalse(conflict)

        score, conflict = dob_score({"dob": "1990-05"}, {"dob": "1990-05"})
        self.assertEqual(score, 0.90)
        self.assertFalse(conflict)

        # Partial date: year only
        score, conflict = dob_score({"dob": "1990-05-15"}, {"dob": "1990"})
        self.assertEqual(score, 0.80)
        self.assertFalse(conflict)

        score, conflict = dob_score({"dob": "1990"}, {"dob": "1990"})
        self.assertEqual(score, 0.80)
        self.assertFalse(conflict)

        # Conflicts: > 2 days difference
        score, conflict = dob_score({"dob": "1990-05-15"}, {"dob": "1990-05-18"})
        self.assertEqual(score, 0.0)
        self.assertTrue(conflict)

        # Conflicts: different months
        score, conflict = dob_score({"dob": "1990-05"}, {"dob": "1990-06"})
        self.assertEqual(score, 0.0)
        self.assertTrue(conflict)

        score, conflict = dob_score({"dob": "1990-05-15"}, {"dob": "1990-06-15"})
        self.assertEqual(score, 0.0)
        self.assertTrue(conflict)

        # Conflicts: different years
        score, conflict = dob_score({"dob": "1990"}, {"dob": "1985"})
        self.assertEqual(score, 0.0)
        self.assertTrue(conflict)

        score, conflict = dob_score({"dob": "1990-05-15"}, {"dob": "1985-02-10"})
        self.assertEqual(score, 0.0)
        self.assertTrue(conflict)

        # Missing
        score, conflict = dob_score({"dob": None}, {"dob": "1985-02-10"})
        self.assertEqual(score, 0.5)
        self.assertFalse(conflict)

    def test_cooccurrence(self):
        o1 = {"persistent_token": "TOK123", "household_id": "HH1", "employer_id": "EMP1"}
        o2 = {"persistent_token": "TOK123", "household_id": "HH1", "employer_id": "EMP1"}
        self.assertGreaterEqual(cooccurrence_score(o1, o2), 0.98)


class TestClusteringAndConstraints(unittest.TestCase):
    def test_transitive_dob_cannot_link(self):
        # A: DOB 1974
        # B: DOB None
        # C: DOB 1965
        # Even if (A, B) and (B, C) have high scores, (A, C) has a DOB conflict.
        # Agglomerative clustering must NOT merge A and C into the same cluster.
        pair_scores = [
            {
                "i": 0, "j": 1, "score": 0.85, "hard_block": False,
                "features": {"dob_conflict": False}
            },
            {
                "i": 1, "j": 2, "score": 0.80, "hard_block": False,
                "features": {"dob_conflict": False}
            },
            {
                "i": 0, "j": 2, "score": 0.10, "hard_block": False,
                "features": {"dob_conflict": True}  # Confirmed DOB conflict!
            },
        ]
        clusters, accepted, rejected, accepted_set = cluster_pairs(3, pair_scores, threshold=0.65)
        # Cluster for 0 and cluster for 2 must remain disjoint
        cluster_map = {}
        for cid, members in enumerate(clusters):
            for m in members:
                cluster_map[m] = cid
        self.assertNotEqual(cluster_map[0], cluster_map[2])


class TestEmailAndPhoneSimilarity(unittest.TestCase):
    def test_email_score_match(self):
        # Shared email address yields 1.0 anchor match
        o1 = {"emails": ["john.smith@gmail.com", "jsmith@corp.com"]}
        o2 = {"emails": ["john.smith@gmail.com"]}
        score, status = email_score(o1, o2)
        self.assertEqual(score, 1.0)
        self.assertEqual(status, "exact_match")

    def test_email_score_evolution(self):
        # Personal <-> Work complementary pair with matching username
        o1 = {"emails": ["john.smith@gmail.com"]}
        o2 = {"emails": ["john_smith@emp-1.com"]}
        score, status = email_score(o1, o2)
        self.assertEqual(score, 0.88)
        self.assertEqual(status, "personal_work_pair")

        # Personal email provider migration (e.g. Yahoo -> Gmail)
        o3 = {"emails": ["john.smith@yahoo.com"]}
        score3, status3 = email_score(o1, o3)
        self.assertEqual(score3, 0.85)
        self.assertEqual(status3, "provider_migration")

    def test_email_score_disjoint_and_missing(self):
        # Disjoint emails
        o1 = {"emails": ["john.smith@gmail.com"]}
        o2 = {"emails": ["jane.doe@yahoo.com"]}
        score, status = email_score(o1, o2)
        self.assertEqual(score, 0.2)
        self.assertEqual(status, "disjoint")

        # Missing email on either or both
        o_empty = {"emails": []}
        score, status = email_score(o1, o_empty)
        self.assertEqual(score, 0.5)
        self.assertEqual(status, "missing")

    def test_phone_score_same_day_vs_temporal_reallocation_decay(self):
        # Contemporaneous match (same day) -> 1.0
        o1 = {"phones": ["+1-212-555-0142"], "timestamp": "2020-01-01"}
        o2 = {"phones": ["+1-212-555-0142"], "timestamp": "2020-01-01"}
        score, status = phone_score(o1, o2)
        self.assertEqual(score, 1.0)
        self.assertEqual(status, "match")

        # Shared phone across 2 years (730 days) -> decayed towards neutral
        o3 = {"phones": ["+1-212-555-0142"], "timestamp": "2022-01-01"}
        score3, status3 = phone_score(o1, o3)
        self.assertAlmostEqual(score3, 0.5 + 0.5 * math.exp(-731 / 730.0), places=2)
        self.assertEqual(status3, "match")
        self.assertLess(score3, 0.70)

        # Shared phone across 6 years (carrier reallocation scenario) -> decays close to 0.5
        o4 = {"phones": ["+1-212-555-0142"], "timestamp": "2026-01-01"}
        score4, status4 = phone_score(o1, o4)
        self.assertAlmostEqual(score4, 0.5, delta=0.05)

    def test_phone_score_disjoint_and_missing(self):
        # Same-day disjoint phones
        o1 = {"phones": ["+1-212-555-0142"], "timestamp": "2020-01-01"}
        o2 = {"phones": ["+1-212-555-9999"], "timestamp": "2020-01-01"}
        score, status = phone_score(o1, o2)
        self.assertAlmostEqual(score, 0.2, places=2)
        self.assertEqual(status, "disjoint")

        # Missing phone
        score_miss, status_miss = phone_score(o1, {"phones": []})
        self.assertEqual(score_miss, 0.5)
        self.assertEqual(status_miss, "missing")

    def test_blocking_keys_include_email_and_phone(self):
        o = {
            "first_name": "James",
            "last_name": "Smith",
            "emails": ["james.smith@gmail.com"],
            "phones": ["+1-212-555-0142"],
        }
        keys = blocking_keys(o)
        self.assertIn(("email", "james.smith@gmail.com"), keys)
        self.assertIn(("phone", "+1-212-555-0142"), keys)


class TestEndToEndResolution(unittest.TestCase):
    def setUp(self):
        data_path = BACKEND_DIR / "data" / "mock_observations.json"
        with open(data_path) as f:
            self.observations = json.load(f)

    def test_benchmark_metrics_reach_100_percent_f1(self):
        cached = extract_all_candidate_features(self.observations)
        res = resolve(self.observations, threshold=0.65, precomputed_features=cached)
        metrics = res["metrics"]

        self.assertEqual(metrics["pairwise_precision"], 1.0)
        self.assertEqual(metrics["pairwise_recall"], 1.0)
        self.assertEqual(metrics["pairwise_f1"], 1.0)
        self.assertEqual(metrics["pairwise_fp"], 0)
        self.assertEqual(metrics["pairwise_fn"], 0)
        self.assertEqual(metrics["n_predicted_clusters"], 30)
        self.assertEqual(metrics["n_true_entities"], 30)

    def test_mobility_categories_and_trajectory_validity(self):
        from collections import defaultdict

        by_entity = defaultdict(list)
        for o in self.observations:
            by_entity[o["entity_id_truth"]].append(o)

        # 1. No consecutive identical coordinates
        consecutive_dupes = 0
        for eid, items in by_entity.items():
            items.sort(key=lambda x: x["timestamp"])
            for i in range(len(items) - 1):
                c1, c2 = items[i], items[i + 1]
                if c1["lat"] is not None and c2["lat"] is not None:
                    if c1["lat"] == c2["lat"] and c1["lon"] == c2["lon"]:
                        consecutive_dupes += 1
        self.assertEqual(consecutive_dupes, 0)

        # 2. Category 1: Neighborhood Stayers (E001-E006) stay within < 10 km
        for eid in [f"E{i:03d}" for i in range(1, 7)]:
            items = by_entity[eid]
            coords = [(x["lat"], x["lon"]) for x in items if x["lat"] is not None]
            max_span = max(
                haversine_km(lat1, lon1, lat2, lon2)
                for i, (lat1, lon1) in enumerate(coords)
                for lat2, lon2 in coords[i + 1 :]
            )
            self.assertLess(max_span, 10.0, f"Entity {eid} moved outside neighborhood: {max_span} km")

        # 3. Category 2: Intra-State Movers (E007-E012) move between 2-3 cities within the same state
        for eid in [f"E{i:03d}" for i in range(7, 13)]:
            items = by_entity[eid]
            cities = [x["city"] for x in items if x.get("city")]
            states = set(c.split(", ")[1] for c in cities if ", " in c)
            self.assertEqual(len(states), 1, f"Entity {eid} crossed states: {states}")
            unique_cities = set(cities)
            self.assertGreaterEqual(len(unique_cities), 2, f"Entity {eid} stayed in single city: {unique_cities}")

        # 4. Category 3: Inter-State Migrators (E013-E018) migrate across 2 to 4 distinct states
        for eid in [f"E{i:03d}" for i in range(13, 19)]:
            items = by_entity[eid]
            cities = [x["city"] for x in items if x.get("city")]
            states = set(c.split(", ")[1] for c in cities if ", " in c)
            self.assertGreaterEqual(len(states), 2, f"Entity {eid} did not cross states: {states}")

        # 5. No unnatural 2-city ping-pong oscillation loops (A -> B -> A -> B)
        for eid, items in by_entity.items():
            cities_seq = [x["city"] for x in items if x.get("city")]
            compressed = [cities_seq[0]]
            for c in cities_seq[1:]:
                if c != compressed[-1]:
                    compressed.append(c)
            for i in range(len(compressed) - 3):
                is_ping_pong = (
                    compressed[i] == compressed[i + 2]
                    and compressed[i + 1] == compressed[i + 3]
                    and compressed[i] != compressed[i + 1]
                )
                self.assertFalse(is_ping_pong, f"Entity {eid} exhibited 2-city ping-pong loop: {compressed}")

    def test_observation_email_realism_constraints(self):
        from resolution import PERSONAL_EMAIL_DOMAINS
        for o in self.observations:
            emails = o.get("emails", [])
            self.assertLessEqual(len(emails), 2, f"Observation {o['observation_id']} has > 2 emails: {emails}")
            p_count = sum(1 for e in emails if any(e.endswith("@" + d) for d in PERSONAL_EMAIL_DOMAINS))
            w_count = len(emails) - p_count
            self.assertLessEqual(p_count, 1, f"Observation {o['observation_id']} has > 1 personal email: {emails}")
            self.assertLessEqual(w_count, 1, f"Observation {o['observation_id']} has > 1 work email: {emails}")

    def test_cooccurrence_and_spatial_persistent_token_toggle(self):
        o1 = {"persistent_token": "abc123token", "household_id": None, "employer_id": None,
              "lat": 40.7128, "lon": -74.0060, "timestamp": "2020-01-01"}
        o2 = {"persistent_token": "abc123token", "household_id": None, "employer_id": None,
              "lat": 34.0522, "lon": -118.2437, "timestamp": "2020-01-10"}  # 9 days apart, cross-country

        # With persistent token enabled:
        self.assertEqual(cooccurrence_score(o1, o2, use_persistent_tokens=True), 0.98)
        _, reloc_with, _, _ = evaluate_spatial_and_relocation(o1, o2, use_persistent_tokens=True)
        # Rapid move supported by anchor has plausibility 0.80 / supported
        self.assertEqual(reloc_with, 0.80)

        # With persistent token disabled:
        self.assertEqual(cooccurrence_score(o1, o2, use_persistent_tokens=False), 0.0)
        _, reloc_without, _, _ = evaluate_spatial_and_relocation(o1, o2, use_persistent_tokens=False)
        # Rapid move without anchor is implausible: 0.10
        self.assertEqual(reloc_without, 0.10)

    def test_resolve_persistent_token_toggle(self):
        # Baseline threshold 0.95:
        # With token enabled -> 30 clusters, F1 = 1.000
        res_with = resolve(self.observations, threshold=0.95, use_persistent_tokens=True)
        self.assertEqual(res_with["metrics"]["n_predicted_clusters"], 30)
        self.assertEqual(res_with["metrics"]["pairwise_f1"], 1.0)
        self.assertGreater(res_with["metrics"]["token_anchored_pairs"], 0)
        self.assertTrue(res_with["use_persistent_tokens"])

        # With token disabled -> clusters begin fragmenting at threshold 0.95
        res_without = resolve(self.observations, threshold=0.95, use_persistent_tokens=False)
        self.assertGreater(res_without["metrics"]["n_predicted_clusters"], 30)
        self.assertLess(res_without["metrics"]["pairwise_f1"], 1.0)
        self.assertFalse(res_without["use_persistent_tokens"])

        # At threshold 0.98, disabling token causes significantly more fragmentation
        res_with_98 = resolve(self.observations, threshold=0.98, use_persistent_tokens=True)
        res_without_98 = resolve(self.observations, threshold=0.98, use_persistent_tokens=False)
        self.assertGreater(
            res_without_98["metrics"]["n_predicted_clusters"],
            res_with_98["metrics"]["n_predicted_clusters"]
        )

    def test_observation_dob_noise_diversity(self):
        import re
        from collections import defaultdict
        year_only = sum(1 for o in self.observations if o.get("dob") and re.match(r"^\d{4}$", o["dob"]))
        year_month = sum(1 for o in self.observations if o.get("dob") and re.match(r"^\d{4}-\d{2}$", o["dob"]))
        full_date = sum(1 for o in self.observations if o.get("dob") and re.match(r"^\d{4}-\d{2}-\d{2}$", o["dob"]))

        self.assertGreater(year_only, 0, "No year-only DOBs found in dataset")
        self.assertGreater(year_month, 0, "No year-month DOBs found in dataset")
        self.assertGreater(full_date, 0, "No full DOBs found in dataset")

        # Verify that some individuals have multiple distinct full dates (+/- 1 day shifts)
        entity_dobs = defaultdict(set)
        for o in self.observations:
            d = o.get("dob")
            if d and len(d) == 10:
                entity_dobs[o["entity_id_truth"]].add(d)

        shifted = [eid for eid, ds in entity_dobs.items() if len(ds) > 1]
        self.assertGreaterEqual(len(shifted), 5, f"Expected multiple entities with 1-day shifts, got {len(shifted)}")


if __name__ == "__main__":
    unittest.main()
