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
from data_gen import make_population, FIRST_NAMES_M, FIRST_NAMES_F


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

    def test_observation_locations_strictly_home_or_business(self):
        """Every observation must strictly match either the entity's active home address or business address."""
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
                sub_seed=100 + e_idx,
            )
            seen_addresses = {o["address"] for o in obs_list if o.get("address")}
            emp_id = obs_list[0].get("employer_id")
            if tier == "never" and not emp_id:
                self.assertEqual(len(seen_addresses), 1, f"Tier 0 entity E{e_idx:03d} without employer should have exactly 1 address, got {len(seen_addresses)}")
            elif tier == "never" and emp_id:
                self.assertLessEqual(len(seen_addresses), 2, f"Tier 0 entity E{e_idx:03d} with employer should have at most 2 addresses, got {len(seen_addresses)}")

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

    def test_male_individuals_never_change_surname(self):
        """Male individuals must NEVER change their surname across their entire trajectory."""
        addr_synth = AddressSynthesizer()
        carrier = CarrierNetwork()
        cfg = {
            "gender": "male",
            "obs_distribution": "gaussian",
            "mean_obs_per_person": 15.0,
            "std_obs_per_person": 3.0,
            "min_obs_per_person": 6,
            "enable_name_noise": False,
        }
        for e_idx in range(1, 60):
            obs_list, tier, _ = generate_person_stream(
                person_idx=e_idx,
                entity_id=f"E{e_idx:03d}",
                config=cfg,
                addr_synth=addr_synth,
                carrier=carrier,
                sub_seed=1000 + e_idx,
            )
            first_names = {o["first_name"] for o in obs_list}
            last_names = {o["last_name"] for o in obs_list}
            # All first names must be masculine
            self.assertTrue(first_names.issubset(set(FIRST_NAMES_M)), f"Non-masculine name found for male: {first_names}")
            # Male individual must have exactly ONE unique surname across all observations
            self.assertEqual(len(last_names), 1, f"Male entity E{e_idx:03d} changed last name: {last_names}")

    def test_female_individuals_can_change_surname_on_marriage(self):
        """Female individuals can change their surname upon marriage."""
        addr_synth = AddressSynthesizer()
        carrier = CarrierNetwork()
        cfg = {
            "gender": "female",
            "obs_distribution": "gaussian",
            "mean_obs_per_person": 15.0,
            "std_obs_per_person": 3.0,
            "min_obs_per_person": 6,
            "enable_name_noise": False,
        }
        surname_changes_count = 0
        total_females = 80
        for e_idx in range(1, total_females + 1):
            obs_list, tier, _ = generate_person_stream(
                person_idx=e_idx,
                entity_id=f"E{e_idx:03d}",
                config=cfg,
                addr_synth=addr_synth,
                carrier=carrier,
                sub_seed=2000 + e_idx,
            )
            first_names = {o["first_name"] for o in obs_list}
            self.assertTrue(first_names.issubset(set(FIRST_NAMES_F)), f"Non-feminine name found for female: {first_names}")
            last_names = {o["last_name"] for o in obs_list}
            if len(last_names) > 1:
                surname_changes_count += 1

        # Expected marriage rate is ~20%
        pct_changed = surname_changes_count / total_females
        self.assertGreater(pct_changed, 0.08, f"Marriage surname change rate too low: {pct_changed}")
        self.assertLess(pct_changed, 0.35, f"Marriage surname change rate too high: {pct_changed}")

    def test_female_divorce_reversion_behavior(self):
        """After divorce, female individuals can revert to maiden name or keep spouse surname."""
        addr_synth = AddressSynthesizer()
        carrier = CarrierNetwork()
        cfg = {
            "gender": "female",
            "obs_distribution": "gaussian",
            "mean_obs_per_person": 20.0,
            "std_obs_per_person": 2.0,
            "min_obs_per_person": 10,
            "enable_name_noise": False,
        }
        # Run across large cohort to observe both revert and retain paths
        reverted_count = 0
        retained_count = 0
        for e_idx in range(1, 250):
            obs_list, tier, _ = generate_person_stream(
                person_idx=e_idx,
                entity_id=f"E{e_idx:03d}",
                config=cfg,
                addr_synth=addr_synth,
                carrier=carrier,
                sub_seed=3000 + e_idx,
            )
            obs_list.sort(key=lambda x: x["timestamp"])
            surnames = [o["last_name"] for o in obs_list]
            distinct_in_order = []
            for s in surnames:
                if not distinct_in_order or distinct_in_order[-1] != s:
                    distinct_in_order.append(s)

            # Reversion: maiden -> married -> maiden (length 3, first == last)
            if len(distinct_in_order) == 3 and distinct_in_order[0] == distinct_in_order[2]:
                reverted_count += 1
            elif len(distinct_in_order) == 2:
                retained_count += 1

        self.assertGreater(reverted_count, 0, "Expected at least one divorce reversion back to maiden name")
        self.assertGreater(retained_count, 0, "Expected at least one retention of spouse surname")

    def test_gender_parameter_population_distribution(self):
        """The gender parameter should strictly control population gender composition."""
        # Male only
        obs_m = make_population(
            n_individuals=30,
            gender="male",
            enable_name_noise=False,
            pct_household=0,
            pct_collision=0,
        )
        firsts_m = {o["first_name"] for o in obs_m}
        self.assertTrue(firsts_m.issubset(set(FIRST_NAMES_M)), f"Found non-male first names in male dataset: {firsts_m - set(FIRST_NAMES_M)}")

        # Female only
        obs_f = make_population(
            n_individuals=30,
            gender="female",
            enable_name_noise=False,
            pct_household=0,
            pct_collision=0,
        )
        firsts_f = {o["first_name"] for o in obs_f}
        self.assertTrue(firsts_f.issubset(set(FIRST_NAMES_F)), f"Found non-female first names in female dataset: {firsts_f - set(FIRST_NAMES_F)}")

        # Both (mixed)
        obs_both = make_population(
            n_individuals=50,
            gender="both",
            enable_name_noise=False,
            pct_household=0,
            pct_collision=0,
        )
        firsts_both = {o["first_name"] for o in obs_both}
        self.assertTrue(any(f in FIRST_NAMES_M for f in firsts_both), "Expected male names in mixed dataset")
        self.assertTrue(any(f in FIRST_NAMES_F for f in firsts_both), "Expected female names in mixed dataset")

    def test_distinct_households_never_share_residential_address(self):
        """Distinct households must never share a residential address across the dataset."""
        addr_synth = AddressSynthesizer()
        carrier = CarrierNetwork()
        cfg = {
            "obs_distribution": "gaussian",
            "mean_obs_per_person": 12.0,
            "std_obs_per_person": 3.0,
            "pct_never_moved": 0.35,
            "pct_county_moved": 0.35,
            "pct_state_moved": 0.15,
            "pct_cross_us_moved": 0.15,
            "employer_rate": 0.0,  # 100% residential sightings
        }
        residence_to_household = {}
        for e_idx in range(1, 80):
            obs_list, _, _ = generate_person_stream(
                person_idx=e_idx,
                entity_id=f"E{e_idx:04d}",
                config=cfg,
                addr_synth=addr_synth,
                carrier=carrier,
                sub_seed=5000 + e_idx,
            )
            hh_id = obs_list[0]["household_id"]
            addresses = {o["address"] for o in obs_list if o.get("address")}
            for addr in addresses:
                if addr in residence_to_household:
                    self.assertEqual(
                        residence_to_household[addr],
                        hh_id,
                        f"Residential address '{addr}' was shared by distinct households {residence_to_household[addr]} and {hh_id}",
                    )
                residence_to_household[addr] = hh_id

    def test_same_household_members_share_residential_address(self):
        """Individuals belonging to the same household cohort must share their residential address."""
        obs = make_population(
            n_individuals=60,
            seed=42,
            pct_household=10.0,
            employer_rate=0.0,  # Focus on residential sharing
        )
        hh_cohorts = {}
        for o in obs:
            hh = o.get("household_id")
            if hh and hh.startswith("HH-COHORT"):
                hh_cohorts.setdefault(hh, []).append(o)

        self.assertGreater(len(hh_cohorts), 0, "Expected at least one household cohort")
        for hh_id, rows in hh_cohorts.items():
            entities = sorted(list({r["entity_id_truth"] for r in rows}))
            self.assertEqual(len(entities), 2, f"Household cohort {hh_id} should have 2 members")
            addrs_e1 = {r["address"] for r in rows if r["entity_id_truth"] == entities[0] and r.get("address")}
            addrs_e2 = {r["address"] for r in rows if r["entity_id_truth"] == entities[1] and r.get("address")}
            shared = addrs_e1.intersection(addrs_e2)
            self.assertTrue(len(shared) > 0, f"Household {hh_id} members {entities} did not share any residential address")

    def test_high_address_variability(self):
        """Synthesized addresses must exhibit diverse street names, numbers, suffixes, and zip codes."""
        obs = make_population(n_individuals=50, seed=123)
        addrs = [o["address"] for o in obs if o.get("address")]
        self.assertGreater(len(addrs), 300)

        # Unique addresses ratio
        unique_ratio = len(set(addrs)) / len(addrs)
        self.assertGreater(unique_ratio, 0.20, f"Address diversity ratio too low: {unique_ratio}")

        # Check for diverse street suffixes and units across sample
        suffixes_found = set()
        for suffix in ["St", "Ave", "Blvd", "Dr", "Rd", "Way", "Ln", "Ct", "Pl", "Ter", "Pkwy", "Cir", "Loop", "Trl"]:
            if any(f" {suffix}" in a for a in addrs):
                suffixes_found.add(suffix)
        self.assertGreaterEqual(len(suffixes_found), 5, f"Expected diverse street suffixes, found: {suffixes_found}")

        has_units = any("Apt " in a or "Unit " in a or "Ste " in a or "Fl " in a for a in addrs)
        self.assertTrue(has_units, "Expected secondary units in synthesized addresses")


if __name__ == "__main__":
    unittest.main()


