import json
import uuid
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from google.cloud import bigquery
from google_play_scraper import reviews, Sort

# ============================
# CONFIG
# ============================
PROJECT_ID = "valid-cedar-485813-v7"
DATASET_ID = "reviews"
TABLE_ID = "raw_reviews"

APPS = {
    "com.naviapp": "Navi",
    "com.fastmoney.loan": "FastMoney",
}

IST = ZoneInfo("Asia/Kolkata")

# ============================
# DATE WINDOW (D-1 IST)
# ============================
today_ist = datetime.now(IST).date()
d1 = today_ist - timedelta(days=1)

start_dt = datetime.combine(d1, time.min).replace(tzinfo=IST)
end_dt = datetime.combine(d1, time.max).replace(tzinfo=IST)

print(f"📅 Fetching reviews from {start_dt} to {end_dt} (IST)")

# ============================
# BIGQUERY CLIENT
# ============================
bq_client = bigquery.Client(project=PROJECT_ID)
table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

# ============================
# SCRAPING
# ============================
rows = []

for app_id, app_name in APPS.items():
    print(f"📦 Scraping {app_id}")

    result, _ = reviews(
        app_id,
        lang="en",
        country="in",
        sort=Sort.NEWEST,
        count=1000,
    )

    for r in result:
        at = r.get("at")

        # ---- SAFE datetime handling ----
        if isinstance(at, datetime):
            review_dt = at.astimezone(IST)
        else:
            try:
                review_dt = datetime.fromisoformat(str(at)).astimezone(IST)
            except Exception:
                continue

        if not (start_dt <= review_dt <= end_dt):
            continue

        reply_at = r.get("replyAt")
        reply_date = (
            reply_at.astimezone(IST).isoformat()
            if isinstance(reply_at, datetime)
            else None
        )

        row = {
            "review_id": r.get("reviewId") or str(uuid.uuid4()),
            "app_name": app_name,
            "review_date": review_dt.isoformat(),
            "rating": int(r.get("score", 0)),
            "review_text": r.get("content", ""),
            "user_name": r.get("userName"),
            "thumbs_up": int(r.get("thumbsUpCount", 0)),
            "reply_text": r.get("replyContent"),
            "reply_date": reply_date,
            "inserted_on": datetime.now(IST).isoformat(),
        }

        rows.append(row)

print(f"✅ Total D-1 reviews collected: {len(rows)}")

# ============================
# HARD JSON SANITIZATION (KEY FIX)
# ============================
if rows:
    # 🔒 This guarantees ZERO datetime objects survive
    safe_rows = json.loads(json.dumps(rows))

    errors = bq_client.insert_rows_json(
        table_ref,
        safe_rows,
        row_ids=[r["review_id"] for r in safe_rows],
    )

    if errors:
        print("❌ BigQuery insert errors:")
        for e in errors:
            print(e)
        raise RuntimeError("BigQuery insert failed")
    else:
        print("🎉 Successfully inserted rows into BigQuery")
else:
    print("⚠️ No reviews found for D-1")
