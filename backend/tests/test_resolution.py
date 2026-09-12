"""
Unit and integration tests for Trajectories resolution engine.
"""

import json
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
    kinematic_check,
    spatiotemporal_kernel,
    dob_score,
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

    def test_kinematic_check_anti_reflexive(self):
        # Same day, different cities (NYC and Boston ~306km) -> hard block!
        o1 = {"lat": 40.7128, "lon": -74.0060, "timestamp": "2020-06-01"}
        o2 = {"lat": 42.3601, "lon": -71.0589, "timestamp": "2020-06-01"}
        feasible, velocity, hard_block = kinematic_check(o1, o2)
        self.assertTrue(hard_block)

        # Same day, extreme distance (NYC to Detroit ~800km in <=30 min = 1600 km/h) -> infeasible velocity!
        o3 = {"lat": 42.3314, "lon": -83.0458, "timestamp": "2020-06-01"}
        feasible3, velocity3, hard_block3 = kinematic_check(o1, o3)
        self.assertTrue(hard_block3)
        self.assertFalse(feasible3)

    def test_kinematic_check_consecutive_days(self):
        # Consecutive days between NYC and Boston -> physically feasible!
        o1 = {"lat": 40.7128, "lon": -74.0060, "timestamp": "2020-06-01"}
        o2 = {"lat": 42.3601, "lon": -71.0589, "timestamp": "2020-06-02"}
        feasible, velocity, hard_block = kinematic_check(o1, o2)
        self.assertFalse(hard_block)  # Not a hard anti-reflexive block
        self.assertTrue(feasible)     # Feasible velocity (~12.7 km/h over 24h)

    def test_spatiotemporal_kernel_missing_coordinates(self):
        # Missing coordinates should return neutral baseline 0.4 on same day
        o1 = {"lat": None, "lon": None, "timestamp": "2020-01-01"}
        o2 = {"lat": 40.7128, "lon": -74.0060, "timestamp": "2020-01-01"}
        k = spatiotemporal_kernel(o1, o2)
        self.assertAlmostEqual(k, 0.4, places=3)


class TestCooccurrenceAndDOB(unittest.TestCase):
    def test_dob_score(self):
        # Match
        score, conflict = dob_score({"dob": "1990-05-15"}, {"dob": "1990-05-15"})
        self.assertEqual(score, 1.0)
        self.assertFalse(conflict)

        # Conflict
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
        self.assertEqual(metrics["n_predicted_clusters"], 28)
        self.assertEqual(metrics["n_true_entities"], 28)


if __name__ == "__main__":
    unittest.main()
