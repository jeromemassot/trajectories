"""
Test script for the updated 3-mobility-archetype data generator.
"""
import json
import random
import hashlib
from datetime import date, timedelta
from pathlib import Path
import sys

BACKEND_DIR = Path('/home/jeromemassot/Projects/Trajectories/backend')
sys.path.insert(0, str(BACKEND_DIR))
from resolution import resolve, extract_all_candidate_features

random.seed(42)

# Expanded authentic city addresses with coordinates on land
CITY_ADDRESSES = {
    # New York
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
    ],
    "Albany, NY": [
        ("100 State St, Albany, NY 12207", 42.6515, -73.7550),
        ("250 Lark St, Albany, NY 12210", 42.6545, -73.7680),
        ("800 Madison Ave, Albany, NY 12208", 42.6610, -73.7915),
        ("400 Central Ave, Albany, NY 12206", 42.6685, -73.7790),
        ("1200 Western Ave, Albany, NY 12203", 42.6730, -73.8190),
    ],
    "Buffalo, NY": [
        ("200 Main St, Buffalo, NY 14202", 42.8835, -78.8765),
        ("700 Elmwood Ave, Buffalo, NY 14222", 42.9150, -78.8770),
        ("1200 Delaware Ave, Buffalo, NY 14209", 42.9180, -78.8685),
        ("300 Connecticut St, Buffalo, NY 14213", 42.9025, -78.8910),
        ("1400 Hertel Ave, Buffalo, NY 14216", 42.9465, -78.8570),
    ],

    # Massachusetts
    "Boston, MA": [
        ("100 Boylston St, Boston, MA 02116", 42.3525, -71.0665),
        ("400 Commonwealth Ave, Boston, MA 02215", 42.3495, -71.0910),
        ("150 Tremont St, Boston, MA 02111", 42.3540, -71.0630),
        ("75 Beacon St, Boston, MA 02108", 42.3565, -71.0705),
        ("600 Washington St, Boston, MA 02111", 42.3520, -71.0620),
        ("120 Huntington Ave, Boston, MA 02116", 42.3460, -71.0805),
        ("800 Harrison Ave, Boston, MA 02118", 42.3365, -71.0735),
        ("300 Hanover St, Boston, MA 02113", 42.3645, -71.0540),
        ("500 Columbus Ave, Boston, MA 02118", 42.3425, -71.0790),
    ],
    "Cambridge, MA": [
        ("100 Main St, Cambridge, MA 02142", 42.3620, -71.0845),
        ("1400 Massachusetts Ave, Cambridge, MA 02138", 42.3735, -71.1190),
        ("500 Technology Sq, Cambridge, MA 02139", 42.3635, -71.0915),
        ("800 Cambridge St, Cambridge, MA 02141", 42.3710, -71.0900),
        ("2000 Massachusetts Ave, Cambridge, MA 02140", 42.3895, -71.1215),
    ],
    "Worcester, MA": [
        ("100 Front St, Worcester, MA 01608", 42.2625, -71.8000),
        ("300 Main St, Worcester, MA 01608", 42.2650, -71.8015),
        ("1000 Grafton St, Worcester, MA 01604", 42.2415, -71.7680),
        ("500 Park Ave, Worcester, MA 01610", 42.2590, -71.8235),
        ("200 Shrewsbury St, Worcester, MA 01604", 42.2640, -71.7860),
    ],

    # Pennsylvania
    "Philadelphia, PA": [
        ("1500 Market St, Philadelphia, PA 19102", 39.9525, -75.1660),
        ("1800 Chestnut St, Philadelphia, PA 19103", 39.9515, -75.1710),
        ("1200 Walnut St, Philadelphia, PA 19107", 39.9495, -75.1610),
        ("3400 Spruce St, Philadelphia, PA 19104", 39.9500, -75.1940),
        ("600 N Broad St, Philadelphia, PA 19130", 39.9635, -75.1605),
        ("200 South St, Philadelphia, PA 19147", 39.9415, -75.1455),
        ("2200 Fairmount Ave, Philadelphia, PA 19130", 39.9680, -75.1740),
    ],
    "Pittsburgh, PA": [
        ("500 Grant St, Pittsburgh, PA 15219", 40.4395, -79.9960),
        ("1800 E Carson St, Pittsburgh, PA 15203", 40.4285, -79.9805),
        ("3800 Forbes Ave, Pittsburgh, PA 15213", 40.4435, -79.9570),
        ("5500 Walnut St, Pittsburgh, PA 15232", 40.4515, -79.9340),
        ("2100 Penn Ave, Pittsburgh, PA 15222", 40.4505, -79.9850),
    ],

    # Illinois
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
    "Naperville, IL": [
        ("100 S Washington St, Naperville, IL 60540", 41.7725, -88.1475),
        ("1200 S Washington St, Naperville, IL 60540", 41.7580, -88.1470),
        ("400 E Ogden Ave, Naperville, IL 60563", 41.7870, -88.1415),
        ("1800 W Jefferson Ave, Naperville, IL 60540", 41.7650, -88.1820),
        ("2800 95th St, Naperville, IL 60564", 41.7210, -88.1960),
    ],
    "Rockford, IL": [
        ("100 N Main St, Rockford, IL 61101", 42.2715, -89.0940),
        ("1600 E State St, Rockford, IL 61104", 42.2680, -89.0620),
        ("2200 Broadway, Rockford, IL 61104", 42.2530, -89.0550),
        ("3200 N Main St, Rockford, IL 61103", 42.3025, -89.0790),
        ("4000 E State St, Rockford, IL 61108", 42.2675, -89.0190),
    ],

    # Texas
    "Dallas, TX": [
        ("1500 Main St, Dallas, TX 75201", 32.7805, -96.7995),
        ("1800 Commerce St, Dallas, TX 75201", 32.7815, -96.7955),
        ("2100 Ross Ave, Dallas, TX 75201", 32.7875, -96.7965),
        ("2600 McKinney Ave, Dallas, TX 75204", 32.7985, -96.8020),
        ("3900 Oak Lawn Ave, Dallas, TX 75219", 32.8120, -96.8080),
        ("2800 Greenville Ave, Dallas, TX 75206", 32.8250, -96.7700),
        ("500 N Bishop Ave, Dallas, TX 75208", 32.7485, -96.8290),
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
    "Houston, TX": [
        ("1000 Louisiana St, Houston, TX 77002", 29.7589, -95.3677),
        ("1800 Main St, Houston, TX 77002", 29.7520, -95.3700),
        ("900 Montrose Blvd, Houston, TX 77019", 29.7570, -95.3910),
        ("2500 Westheimer Rd, Houston, TX 77098", 29.7420, -95.4190),
        ("3000 Washington Ave, Houston, TX 77007", 29.7680, -95.3905),
        ("1500 Post Oak Blvd, Houston, TX 77056", 29.7512, -95.4618),
    ],
    "San Antonio, TX": [
        ("300 E Houston St, San Antonio, TX 78205", 29.4260, -98.4895),
        ("1000 Broadway, San Antonio, TX 78215", 29.4340, -98.4830),
        ("200 S Alamo St, San Antonio, TX 78205", 29.4225, -98.4880),
        ("1200 S St Marys St, San Antonio, TX 78210", 29.4110, -98.4920),
        ("2500 N St Marys St, San Antonio, TX 78212", 29.4475, -98.4840),
    ],

    # California
    "San Francisco, CA": [
        ("2200 Mission St, San Francisco, CA 94110", 37.7615, -122.4195),
        ("1200 Valencia St, San Francisco, CA 94110", 37.7535, -122.4215),
        ("3000 24th St, San Francisco, CA 94110", 37.7525, -122.4110),
        ("500 Castro St, San Francisco, CA 94114", 37.7605, -122.4350),
        ("1500 Haight St, San Francisco, CA 94117", 37.7700, -122.4470),
        ("1800 Geary Blvd, San Francisco, CA 94115", 37.7845, -122.4335),
        ("2400 California St, San Francisco, CA 94115", 37.7890, -122.4345),
        ("1000 Market St, San Francisco, CA 94102", 37.7815, -122.4115),
    ],
    "Los Angeles, CA": [
        ("600 S Grand Ave, Los Angeles, CA 90017", 34.0495, -118.2565),
        ("6800 Hollywood Blvd, Los Angeles, CA 90028", 34.1015, -118.3395),
        ("8400 Wilshire Blvd, Beverly Hills, CA 90211", 34.0665, -118.3740),
        ("1400 Santa Monica Blvd, Santa Monica, CA 90404", 34.0265, -118.4845),
        ("4500 Sunset Blvd, Los Angeles, CA 90027", 34.0980, -118.2885),
        ("1600 N Cahuenga Blvd, Los Angeles, CA 90028", 34.1005, -118.3295),
    ],
    "San Diego, CA": [
        ("1400 5th Ave, San Diego, CA 92101", 32.7215, -117.1600),
        ("3800 5th Ave, San Diego, CA 92103", 32.7480, -117.1605),
        ("2900 University Ave, San Diego, CA 92104", 32.7485, -117.1310),
        ("4600 Mission Blvd, San Diego, CA 92109", 32.7985, -117.2550),
        ("700 G St, San Diego, CA 92101", 32.7135, -117.1575),
        ("2200 Fern St, San Diego, CA 92104", 32.7275, -117.1285),
    ],
    "San Jose, CA": [
        ("100 S 1st St, San Jose, CA 95113", 37.3355, -121.8895),
        ("300 Santana Row, San Jose, CA 95128", 37.3210, -121.9480),
        ("1500 The Alameda, San Jose, CA 95126", 37.3340, -121.9160),
        ("400 E Santa Clara St, San Jose, CA 95113", 37.3395, -121.8835),
        ("2100 Lincoln Ave, San Jose, CA 95125", 37.2995, -121.8950),
    ],

    # Washington
    "Seattle, WA": [
        ("1200 Pine St, Seattle, WA 98101", 47.6145, -122.3295),
        ("400 Broadway E, Seattle, WA 98102", 47.6225, -122.3210),
        ("1800 Queen Anne Ave N, Seattle, WA 98109", 47.6355, -122.3565),
        ("3500 Fremont Ave N, Seattle, WA 98103", 47.6515, -122.3500),
        ("2200 Westlake Ave, Seattle, WA 98121", 47.6175, -122.3385),
        ("1500 1st Ave, Seattle, WA 98101", 47.6090, -122.3395),
    ],
    "Tacoma, WA": [
        ("900 Pacific Ave, Tacoma, WA 98402", 47.2530, -122.4385),
        ("2700 6th Ave, Tacoma, WA 98406", 47.2555, -122.4735),
        ("1500 N 30th St, Tacoma, WA 98403", 47.2720, -122.4600),
        ("1100 Ruston Way, Tacoma, WA 98402", 47.2760, -122.4580),
        ("5000 S Tacoma Way, Tacoma, WA 98409", 47.2110, -122.4785),
    ],
    "Spokane, WA": [
        ("200 N Wall St, Spokane, WA 99201", 47.6590, -117.4205),
        ("1000 W 1st Ave, Spokane, WA 99201", 47.6565, -117.4260),
        ("1400 S Grand Blvd, Spokane, WA 99202", 47.6430, -117.4085),
        ("2200 E Sprague Ave, Spokane, WA 99202", 47.6570, -117.3780),
        ("800 W Garland Ave, Spokane, WA 99205", 47.6970, -117.4230),
    ],

    # Florida
    "Miami, FL": [
        ("1450 Brickell Ave, Miami, FL 33131", 25.7592, -80.1925),
        ("801 S Miami Ave, Miami, FL 33130", 25.7660, -80.1935),
        ("100 SE 2nd St, Miami, FL 33131", 25.7725, -80.1900),
        ("150 W Flagler St, Miami, FL 33130", 25.7740, -80.1950),
        ("1800 SW 1st Ave, Miami, FL 33129", 25.7580, -80.1980),
        ("1111 SW 8th St, Miami, FL 33130", 25.7650, -80.2120),
        ("2600 S Bayshore Dr, Miami, FL 33133", 25.7335, -80.2370),
        ("3000 Biscayne Blvd, Miami, FL 33137", 25.8050, -80.1895),
        ("500 NW 36th St, Miami, FL 33127", 25.8105, -80.2045),
    ],
    "Tampa, FL": [
        ("400 N Ashley Dr, Tampa, FL 33602", 27.9490, -82.4600),
        ("800 N Franklin St, Tampa, FL 33602", 27.9505, -82.4575),
        ("1600 E 7th Ave, Tampa, FL 33605", 27.9600, -82.4410),
        ("2200 W Platt St, Tampa, FL 33606", 27.9395, -82.4835),
        ("1200 S Howard Ave, Tampa, FL 33606", 27.9315, -82.4830),
    ],
    "Orlando, FL": [
        ("200 S Orange Ave, Orlando, FL 32801", 28.5410, -81.3790),
        ("700 E Washington St, Orlando, FL 32801", 28.5430, -81.3690),
        ("1000 N Orange Ave, Orlando, FL 32804", 28.5580, -81.3765),
        ("2400 Edgewater Dr, Orlando, FL 32804", 28.5695, -81.3880),
        ("1800 E Michigan St, Orlando, FL 32806", 28.5170, -81.3530),
    ],

    # Other single-metro states
    "Washington, DC": [
        ("1200 Connecticut Ave NW, Washington, DC 20036", 38.9055, -77.0415),
        ("1600 Pennsylvania Ave NW, Washington, DC 20500", 38.8977, -77.0365),
        ("1000 K St NW, Washington, DC 20001", 38.9025, -77.0265),
        ("3000 M St NW, Washington, DC 20007", 38.9050, -77.0590),
        ("1400 14th St NW, Washington, DC 20005", 38.9090, -77.0320),
        ("600 H St NE, Washington, DC 20002", 38.9005, -76.9980),
    ],
    "Detroit, MI": [
        ("1000 Woodward Ave, Detroit, MI 48226", 42.3325, -83.0475),
        ("4400 Cass Ave, Detroit, MI 48201", 42.3530, -83.0645),
        ("2100 Michigan Ave, Detroit, MI 48216", 42.3315, -83.0725),
        ("1500 E Jefferson Ave, Detroit, MI 48207", 42.3410, -83.0290),
        ("2800 Grand River Ave, Detroit, MI 48201", 42.3400, -83.0690),
    ],
    "Denver, CO": [
        ("1600 Broadway, Denver, CO 80202", 39.7435, -104.9875),
        ("1200 Colfax Ave, Denver, CO 80218", 39.7400, -104.9730),
        ("1500 Wynkoop St, Denver, CO 80202", 39.7525, -104.9995),
        ("3200 Tejon St, Denver, CO 80211", 39.7625, -105.0110),
        ("2800 Larimer St, Denver, CO 80205", 39.7600, -104.9825),
        ("600 17th St, Denver, CO 80202", 39.7470, -104.9920),
    ],
    "Portland, OR": [
        ("700 SW Broadway, Portland, OR 97205", 45.5190, -122.6800),
        ("400 NW 23rd Ave, Portland, OR 97210", 45.5260, -122.6985),
        ("1500 SE Hawthorne Blvd, Portland, OR 97214", 45.5120, -122.6505),
        ("2000 NE Alberta St, Portland, OR 97211", 45.5590, -122.6450),
        ("1100 NW Glisan St, Portland, OR 97209", 45.5270, -122.6825),
        ("800 N Mississippi Ave, Portland, OR 97227", 45.5425, -122.6755),
    ],
    "Phoenix, AZ": [
        ("100 N Central Ave, Phoenix, AZ 85004", 33.4495, -112.0740),
        ("2400 E Camelback Rd, Phoenix, AZ 85016", 33.5095, -112.0305),
        ("4000 N Central Ave, Phoenix, AZ 85012", 33.4950, -112.0740),
        ("700 E McDowell Rd, Phoenix, AZ 85006", 33.4660, -112.0645),
        ("300 W Washington St, Phoenix, AZ 85003", 33.4485, -112.0785),
    ],
    "Atlanta, GA": [
        ("800 Peachtree St NE, Atlanta, GA 30308", 33.7770, -84.3855),
        ("1000 Piedmont Ave NE, Atlanta, GA 30309", 33.7820, -84.3795),
        ("600 Ponce De Leon Ave NE, Atlanta, GA 30308", 33.7725, -84.3665),
        ("3300 Peachtree Rd NE, Atlanta, GA 30326", 33.8465, -84.3645),
        ("400 Marietta St NW, Atlanta, GA 30313", 33.7625, -84.3970),
    ],
    "Minneapolis, MN": [
        ("800 Nicollet Mall, Minneapolis, MN 55402", 44.9765, -93.2725),
        ("2600 Hennepin Ave, Minneapolis, MN 55408", 44.9555, -93.2980),
        ("1400 Lake St W, Minneapolis, MN 55408", 44.9485, -93.2975),
        ("400 Central Ave SE, Minneapolis, MN 55414", 44.9875, -93.2530),
        ("200 1st St N, Minneapolis, MN 55401", 44.9855, -93.2685),
    ],
}

CITY_AREA_CODES = {
    "New York, NY": "212", "Albany, NY": "518", "Buffalo, NY": "716",
    "Boston, MA": "617", "Cambridge, MA": "617", "Worcester, MA": "508",
    "Philadelphia, PA": "215", "Pittsburgh, PA": "412",
    "Chicago, IL": "312", "Naperville, IL": "630", "Rockford, IL": "815",
    "Dallas, TX": "214", "Austin, TX": "512", "Houston, TX": "713", "San Antonio, TX": "210",
    "San Francisco, CA": "415", "Los Angeles, CA": "213", "San Diego, CA": "619", "San Jose, CA": "408",
    "Seattle, WA": "206", "Tacoma, WA": "253", "Spokane, WA": "509",
    "Miami, FL": "305", "Tampa, FL": "813", "Orlando, FL": "407",
    "Washington, DC": "202", "Detroit, MI": "313", "Denver, CO": "303",
    "Portland, OR": "503", "Phoenix, AZ": "602", "Atlanta, GA": "404", "Minneapolis, MN": "612",
}

# Explicit neighborhood address subsets for Category 1 (Neighborhood Stayers)
CITY_NEIGHBORHOODS = {
    "Miami, FL": [
        ("1450 Brickell Ave, Miami, FL 33131", 25.7592, -80.1925),
        ("801 S Miami Ave, Miami, FL 33130", 25.7660, -80.1935),
        ("100 SE 2nd St, Miami, FL 33131", 25.7725, -80.1900),
        ("150 W Flagler St, Miami, FL 33130", 25.7740, -80.1950),
        ("1800 SW 1st Ave, Miami, FL 33129", 25.7580, -80.1980),
    ],
    "Dallas, TX": [
        ("1500 Main St, Dallas, TX 75201", 32.7805, -96.7995),
        ("1800 Commerce St, Dallas, TX 75201", 32.7815, -96.7955),
        ("2100 Ross Ave, Dallas, TX 75201", 32.7875, -96.7965),
        ("2600 McKinney Ave, Dallas, TX 75204", 32.7985, -96.8020),
    ],
    "Boston, MA": [
        ("100 Boylston St, Boston, MA 02116", 42.3525, -71.0665),
        ("150 Tremont St, Boston, MA 02111", 42.3540, -71.0630),
        ("75 Beacon St, Boston, MA 02108", 42.3565, -71.0705),
        ("600 Washington St, Boston, MA 02111", 42.3520, -71.0620),
        ("120 Huntington Ave, Boston, MA 02116", 42.3460, -71.0805),
    ],
    "Chicago, IL": [
        ("2400 N Lincoln Ave, Chicago, IL 60614", 41.9255, -87.6495),
        ("3200 N Halsted St, Chicago, IL 60657", 41.9405, -87.6490),
        ("1400 N Milwaukee Ave, Chicago, IL 60622", 41.9075, -87.6740),
        ("1800 W Division St, Chicago, IL 60622", 41.9030, -87.6730),
    ],
    "San Francisco, CA": [
        ("2200 Mission St, San Francisco, CA 94110", 37.7615, -122.4195),
        ("1200 Valencia St, San Francisco, CA 94110", 37.7535, -122.4215),
        ("3000 24th St, San Francisco, CA 94110", 37.7525, -122.4110),
        ("500 Castro St, San Francisco, CA 94114", 37.7605, -122.4350),
    ],
    "New York, NY": [
        ("350 5th Ave, New York, NY 10118", 40.7484, -73.9857),
        ("230 Park Ave, New York, NY 10169", 40.7540, -73.9760),
        ("420 Lexington Ave, New York, NY 10170", 40.7522, -73.9765),
        ("168 7th Ave, New York, NY 10011", 40.7425, -73.9985),
        ("1180 2nd Ave, New York, NY 10065", 40.7625, -73.9625),
    ],
}

STATE_CITIES = {
    "TX": ["Dallas, TX", "Austin, TX", "Houston, TX", "San Antonio, TX"],
    "CA": ["San Francisco, CA", "Los Angeles, CA", "San Diego, CA", "San Jose, CA"],
    "FL": ["Miami, FL", "Tampa, FL", "Orlando, FL"],
    "NY": ["New York, NY", "Albany, NY", "Buffalo, NY"],
    "WA": ["Seattle, WA", "Tacoma, WA", "Spokane, WA"],
    "IL": ["Chicago, IL", "Naperville, IL", "Rockford, IL"],
    "MA": ["Boston, MA", "Cambridge, MA", "Worcester, MA"],
    "PA": ["Philadelphia, PA", "Pittsburgh, PA"],
}

CITIES = [(c, addrs[0][1], addrs[0][2]) for c, addrs in CITY_ADDRESSES.items()]

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
    def __init__(self):
        self.reallocated_pool = []
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
                 employer_id=None, carrier=None, home_addr_tuple=None):
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
        self.events = []
        self.carrier = carrier or CarrierNetwork()

        self.residence_timeline = []
        if home_addr_tuple:
            h_addr, h_lat, h_lon = home_addr_tuple
        elif self.household_id in HOUSEHOLD_RESIDENCES:
            h_addr, h_lat, h_lon = HOUSEHOLD_RESIDENCES[self.household_id]
        else:
            h_addr, h_lat, h_lon = random.choice(CITY_ADDRESSES[home_city])
            HOUSEHOLD_RESIDENCES[self.household_id] = (h_addr, h_lat, h_lon)
        self.residence_timeline.append((START_DATE, h_addr, h_lat, h_lon, home_city))

        self.email_timeline = []
        if random.random() < 0.90:
            f, l = first.lower(), last.lower()
            dom = random.choice(EMAIL_DOMAINS)
            self.email_timeline.append((START_DATE, f"{f}.{l}@{dom}"))

        self.multi_phone = random.random() < 0.20
        self.phone_timeline = []
        if random.random() < 0.95:
            p1 = self.carrier.acquire_phone(home_city, START_DATE)
            if self.multi_phone:
                p2 = self.carrier.acquire_phone(home_city, START_DATE)
                self.phone_timeline.append((START_DATE, [p1, p2]))
            else:
                self.phone_timeline.append((START_DATE, [p1]))

    def relocate(self, new_city, reloc_date, new_addr_tuple=None):
        if new_addr_tuple:
            new_addr, new_lat, new_lon = new_addr_tuple
        else:
            new_addr, new_lat, new_lon = random.choice(CITY_ADDRESSES[new_city])
        self.residence_timeline.append((reloc_date, new_addr, new_lat, new_lon, new_city))

    def residence_at(self, t):
        curr = self.residence_timeline[0]
        for eff_date, addr, lat, lon, city in sorted(self.residence_timeline, key=lambda x: x[0]):
            if eff_date <= t:
                curr = (addr, lat, lon, city)
        return curr

    def add_email(self, date_added, email):
        if email and email not in [e[1] for e in self.email_timeline]:
            self.email_timeline.append((date_added, email))

    def change_phone(self, change_date, city=None):
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
        emails = []
        for d, em in sorted(self.email_timeline, key=lambda x: x[0]):
            if d <= t and em not in emails:
                emails.append(em)
        return emails

    def active_phones_at(self, t):
        active = []
        for d, phones in sorted(self.phone_timeline, key=lambda x: x[0]):
            if d <= t:
                active = phones
        return list(active)

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
            "entity_id_truth": entity_id,
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

    def sample_venue_sequence(pool, n_samples):
        """Sample n_samples distinct venue sightings from pool ensuring no consecutive repeats."""
        if len(pool) == 1:
            return [pool[0]] * n_samples
        seq = []
        prev = None
        for _ in range(n_samples):
            candidates = [p for p in pool if p != prev]
            chosen = random.choice(candidates)
            seq.append(chosen)
            prev = chosen
        return seq

    # ---------------- 1. Category 1: Neighborhood Stayers (6 individuals) ----
    # Stay in the same neighborhood; when they move, stay in same neighborhood
    neighborhood_cities = ["Miami, FL", "Dallas, TX", "Boston, MA", "Chicago, IL", "San Francisco, CA", "New York, NY"]
    for i in range(6):
        sex = random.choice(["M", "F"])
        first = random.choice(FIRST_NAMES_M if sex == "M" else FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)
        dob = rand_date_between(date(1955, 1, 1), date(2000, 1, 1))
        home_city = neighborhood_cities[i % len(neighborhood_cities)]
        nb_pool = CITY_NEIGHBORHOODS[home_city]

        # Initial home address in neighborhood
        home_addr = nb_pool[0]
        employer_id = f"EMP-{random.randint(1,6)}" if random.random() < 0.7 else None
        p = Person(first, last, sex, dob, home_city, employer_id=employer_id, carrier=carrier, home_addr_tuple=home_addr)
        people.append(p)

        n_obs = random.randint(8, 14)
        timeline_dates = sorted(rand_date_between(START_DATE, END_DATE) for _ in range(n_obs))

        if employer_id and len(timeline_dates) > 2:
            p.add_email(timeline_dates[len(timeline_dates) // 3], f"{first.lower()}_{last.lower()}@{employer_id.lower()}.com")

        # 50% chance of neighborhood move ("when move they stay in the same neighborhood")
        will_move_neighborhood = (i % 2 == 1)
        move_idx = len(timeline_dates) // 2 if will_move_neighborhood else None
        new_home_addr = nb_pool[1] if will_move_neighborhood else home_addr

        # Life event: marriage surname change
        will_marry = (i == 2 or i == 5)
        marriage_idx = len(timeline_dates) // 2 if will_marry else None
        new_last = random.choice(LAST_NAMES) if will_marry else None

        # Build address sequence across timeline
        epoch1_dates = timeline_dates[:move_idx] if move_idx else timeline_dates
        epoch2_dates = timeline_dates[move_idx:] if move_idx else []

        # Venues in neighborhood
        venues1 = [home_addr] + nb_pool[1:]
        seq1 = sample_venue_sequence(venues1, len(epoch1_dates))

        venues2 = [new_home_addr] + [a for a in nb_pool if a != new_home_addr]
        seq2 = sample_venue_sequence(venues2, len(epoch2_dates)) if epoch2_dates else []

        all_addrs = seq1 + seq2
        cur_last = last
        for idx, d in enumerate(timeline_dates):
            if marriage_idx is not None and idx == marriage_idx:
                cur_last = new_last
            if move_idx is not None and idx == move_idx:
                p.relocate(home_city, d, new_addr_tuple=new_home_addr)

            obs_addr, obs_lat, obs_lon = all_addrs[idx]
            drop_dob = random.random() < 0.12
            drop_addr = random.random() < 0.10
            drop_em = random.random() < 0.08
            drop_ph = random.random() < 0.08

            new_obs(p.entity_id, first, cur_last, dob, d, home_city,
                    obs_addr, obs_lat, obs_lon,
                    p.household_id, employer_id, p.persistent_token,
                    emails=p.emails_at(d), phones=p.active_phones_at(d),
                    name_noise=True, drop_dob=drop_dob, drop_address=drop_addr,
                    drop_email=drop_em, drop_phone=drop_ph)

    # ---------------- 2. Category 2: Intra-State Movers (6 individuals) -------
    # Move between 2 to 3 cities within their state of origin
    intra_states = ["TX", "CA", "FL", "NY", "WA", "IL"]
    for i in range(6):
        state_code = intra_states[i]
        cities_in_state = STATE_CITIES[state_code]
        # Choose 2 or 3 cities in order
        n_cities = 3 if i % 2 == 0 and len(cities_in_state) >= 3 else 2
        route_cities = cities_in_state[:n_cities]

        sex = random.choice(["M", "F"])
        first = random.choice(FIRST_NAMES_M if sex == "M" else FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)
        dob = rand_date_between(date(1955, 1, 1), date(2000, 1, 1))
        home_city = route_cities[0]
        employer_id = f"EMP-{random.randint(1,6)}" if random.random() < 0.7 else None
        p = Person(first, last, sex, dob, home_city, employer_id=employer_id, carrier=carrier)
        people.append(p)

        n_obs = random.randint(9, 14)
        timeline_dates = sorted(rand_date_between(START_DATE, END_DATE) for _ in range(n_obs))

        if employer_id and len(timeline_dates) > 2:
            p.add_email(timeline_dates[len(timeline_dates) // 3], f"{first.lower()}_{last.lower()}@{employer_id.lower()}.com")

        # Partition timeline across the cities
        if n_cities == 2:
            split1 = len(timeline_dates) // 2
            city_splits = [(route_cities[0], timeline_dates[:split1]),
                           (route_cities[1], timeline_dates[split1:])]
        else:
            split1 = len(timeline_dates) // 3
            split2 = 2 * len(timeline_dates) // 3
            city_splits = [(route_cities[0], timeline_dates[:split1]),
                           (route_cities[1], timeline_dates[split1:split2]),
                           (route_cities[2], timeline_dates[split2:])]

        will_marry = (i == 1)
        marriage_idx = len(timeline_dates) // 2 if will_marry else None
        new_last = random.choice(LAST_NAMES) if will_marry else None

        cur_last = last
        obs_idx_counter = 0
        for city_idx, (city_name, c_dates) in enumerate(city_splits):
            c_addrs = CITY_ADDRESSES[city_name]
            # Primary residence in this city
            res_tuple = c_addrs[0]
            if city_idx > 0:
                p.relocate(city_name, c_dates[0], new_addr_tuple=res_tuple)
                # Phone update on intra-state relocation
                p.change_phone(c_dates[0], city_name)

            venues = [res_tuple] + c_addrs[1:]
            seq = sample_venue_sequence(venues, len(c_dates))

            for d_idx, d in enumerate(c_dates):
                if marriage_idx is not None and obs_idx_counter == marriage_idx:
                    cur_last = new_last

                obs_addr, obs_lat, obs_lon = seq[d_idx]
                drop_dob = random.random() < 0.12
                drop_addr = random.random() < 0.10
                drop_em = random.random() < 0.08
                drop_ph = random.random() < 0.08

                new_obs(p.entity_id, first, cur_last, dob, d, city_name,
                        obs_addr, obs_lat, obs_lon,
                        p.household_id, employer_id, p.persistent_token,
                        emails=p.emails_at(d), phones=p.active_phones_at(d),
                        name_noise=True, drop_dob=drop_dob, drop_address=drop_addr,
                        drop_email=drop_em, drop_phone=drop_ph)
                obs_idx_counter += 1

    # ---------------- 3. Category 3: Inter-State Migrators (6 individuals) ----
    # Multi-hop migration across 2 to 4 distinct states
    inter_routes = [
        ["Boston, MA", "Washington, DC", "Atlanta, GA", "Miami, FL"],
        ["New York, NY", "Chicago, IL", "Denver, CO", "Seattle, WA"],
        ["Philadelphia, PA", "Dallas, TX", "Phoenix, AZ", "Los Angeles, CA"],
        ["Minneapolis, MN", "Chicago, IL", "Austin, TX"],
        ["Detroit, MI", "Denver, CO", "Portland, OR"],
        ["Atlanta, GA", "Dallas, TX", "San Diego, CA"],
    ]

    for i in range(6):
        route_cities = inter_routes[i]
        n_cities = len(route_cities)

        sex = random.choice(["M", "F"])
        first = random.choice(FIRST_NAMES_M if sex == "M" else FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)
        dob = rand_date_between(date(1955, 1, 1), date(2000, 1, 1))
        home_city = route_cities[0]
        employer_id = f"EMP-{random.randint(1,6)}" if random.random() < 0.7 else None
        p = Person(first, last, sex, dob, home_city, employer_id=employer_id, carrier=carrier)
        people.append(p)

        n_obs = random.randint(10, 15)
        timeline_dates = sorted(rand_date_between(START_DATE, END_DATE) for _ in range(n_obs))

        if employer_id and len(timeline_dates) > 2:
            p.add_email(timeline_dates[len(timeline_dates) // 3], f"{first.lower()}_{last.lower()}@{employer_id.lower()}.com")

        # Partition dates evenly across cities
        k_step = len(timeline_dates) // n_cities
        city_splits = []
        for c_i in range(n_cities):
            start_i = c_i * k_step
            end_i = (c_i + 1) * k_step if c_i < n_cities - 1 else len(timeline_dates)
            city_splits.append((route_cities[c_i], timeline_dates[start_i:end_i]))

        will_marry = (i == 0 or i == 3)
        marriage_idx = len(timeline_dates) // 2 if will_marry else None
        new_last = random.choice(LAST_NAMES) if will_marry else None

        cur_last = last
        obs_idx_counter = 0
        for city_idx, (city_name, c_dates) in enumerate(city_splits):
            c_addrs = CITY_ADDRESSES[city_name]
            res_tuple = c_addrs[0]
            if city_idx > 0:
                p.relocate(city_name, c_dates[0], new_addr_tuple=res_tuple)
                p.change_phone(c_dates[0], city_name)

            venues = [res_tuple] + c_addrs[1:]
            seq = sample_venue_sequence(venues, len(c_dates))

            for d_idx, d in enumerate(c_dates):
                if marriage_idx is not None and obs_idx_counter == marriage_idx:
                    cur_last = new_last

                obs_addr, obs_lat, obs_lon = seq[d_idx]
                drop_dob = random.random() < 0.12
                drop_addr = random.random() < 0.10
                drop_em = random.random() < 0.08
                drop_ph = random.random() < 0.08

                new_obs(p.entity_id, first, cur_last, dob, d, city_name,
                        obs_addr, obs_lat, obs_lon,
                        p.household_id, employer_id, p.persistent_token,
                        emails=p.emails_at(d), phones=p.active_phones_at(d),
                        name_noise=True, drop_dob=drop_dob, drop_address=drop_addr,
                        drop_email=drop_em, drop_phone=drop_ph)
                obs_idx_counter += 1

    # ---------------- 4. Household Confounders (3 pairs = 6 individuals) -----
    # Siblings/spouses in shared household (Category 1 neighborhood stayers)
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

        city_addrs = CITY_ADDRESSES[home_city]
        for p in siblings:
            n_obs = random.randint(6, 10)
            dts = sorted(rand_date_between(START_DATE, END_DATE) for _ in range(n_obs))
            seq = sample_venue_sequence(city_addrs, len(dts))
            for s_idx, d in enumerate(dts):
                obs_addr, obs_lat, obs_lon = seq[s_idx]
                new_obs(p.entity_id, p.first, p.last, p.dob, d, home_city,
                        obs_addr, obs_lat, obs_lon,
                        household_id, None, p.persistent_token,
                        emails=p.emails_at(d), phones=p.active_phones_at(d),
                        name_noise=True)

        common_date = rand_date_between(START_DATE, END_DATE)
        res_addr, res_lat, res_lon, _ = siblings[0].residence_at(common_date)
        for p in siblings:
            new_obs(p.entity_id, p.first, p.last, p.dob, common_date, home_city,
                    res_addr, res_lat, res_lon, household_id, None, p.persistent_token,
                    emails=p.emails_at(common_date), phones=p.active_phones_at(common_date))

    # ---------------- 5. Name-Collision Confounders (2 pairs = 4 individuals) -
    # Unrelated people with identical names in distant cities/states
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
            city_addrs = CITY_ADDRESSES[cur_c]
            seq = sample_venue_sequence(city_addrs, len(dts))
            for n_idx, d in enumerate(dts):
                obs_addr, obs_lat, obs_lon = seq[n_idx]
                new_obs(p.entity_id, p.first, p.last, p.dob, d, cur_c,
                        obs_addr, obs_lat, obs_lon,
                        p.household_id, None, p.persistent_token,
                        emails=p.emails_at(d), phones=p.active_phones_at(d),
                        name_noise=True)

        clash_date = rand_date_between(START_DATE, END_DATE)
        addrA, latA, lonA = CITY_ADDRESSES[cityA][0]
        new_obs(pA.entity_id, first, last, dobA, clash_date, cityA,
                addrA, latA, lonA,
                pA.household_id, None, pA.persistent_token,
                emails=pA.emails_at(clash_date), phones=pA.active_phones_at(clash_date))
        addrB, latB, lonB = CITY_ADDRESSES[cityB][0]
        new_obs(pB.entity_id, first, last, dobB, clash_date, cityB,
                addrB, latB, lonB,
                pB.household_id, None, pB.persistent_token,
                emails=pB.emails_at(clash_date), phones=pB.active_phones_at(clash_date))

    # ---------------- 6. Phone Reallocation Confounder (2 individuals) -------
    reallocated_number = "+1-555-0199"
    p_realloc_early = Person("Marcus", "Vance", "M", date(1972, 4, 15), "Boston, MA", carrier=carrier)
    p_realloc_early.phone_timeline = [
        (date(2016, 1, 1), [reallocated_number]),
        (date(2018, 5, 1), [rand_phone("Boston, MA")]),
    ]
    people.append(p_realloc_early)
    boston_addrs = CITY_ADDRESSES["Boston, MA"]
    b_seq = sample_venue_sequence(boston_addrs, 4)
    for m_idx, d in enumerate([date(2016, 3, 10), date(2017, 1, 15), date(2017, 8, 22), date(2018, 2, 14)]):
        addr, lat, lon = b_seq[m_idx]
        new_obs(p_realloc_early.entity_id, "Marcus", "Vance", p_realloc_early.dob, d,
                "Boston, MA", addr, lat, lon, p_realloc_early.household_id, None,
                p_realloc_early.persistent_token, emails=p_realloc_early.emails_at(d),
                phones=p_realloc_early.active_phones_at(d))

    p_realloc_late = Person("Clara", "Oswald", "F", date(1994, 11, 23), "Denver, CO", carrier=carrier)
    p_realloc_late.phone_timeline = [(date(2021, 1, 1), [reallocated_number])]
    people.append(p_realloc_late)
    denver_addrs = CITY_ADDRESSES["Denver, CO"]
    d_seq = sample_venue_sequence(denver_addrs, 4)
    for c_idx, d in enumerate([date(2021, 4, 5), date(2022, 6, 18), date(2023, 3, 12), date(2024, 1, 20)]):
        addr, lat, lon = d_seq[c_idx]
        new_obs(p_realloc_late.entity_id, "Clara", "Oswald", p_realloc_late.dob, d,
                "Denver, CO", addr, lat, lon, p_realloc_late.household_id, None,
                p_realloc_late.persistent_token, emails=p_realloc_late.emails_at(d),
                phones=p_realloc_late.active_phones_at(d))

    # Eliminate consecutive duplicate coordinates for the same individual
    by_entity = {}
    for o in obs_rows:
        by_entity.setdefault(o["entity_id_truth"], []).append(o)

    for eid, items in by_entity.items():
        items.sort(key=lambda x: x["timestamp"])
        for i in range(1, len(items)):
            prev_o = items[i - 1]
            curr_o = items[i]
            if curr_o["lat"] is not None and prev_o["lat"] is not None:
                if curr_o["lat"] == prev_o["lat"] and curr_o["lon"] == prev_o["lon"]:
                    city = curr_o["city"]
                    pool = CITY_NEIGHBORHOODS.get(city) or CITY_ADDRESSES.get(city) or []
                    alternatives = [a for a in pool if a[1] != prev_o["lat"] or a[2] != prev_o["lon"]]
                    if alternatives:
                        alt_addr, alt_lat, alt_lon = alternatives[0]
                        curr_o["address"] = alt_addr
                        curr_o["lat"] = alt_lat
                        curr_o["lon"] = alt_lon

    random.shuffle(obs_rows)
    for i, row in enumerate(obs_rows, start=1):
        row["observation_id"] = f"O{i:04d}"

    return obs_rows

if __name__ == "__main__":
    obs = make_population()
    print(f"Generated {len(obs)} observations.")
    features = extract_all_candidate_features(obs)
    res = resolve(obs, threshold=0.65, precomputed_features=features)
    metrics = res["metrics"]
    print("Resolution metrics:", json.dumps(metrics, indent=2))

    data_dir = BACKEND_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_file = data_dir / "mock_observations.json"
    with open(out_file, "w") as f:
        json.dump(obs, f, indent=2)
    print(f"Saved dataset to {out_file}")

