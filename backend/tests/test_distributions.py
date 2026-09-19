"""Unit tests for observation count distributions, 4-tier relocation model, and massive generator."""

import os
import tempfile
import unittest
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from massive_gen import (
    sample_obs_count,
    sample_relocation_tier,
    sample_move_count,
    generate_person_stream,
    generate_preview_sample,
    BatchGenerationJob,
    AddressSynthesizer,
    CarrierNetwork,
)
from data_gen import make_population


class TestDistributionsAndRelocation(unittest.TestCase):
    def test_sample_obs_count_gaussian(self):
        """Gaussian distribution should have mean close to target and respect min clamp."""
        samples = [sample_obs_count("gaussian", mean_val=15.0, std_val=3.0, min_val=4) for _ in range(500)]
        avg = sum(samples) / len(samples)
        self.assertAlmostEqual(avg, 15.0, delta=0.6)
        self.assertTrue(all(s >= 4 for s in samples))

    def test_sample_obs_count_negative_binomial(self):
        """Negative Binomial distribution should generate positive counts near target mean."""
        samples = [sample_obs_count("negative_binomial", mean_val=12.0, std_val=4.0, min_val=2) for _ in range(500)]
        avg = sum(samples) / len(samples)
        self.assertAlmostEqual(avg, 12.0, delta=1.2)
        self.assertTrue(all(s >= 2 for s in samples))

    def test_sample_obs_count_log_normal(self):
        """Log-Normal distribution should produce positive counts with right-skew."""
        samples = [sample_obs_count("log_normal", mean_val=10.0, std_val=4.0, min_val=2) for _ in range(500)]
        self.assertTrue(all(s >= 2 for s in samples))
        self.assertGreater(max(samples), 15)

    def test_sample_obs_count_uniform_and_fixed(self):
        """Uniform and Fixed distributions should strictly adhere to boundaries."""
        samples_fixed = [sample_obs_count("fixed", mean_val=8.0) for _ in range(100)]
        self.assertTrue(all(s == 8 for s in samples_fixed))

        samples_uniform = [sample_obs_count("uniform", mean_val=10.0, std_val=2.0) for _ in range(200)]
        self.assertTrue(all(8 <= s <= 12 for s in samples_uniform))

    def test_sample_relocation_tier(self):
        """Categorical sampling should reflect the specified proportions."""
        # 70% never, 30% cross_us
        samples = [sample_relocation_tier(0.70, 0.0, 0.0, 0.30) for _ in range(1000)]
        p_never = samples.count("never") / len(samples)
        self.assertAlmostEqual(p_never, 0.70, delta=0.06)

    def test_sample_move_count_tiers(self):
        """Never movers have 0 moves; mover tiers have >= 1 moves."""
        cfg = {"mean_county_moves": 2.0, "std_county_moves": 0.5}
        self.assertEqual(sample_move_count("never", cfg), 0)
        moves = [sample_move_count("county", cfg) for _ in range(200)]
        self.assertTrue(all(m >= 1 for m in moves))
        avg = sum(moves) / len(moves)
        self.assertAlmostEqual(avg, 2.0, delta=0.2)

    def test_zero_consecutive_duplicate_coordinates(self):
        """Option A streaming generator must guarantee 0.0% consecutive identical coordinates."""
        addr_synth = AddressSynthesizer()
        carrier = CarrierNetwork()
        cfg = {
            "obs_distribution": "gaussian",
            "mean_obs_per_person": 20.0,
            "std_obs_per_person": 4.0,
            "pct_never_moved": 0.25,
            "pct_county_moved": 0.25,
            "pct_state_moved": 0.25,
            "pct_cross_us_moved": 0.25,
        }
        for e_idx in range(1, 40):
            obs_list, tier, _ = generate_person_stream(
                person_idx=e_idx,
                entity_id=f"E{e_idx:03d}",
                config=cfg,
                addr_synth=addr_synth,
                carrier=carrier,
            )
            for i in range(1, len(obs_list)):
                c_prev = (obs_list[i - 1]["lat"], obs_list[i - 1]["lon"])
                c_curr = (obs_list[i]["lat"], obs_list[i]["lon"])
                # If neither coordinate is dropped, they must not be identical
                if c_prev[0] is not None and c_curr[0] is not None:
                    self.assertNotEqual(c_prev, c_curr, f"Duplicate consecutive coords found for entity E{e_idx:03d}")

    def test_make_population_statistical_mode(self):
        """make_population with n_individuals and relocation percentages should run properly."""
        obs, summary = make_population(
            n_individuals=25,
            obs_distribution="gaussian",
            mean_obs_per_person=8.0,
            std_obs_per_person=2.0,
            pct_never_moved=0.50,
            pct_county_moved=0.30,
            pct_state_moved=0.10,
            pct_cross_us_moved=0.10,
            pct_household=8.0,
            pct_collision=4.0,
            return_summary=True,
        )
        self.assertEqual(summary["total_entities"], 25)
        self.assertGreater(summary["total_observations"], 100)
        self.assertLess(summary["total_observations"], 300)

    def test_batch_streaming_generation(self):
        """BatchGenerationJob should stream valid JSONL and CSV files to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "test_stream.jsonl"
            job = BatchGenerationJob()
            cfg = {
                "n_individuals": 150,
                "mean_obs_per_person": 6.0,
                "std_obs_per_person": 1.5,
                "pct_never_moved": 0.40,
                "pct_county_moved": 0.30,
                "pct_state_moved": 0.20,
                "pct_cross_us_moved": 0.10,
                "seed": 99,
            }
            ok, job_id = job.start(cfg, str(jsonl_path))
            self.assertTrue(ok)
            # Wait for completion
            while job.get_status()["status"] == "running":
                pass
            status = job.get_status()
            self.assertEqual(status["status"], "completed")
            self.assertGreater(status["rows_written"], 500)
            self.assertTrue(jsonl_path.exists())
            self.assertGreater(jsonl_path.stat().st_size, 10000)

    def test_generate_preview_sample(self):
        """generate_preview_sample should return an in-memory sample with diverse tiers."""
        cfg = {
            "mean_obs_per_person": 10.0,
            "pct_never_moved": 0.40,
            "pct_county_moved": 0.30,
            "pct_state_moved": 0.20,
            "pct_cross_us_moved": 0.10,
        }
        rows, summary = generate_preview_sample(cfg, target_obs=250)
        self.assertGreaterEqual(len(rows), 100)
        self.assertTrue(summary["sample_preview"])
        self.assertIn("mobility_tiers", summary)
        self.assertGreater(summary["n_entities"], 5)


    def test_zero_post_relocation_returns_to_retired_residences(self):
        """Individuals who relocate must never return to any previously held residential address."""
        addr_synth = AddressSynthesizer()
        carrier = CarrierNetwork()
        cfg = {
            "obs_distribution": "gaussian",
            "mean_obs_per_person": 20.0,
            "std_obs_per_person": 3.0,
            "min_obs_per_person": 15,
            "pct_never_moved": 0.0,
            "pct_county_moved": 0.35,
            "pct_state_moved": 0.35,
            "pct_cross_us_moved": 0.30,
        }
        for e_idx in range(1, 50):
            obs_list, tier, moves = generate_person_stream(
                person_idx=e_idx,
                entity_id=f"E{e_idx:03d}",
                config=cfg,
                addr_synth=addr_synth,
                carrier=carrier,
                sub_seed=500 + e_idx,
            )
            # Find all residential relocations and ensure prior residences are never visited post-move
            # For each address, record the index of its first and last appearance
            addr_history = {}
            for idx, o in enumerate(obs_list):
                addr = o.get("address")
                if addr:
                    addr_history.setdefault(addr, []).append(idx)

            # In an acyclic trajectory, once an individual moves to a new city,
            # no prior city's addresses should appear in subsequent observations
            seen_cities = []
            for o in obs_list:
                c = o.get("city")
                if not seen_cities or seen_cities[-1] != c:
                    self.assertNotIn(c, seen_cities, f"Entity E{e_idx:03d} returned to previously exited city {c}")
                    seen_cities.append(c)


if __name__ == "__main__":
    unittest.main()

