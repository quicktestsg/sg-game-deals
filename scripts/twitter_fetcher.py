#!/usr/bin/env python3
"""
Twitter/X Deal Fetcher for SG Game Deals.

Only fetches tweets NEWER than the last run — zero overlap with cached deals.
Records last-run timestamp in scripts/last_twitter_run.txt.

USAGE:
  python3 twitter_fetcher.py              # Fetch new tweets since last run
  python3 twitter_fetcher.py --list       # Show cached Twitter deals only
  python3 twitter_fetcher.py --dry-run    # Search but don't save (preview only)
  python3 twitter_fetcher.py --reset      # Reset last-run timestamp (fetch all)

ZERO TOKENS — pure script. The cron agent only translates new deals.
"""
import subprocess
import json
import re
import sys
import os
import html
import hashlib
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(SCRIPT_DIR, "deals_cache.json")
LAST_RUN_PATH = os.path.join(SCRIPT_DIR, "last_twitter_run.txt")
BIRD = "/opt/homebrew/bin/bird"

# ─── Sources ───
# Each search: (label, query, badge_color, deal_type_default)
SOURCES = [
    {
        "label": "ShopeeSG",
        "query": "from:Shopee_SG gaming OR Switch OR Nintendo OR PS5",
        "color": "#ee4d2d",
        "default_type": "deal",
    },
    {
        "label": "Qisahn",
        "query": "from:qisahn",
        "color": "#3b82f6",
        "default_type": "deal",
    },
]

# ─── Keyword filters ───
INCLUDE_KEYWORDS = [
    "Switch", "PS5", "PS4", "Xbox", "Nintendo", "game", "gaming",
    "console", "controller", "deal", "deals", "sale", "discount",
    "promo", "off", "SGD", "S$", "bundle", "digital", "physical",
    "cartridge", "eShop", "PSN", "Steam",
    "游戏", "主机", "打折", "优惠", "折扣", "特价", "特卖",
]

EXCLUDE_KEYWORDS = [
    "food", "restaurant", "dining", "meal",
    "insurance", "loan", "mortgage",
    "fixed deposit", "savings account", "interest rate",
    "property", "condo launch",
    "食物", "餐厅", "保险",
]


def matches_keywords(text):
    text_lower = text.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text_lower:
            return False
    for kw in INCLUDE_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    return False


def detect_deal_type(text):
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["free", "giveaway", "免费", "赠送"]):
        return "free"
    return "deal"


def get_last_run_date():
    """Read last-run date from file. Returns YYYY-MM-DD string."""
    if os.path.exists(LAST_RUN_PATH):
        with open(LAST_RUN_PATH, "r") as f:
            return f.read().strip()
    # Default: 3 days ago
    dt = datetime.now(timezone.utc) - timedelta(days=3)
    return dt.strftime("%Y-%m-%d")


def save_last_run_date():
    """Save today's date as last-run."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(LAST_RUN_PATH, "w") as f:
        f.write(today)


def search_twitter(query, since_date, count=30):
    """Run bird search with since: filter. Returns list of parsed tweets."""
    # Add since: to query
    full_query = f"{query} since:{since_date}"
    cmd = [BIRD, "search", full_query, "-n", str(count), "--plain"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  ⚠ bird search failed: {result.stderr[:200]}", file=sys.stderr)
            return []
        return parse_bird_output(result.stdout)
    except Exception as e:
        print(f"  ⚠ search error: {e}", file=sys.stderr)
        return []


def parse_bird_output(output):
    """Parse bird --plain output into list of tweet dicts."""
    tweets = []
    current = {}
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("@"):
            if current:
                tweets.append(current)
            # Handle "@handle (Name):"
            m = re.match(r'@(\S+)\s*\((.+?)\)', line)
            if m:
                current = {
                    "handle": m.group(1),
                    "name": m.group(2),
                    "text": "",
                    "url": "",
                    "date": "",
                }
            else:
                current = {"handle": "", "name": "", "text": "", "url": "", "date": ""}
        elif line.startswith("url:"):
            current["url"] = line.replace("url:", "").strip()
        elif line.startswith("date:"):
            current["date"] = line.replace("date:", "").strip()
        elif line.startswith("PHOTO:") or line.startswith("VIDEO:"):
            # Media URLs — collect first photo
            if not current.get("photo"):
                current["photo"] = line.split(":", 1)[1].strip() if ":" in line else ""
        elif line and not line.startswith("─"):
            # Append to text (bird outputs text on lines after handle)
            if current.get("handle"):
                if current["text"]:
                    current["text"] += " "
                current["text"] += line
    if current:
        tweets.append(current)
    return tweets


def extract_tweet_id(url):
    match = re.search(r'/status/(\d+)', url)
    return match.group(1) if match else None


def process_tweets(tweets, source_config, existing_ids):
    """Filter and convert tweets to cache entries. Returns list of new deals."""
    deals = []
    for tweet in tweets:
        if not tweet.get("url") or not tweet.get("text"):
            continue

        tweet_id = extract_tweet_id(tweet["url"])
        if not tweet_id:
            continue
        if tweet_id in existing_ids:
            continue

        text = tweet["text"]
        if not matches_keywords(text):
            continue

        deal = {
            "id": tweet_id,
            "url": tweet["url"],
            "label": source_config["label"],
            "color": source_config["color"],
            "deal_type": detect_deal_type(text),
            "country": "SG",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "translation_zh": "",
            "tweet_data": {
                "text": text,
                "user": {
                    "screen_name": tweet.get("handle", ""),
                    "name": tweet.get("name", ""),
                },
                "created_at": parse_twitter_date(tweet.get("date", "")),
                "favorite_count": 0,
                "reply_count": 0,
                "retweet_count": 0,
                "photos": [{"url": tweet["photo"]}] if tweet.get("photo") else [],
            },
        }
        deals.append(deal)
        existing_ids.add(tweet_id)
    return deals


def parse_twitter_date(date_str):
    """Parse Twitter date format to ISO 8601."""
    try:
        dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")
        return dt.isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    return {"deals": []}


def save_cache(cache):
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch_tweet_data_full(tweet_id):
    """Fetch full tweet data from syndication API (for avatars, verified, counts)."""
    import urllib.request
    url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=a"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def main():
    dry_run = "--dry-run" in sys.argv
    list_only = "--list" in sys.argv
    reset = "--reset" in sys.argv

    cache = load_cache()

    if list_only:
        tw = [d for d in cache["deals"] if d.get("source_type") != "rss"]
        print(f"\nTwitter deals in cache: {len(tw)}")
        for d in sorted(tw, key=lambda x: x.get("tweet_data", {}).get("created_at", ""), reverse=True)[:20]:
            print(f"  [{d['label']}] {d.get('tweet_data',{}).get('text','')[:60]}...")
        return

    if reset:
        if os.path.exists(LAST_RUN_PATH):
            os.remove(LAST_RUN_PATH)
        print("Last-run timestamp reset. Next fetch will get all tweets.", file=sys.stderr)
        return

    since_date = get_last_run_date()
    existing_ids = {d["id"] for d in cache["deals"]}

    print(f"Fetching tweets since {since_date}...", file=sys.stderr)
    print(f"Existing cached IDs: {len(existing_ids)}", file=sys.stderr)

    all_new = []
    for source in SOURCES:
        tweets = search_twitter(source["query"], since_date, count=30)
        new_deals = process_tweets(tweets, source, existing_ids)
        print(f"  {source['label']}: {len(new_deals)} new deals (from {len(tweets)} tweets)", file=sys.stderr)

        if dry_run:
            for d in new_deals:
                print(f"    [NEW] {d['tweet_data']['text'][:70]}")
            all_new.extend(new_deals)
        else:
            # Enrich with full tweet data from syndication API
            for d in new_deals:
                full_data = fetch_tweet_data_full(d["id"])
                if full_data:
                    d["tweet_data"] = full_data
            all_new.extend(new_deals)

    print(f"\nTotal new deals: {len(all_new)}", file=sys.stderr)

    if dry_run:
        return

    # Merge into cache
    before = len(cache["deals"])
    cache["deals"].extend(all_new)
    save_cache(cache)

    # Update last-run timestamp
    save_last_run_date()

    tw_count = len([d for d in cache["deals"] if d.get("source_type") != "rss"])
    rss_count = len([d for d in cache["deals"] if d.get("source_type") == "rss"])

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Twitter Fetch Complete", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  New deals added:    {len(all_new)}", file=sys.stderr)
    print(f"  Searched since:     {since_date}", file=sys.stderr)
    print(f"  Cache:              {before} → {len(cache['deals'])} (Twitter: {tw_count}, RSS: {rss_count})", file=sys.stderr)


if __name__ == "__main__":
    main()
