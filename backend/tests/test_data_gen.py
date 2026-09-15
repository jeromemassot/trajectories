"""Unit tests for the parameterized synthetic data generator (data_gen.py)."""

import unittest
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data_gen import make_population, summarize_dataset


class TestDataGen(unittest.TestCase):
    def test_make_population_defaults(self):
        """Default call should produce 306 observations across 30 entities."""
        obs, summary = make_population(return_summary=True)
        self.assertEqual(len(obs), 306)
        self.assertEqual(summary["total_observations"], 306)
        self.assertEqual(summary["total_entities"], 30)

        # Check required fields in all observations
        for o in obs:
            self.assertIn("observation_id", o)
            self.assertIn("entity_id_truth", o)
            self.assertIn("first_name", o)
            self.assertIn("last_name", o)
            self.assertIn("timestamp", o)

    def test_make_population_clean_zero_noise(self):
        """Zero noise preset should produce 100% full DOBs and 100% addresses."""
        obs, summary = make_population(
            enable_dob_noise=False,
            rate_dob_year_only=0.0,
            rate_dob_year_month=0.0,
            rate_dob_shift=0.0,
            drop_dob_rate=0.0,
            enable_name_noise=False,
            rate_first_noise=0.0,
            rate_last_noise=0.0,
            drop_address_rate=0.0,
            drop_phone_rate=0.0,
            drop_email_rate=0.0,
            return_summary=True,
        )
        self.assertGreater(len(obs), 0)
        dob_stats = summary["dob_stats"]
        self.assertEqual(dob_stats["missing"], 0)
        self.assertEqual(dob_stats["year_only"], 0)
        self.assertEqual(dob_stats["year_month"], 0)
        self.assertEqual(dob_stats["full"], len(obs))

        # Check that no addresses or coordinates were dropped
        for o in obs:
            self.assertIsNotNone(o["address"])
            self.assertIsNotNone(o["lat"])
            self.assertIsNotNone(o["lon"])

    def test_make_population_custom_archetypes(self):
        """Custom entity counts should match the requested configuration."""
        obs, summary = make_population(
            n_neighborhood=2,
            n_intrastate=3,
            n_interstate=2,
            n_household_pairs=1,
            n_name_collision_pairs=1,
            include_phone_reallocation=False,
            return_summary=True,
        )
        # Expected entities: 2 (Cat 1) + 3 (Cat 2) + 2 (Cat 3) + 2 (HH) + 2 (Name) = 11 entities
        expected_entities = 2 + 3 + 2 + 2 + 2
        self.assertEqual(summary["total_entities"], expected_entities)

    def test_summarize_dataset(self):
        """summarize_dataset should accurately compute statistics on raw observation list."""
        sample_obs = [
            {"observation_id": "O0001", "entity_id_truth": "E001", "dob": "1990-05-15",
             "address": "123 Main St", "phones": ["+1-555-0101"], "emails": ["a@b.com"],
             "persistent_token": "abc123456789", "employer_id": "EMP-1"},
            {"observation_id": "O0002", "entity_id_truth": "E001", "dob": "1990-05",
             "address": None, "phones": [], "emails": [],
             "persistent_token": None, "employer_id": None},
            {"observation_id": "O0003", "entity_id_truth": "E002", "dob": "1985",
             "address": "456 Oak St", "phones": ["+1-555-0102"], "emails": [],
             "persistent_token": "def123456789", "employer_id": None},
            {"observation_id": "O0004", "entity_id_truth": "E002", "dob": None,
             "address": "789 Pine St", "phones": [], "emails": ["c@d.com"],
             "persistent_token": None, "employer_id": "EMP-2"},
        ]
        summary = summarize_dataset(sample_obs)
        self.assertEqual(summary["total_observations"], 4)
        self.assertEqual(summary["total_entities"], 2)
        self.assertEqual(summary["dob_stats"]["full"], 1)
        self.assertEqual(summary["dob_stats"]["year_month"], 1)
        self.assertEqual(summary["dob_stats"]["year_only"], 1)
        self.assertEqual(summary["dob_stats"]["missing"], 1)
        self.assertEqual(summary["coverage"]["persistent_token_obs"], 2)
        self.assertEqual(summary["coverage"]["employer_obs"], 2)
        self.assertEqual(summary["coverage"]["address_obs"], 3)

    def test_make_population_custom_target_observations(self):
        """make_population should produce exactly the requested number of target observations."""
        for target in [100, 180, 250, 400]:
            obs, summary = make_population(target_obs=target, return_summary=True)
            self.assertEqual(len(obs), target)
            self.assertEqual(summary["total_observations"], target)


if __name__ == "__main__":
    unittest.main()
