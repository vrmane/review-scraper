import os
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from dateutil import parser
from google.cloud import bigquery
from google_play_scraper import reviews, Sort

# ---------------- CONFIG ----------------
PROJECT_ID = "valid-cedar-485813-v7"
DATASET_ID = "reviews"
TABLE_ID = "raw_reviews"

APPS = {
    "com.naviapp": "Navi",
    "com.fastmoney.loan": "FastMoney"
}

IST = ZoneInfo("Asia/Kolkata")

# ---------------- DATE RANGE (D-1) ----------------
today_ist = datetime.now(IST).date()
d1 = today_ist - timedelta(days=1)

START_DT = datetime.combine(d1, time.min, IST)
END_DT = datetime.combine(d1, time.max, IST)

print(f"📅 Fetching reviews from {START_DT} to {END_DT} (IST)")

# ---------------- BIGQUERY CLIENT ----------------
bq_client = bigquery.Client(project=PROJECT_ID)
table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

rows_to_insert = []

# ---------------- SCRAPING ----------------
for app_id, app_name in APPS.items():
    print(f"📦 Scraping {app_id}")

    result, _ = reviews(
        app_id,
        lang="en",
        country="in",
        sort=Sort.NEWEST,
        count=1000
    )

    for r in result:
        raw_dt = r.get("at")

        # Handle both datetime and string safely
        if isinstance(raw_dt, datetime):
            review_dt = raw_dt.astimezone(IST)
        else:
            review_dt = parser.isoparse(str(raw_dt)).astimezone(IST)

        if not (START_DT <= review_dt <= END_DT):
            continue

        rows_to_insert.append({
            "review_id": r.get("reviewId"),
            "app_name": app_name,
            "review_date": review_dt.isoformat(),          # ✅ STRING
            "rating": int(r.get("score", 0)),
            "review_text": r.get("content", ""),
            "inserted_on": datetime.now(IST).isoformat()   # ✅ STRING
        })

print(f"✅ Total D-1 reviews collected: {len(rows_to_insert)}")

# ---------------- BIGQUERY INSERT ----------------
if rows_to_insert:
    errors = bq_client.insert_rows_json(
        table_ref,
        rows_to_insert,
        row_ids=[r["review_id"] for r in rows_to_insert]
    )

    if errors:
        print("❌ BigQuery insert errors:")
        for e in errors:
            print(e)
    else:
        print("🎉 Successfully inserted rows into BigQuery")
else:
    print("⚠️ No reviews found for D-1")
