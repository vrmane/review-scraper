import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.cloud import bigquery
from google_play_scraper import reviews, Sort

IST = ZoneInfo("Asia/Kolkata")

PROJECT_ID = "valid-cedar-485813-v7"
DATASET_ID = "reviews"
TABLE_ID = "raw_reviews"

APPS = {
    "Navi": "com.naviapp",
    "FastMoney": "com.fastmoney.loan",
}

# -----------------------------
# 1. Date window (D-1 IST)
# -----------------------------
today_ist = datetime.now(IST).date()
d1 = today_ist - timedelta(days=1)

start_dt = datetime.combine(d1, datetime.min.time(), IST)
end_dt = datetime.combine(d1, datetime.max.time(), IST)

print(f"📅 Fetching reviews from {start_dt} to {end_dt} (IST)")

# -----------------------------
# 2. Fetch reviews
# -----------------------------
rows = []

for app_name, app_id in APPS.items():
    print(f"📦 Scraping {app_id}")

    result, _ = reviews(
        app_id,
        lang="en",
        country="in",
        sort=Sort.NEWEST,
        count=1000,
    )

    for r in result:
        review_dt = r["at"]

        # Ensure timezone-aware
        if review_dt.tzinfo is None:
            review_dt = review_dt.replace(tzinfo=IST)
        else:
            review_dt = review_dt.astimezone(IST)

        if not (start_dt <= review_dt <= end_dt):
            continue

        row = {
            "review_id": str(r["reviewId"]),
            "app_name": app_name,
            "review_date": review_dt.isoformat(),  # ✅ STRING
            "rating": int(r["score"]),
            "review_text": r.get("content", ""),
            "inserted_on": datetime.now(IST).isoformat(),  # ✅ STRING
        }

        rows.append(row)

print(f"✅ Total D-1 reviews collected: {len(rows)}")

if not rows:
    print("⚠️ No rows to insert. Exiting.")
    exit(0)

# -----------------------------
# 3. Insert into BigQuery
# -----------------------------
bq_client = bigquery.Client(project=PROJECT_ID)
table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

errors = bq_client.insert_rows_json(table_ref, rows)

if errors:
    print("❌ BigQuery insertion errors:")
    for e in errors:
        print(e)
    raise RuntimeError("BigQuery insert failed")

print("🎉 Successfully inserted rows into BigQuery")
