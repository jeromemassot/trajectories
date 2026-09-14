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
    ("New York, NY", 40.7484, -73.9857),
    ("Boston, MA", 42.3525, -71.0665),
    ("Philadelphia, PA", 39.9525, -75.1660),
    ("Washington, DC", 38.9055, -77.0415),
    ("Chicago, IL", 41.8790, -87.6245),
    ("Detroit, MI", 42.3325, -83.0475),
    ("Austin, TX", 30.2685, -97.7425),
    ("Dallas, TX", 32.7805, -96.7995),
    ("Denver, CO", 39.7435, -104.9875),
    ("Seattle, WA", 47.6145, -122.3295),
    ("Portland, OR", 45.5190, -122.6800),
    ("San Francisco, CA", 37.7615, -122.4195),
    ("Los Angeles, CA", 34.0495, -118.2565),
    ("San Diego, CA", 32.7215, -117.1600),
    ("Phoenix, AZ", 33.4495, -112.0740),
    ("Miami, FL", 25.7660, -80.1935),
    ("Atlanta, GA", 33.7770, -84.3855),
    ("Minneapolis, MN", 44.9765, -93.2725),
]

CITY_ADDRESSES = {
    "New York, NY": [
        ("350 5th Ave, New York, NY 10118", 40.7484, -73.9857),
        ("230 Park Ave, New York, NY 10169", 40.7540, -73.9760),
        ("55 Broadway, New York, NY 10006", 40.7075, -74.0125),
        ("420 Lexington Ave, New York, NY 10170", 40.7522, -73.9765),
        ("168 7th Ave, New York, NY 10011", 40.7425, -73.9985),
        ("140 Amsterdam Ave, New York, NY 10023", 40.7745, -73.9840),
        ("1180 2nd Ave, New York, NY 10065", 40.7625, -73.9625),
        ("250 Bedford Ave, Brooklyn, NY 11211", 40.7160, -73.9600),
        ("100 8th Ave, Brooklyn, NY 11215", 40.6740, -73.9760),
        ("125 W 125th St, New York, NY 10027", 40.8080, -73.9475),
    ],
    "Boston, MA": [
        ("100 Boylston St, Boston, MA 02116", 42.3525, -71.0665),
        ("400 Commonwealth Ave, Boston, MA 02215", 42.3495, -71.0910),
        ("150 Tremont St, Boston, MA 02111", 42.3540, -71.0630),
        ("75 Beacon St, Boston, MA 02108", 42.3565, -71.0705),
        ("250 Massachusetts Ave, Cambridge, MA 02139", 42.3615, -71.0965),
        ("600 Washington St, Boston, MA 02111", 42.3520, -71.0620),
        ("120 Huntington Ave, Boston, MA 02116", 42.3460, -71.0805),
        ("800 Harrison Ave, Boston, MA 02118", 42.3365, -71.0735),
        ("300 Hanover St, Boston, MA 02113", 42.3645, -71.0540),
        ("500 Columbus Ave, Boston, MA 02118", 42.3425, -71.0790),
    ],
    "Philadelphia, PA": [
        ("1500 Market St, Philadelphia, PA 19102", 39.9525, -75.1660),
        ("1800 Chestnut St, Philadelphia, PA 19103", 39.9515, -75.1710),
        ("1200 Walnut St, Philadelphia, PA 19107", 39.9495, -75.1610),
        ("3400 Spruce St, Philadelphia, PA 19104", 39.9500, -75.1940),
        ("600 N Broad St, Philadelphia, PA 19130", 39.9635, -75.1605),
        ("200 South St, Philadelphia, PA 19147", 39.9415, -75.1455),
        ("2200 Fairmount Ave, Philadelphia, PA 19130", 39.9680, -75.1740),
        ("4000 Locust St, Philadelphia, PA 19104", 39.9520, -75.2025),
    ],
    "Washington, DC": [
        ("1200 Connecticut Ave NW, Washington, DC 20036", 38.9055, -77.0415),
        ("1600 Pennsylvania Ave NW, Washington, DC 20500", 38.8977, -77.0365),
        ("1000 K St NW, Washington, DC 20001", 38.9025, -77.0265),
        ("3000 M St NW, Washington, DC 20007", 38.9050, -77.0590),
        ("400 8th St SE, Washington, DC 20003", 38.8845, -76.9950),
        ("1400 14th St NW, Washington, DC 20005", 38.9090, -77.0320),
        ("2400 Wisconsin Ave NW, Washington, DC 20007", 38.9220, -77.0725),
        ("600 H St NE, Washington, DC 20002", 38.9005, -76.9980),
    ],
    "Chicago, IL": [
        ("200 S Michigan Ave, Chicago, IL 60604", 41.8790, -87.6245),
        ("600 N Clark St, Chicago, IL 60654", 41.8930, -87.6315),
        ("2400 N Lincoln Ave, Chicago, IL 60614", 41.9255, -87.6495),
        ("3200 N Halsted St, Chicago, IL 60657", 41.9405, -87.6490),
        ("1400 N Milwaukee Ave, Chicago, IL 60622", 41.9075, -87.6740),
        ("1100 S State St, Chicago, IL 60605", 41.8690, -87.6275),
        ("1800 W Division St, Chicago, IL 60622", 41.9030, -87.6730),
        ("800 W Randolph St, Chicago, IL 60607", 41.8845, -87.6480),
    ],
    "Detroit, MI": [
        ("1000 Woodward Ave, Detroit, MI 48226", 42.3325, -83.0475),
        ("4400 Cass Ave, Detroit, MI 48201", 42.3530, -83.0645),
        ("2100 Michigan Ave, Detroit, MI 48216", 42.3315, -83.0725),
        ("1500 E Jefferson Ave, Detroit, MI 48207", 42.3410, -83.0290),
        ("7300 Woodward Ave, Detroit, MI 48202", 42.3735, -83.0750),
        ("2800 Grand River Ave, Detroit, MI 48201", 42.3400, -83.0690),
        ("500 Monroe St, Detroit, MI 48226", 42.3340, -83.0425),
    ],
    "Austin, TX": [
        ("600 Congress Ave, Austin, TX 78701", 30.2685, -97.7425),
        ("1400 S Congress Ave, Austin, TX 78704", 30.2505, -97.7495),
        ("2200 Guadalupe St, Austin, TX 78705", 30.2855, -97.7420),
        ("1600 E 6th St, Austin, TX 78702", 30.2625, -97.7250),
        ("1200 S Lamar Blvd, Austin, TX 78704", 30.2550, -97.7635),
        ("3800 N Lamar Blvd, Austin, TX 78756", 30.3060, -97.7445),
        ("1100 E 11th St, Austin, TX 78702", 30.2690, -97.7285),
    ],
    "Dallas, TX": [
        ("1500 Main St, Dallas, TX 75201", 32.7805, -96.7995),
        ("2600 McKinney Ave, Dallas, TX 75204", 32.7985, -96.8020),
        ("3900 Oak Lawn Ave, Dallas, TX 75219", 32.8120, -96.8080),
        ("1800 Commerce St, Dallas, TX 75201", 32.7815, -96.7955),
        ("2800 Greenville Ave, Dallas, TX 75206", 32.8250, -96.7700),
        ("500 N Bishop Ave, Dallas, TX 75208", 32.7485, -96.8290),
        ("2100 Ross Ave, Dallas, TX 75201", 32.7875, -96.7965),
    ],
    "Denver, CO": [
        ("1600 Broadway, Denver, CO 80202", 39.7435, -104.9875),
        ("1200 Colfax Ave, Denver, CO 80218", 39.7400, -104.9730),
        ("1500 Wynkoop St, Denver, CO 80202", 39.7525, -104.9995),
        ("3200 Tejon St, Denver, CO 80211", 39.7625, -105.0110),
        ("2500 E 2nd Ave, Denver, CO 80206", 39.7195, -104.9565),
        ("2800 Larimer St, Denver, CO 80205", 39.7600, -104.9825),
        ("600 17th St, Denver, CO 80202", 39.7470, -104.9920),
    ],
    "Seattle, WA": [
        ("1200 Pine St, Seattle, WA 98101", 47.6145, -122.3295),
        ("400 Broadway E, Seattle, WA 98102", 47.6225, -122.3210),
        ("1800 Queen Anne Ave N, Seattle, WA 98109", 47.6355, -122.3565),
        ("3500 Fremont Ave N, Seattle, WA 98103", 47.6515, -122.3500),
        ("2200 Westlake Ave, Seattle, WA 98121", 47.6175, -122.3385),
        ("4500 University Way NE, Seattle, WA 98105", 47.6615, -122.3130),
        ("5200 Ballard Ave NW, Seattle, WA 98107", 47.6655, -122.3820),
        ("1500 1st Ave, Seattle, WA 98101", 47.6090, -122.3395),
    ],
    "Portland, OR": [
        ("700 SW Broadway, Portland, OR 97205", 45.5190, -122.6800),
        ("400 NW 23rd Ave, Portland, OR 97210", 45.5260, -122.6985),
        ("1500 SE Hawthorne Blvd, Portland, OR 97214", 45.5120, -122.6505),
        ("2000 NE Alberta St, Portland, OR 97211", 45.5590, -122.6450),
        ("1100 NW Glisan St, Portland, OR 97209", 45.5270, -122.6825),
        ("2800 SE Belmont St, Portland, OR 97214", 45.5165, -122.6365),
        ("800 N Mississippi Ave, Portland, OR 97227", 45.5425, -122.6755),
    ],
    "San Francisco, CA": [
        ("2200 Mission St, San Francisco, CA 94110", 37.7615, -122.4195),
        ("1200 Valencia St, San Francisco, CA 94110", 37.7535, -122.4215),
        ("1800 Geary Blvd, San Francisco, CA 94115", 37.7845, -122.4335),
        ("2400 California St, San Francisco, CA 94115", 37.7890, -122.4345),
        ("3000 24th St, San Francisco, CA 94110", 37.7525, -122.4110),
        ("1500 Haight St, San Francisco, CA 94117", 37.7700, -122.4470),
        ("800 Irving St, San Francisco, CA 94122", 37.7640, -122.4665),
        ("500 Castro St, San Francisco, CA 94114", 37.7605, -122.4350),
        ("1000 Market St, San Francisco, CA 94102", 37.7815, -122.4115),
    ],
    "Los Angeles, CA": [
        ("600 S Grand Ave, Los Angeles, CA 90017", 34.0495, -118.2565),
        ("6800 Hollywood Blvd, Los Angeles, CA 90028", 34.1015, -118.3395),
        ("8400 Wilshire Blvd, Beverly Hills, CA 90211", 34.0665, -118.3740),
        ("1400 Santa Monica Blvd, Santa Monica, CA 90404", 34.0265, -118.4845),
        ("4500 Sunset Blvd, Los Angeles, CA 90027", 34.0980, -118.2885),
        ("350 S Pasadena Ave, Pasadena, CA 91105", 34.1415, -118.1565),
        ("1600 N Cahuenga Blvd, Los Angeles, CA 90028", 34.1005, -118.3295),
    ],
    "San Diego, CA": [
        ("1400 5th Ave, San Diego, CA 92101", 32.7215, -117.1600),
        ("3800 5th Ave, San Diego, CA 92103", 32.7480, -117.1605),
        ("2900 University Ave, San Diego, CA 92104", 32.7485, -117.1310),
        ("4600 Mission Blvd, San Diego, CA 92109", 32.7985, -117.2550),
        ("3000 El Cajon Blvd, San Diego, CA 92104", 32.7550, -117.1290),
        ("700 G St, San Diego, CA 92101", 32.7135, -117.1575),
        ("2200 Fern St, San Diego, CA 92104", 32.7275, -117.1285),
    ],
    "Phoenix, AZ": [
        ("100 N Central Ave, Phoenix, AZ 85004", 33.4495, -112.0740),
        ("2400 E Camelback Rd, Phoenix, AZ 85016", 33.5095, -112.0305),
        ("4000 N Central Ave, Phoenix, AZ 85012", 33.4950, -112.0740),
        ("700 E McDowell Rd, Phoenix, AZ 85006", 33.4660, -112.0645),
        ("1800 E Thomas Rd, Phoenix, AZ 85016", 33.4800, -112.0430),
        ("300 W Washington St, Phoenix, AZ 85003", 33.4485, -112.0785),
        ("5000 N 7th Ave, Phoenix, AZ 85013", 33.5100, -112.0825),
    ],
    "Miami, FL": [
        ("1450 Brickell Ave, Miami, FL 33131", 25.7592, -80.1925),
        ("801 S Miami Ave, Miami, FL 33130", 25.7660, -80.1935),
        ("100 SE 2nd St, Miami, FL 33131", 25.7725, -80.1900),
        ("150 W Flagler St, Miami, FL 33130", 25.7740, -80.1950),
        ("1111 SW 8th St, Miami, FL 33130", 25.7650, -80.2120),
        ("1800 SW 1st Ave, Miami, FL 33129", 25.7580, -80.1980),
        ("2200 Coral Way, Miami, FL 33145", 25.7505, -80.2290),
        ("2600 S Bayshore Dr, Miami, FL 33133", 25.7335, -80.2370),
        ("3000 Biscayne Blvd, Miami, FL 33137", 25.8050, -80.1895),
        ("350 NW 2nd Ave, Miami, FL 33128", 25.7770, -80.1970),
        ("1300 SW 12th Ave, Miami, FL 33129", 25.7610, -80.2140),
        ("500 NW 36th St, Miami, FL 33127", 25.8105, -80.2045),
    ],
    "Atlanta, GA": [
        ("800 Peachtree St NE, Atlanta, GA 30308", 33.7770, -84.3855),
        ("1000 Piedmont Ave NE, Atlanta, GA 30309", 33.7820, -84.3795),
        ("600 Ponce De Leon Ave NE, Atlanta, GA 30308", 33.7725, -84.3665),
        ("3300 Peachtree Rd NE, Atlanta, GA 30326", 33.8465, -84.3645),
        ("400 Marietta St NW, Atlanta, GA 30313", 33.7625, -84.3970),
        ("1200 Howell Mill Rd NW, Atlanta, GA 30318", 33.7865, -84.4115),
        ("200 14th St NE, Atlanta, GA 30309", 33.7860, -84.3825),
    ],
    "Minneapolis, MN": [
        ("800 Nicollet Mall, Minneapolis, MN 55402", 44.9765, -93.2725),
        ("2600 Hennepin Ave, Minneapolis, MN 55408", 44.9555, -93.2980),
        ("1400 Lake St W, Minneapolis, MN 55408", 44.9485, -93.2975),
        ("400 Central Ave SE, Minneapolis, MN 55414", 44.9875, -93.2530),
        ("300 Washington Ave SE, Minneapolis, MN 55455", 44.9740, -93.2345),
        ("200 1st St N, Minneapolis, MN 55401", 44.9855, -93.2685),
        ("2100 Lyndale Ave S, Minneapolis, MN 55405", 44.9620, -93.2885),
    ],
}

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

START_DATE = date(2016, 1, 1)
END_DATE = date(2024, 6, 30)


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


HOUSEHOLD_RESIDENCES = {}


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

        # Residence timeline: [(date_effective, address, lat, lon, city)]
        self.residence_timeline = []
        if self.household_id in HOUSEHOLD_RESIDENCES:
            h_addr, h_lat, h_lon = HOUSEHOLD_RESIDENCES[self.household_id]
        else:
            h_addr, h_lat, h_lon = random.choice(CITY_ADDRESSES[home_city])
            HOUSEHOLD_RESIDENCES[self.household_id] = (h_addr, h_lat, h_lon)
        self.residence_timeline.append((START_DATE, h_addr, h_lat, h_lon, home_city))

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

    def relocate(self, new_city, reloc_date):
        """Relocate to a new authentic residential address in new_city."""
        new_addr, new_lat, new_lon = random.choice(CITY_ADDRESSES[new_city])
        self.residence_timeline.append((reloc_date, new_addr, new_lat, new_lon, new_city))

    def residence_at(self, t):
        """Return (address, lat, lon, city) effective on date t."""
        curr = self.residence_timeline[0]
        for eff_date, addr, lat, lon, city in sorted(self.residence_timeline, key=lambda x: x[0]):
            if eff_date <= t:
                curr = (addr, lat, lon, city)
        return curr

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


def make_population():
    random.seed(42)
    Person._next_id = 1
    HOUSEHOLD_RESIDENCES.clear()
    carrier = CarrierNetwork()
    people = []
    obs_rows = []
    obs_counter = 1

    def new_obs(entity_id, first, last, dob, d, city, address, lat, lon, household_id,
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
        for idx, d in enumerate(timeline_dates):
            if marriage_idx is not None and idx == marriage_idx:
                cur_last = new_last
            if reloc_idx is not None and idx == reloc_idx:
                p.relocate(new_city, d)
            if phone_change_idx is not None and idx == phone_change_idx:
                p.change_phone(d, p.residence_at(d)[3])

            cur_addr, cur_lat, cur_lon, cur_city = p.residence_at(d)
            if random.random() < 0.20:
                obs_addr, obs_lat, obs_lon = random.choice(CITY_ADDRESSES[cur_city])
            else:
                obs_addr, obs_lat, obs_lon = cur_addr, cur_lat, cur_lon

            drop_dob = random.random() < 0.12
            drop_addr = random.random() < 0.10
            drop_em = random.random() < 0.08
            drop_ph = random.random() < 0.08

            new_obs(p.entity_id, first, cur_last, dob, d, cur_city,
                    obs_addr, obs_lat, obs_lon,
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
                res_addr, res_lat, res_lon, cur_city = p.residence_at(d)
                if random.random() < 0.20:
                    obs_addr, obs_lat, obs_lon = random.choice(CITY_ADDRESSES[cur_city])
                else:
                    obs_addr, obs_lat, obs_lon = res_addr, res_lat, res_lon
                new_obs(p.entity_id, p.first, p.last, p.dob, d, home_city,
                        obs_addr, obs_lat, obs_lon,
                        household_id, None, p.persistent_token,
                        emails=p.emails_at(d), phones=p.active_phones_at(d),
                        name_noise=True)

        common_date = rand_date_between(START_DATE, END_DATE)
        for p in siblings:
            res_addr, res_lat, res_lon, _ = p.residence_at(common_date)
            new_obs(p.entity_id, p.first, p.last, p.dob, common_date, home_city,
                    res_addr, res_lat, res_lon, household_id, None, p.persistent_token,
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

        for p, cur_c in [(pA, cityA), (pB, cityB)]:
            n_obs = random.randint(5, 9)
            dts = sorted(rand_date_between(START_DATE, END_DATE) for _ in range(n_obs))
            for d in dts:
                res_addr, res_lat, res_lon, _ = p.residence_at(d)
                if random.random() < 0.20:
                    obs_addr, obs_lat, obs_lon = random.choice(CITY_ADDRESSES[cur_c])
                else:
                    obs_addr, obs_lat, obs_lon = res_addr, res_lat, res_lon
                new_obs(p.entity_id, p.first, p.last, p.dob, d, cur_c,
                        obs_addr, obs_lat, obs_lon,
                        p.household_id, None, p.persistent_token,
                        emails=p.emails_at(d), phones=p.active_phones_at(d),
                        name_noise=True)

        # Anti-reflexive kinematic clash: observed on exact same day in distant cities
        clash_date = rand_date_between(START_DATE, END_DATE)
        addrA, latA, lonA, _ = pA.residence_at(clash_date)
        new_obs(pA.entity_id, first, last, dobA, clash_date, cityA,
                addrA, latA, lonA,
                pA.household_id, None, pA.persistent_token,
                emails=pA.emails_at(clash_date), phones=pA.active_phones_at(clash_date))
        addrB, latB, lonB, _ = pB.residence_at(clash_date)
        new_obs(pB.entity_id, first, last, dobB, clash_date, cityB,
                addrB, latB, lonB,
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
        addr, lat, lon, _ = p_realloc_early.residence_at(d)
        new_obs(p_realloc_early.entity_id, "Marcus", "Vance", p_realloc_early.dob, d,
                "Boston, MA", addr, lat, lon, p_realloc_early.household_id, None,
                p_realloc_early.persistent_token, emails=p_realloc_early.emails_at(d),
                phones=p_realloc_early.active_phones_at(d))

    p_realloc_late = Person("Clara", "Oswald", "F", date(1994, 11, 23), "Denver, CO", carrier=carrier)
    p_realloc_late.phone_timeline = [(date(2021, 1, 1), [reallocated_number])]
    people.append(p_realloc_late)
    for d in [date(2021, 4, 5), date(2022, 6, 18), date(2023, 3, 12), date(2024, 1, 20)]:
        addr, lat, lon, _ = p_realloc_late.residence_at(d)
        new_obs(p_realloc_late.entity_id, "Clara", "Oswald", p_realloc_late.dob, d,
                "Denver, CO", addr, lat, lon, p_realloc_late.household_id, None,
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
