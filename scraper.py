import requests
import pandas as pd
import time
import os
from datetime import datetime, timezone
from supabase import create_client

SUPABASE_URL = "https://fnldzkdgrxjtljretgda.supabase.co"
SUPABASE_KEY = "sb_publishable_viHBsJ0z28PcAcKahfClPA_UTtvBfYt"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

# ── Step 1: collect appids ───────────────────────────────────────────────────
appids = []

for page in range(1, 4):
    params = {
        "filter": "topsellers",
        "cc":     "BE",
        "l":      "english",
        "page":   page,
        "json":   1
    }
    r = requests.get(
        "https://store.steampowered.com/search/results/",
        params=params, headers=headers, timeout=20
    )
    items = r.json().get("items", [])
    for item in items:
        logo  = item.get("logo", "")
        parts = [p for p in logo.split("/") if p.isdigit()]
        if parts:
            appids.append(parts[0])

appids = list(dict.fromkeys(appids))[:30]
print(f"Collected {len(appids)} app IDs")

# ── Step 2: fetch full metadata per appid ───────────────────────────────────
rows = []
scraped_at = datetime.now(timezone.utc).isoformat()

for appid in appids:
    r = requests.get(
        "https://store.steampowered.com/api/appdetails",
        params={"appids": appid, "cc": "BE", "filters": "price_overview,basic,genres,categories"},
        headers=headers,
        timeout=20
    )
    data  = r.json().get(appid, {}).get("data", {})
    title = data.get("name", "N/A")
    price = data.get("price_overview", {})

    final_price    = round(price.get("final",           0) / 100, 2) if price else 0.0
    original_price = round(price.get("initial",         0) / 100, 2) if price else 0.0
    discount_pct   = price.get("discount_percent",       0)          if price else 0
    is_free        = data.get("is_free", False)

    if price:
        price_raw = f"€{final_price:.2f}"
    elif is_free:
        price_raw = "Free"
    else:
        price_raw = "N/A"

    genres    = ", ".join([g["description"] for g in data.get("genres",     [])]) or "Unknown"
    developer = ", ".join(data.get("developers", [])) or "Unknown"
    publisher = ", ".join(data.get("publishers", [])) or "Unknown"
    review_score = data.get("metacritic", {}).get("score", None)

    rows.append({
        "appid":          appid,
        "title":          title,
        "genres":         genres,
        "developer":      developer,
        "publisher":      publisher,
        "review_score":   review_score,
        "price_raw":      price_raw,
        "final_price":    final_price,
        "original_price": original_price,
        "discount_pct":   discount_pct,
        "is_free":        is_free,
        "scraped_at":     scraped_at,
    })

    time.sleep(0.3)

# ── Step 3: clean + insert ───────────────────────────────────────────────────
df = pd.DataFrame(rows)
df["title"]     = df["title"].fillna("Unknown")
df["genres"]    = df["genres"].fillna("Unknown")
df["developer"] = df["developer"].fillna("Unknown")
df["publisher"] = df["publisher"].fillna("Unknown")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

insert_rows = []
for _, row in df.iterrows():
    insert_rows.append({
        "appid":          str(row["appid"]),
        "title":          str(row["title"]),
        "genres":         str(row["genres"]),
        "developer":      str(row["developer"]),
        "publisher":      str(row["publisher"]),
        "review_score":   int(row["review_score"]) if row["review_score"] else None,
        "price_raw":      str(row["price_raw"]),
        "final_price":    float(row["final_price"]),
        "original_price": float(row["original_price"]),
        "discount_pct":   int(row["discount_pct"]),
        "is_free":        bool(row["is_free"]),
        "scraped_at":     str(row["scraped_at"]),
    })

result = supabase.table("mkdir -p .github/workflowsgames").insert(insert_rows).execute()
print(f"✅ Inserted {len(insert_rows)} rows at {scraped_at}")