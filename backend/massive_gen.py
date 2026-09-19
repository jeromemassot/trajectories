"""
massive_gen.py - High-Performance Streaming Synthetic Data Generator

Supports generating datasets from small interactive benchmarks up to hundreds of millions
of observations with O(1) memory consumption per worker, direct disk streaming (JSONL/CSV),
user-defined statistical observation distributions (Truncated Gaussian, Negative Binomial,
Log-Normal, Uniform), a 4-tier Gaussian relocation behavior model, and percentage-scaled confounders.
"""

import csv
import gzip
import hashlib
import json
import math
import os
import random
import sys
import threading
import time
from datetime import date, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data_gen import (
    CITY_ADDRESSES,
    CITY_NEIGHBORHOODS,
    STATE_CITIES,
    CITIES,
    FIRST_NAMES_M,
    FIRST_NAMES_F,
    LAST_NAMES,
    NICKNAMES,
    EMAIL_DOMAINS,
    START_DATE,
    END_DATE,
    CarrierNetwork,
    rand_phone,
    typo,
    token_hash,
)

# Extended street names for procedural address scaling
STREET_NAMES = [
    "Main St", "Broadway", "Market St", "Washington St", "Park Ave", "Lincoln Ave",
    "Oak St", "Pine St", "Maple Ave", "Cedar St", "Elm St", "Chestnut St", "Walnut St",
    "State St", "Central Ave", "2nd Ave", "3rd Ave", "4th Ave", "5th Ave", "Commerce St",
    "Grand Ave", "Sunset Blvd", "Spring St", "Church St", "Highland Ave", "Union St",
    "Franklin St", "Jackson St", "Jefferson St", "Madison St", "Monroe St", "Adams St",
    "Taylor St", "Wilson St", "Clark St", "Harrison St", "Peachtree St", "Colfax Ave",
]


def sample_obs_count(dist_type, mean_val, std_val=3.0, min_val=2, max_val=100, rng=None):
    """Sample observation count Ki for an individual based on the selected distribution."""
    r = rng or random
    dist = (dist_type or "gaussian").lower()

    if dist == "gaussian":
        val = r.gauss(mean_val, std_val)
        return max(min_val, min(max_val, int(round(val))))

    elif dist == "negative_binomial":
        var = max(mean_val + 0.1, std_val ** 2)
        r_disp = (mean_val ** 2) / (var - mean_val) if var > mean_val else 5.0
        p = r_disp / (r_disp + mean_val)
        lam = r.gammavariate(r_disp, (1.0 - p) / p)
        k = 0
        p_acc = 1.0
        l_exp = math.exp(-lam) if lam < 700 else 0.0
        while p_acc > l_exp:
            k += 1
            p_acc *= r.random()
        return max(min_val, min(max_val, k - 1))

    elif dist == "log_normal":
        var = max(0.5, std_val ** 2)
        sigma2 = math.log(1.0 + var / (mean_val ** 2))
        mu = math.log(mean_val) - 0.5 * sigma2
        val = math.exp(r.gauss(mu, math.sqrt(sigma2)))
        return max(min_val, min(max_val, int(round(val))))

    elif dist == "uniform":
        low = max(min_val, int(round(mean_val - std_val)))
        high = min(max_val, max(low + 1, int(round(mean_val + std_val))))
        return r.randint(low, high)

    elif dist == "fixed":
        return max(min_val, min(max_val, int(round(mean_val))))

    return max(min_val, min(max_val, int(round(r.gauss(mean_val, std_val)))))


def sample_relocation_tier(p_never, p_county, p_state, p_cross_us, rng=None):
    """Categorically assign an individual to one of the 4 mobility tiers."""
    r = rng or random
    total = p_never + p_county + p_state + p_cross_us
    if total <= 0:
        return "never"
    roll = r.random() * total
    if roll < p_never:
        return "never"
    elif roll < p_never + p_county:
        return "county"
    elif roll < p_never + p_county + p_state:
        return "state"
    else:
        return "cross_us"


def sample_move_count(tier, config, rng=None):
    """Sample number of moves M_i for a mover tier assuming Gaussian clamped >= 1."""
    r = rng or random
    if tier == "never":
        return 0
    elif tier == "county":
        mu = config.get("mean_county_moves", 1.8)
        sigma = config.get("std_county_moves", 0.8)
        return max(1, int(round(r.gauss(mu, sigma))))
    elif tier == "state":
        mu = config.get("mean_state_moves", 2.2)
        sigma = config.get("std_state_moves", 0.9)
        return max(1, int(round(r.gauss(mu, sigma))))
    elif tier == "cross_us":
        mu = config.get("mean_cross_moves", 3.1)
        sigma = config.get("std_cross_moves", 1.2)
        return max(1, int(round(r.gauss(mu, sigma))))
    return 1


class AddressSynthesizer:
    """Provides authentic addresses and generates procedural local venues at scale."""
    def __init__(self, rng=None):
        self.rng = rng or random
        self.cache = {}

    def get_city_venues(self, city_name, needed=10):
        """Retrieve verified venues and synthetically scale within city bounds if needed."""
        if city_name in self.cache:
            pool = self.cache[city_name]
            if len(pool) >= needed:
                return pool
        base_pool = CITY_ADDRESSES.get(city_name)
        if not base_pool:
            for c, lat, lon in CITIES:
                if c == city_name:
                    base_pool = [(f"100 Main St, {city_name}", lat, lon)]
                    break
        if not base_pool:
            base_pool = [(f"100 Main St, {city_name}", 37.0902, -95.7129)]

        pool = list(base_pool)
        ref_lat, ref_lon = base_pool[0][1], base_pool[0][2]
        city_short = city_name.split(",")[0]
        state_short = city_name.split(",")[1].strip() if "," in city_name else ""

        while len(pool) < needed:
            num = self.rng.randint(100, 8900)
            street = self.rng.choice(STREET_NAMES)
            j_lat = round(ref_lat + self.rng.uniform(-0.025, 0.025), 4)
            j_lon = round(ref_lon + self.rng.uniform(-0.025, 0.025), 4)
            pool.append((f"{num} {street}, {city_short}, {state_short}", j_lat, j_lon))

        self.cache[city_name] = pool
        return pool


def format_noisy_dob(dob, enable_dob_noise, rate_year_only, rate_year_month, rate_shift, drop_dob_rate, rng=None):
    """Format date of birth with realistic recording noise."""
    r = rng or random
    if dob is None or (enable_dob_noise and r.random() < drop_dob_rate):
        return None
    if not enable_dob_noise:
        return dob.isoformat()

    roll = r.random()
    th_year = rate_year_only
    th_ym = th_year + rate_year_month
    th_shift = th_ym + rate_shift

    if roll < th_year:
        return f"{dob.year:04d}"
    elif roll < th_ym:
        return f"{dob.year:04d}-{dob.month:02d}"
    elif roll < th_shift:
        offset = r.choice([-1, 1])
        noisy_d = dob + timedelta(days=offset)
        return noisy_d.isoformat()
    else:
        return dob.isoformat()


def build_observation_row(
    obs_id,
    entity_id,
    first,
    last,
    dob,
    ts_date,
    city,
    address,
    lat,
    lon,
    household_id,
    employer_id,
    persistent_token,
    emails,
    phones,
    config,
    rng=None,
):
    """Builds a single observation dict with configured field noise."""
    r = rng or random
    f, l = first, last
    enable_name_noise = config.get("enable_name_noise", True)
    if enable_name_noise:
        if r.random() < config.get("rate_first_noise", 0.35):
            if f in NICKNAMES and r.random() < 0.6:
                f = r.choice(NICKNAMES[f])
            else:
                f = typo(f)
        if r.random() < config.get("rate_last_noise", 0.15):
            l = typo(l)

    drop_address = r.random() < config.get("drop_address_rate", 0.10)
    drop_phone = r.random() < config.get("drop_phone_rate", 0.08)
    drop_email = r.random() < config.get("drop_email_rate", 0.08)

    noisy_dob = format_noisy_dob(
        dob,
        config.get("enable_dob_noise", True),
        config.get("rate_dob_year_only", 0.10),
        config.get("rate_dob_year_month", 0.10),
        config.get("rate_dob_shift", 0.12),
        config.get("drop_dob_rate", 0.12),
        rng=r,
    )

    return {
        "observation_id": obs_id,
        "entity_id_truth": entity_id,
        "first_name": f,
        "last_name": l,
        "dob": noisy_dob,
        "timestamp": ts_date.isoformat(),
        "address": None if drop_address else address,
        "city": city,
        "lat": None if drop_address else lat,
        "lon": None if drop_address else lon,
        "household_id": household_id,
        "employer_id": employer_id,
        "persistent_token": persistent_token,
        "emails": [] if drop_email else list(emails),
        "phones": [] if drop_phone else list(phones),
    }


def generate_person_stream(
    person_idx,
    entity_id,
    config,
    addr_synth,
    carrier,
    obs_counter_start=1,
    sub_seed=None,
    household_override=None,
    name_override=None,
    city_override=None,
):
    """Generates an individual's complete chronological trajectory using Option A (Direct Stream)."""
    rng = random.Random(sub_seed) if sub_seed is not None else random

    sex = rng.choice(["M", "F"])
    if name_override:
        first, last = name_override
    else:
        first = rng.choice(FIRST_NAMES_M if sex == "M" else FIRST_NAMES_F)
        last = rng.choice(LAST_NAMES)

    dob = date(1955, 1, 1) + timedelta(days=rng.randint(0, (date(2002, 1, 1) - date(1955, 1, 1)).days))
    household_id = household_override or f"HH-{token_hash(f'{last}{person_idx}{dob}')}"

    has_token = rng.random() < config.get("token_rate", 0.60)
    persistent_token = token_hash(f"{first}{last}{dob}") if has_token else None

    has_emp = rng.random() < config.get("employer_rate", 0.70)
    employer_id = f"EMP-{rng.randint(1, 12)}" if has_emp else None

    n_obs = sample_obs_count(
        config.get("obs_distribution", "gaussian"),
        config.get("mean_obs_per_person", 10.0),
        config.get("std_obs_per_person", 3.5),
        config.get("min_obs_per_person", 2),
        config.get("max_obs_per_person", 80),
        rng=rng,
    )

    total_days = (END_DATE - START_DATE).days
    day_offsets = sorted(rng.randint(0, total_days) for _ in range(n_obs))
    timeline_dates = [START_DATE + timedelta(days=d) for d in day_offsets]

    if city_override:
        tier = "never"
        home_city = city_override
    else:
        tier = sample_relocation_tier(
            config.get("pct_never_moved", 0.50),
            config.get("pct_county_moved", 0.30),
            config.get("pct_state_moved", 0.15),
            config.get("pct_cross_us_moved", 0.05),
            rng=rng,
        )
        origin_city_entry = rng.choice(CITIES)
        home_city = origin_city_entry[0]

    moves_count = sample_move_count(tier, config, rng=rng)

    residence_timeline = []
    used_residences = set()

    if tier == "never":
        venues = addr_synth.get_city_venues(home_city, needed=max(8, n_obs // 2))
        primary_res = venues[0]
        used_residences.add(primary_res)
        residence_timeline.append((START_DATE, home_city, primary_res))

    elif tier == "county":
        needed_venues = max(15, moves_count + 10)
        venues = addr_synth.get_city_venues(home_city, needed=needed_venues)
        step_idx = max(1, len(timeline_dates) // (moves_count + 1))
        for m_i in range(moves_count + 1):
            t_idx = min(len(timeline_dates) - 1, m_i * step_idx)
            m_date = timeline_dates[t_idx]
            res_addr = venues[m_i]
            used_residences.add(res_addr)
            residence_timeline.append((m_date, home_city, res_addr))

    elif tier == "state":
        state_code = home_city.split(",")[1].strip() if "," in home_city else "TX"
        state_pool = STATE_CITIES.get(state_code, [home_city])
        route_cities = [home_city]
        visited_cities = {home_city}
        for _ in range(moves_count):
            remaining = [c for c in state_pool if c not in visited_cities]
            if remaining:
                next_c = rng.choice(remaining)
                visited_cities.add(next_c)
                route_cities.append(next_c)
            else:
                route_cities.append(route_cities[-1])

        step_idx = max(1, len(timeline_dates) // len(route_cities))
        for m_i, c_name in enumerate(route_cities):
            t_idx = min(len(timeline_dates) - 1, m_i * step_idx)
            m_date = timeline_dates[t_idx]
            c_venues = addr_synth.get_city_venues(c_name, needed=max(12, m_i + 5))
            avail_res = [v for v in c_venues if v not in used_residences]
            res_addr = avail_res[0] if avail_res else c_venues[0]
            used_residences.add(res_addr)
            residence_timeline.append((m_date, c_name, res_addr))

    elif tier == "cross_us":
        all_state_codes = list(STATE_CITIES.keys())
        route_cities = [home_city]
        cur_state = home_city.split(",")[1].strip() if "," in home_city else "TX"
        visited_states = {cur_state}
        for _ in range(moves_count):
            avail_states = [s for s in all_state_codes if s not in visited_states]
            if not avail_states:
                avail_states = [s for s in all_state_codes if s != cur_state]
            next_state = rng.choice(avail_states)
            visited_states.add(next_state)
            cur_state = next_state
            next_c = rng.choice(STATE_CITIES[next_state])
            route_cities.append(next_c)

        step_idx = max(1, len(timeline_dates) // len(route_cities))
        for m_i, c_name in enumerate(route_cities):
            t_idx = min(len(timeline_dates) - 1, m_i * step_idx)
            m_date = timeline_dates[t_idx]
            c_venues = addr_synth.get_city_venues(c_name, needed=max(12, m_i + 5))
            avail_res = [v for v in c_venues if v not in used_residences]
            res_addr = avail_res[0] if avail_res else c_venues[0]
            used_residences.add(res_addr)
            residence_timeline.append((m_date, c_name, res_addr))

    active_phones = [carrier.acquire_phone(home_city, START_DATE)]
    personal_email = f"{first.lower()}.{last.lower()}@{rng.choice(EMAIL_DOMAINS)}"
    work_email = f"{first.lower()}_{last.lower()}@{employer_id.lower()}.com" if employer_id else None

    # Establish business address per visited city if individual has an employer
    business_addresses = {}
    if employer_id:
        all_cities = {entry[1] for entry in residence_timeline}
        for c_name in all_cities:
            c_venues = addr_synth.get_city_venues(c_name, needed=10)
            avail_bus = [v for v in c_venues if v not in used_residences]
            bus_addr = avail_bus[0] if avail_bus else c_venues[-1]
            business_addresses[c_name] = bus_addr

    will_marry = rng.random() < 0.15
    marriage_date = timeline_dates[len(timeline_dates) // 2] if will_marry else None
    married_last = rng.choice(LAST_NAMES) if will_marry else last

    observations = []
    cur_res_idx = 0

    for idx, d in enumerate(timeline_dates):
        obs_id = f"O{obs_counter_start + idx:05d}"
        cur_last = married_last if (will_marry and d >= marriage_date) else last

        while cur_res_idx + 1 < len(residence_timeline) and d >= residence_timeline[cur_res_idx + 1][0]:
            cur_res_idx += 1
            new_city = residence_timeline[cur_res_idx][1]
            if new_city != residence_timeline[cur_res_idx - 1][1]:
                active_phones = [carrier.acquire_phone(new_city, d)]

        active_city = residence_timeline[cur_res_idx][1]
        active_home_res = residence_timeline[cur_res_idx][2]
        active_bus_res = business_addresses.get(active_city)

        sighting_emails = []
        em_seed = rng.random()
        if em_seed < 0.50 and personal_email:
            sighting_emails = [personal_email]
        elif em_seed < 0.85 and personal_email and work_email:
            sighting_emails = [personal_email, work_email]
        elif em_seed < 0.95 and work_email:
            sighting_emails = [work_email]

        # Account/service registration location: strictly Home address or Business address
        if active_bus_res is not None:
            # Corporate transaction: use business address
            if work_email and work_email in sighting_emails and personal_email not in sighting_emails:
                chosen_loc = active_bus_res
            elif work_email and work_email in sighting_emails:
                # Both personal and work email: 50% business, 50% home
                chosen_loc = active_bus_res if rng.random() < 0.50 else active_home_res
            else:
                # Personal transaction: 85% home address, 15% business address
                chosen_loc = active_bus_res if rng.random() < 0.15 else active_home_res
        else:
            # No employer/business: 100% home address
            chosen_loc = active_home_res

        row = build_observation_row(
            obs_id=obs_id,
            entity_id=entity_id,
            first=first,
            last=cur_last,
            dob=dob,
            ts_date=d,
            city=active_city,
            address=chosen_loc[0],
            lat=chosen_loc[1],
            lon=chosen_loc[2],
            household_id=household_id,
            employer_id=employer_id,
            persistent_token=persistent_token,
            emails=sighting_emails,
            phones=active_phones,
            config=config,
            rng=rng,
        )
        observations.append(row)

    return observations, tier, moves_count


class BatchGenerationJob:
    """Manages asynchronous streaming batch generation jobs to disk."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BatchGenerationJob, cls).__new__(cls)
                cls._instance._init_state()
            return cls._instance

    def _init_state(self):
        self.job_id = None
        self.status = "idle"
        self.output_path = None
        self.rows_written = 0
        self.total_expected_rows = 0
        self.entities_written = 0
        self.total_entities = 0
        self.throughput_rows_sec = 0.0
        self.start_time = 0.0
        self.elapsed_sec = 0.0
        self.eta_sec = 0.0
        self.error_message = None
        self._stop_event = threading.Event()
        self._thread = None

    def get_status(self):
        with self._lock:
            if self.status == "running" and self.start_time > 0:
                self.elapsed_sec = time.time() - self.start_time
                if self.elapsed_sec > 0.2:
                    self.throughput_rows_sec = round(self.rows_written / self.elapsed_sec, 1)
                    if self.throughput_rows_sec > 0 and self.total_expected_rows > self.rows_written:
                        rem = self.total_expected_rows - self.rows_written
                        self.eta_sec = round(rem / self.throughput_rows_sec, 1)
                    else:
                        self.eta_sec = 0.0
            pct = 0.0
            if self.total_expected_rows > 0:
                pct = round(min(100.0, (self.rows_written / self.total_expected_rows) * 100), 1)
            elif self.total_entities > 0:
                pct = round(min(100.0, (self.entities_written / self.total_entities) * 100), 1)

            file_sz = 0
            if self.output_path and Path(self.output_path).exists():
                try:
                    file_sz = Path(self.output_path).stat().st_size
                except OSError:
                    file_sz = 0

            return {
                "job_id": self.job_id,
                "status": self.status,
                "output_path": str(self.output_path) if self.output_path else None,
                "output_file": str(self.output_path) if self.output_path else None,
                "rows_written": self.rows_written,
                "generated_observations": self.rows_written,
                "total_expected_rows": self.total_expected_rows,
                "entities_written": self.entities_written,
                "generated_individuals": self.entities_written,
                "total_entities": self.total_entities,
                "total_individuals": self.total_entities,
                "progress_pct": pct,
                "pct_complete": pct,
                "throughput_rows_sec": self.throughput_rows_sec,
                "rows_per_second": self.throughput_rows_sec,
                "elapsed_sec": round(self.elapsed_sec, 1),
                "elapsed_seconds": round(self.elapsed_sec, 1),
                "eta_sec": self.eta_sec,
                "eta_seconds": self.eta_sec,
                "file_size_bytes": file_sz,
                "error": self.error_message,
            }

    def cancel(self):
        with self._lock:
            if self.status == "running":
                self._stop_event.set()
                self.status = "cancelled"
                return True
            return False

    def start(self, config, output_path):
        with self._lock:
            if self.status == "running":
                return False, "A batch generation job is already running."
            self._init_state()
            self.job_id = f"job_{int(time.time())}"
            self.status = "running"
            self.output_path = Path(output_path).resolve()
            self.total_entities = int(config.get("n_individuals", 1000))
            mean_obs = float(config.get("mean_obs_per_person", 10.0))
            self.total_expected_rows = int(round(self.total_entities * mean_obs))
            self.start_time = time.time()
            self._stop_event.clear()

            self._thread = threading.Thread(
                target=self._run_streaming,
                args=(config, self.output_path),
                daemon=True,
            )
            self._thread.start()
            return True, self.job_id

    def _run_streaming(self, config, out_path):
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            is_jsonl = out_path.suffix.lower() in (".jsonl", ".ndjson")
            is_csv = out_path.suffix.lower() == ".csv"
            is_gz = out_path.suffix.lower() == ".gz"

            open_fn = gzip.open if is_gz else open
            mode = "wt" if is_gz else "w"

            addr_synth = AddressSynthesizer()
            carrier = CarrierNetwork()
            global_seed = int(config.get("seed", 42))

            csv_writer = None

            with open_fn(out_path, mode, encoding="utf-8") as f:
                if is_csv:
                    fieldnames = [
                        "observation_id", "entity_id_truth", "first_name", "last_name",
                        "dob", "timestamp", "address", "city", "lat", "lon",
                        "household_id", "employer_id", "persistent_token", "emails", "phones"
                    ]
                    csv_writer = csv.DictWriter(f, fieldnames=fieldnames)
                    csv_writer.writeheader()

                obs_counter = 1
                n_entities = self.total_entities

                pct_hh = float(config.get("pct_household", 5.0)) / 100.0
                pct_coll = float(config.get("pct_collision", 2.0)) / 100.0

                n_hh_entities = int(round(n_entities * pct_hh))
                if n_hh_entities % 2 != 0:
                    n_hh_entities += 1
                n_coll_entities = int(round(n_entities * pct_coll))
                if n_coll_entities % 2 != 0:
                    n_coll_entities += 1

                for e_idx in range(1, n_entities + 1):
                    if self._stop_event.is_set():
                        self.status = "cancelled"
                        return

                    sub_seed = int(hashlib.md5(f"{global_seed}_{e_idx}".encode()).hexdigest()[:8], 16)
                    entity_id = f"E{e_idx:05d}"

                    hh_override = None
                    name_override = None
                    city_override = None

                    if e_idx <= n_hh_entities:
                        hh_group_id = (e_idx - 1) // 2
                        hh_override = f"HH-COHORT-{hh_group_id:04d}"
                    elif e_idx <= n_hh_entities + n_coll_entities:
                        coll_group_id = (e_idx - n_hh_entities - 1) // 2
                        name_override = ("James", "Smith") if (coll_group_id % 2 == 0) else ("Maria", "Garcia")
                        state_choices = ["New York, NY", "Los Angeles, CA", "Dallas, TX", "Chicago, IL", "Miami, FL"]
                        city_override = state_choices[(coll_group_id + (e_idx % 2)) % len(state_choices)]

                    obs_list, tier, _ = generate_person_stream(
                        person_idx=e_idx,
                        entity_id=entity_id,
                        config=config,
                        addr_synth=addr_synth,
                        carrier=carrier,
                        obs_counter_start=obs_counter,
                        sub_seed=sub_seed,
                        household_override=hh_override,
                        name_override=name_override,
                        city_override=city_override,
                    )

                    obs_counter += len(obs_list)
                    self.rows_written += len(obs_list)
                    self.entities_written += 1

                    if is_csv:
                        for row in obs_list:
                            csv_row = dict(row)
                            csv_row["emails"] = ";".join(csv_row["emails"])
                            csv_row["phones"] = ";".join(csv_row["phones"])
                            csv_writer.writerow(csv_row)
                    else:
                        for row in obs_list:
                            f.write(json.dumps(row) + "\n")

            self.status = "completed"
            self.elapsed_sec = time.time() - self.start_time
            if self.elapsed_sec > 0:
                self.throughput_rows_sec = round(self.rows_written / self.elapsed_sec, 1)

        except Exception as e:
            self.status = "error"
            self.error_message = str(e)


def generate_preview_sample(config, target_obs=400):
    """Generates a stratified in-memory sample conforming to the configured parameters for UI map preview."""
    mean_obs = float(config.get("mean_obs_per_person", 10.0))
    target_entities = max(10, min(80, int(round(target_obs / max(1.0, mean_obs)))))

    addr_synth = AddressSynthesizer()
    carrier = CarrierNetwork()
    seed = int(config.get("seed", 42))

    preview_rows = []
    obs_counter = 1
    tier_counts = {"never": 0, "county": 0, "state": 0, "cross_us": 0}

    for e_idx in range(1, target_entities + 1):
        sub_seed = int(hashlib.md5(f"{seed}_preview_{e_idx}".encode()).hexdigest()[:8], 16)
        entity_id = f"E{e_idx:03d}"
        obs_list, tier, _ = generate_person_stream(
            person_idx=e_idx,
            entity_id=entity_id,
            config=config,
            addr_synth=addr_synth,
            carrier=carrier,
            obs_counter_start=obs_counter,
            sub_seed=sub_seed,
        )
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        obs_counter += len(obs_list)
        preview_rows.extend(obs_list)

    preview_rows.sort(key=lambda x: x["timestamp"])
    for i, r in enumerate(preview_rows, start=1):
        r["observation_id"] = f"O{i:04d}"

    summary = {
        "n_observations": len(preview_rows),
        "n_entities": target_entities,
        "mobility_tiers": tier_counts,
        "sample_preview": True,
    }
    return preview_rows, summary
