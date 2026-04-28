import requests
import pandas as pd
import time
import os
from datetime import datetime, timezone
from supabase import create_client

print("🚀 Starting Steam pipeline...")

# ── Supabase credentials (from GitHub Secrets) ──
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Headers ─────────────────────────────────────
headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9"
}

# ── Step 1: collect appids ─────────────────────
appids = []

for page in range(1, 4):
    try:
        params = {
            "filter": "topsellers",
            "cc": "BE",
            "l": "english",
            "page": page,
            "json": 1
        }

        r = requests.get(
            "https://store.steampowered.com/search/results/",
            params=params,
            headers=headers,
            timeout=20
        )

        items = r.json().get("items", [])

        for item in items:
            logo = item.get("logo", "")
            parts = [p for p in logo.split("/") if p.isdigit()]
            if parts:
                appids.append(parts[0])

    except Exception as e:
        print(f"❌ Error on page {page}: {e}")

# remove duplicates + limit
appids = list(dict.fromkeys(appids))[:30]
print(f"Collected {len(appids)} app IDs")

# ── Step 2: fetch metadata ─────────────────────
rows = []
scraped_at = datetime.now(timezone.utc).isoformat()

for appid in appids:
    try:
        r = requests.get(
            "https://store.steampowered.com/api/appdetails",
            params={
                "appids": appid,
                "cc": "BE",
                "filters": "price_overview,basic,genres,categories"
            },
            headers=headers,
            timeout=20
        )

        data = r.json().get(appid, {}).get("data", {})

        title = data.get("name", "N/A")
        price = data.get("price_overview", {})

        final_price = round(price.get("final", 0) / 100, 2) if price else 0.0
        original_price = round(price.get("initial", 0) / 100, 2) if price else 0.0
        discount_pct = price.get("discount_percent", 0) if price else 0
        is_free = data.get("is_free", False)

        if price:
            price_raw = f"€{final_price:.2f}"
        elif is_free:
            price_raw = "Free"
        else:
            price_raw = "N/A"

        genres = ", ".join([g["description"] for g in data.get("genres", [])]) or "Unknown"
        developer = ", ".join(data.get("developers", [])) or "Unknown"
        publisher = ", ".join(data.get("publishers", [])) or "Unknown"
        review_score = data.get("metacritic", {}).get("score", None)

        rows.append({
            "appid": str(appid),
            "title": str(title),
            "genres": str(genres),
            "developer": str(developer),
            "publisher": str(publisher),
            "review_score": int(review_score) if review_score else None,
            "price_raw": str(price_raw),
            "final_price": float(final_price),
            "original_price": float(original_price),
            "discount_pct": int(discount_pct),
            "is_free": bool(is_free),
            "scraped_at": scraped_at
        })

        time.sleep(0.3)

    except Exception as e:
        print(f"❌ Error fetching app {appid}: {e}")

# ── Step 3: clean + insert ─────────────────────
df = pd.DataFrame(rows)

if df.empty:
    print("⚠️ No data collected — stopping pipeline")
    exit()

df["title"] = df["title"].fillna("Unknown")
df["genres"] = df["genres"].fillna("Unknown")
df["developer"] = df["developer"].fillna("Unknown")
df["publisher"] = df["publisher"].fillna("Unknown")

insert_rows = df.to_dict(orient="records")

result = supabase.table("steamgames").insert(insert_rows).execute()

if result.data:
    print(f"✅ Inserted {len(insert_rows)} rows at {scraped_at}")
else:
    print("❌ Insert failed:", result)


avg_price = df["final_price"].mean()

# Alert 1: Low average price
if avg_price < 10:
    print(f"⚠️ ALERT: Average price dropped to €{avg_price:.2f}")

# Alert 2: Free games
free_games = df[df["is_free"] == True]
if not free_games.empty:
    print(f"🎮 {len(free_games)} free games detected")

# Alert 3: High discounts
high_discount = df[df["discount_pct"] > 70]
if not high_discount.empty:
    print(f"🔥 {len(high_discount)} games with >70% discount detected")

print("🏁 Pipeline finished")