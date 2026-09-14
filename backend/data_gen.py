"""
Mock dataset generator for the Trajectories entity-resolution prototype.

Produces a synthetic population of "true" individuals, each emitting a
sequence of time-stamped Observations (the only thing a real system would
ever see). Ground-truth entity ids are kept ONLY for evaluation - the
resolution pipeline never sees them.

The dataset is deliberately built to exercise the specific failure modes
discussed in the project brief:
  - maiden -> married name changes (attribute mutation)
  - relocations across time (spatio-temporal continuity)
  - simultaneous name + address change ("discontinuity")
  - two different people who share a common name (name collision / blocking)
  - two different people photographed/logged at the same instant in two
    different cities (anti-reflexive / kinematic impossibility)
  - siblings/spouses sharing a household + surname (entity chimerism risk)
  - missing fields (no DOB, no address) on some observations
  - typos / nicknames / OCR-like noise on names

Run directly to (re)generate backend/data/mock_observations.json.
"""

import json
import random
import hashlib
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

CITIES = [
    ("New York, NY", 40.7128, -74.0060),
    ("Boston, MA", 42.3601, -71.0589),
    ("Philadelphia, PA", 39.9526, -75.1652),
    ("Washington, DC", 38.9072, -77.0369),
    ("Chicago, IL", 41.8781, -87.6298),
    ("Detroit, MI", 42.3314, -83.0458),
    ("Austin, TX", 30.2672, -97.7431),
    ("Dallas, TX", 32.7767, -96.7970),
    ("Denver, CO", 39.7392, -104.9903),
    ("Seattle, WA", 47.6062, -122.3321),
    ("Portland, OR", 45.5152, -122.6784),
    ("San Francisco, CA", 37.7749, -122.4194),
    ("Los Angeles, CA", 34.0522, -118.2437),
    ("San Diego, CA", 32.7157, -117.1611),
    ("Phoenix, AZ", 33.4484, -112.0740),
    ("Miami, FL", 25.7617, -80.1918),
    ("Atlanta, GA", 33.7490, -84.3880),
    ("Minneapolis, MN", 44.9778, -93.2650),
]

CITY_AREA_CODES = {
    "New York, NY": "212",
    "Boston, MA": "617",
    "Philadelphia, PA": "215",
    "Washington, DC": "202",
    "Chicago, IL": "312",
    "Detroit, MI": "313",
    "Austin, TX": "512",
    "Dallas, TX": "214",
    "Denver, CO": "303",
    "Seattle, WA": "206",
    "Portland, OR": "503",
    "San Francisco, CA": "415",
    "Los Angeles, CA": "213",
    "San Diego, CA": "619",
    "Phoenix, AZ": "602",
    "Miami, FL": "305",
    "Atlanta, GA": "404",
    "Minneapolis, MN": "612",
}

EMAIL_DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "icloud.com", "fastmail.com"]

FIRST_NAMES_M = ["James", "Robert", "John", "Michael", "David", "William",
                  "Daniel", "Matthew", "Anthony", "Joseph", "Kevin", "Thomas"]
FIRST_NAMES_F = ["Mary", "Jennifer", "Linda", "Elizabeth", "Susan", "Jessica",
                  "Sarah", "Karen", "Nancy", "Emily", "Amanda", "Laura"]
NICKNAMES = {
    "Robert": ["Rob", "Bob", "Bobby"], "William": ["Bill", "Will", "Billy"],
    "James": ["Jim", "Jimmy"], "Elizabeth": ["Liz", "Beth", "Eliza"],
    "Jennifer": ["Jen", "Jenny"], "Michael": ["Mike", "Mikey"],
    "Daniel": ["Dan", "Danny"], "Susan": ["Sue", "Susie"],
    "Anthony": ["Tony"], "Thomas": ["Tom", "Tommy"], "Matthew": ["Matt"],
    "Jessica": ["Jess"], "Kevin": ["Kev"], "Sarah": ["Sara"],
}
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
              "Miller", "Davis", "Martinez", "Anderson", "Taylor", "Thomas",
              "Moore", "Jackson", "Martin", "Lee", "Perez", "White", "Harris",
              "Clark"]

STREET_NAMES = ["Main St", "Oak Ave", "Maple Dr", "2nd St", "Elm St",
                "Washington Blvd", "Park Ave", "Cedar Ln", "Highland Rd",
                "Sunset Blvd", "River Rd", "Lake St"]

START_DATE = date(2016, 1, 1)
END_DATE = date(2024, 6, 30)


def jitter_latlon(lat, lon, km=0.8):
    """Small random jitter around a city center to simulate distinct addresses."""
    dlat = random.uniform(-km, km) / 111.0
    dlon = random.uniform(-km, km) / (111.0 * 0.7)
    return round(lat + dlat, 5), round(lon + dlon, 5)


def rand_address(city_name):
    return f"{random.randint(1,9999)} {random.choice(STREET_NAMES)}, {city_name}"


def rand_date_between(d1, d2):
    delta = (d2 - d1).days
    if delta <= 0:
        return d1
    return d1 + timedelta(days=random.randint(0, delta))


def typo(s):
    """Introduce a light OCR/keyboard-style typo."""
    if len(s) < 3:
        return s
    i = random.randint(1, len(s) - 2)
    ops = ["swap", "drop", "dup"]
    op = random.choice(ops)
    if op == "swap":
        chars = list(s)
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
        return "".join(chars)
    if op == "drop":
        return s[:i] + s[i + 1:]
    return s[:i] + s[i] + s[i:]


def token_hash(seed):
    return hashlib.sha256(seed.encode()).hexdigest()[:12]


def rand_phone(city=None):
    area = CITY_AREA_CODES.get(city, str(random.randint(201, 989)))
    prefix = random.randint(200, 999)
    line = random.randint(1000, 9999)
    return f"+1-{area}-{prefix:03d}-{line:04d}"


class CarrierNetwork:
    """Simulates carrier reallocation of phone numbers across individuals over time."""
    def __init__(self):
        self.reallocated_pool = []  # [(available_from_date, phone_number)]

    def acquire_phone(self, city, on_date):
        for idx, (avail_date, phone) in enumerate(self.reallocated_pool):
            if avail_date <= on_date:
                self.reallocated_pool.pop(idx)
                return phone
        return rand_phone(city)

    def release_phone(self, phone, on_date, quarantine_days=540):
        avail_date = on_date + timedelta(days=quarantine_days)
        self.reallocated_pool.append((avail_date, phone))


class Person:
    _next_id = 1

    def __init__(self, first, last, sex, dob, home_city, household_id=None,
                 employer_id=None, carrier=None):
        self.entity_id = f"E{Person._next_id:03d}"
        Person._next_id += 1
        self.first = first
        self.last = last
        self.sex = sex
        self.dob = dob
        self.home_city = home_city
        self.household_id = household_id or f"HH-{token_hash(self.entity_id)}"
        self.employer_id = employer_id
        self.has_persistent_token = random.random() < 0.6
        self.persistent_token = token_hash(f"{first}{last}{dob}") if self.has_persistent_token else None
        self.events = []  # list of dicts describing life events, sorted by date
        self.carrier = carrier or CarrierNetwork()

        # Email addresses: 0, 1, or several. Appended with time.
        self.email_timeline = []  # [(date_added, email_str)]
        has_initial_email = random.random() < 0.90
        if has_initial_email:
            f = first.lower()
            l = last.lower()
            dom = random.choice(EMAIL_DOMAINS)
            self.email_timeline.append((START_DATE, f"{f}.{l}@{dom}"))

        # Phone numbers:
        # In most case scenarios, only one phone number is active at time t
        # (the last one added). A subset (~20%) have multiple active phone numbers.
        self.multi_phone = random.random() < 0.20
        self.phone_timeline = []  # [(date_effective, [active_phones])]
        has_initial_phone = random.random() < 0.95
        if has_initial_phone:
            p1 = self.carrier.acquire_phone(home_city, START_DATE)
            if self.multi_phone:
                p2 = self.carrier.acquire_phone(home_city, START_DATE)
                self.phone_timeline.append((START_DATE, [p1, p2]))
            else:
                self.phone_timeline.append((START_DATE, [p1]))

    def add_email(self, date_added, email):
        """Append a new email address to the individual's collection at date_added."""
        if email and email not in [e[1] for e in self.email_timeline]:
            self.email_timeline.append((date_added, email))

    def change_phone(self, change_date, city=None):
        """Update phone number. For single-phone individuals, old phone is released to carrier."""
        city = city or self.home_city
        if not self.phone_timeline:
            new_p = self.carrier.acquire_phone(city, change_date)
            self.phone_timeline.append((change_date, [new_p]))
            return

        current_active = self.phone_timeline[-1][1]
        if self.multi_phone:
            old_p = current_active[-1]
            self.carrier.release_phone(old_p, change_date)
            new_p = self.carrier.acquire_phone(city, change_date)
            self.phone_timeline.append((change_date, [current_active[0], new_p]))
        else:
            for old_p in current_active:
                self.carrier.release_phone(old_p, change_date)
            new_p = self.carrier.acquire_phone(city, change_date)
            self.phone_timeline.append((change_date, [new_p]))

    def emails_at(self, t):
        """Collection of email addresses accumulated up to date t."""
        emails = []
        for d, em in sorted(self.email_timeline, key=lambda x: x[0]):
            if d <= t and em not in emails:
                emails.append(em)
        return emails

    def active_phones_at(self, t):
        """List of active phone numbers on date t."""
        active = []
        for d, phones in sorted(self.phone_timeline, key=lambda x: x[0]):
            if d <= t:
                active = phones
        return list(active)

    def name_at(self, t):
        for ev in sorted(self.events, key=lambda e: e["date"]):
            if ev["type"] == "name_change" and ev["date"] <= t:
                self.last = ev["new_last"]
        return self.first, self.last


def build_timeline(events, min_gap_days=25):
    """events: list of (date, city_name, lat, lon, last_name, household_id)"""
    events = sorted(events, key=lambda e: e[0])
    obs = []
    for (d, city, lat, lon, last, hh) in events:
        obs.append({
            "date": d, "city": city, "lat": lat, "lon": lon,
            "last": last, "household_id": hh,
        })
    return obs


def make_population():
    random.seed(42)
    Person._next_id = 1
    carrier = CarrierNetwork()
    people = []
    obs_rows = []
    obs_counter = 1

    def new_obs(entity_id, first, last, dob, d, city, lat, lon, household_id,
                employer_id, persistent_token, emails, phones, name_noise=False,
                drop_dob=False, drop_address=False, drop_email=False, drop_phone=False):
        nonlocal obs_counter
        f, l = first, last
        if name_noise and random.random() < 0.35:
            if f in NICKNAMES and random.random() < 0.6:
                f = random.choice(NICKNAMES[f])
            else:
                f = typo(f)
        if name_noise and random.random() < 0.15:
            l = typo(l)
        row = {
            "observation_id": f"O{obs_counter:04d}",
            "entity_id_truth": entity_id,          # ground truth, hidden from algorithm
            "first_name": f,
            "last_name": l,
            "dob": None if drop_dob else dob.isoformat(),
            "timestamp": d.isoformat(),
            "address": None if drop_address else rand_address(city),
            "city": city,
            "lat": None if drop_address else lat,
            "lon": None if drop_address else lon,
            "household_id": household_id,
            "employer_id": employer_id,
            "persistent_token": persistent_token,
            "emails": [] if drop_email else list(emails),
            "phones": [] if drop_phone else list(phones),
        }
        obs_counter += 1
        obs_rows.append(row)

    # ---------------- Core population: ~18 individuals with realistic lives ----
    n_core = 18
    for i in range(n_core):
        sex = random.choice(["M", "F"])
        first = random.choice(FIRST_NAMES_M if sex == "M" else FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)
        dob = rand_date_between(date(1955, 1, 1), date(2000, 1, 1))
        home_city, hlat, hlon = random.choice(CITIES)
        employer_id = f"EMP-{random.randint(1,6)}" if random.random() < 0.7 else None
        p = Person(first, last, sex, dob, home_city, employer_id=employer_id, carrier=carrier)
        people.append(p)

        n_obs = random.randint(6, 14)
        timeline_dates = sorted(rand_date_between(START_DATE, END_DATE) for _ in range(n_obs))

        # Email accumulation: append work email or secondary personal email over time
        if employer_id and len(timeline_dates) > 2:
            work_email_date = timeline_dates[len(timeline_dates) // 3]
            p.add_email(work_email_date, f"{first.lower()}_{last.lower()}@{employer_id.lower()}.com")
        if random.random() < 0.35 and len(timeline_dates) > 3:
            sec_email_date = timeline_dates[2 * len(timeline_dates) // 3]
            p.add_email(sec_email_date, f"{first.lower()}{random.randint(10, 99)}@fastmail.com")

        will_marry = random.random() < 0.35
        marriage_idx = random.randint(len(timeline_dates)//3, 2*len(timeline_dates)//3) if will_marry else None
        new_last = random.choice(LAST_NAMES) if will_marry else None

        will_relocate = random.random() < 0.45
        reloc_idx = random.randint(2, len(timeline_dates) - 2) if (will_relocate and len(timeline_dates) > 4) else None
        new_city, nlat, nlon = random.choice([c for c in CITIES if c[0] != home_city])

        # Simultaneous-change ("discontinuity") variant: marriage & relocation align
        simultaneous = will_marry and will_relocate and random.random() < 0.5
        if simultaneous and marriage_idx is not None and reloc_idx is not None:
            reloc_idx = marriage_idx

        # Phone change event (e.g. carrier churn / relocation)
        phone_change_idx = reloc_idx if reloc_idx is not None else (
            random.randint(len(timeline_dates)//2, len(timeline_dates)-1) if random.random() < 0.35 else None
        )

        cur_last = last
        cur_city, cur_lat, cur_lon = home_city, hlat, hlon
        for idx, d in enumerate(timeline_dates):
            if marriage_idx is not None and idx == marriage_idx:
                cur_last = new_last
            if reloc_idx is not None and idx == reloc_idx:
                cur_city, cur_lat, cur_lon = new_city, nlat, nlon
            if phone_change_idx is not None and idx == phone_change_idx:
                p.change_phone(d, cur_city)

            lat_j, lon_j = jitter_latlon(cur_lat, cur_lon)
            drop_dob = random.random() < 0.12
            drop_addr = random.random() < 0.10
            drop_em = random.random() < 0.08
            drop_ph = random.random() < 0.08

            new_obs(p.entity_id, first, cur_last, dob, d, cur_city, lat_j, lon_j,
                    p.household_id, employer_id, p.persistent_token,
                    emails=p.emails_at(d), phones=p.active_phones_at(d),
                    name_noise=True, drop_dob=drop_dob, drop_address=drop_addr,
                    drop_email=drop_em, drop_phone=drop_ph)

    # ---------------- Household confounders: spouses/siblings sharing --------
    # surname + address + landline (risk of over-merging / chimerism)
    for _ in range(3):
        last = random.choice(LAST_NAMES)
        home_city, hlat, hlon = random.choice(CITIES)
        household_id = f"HH-{token_hash(last + home_city + str(random.random()))}"
        household_landline = rand_phone(home_city)
        siblings = []
        for _ in range(2):
            sex = random.choice(["M", "F"])
            first = random.choice(FIRST_NAMES_M if sex == "M" else FIRST_NAMES_F)
            dob = rand_date_between(date(1960, 1, 1), date(2002, 1, 1))
            p = Person(first, last, sex, dob, home_city, household_id=household_id, carrier=carrier)
            p.phone_timeline = [(START_DATE, [household_landline])]
            people.append(p)
            siblings.append(p)

        for p in siblings:
            n_obs = random.randint(6, 10)
            dts = sorted(rand_date_between(START_DATE, END_DATE) for _ in range(n_obs))
            for d in dts:
                lat_j, lon_j = jitter_latlon(hlat, hlon)
                new_obs(p.entity_id, p.first, p.last, p.dob, d, home_city, lat_j, lon_j,
                        household_id, None, p.persistent_token,
                        emails=p.emails_at(d), phones=p.active_phones_at(d),
                        name_noise=True)

        common_date = rand_date_between(START_DATE, END_DATE)
        for p in siblings:
            lat_j, lon_j = jitter_latlon(hlat, hlon)
            new_obs(p.entity_id, p.first, p.last, p.dob, common_date, home_city,
                    lat_j, lon_j, household_id, None, p.persistent_token,
                    emails=p.emails_at(common_date), phones=p.active_phones_at(common_date))

    # ---------------- Name-collision confounders: two unrelated people with --
    # the exact same full name in different cities (tests blocking / kinematics)
    for _ in range(2):
        sex = random.choice(["M", "F"])
        first = random.choice(FIRST_NAMES_M if sex == "M" else FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)
        cityA, latA, lonA = random.choice(CITIES)
        remaining = [c for c in CITIES if c[0] != cityA]
        cityB, latB, lonB = random.choice(remaining)

        dobA = rand_date_between(date(1958, 1, 1), date(1998, 1, 1))
        dobB = rand_date_between(date(1958, 1, 1), date(1998, 1, 1))
        pA = Person(first, last, sex, dobA, cityA, carrier=carrier)
        pB = Person(first, last, sex, dobB, cityB, carrier=carrier)
        people += [pA, pB]

        for p, city, lat, lon, dob in [(pA, cityA, latA, lonA, dobA),
                                        (pB, cityB, latB, lonB, dobB)]:
            n_obs = random.randint(5, 9)
            dts = sorted(rand_date_between(START_DATE, END_DATE) for _ in range(n_obs))
            for d in dts:
                lat_j, lon_j = jitter_latlon(lat, lon)
                new_obs(p.entity_id, p.first, p.last, dob, d, city, lat_j, lon_j,
                        p.household_id, None, p.persistent_token,
                        emails=p.emails_at(d), phones=p.active_phones_at(d),
                        name_noise=True)

        # Anti-reflexive kinematic clash: observed on exact same day in distant cities
        clash_date = rand_date_between(START_DATE, END_DATE)
        lat_j, lon_j = jitter_latlon(latA, lonA)
        new_obs(pA.entity_id, first, last, dobA, clash_date, cityA, lat_j, lon_j,
                pA.household_id, None, pA.persistent_token,
                emails=pA.emails_at(clash_date), phones=pA.active_phones_at(clash_date))
        lat_j, lon_j = jitter_latlon(latB, lonB)
        new_obs(pB.entity_id, first, last, dobB, clash_date, cityB, lat_j, lon_j,
                pB.household_id, None, pB.persistent_token,
                emails=pB.emails_at(clash_date), phones=pB.active_phones_at(clash_date))

    # ---------------- Phone Reallocation Confounder --------------------------
    # Person A uses a phone in 2016-2018, then changes phone.
    # Carrier reallocates that same phone number to Person B in 2021-2024.
    reallocated_number = "+1-555-0199"
    p_realloc_early = Person("Marcus", "Vance", "M", date(1972, 4, 15), "Boston, MA", carrier=carrier)
    p_realloc_early.phone_timeline = [
        (date(2016, 1, 1), [reallocated_number]),
        (date(2018, 5, 1), [rand_phone("Boston, MA")]),
    ]
    people.append(p_realloc_early)
    for d in [date(2016, 3, 10), date(2017, 1, 15), date(2017, 8, 22), date(2018, 2, 14)]:
        lat_j, lon_j = jitter_latlon(42.3601, -71.0589)
        new_obs(p_realloc_early.entity_id, "Marcus", "Vance", p_realloc_early.dob, d,
                "Boston, MA", lat_j, lon_j, p_realloc_early.household_id, None,
                p_realloc_early.persistent_token, emails=p_realloc_early.emails_at(d),
                phones=p_realloc_early.active_phones_at(d))

    p_realloc_late = Person("Clara", "Oswald", "F", date(1994, 11, 23), "Denver, CO", carrier=carrier)
    p_realloc_late.phone_timeline = [(date(2021, 1, 1), [reallocated_number])]
    people.append(p_realloc_late)
    for d in [date(2021, 4, 5), date(2022, 6, 18), date(2023, 3, 12), date(2024, 1, 20)]:
        lat_j, lon_j = jitter_latlon(39.7392, -104.9903)
        new_obs(p_realloc_late.entity_id, "Clara", "Oswald", p_realloc_late.dob, d,
                "Denver, CO", lat_j, lon_j, p_realloc_late.household_id, None,
                p_realloc_late.persistent_token, emails=p_realloc_late.emails_at(d),
                phones=p_realloc_late.active_phones_at(d))

    random.shuffle(obs_rows)
    # renumber observation ids after shuffle for a "raw feed" feel, keep truth
    for i, row in enumerate(obs_rows, start=1):
        row["observation_id"] = f"O{i:04d}"

    return obs_rows


def main():
    obs_rows = make_population()
    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "mock_observations.json"
    with open(out_path, "w") as f:
        json.dump(obs_rows, f, indent=2)
    n_entities = len({r["entity_id_truth"] for r in obs_rows})
    print(f"Wrote {len(obs_rows)} observations for {n_entities} ground-truth "
          f"entities -> {out_path}")


if __name__ == "__main__":
    main()
