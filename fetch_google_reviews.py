import os
from datetime import datetime, timedelta, timezone
import pytz
from dateutil import parser

from google.cloud import bigquery
from google_play_scraper import reviews, Sort

# -----------------------------
# CONFIG
# -----------------------------
PROJECT_ID = "valid-cedar-485813-v7"
DATASET_ID = "reviews"
TABLE_ID = "raw_reviews"

APPS = [
    {"app_id": "com.naviapp", "app_name": "Navi"},
    {"app_id": "com.fastmoney.loan", "app_name": "FastMoney"},
]

IST = pytz.timezone("Asia/Kolkata")

# -----------------------------
# BIGQUERY
# -----------------------------
bq_client = bigquery.Client(project=PROJECT_ID)
TABLE_FQN = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

# -----------------------------
# DATE WINDOW (D-1 IST)
# -----------------------------
today_ist = datetime.now(IST).date()
d1 = today_ist - timedelta(days=1)

start_dt = IST.localize(datetime.combine(d1, datetime.min.time()))
end_dt = IST.localize(datetime.combine(d1, datetime.max.time()))

print(f"📅 Fetching reviews from {start_dt} to {end_dt} (IST)")

rows_to_insert = []

# -----------------------------
# SCRAPE
# -----------------------------
for app in APPS:
    print(f"📦 Scraping {app['app_id']}")

    result, _ = reviews(
        app["app_id"],
        lang="en",
        country="in",
        sort=Sort.NEWEST,
        count=1000,
    )

    for r in result:
        at = r.get("at")
        if not at:
            continue

        # --- SAFE DATE HANDLING ---
        if isinstance(at, datetime):
            review_dt = at
        else:
            review_dt = parser.isoparse(at)

        if review_dt.tzinfo is None:
            review_dt = IST.localize(review_dt)
        else:
            review_dt = review_dt.astimezone(IST)

        if not (start_dt <= review_dt <= end_dt):
            continue

        review_dt_utc = review_dt.astimezone(timezone.utc)

        rows_to_insert.append({
            "review_id": r["reviewId"],
            "app_name": app["app_name"],
            "review_date": review_dt_utc.isoformat(),     # ✅ FIX
            "rating": int(r["score"]),
            "review_text": (r.get("content") or "").strip(),
            "inserted_on": datetime.utcnow().isoformat(), # ✅ FIX
        })

print(f"✅ Total D-1 reviews collected: {len(rows_to_insert)}")

# -----------------------------
# INSERT INTO BIGQUERY
# -----------------------------
if rows_to_insert:
    errors = bq_client.insert_rows_json(
        TABLE_FQN,
        rows_to_insert,
        skip_invalid_rows=False,
        ignore_unknown_values=False,
    )

    if errors:
        print("❌ BigQuery insert errors:")
        for e in errors[:5]:
            print(e)
        raise RuntimeError("BigQuery insert failed")
    else:
        print(f"✅ Inserted {len(rows_to_insert)} rows into BigQuery")
else:
    print("⚠️ No D-1 reviews found. Nothing inserted.")
