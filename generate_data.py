"""
Generate synthetic vehicle registration data, plant known defects, load into
PostgreSQL, and write defect_log.csv (the "answer key" for your validation checks).

Setup:
    pip install psycopg2-binary faker
Run:
    set PGPASSWORD=your_password      (Windows cmd)
    $env:PGPASSWORD="your_password"   (PowerShell)
    export PGPASSWORD=your_password   (Mac/Linux)
    python generate_data.py

WARNING: this TRUNCATES all four tables every run, so it is safe to re-run.
"""
import csv
import os
import random
import string
from datetime import date, timedelta

import psycopg2
from faker import Faker
from psycopg2.extras import execute_values

SEED = 42
N_OWNERS = 1000
N_VEHICLES = 1500

DB = dict(
    host="127.0.0.1",
    port=5433,  # change to 5433 if you remapped the port in Docker
    dbname="reg_validation",
    user="qa_user",
    password=os.environ.get("PGPASSWORD", ""),
)

random.seed(SEED)
Faker.seed(SEED)
fake = Faker("en_US")
TODAY = date.today()

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}
STATE_CODES = list(STATES)
STATE_FEES = {code: round(random.uniform(25, 150), 2) for code in STATE_CODES}

MODELS = {
    "Ford": ["F-150", "Transit", "Explorer"],
    "Chevrolet": ["Silverado", "Equinox", "Express"],
    "Toyota": ["Camry", "Tacoma", "RAV4"],
    "Honda": ["Civic", "Accord", "CR-V"],
    "Ram": ["1500", "ProMaster", "2500"],
}

VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"  # real VINs never use I, O, Q


# ---------------------------------------------------------------- clean data
def build_clean_data():
    owners = []
    for oid in range(1, N_OWNERS + 1):
        owners.append(dict(
            owner_id=oid,
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            address_line=fake.street_address()[:100],
            city=fake.city()[:50],
            state_code=random.choice(STATE_CODES),
            zip_code=f"{random.randint(10000, 99999)}",
        ))

    vins = set()
    vehicles = []
    for vid in range(1, N_VEHICLES + 1):
        while True:
            vin = "".join(random.choices(VIN_CHARS, k=17))
            if vin not in vins:
                vins.add(vin)
                break
        make = random.choice(list(MODELS))
        vehicles.append(dict(
            vehicle_id=vid,
            vin=vin,
            make=make,
            model=random.choice(MODELS[make]),
            model_year=random.randint(2008, 2026),
            purchase_date=TODAY - timedelta(days=random.randint(30, 1000)),
            purchase_price=round(random.uniform(8000, 85000), 2),
        ))

    plates = set()
    registrations = []
    for rid, v in enumerate(vehicles, start=1):
        owner = random.choice(owners)
        while True:
            plate = "".join(random.choices(string.ascii_uppercase, k=3)) + \
                    "".join(random.choices(string.digits, k=4))
            key = (owner["state_code"], plate)
            if key not in plates:
                plates.add(key)
                break
        issue = v["purchase_date"] + timedelta(days=random.randint(0, 30))
        expiration = issue + timedelta(days=365)
        registrations.append(dict(
            registration_id=rid,
            vehicle_id=v["vehicle_id"],
            owner_id=owner["owner_id"],
            state_code=owner["state_code"],
            plate_number=plate,
            issue_date=issue,
            expiration_date=expiration,
            fee_paid=STATE_FEES[owner["state_code"]],
            status="EXPIRED" if expiration < TODAY else "ACTIVE",
        ))
    return owners, vehicles, registrations


# ------------------------------------------------------------ defect planting
defect_log = []


def log(rule_id, table, record_id, description):
    defect_log.append(dict(rule_id=rule_id, table=table,
                           record_id=record_id, description=description))


def pick(rows, n, used, key):
    """Pick n rows not already damaged by another defect."""
    pool = [r for r in rows if (key, r[key]) not in used]
    chosen = random.sample(pool, n)
    for r in chosen:
        used.add((key, r[key]))
    return chosen


def inject_defects(owners, vehicles, registrations):
    used_v, used_r, used_o = set(), set(), set()

    # --- vehicles
    for v in pick(vehicles, 10, used_v, "vehicle_id"):
        v["vin"] = None
        log("VR-001", "vehicles", v["vehicle_id"], "VIN is NULL")

    originals = random.sample(vehicles, 40)
    dup_targets = pick(vehicles, 8, used_v, "vehicle_id")
    for v, src in zip(dup_targets, originals):
        if src["vin"] is None or src["vehicle_id"] == v["vehicle_id"]:
            src = next(x for x in vehicles if x["vin"] and x["vehicle_id"] != v["vehicle_id"])
        v["vin"] = src["vin"]
        log("VR-002", "vehicles", v["vehicle_id"],
            f"Duplicate VIN (same as vehicle_id {src['vehicle_id']})")

    for v in pick(vehicles, 10, used_v, "vehicle_id"):
        v["vin"] = v["vin"][:random.choice([10, 15, 16])] if random.random() < 0.7 \
            else v["vin"] + "X"
        log("VR-003", "vehicles", v["vehicle_id"], f"VIN length is {len(v['vin'])}, not 17")

    for v in pick(vehicles, 6, used_v, "vehicle_id"):
        v["model_year"] = random.choice([1899, 1950, 2035, 2099])
        log("VR-007", "vehicles", v["vehicle_id"], f"Implausible model_year {v['model_year']}")

    # --- registrations
    for r in pick(registrations, 12, used_r, "registration_id"):
        r["vehicle_id"] = random.randint(90000, 99999)
        log("VR-004", "registrations", r["registration_id"],
            f"Orphan vehicle_id {r['vehicle_id']}")

    for r in pick(registrations, 8, used_r, "registration_id"):
        r["owner_id"] = random.randint(90000, 99999)
        log("VR-012", "registrations", r["registration_id"],
            f"Orphan owner_id {r['owner_id']}")

    for r in pick(registrations, 10, used_r, "registration_id"):
        r["expiration_date"] = r["issue_date"] - timedelta(days=random.randint(1, 200))
        log("VR-005", "registrations", r["registration_id"], "expiration_date before issue_date")

    vehicle_by_id = {v["vehicle_id"]: v for v in vehicles}
    for r in pick(registrations, 10, used_r, "registration_id"):
        v = vehicle_by_id[r["vehicle_id"]]
        r["issue_date"] = v["purchase_date"] - timedelta(days=60)
        log("VR-009", "registrations", r["registration_id"],
            "issue_date is before the vehicle's purchase_date")

    for r in pick(registrations, 8, used_r, "registration_id"):
        r["fee_paid"] = None if random.random() < 0.5 else -abs(r["fee_paid"])
        log("VR-008", "registrations", r["registration_id"],
            f"fee_paid invalid ({r['fee_paid']})")

    clean_regs = [r for r in registrations if ("registration_id", r["registration_id"]) not in used_r]
    for r, src in zip(pick(registrations, 6, used_r, "registration_id"),
                      random.sample(clean_regs, 6)):
        r["plate_number"], r["state_code"] = src["plate_number"], src["state_code"]
        log("VR-010", "registrations", r["registration_id"],
            f"Duplicate plate in state (same as registration_id {src['registration_id']})")

    # --- owners
    for o in pick(owners, 8, used_o, "owner_id"):
        o["state_code"] = random.choice(["ZZ", "XX", "QQ", "99"])
        log("VR-006", "owners", o["owner_id"], f"Invalid state_code '{o['state_code']}'")

    for o in pick(owners, 8, used_o, "owner_id"):
        o["zip_code"] = random.choice(["1234", "ABCDE", "123456", "12-345"])
        log("VR-011", "owners", o["owner_id"], f"Invalid zip_code '{o['zip_code']}'")


# -------------------------------------------------------------------- loading
def load(owners, vehicles, registrations):
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("TRUNCATE registrations, vehicles, owners, states RESTART IDENTITY;")

    execute_values(cur, "INSERT INTO states VALUES %s",
                   [(c, STATES[c], STATE_FEES[c]) for c in STATE_CODES])

    for table, rows, cols in [
        ("owners", owners, ["owner_id", "first_name", "last_name", "address_line",
                            "city", "state_code", "zip_code"]),
        ("vehicles", vehicles, ["vehicle_id", "vin", "make", "model", "model_year",
                                "purchase_date", "purchase_price"]),
        ("registrations", registrations, ["registration_id", "vehicle_id", "owner_id",
                                          "state_code", "plate_number", "issue_date",
                                          "expiration_date", "fee_paid", "status"]),
    ]:
        execute_values(cur, f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s",
                       [tuple(r[c] for c in cols) for r in rows])
        pk = cols[0]
        cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), "
                    f"(SELECT MAX({pk}) FROM {table}));")

    conn.commit()
    cur.close()
    conn.close()


def write_defect_log(path="defect_log.csv"):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rule_id", "table", "record_id", "description"])
        w.writeheader()
        w.writerows(sorted(defect_log, key=lambda d: (d["rule_id"], d["record_id"])))


if __name__ == "__main__":
    if not DB["password"]:
        raise SystemExit("Set the PGPASSWORD environment variable first.")
    owners, vehicles, registrations = build_clean_data()
    inject_defects(owners, vehicles, registrations)
    load(owners, vehicles, registrations)
    write_defect_log()
    print(f"Loaded {len(owners)} owners, {len(vehicles)} vehicles, "
          f"{len(registrations)} registrations.")
    print(f"Planted {len(defect_log)} defects. See defect_log.csv")
