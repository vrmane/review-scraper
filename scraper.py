import os
import json
import uuid
from datetime import datetime, timedelta
from dateutil import parser
import pytz

from google.cloud import bigquery
from google_play_scraper import reviews, Sort


# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
PROJECT_ID = "valid-cedar-485813-v7"
DATASET_ID = "reviews"
TABLE_ID = "raw_reviews"

APP_IDS = [
    "com.naviapp",
    "com.fastmoney.loan",
]

IST = pytz.timezone("Asia/Kolkata")


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def to_iso(val):
    """Convert datetime → ISO string, leave others untouched"""
    if isinstance(val, datetime):
        return val.isoformat()
    return val


def parse_datetime(val):
    """
    google-play-scraper may return:
    - datetime
    - ISO string
    - None
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.astimezone(IST)
    return parser.isoparse(str(val)).astimezone(IST)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # ── D-1 window (IST)
    today_ist = datetime.now(IST).date()
    d1 = today_ist - timedelta(days=1)

    start_dt = IST.localize(datetime.combine(d1, datetime.min.time()))
    end_dt = IST.localize(datetime.combine(d1, datetime.max.time()))

    print(
        f"📅 Fetching reviews from {start_dt} to {end_dt} (IST)",
        flush=True,
    )

    all_rows = []

    # ── Scrape apps
    for app_id in APP_IDS:
        print(f"📦 Scraping {app_id}", flush=True)

        result, _ = reviews(
            app_id,
            lang="en",
            country="in",
            sort=Sort.NEWEST,
            count=1000,
        )

        for r in result:
            review_dt = parse_datetime(r.get("at"))
            if not review_dt:
                continue

            if not (start_dt <= review_dt <= end_dt):
                continue

            reply_dt = parse_datetime(r.get("repliedAt"))

            row = {
                "review_id": r.get("reviewId") or str(uuid.uuid4()),
                "app_name": app_id,
                "review_date": to_iso(review_dt),
                "rating": int(r.get("score") or 0),
                "review_text": r.get("content") or "",
                "inserted_on": datetime.now(IST).isoformat(),
            }

            all_rows.append(row)

    print(f"✅ Total D-1 reviews collected: {len(all_rows)}", flush=True)

    if not all_rows:
        print("⚠️ No reviews to insert. Exiting.", flush=True)
        exit(0)

    # ─────────────────────────────────────────────────────────────
    # BIGQUERY INSERT (SAFE)
    # ─────────────────────────────────────────────────────────────
    bq_client = bigquery.Client(project=PROJECT_ID)

    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    # 🔥 HARD JSON SANITIZATION (CRITICAL FIX)
    safe_rows = json.loads(json.dumps(all_rows))

    errors = bq_client.insert_rows_json(
        table_ref,
        safe_rows,
        row_ids=[r["review_id"] for r in safe_rows],
    )

    if errors:
        print("❌ BigQuery insertion errors:")
        print(errors)
        raise RuntimeError("BigQuery insert failed")

    print(f"🎯 Successfully inserted {len(safe_rows)} rows into {table_ref}", flush=True)
