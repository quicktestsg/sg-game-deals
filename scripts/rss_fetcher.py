#!/usr/bin/env python3
"""
RSS Feed Fetcher for GG Deals.

Fetches deal/promo entries from gaming deal blogs and aggregators via their RSS
feeds, extracts structured data (title, excerpt, image, date, link), and merges
into the same deals_cache.json used by the Twitter deal pipeline.

USAGE:
  python3 rss_fetcher.py              # Fetch from all configured feeds
  python3 rss_fetcher.py --list       # Show cached RSS deals only
  python3 rss_fetcher.py --dry-run    # Fetch but don't save (preview only)

ZERO TOKENS — this is a pure script, no AI reasoning needed.
The cron agent only needs to read the cached data for synthesis/rewriting.
"""
import feedparser
import json
import re
import sys
import os
import html
import urllib.request
import hashlib
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(SCRIPT_DIR, "deals_cache.json")

# ─── Feed Sources ───
# Focus on gaming news + deal sources. The cron agent will synthesize original
# deal content from these feeds — we don't copy the original text verbatim.
FEEDS = [
    {
        "name": "Nintendo Life",
        "url": "https://www.nintendolife.com/feeds/latest",
        "color": "#e60012",
        "lang": "en",
        "default_type": "deal",
        "favicon": "https://www.google.com/s2/favicons?domain=nintendolife.com&sz=64",
        "max_entries": 20,
    },
    {
        "name": "Push Square",
        "url": "https://www.pushsquare.com/feeds/latest",
        "color": "#003791",
        "lang": "en",
        "default_type": "deal",
        "favicon": "https://www.google.com/s2/favicons?domain=pushsquare.com&sz=64",
        "max_entries": 20,
    },
    {
        "name": "Pure Xbox",
        "url": "https://www.purexbox.com/feeds/latest",
        "color": "#107c10",
        "lang": "en",
        "default_type": "deal",
        "favicon": "https://www.google.com/s2/favicons?domain=purexbox.com&sz=64",
        "max_entries": 20,
    },
    {
        "name": "VG247",
        "url": "https://www.vg247.com/feed",
        "color": "#8b5cf6",
        "lang": "en",
        "default_type": "deal",
        "favicon": "https://www.google.com/s2/favicons?domain=vg247.com&sz=64",
        "max_entries": 20,
    },
    {
        "name": "Eurogamer",
        "url": "https://www.eurogamer.net/feed",
        "color": "#06b6d4",
        "lang": "en",
        "default_type": "deal",
        "favicon": "https://www.google.com/s2/favicons?domain=eurogamer.net&sz=64",
        "max_entries": 20,
    },
    {
        "name": "Slickdeals Gaming",
        "url": "https://slickdeals.net/newsearch.php?mode=frontpage&searchtext=gaming+OR+switch+OR+ps5+OR+xbox&rss=1",
        "color": "#3b82f6",
        "lang": "en",
        "default_type": "deal",
        "favicon": "https://www.google.com/s2/favicons?domain=slickdeals.net&sz=64",
        "max_entries": 15,
    },
]

# ─── Keyword Filters ───
# Keep entries about deals, sales, discounts, new releases, DLC, etc.

INCLUDE_KEYWORDS_EN = [
    "deal", "deals", "discount", "sale", "offer", "price drop", "price cut",
    "save", "off", "lowest", "cheapest", "free", "freebie",
    "pre-order", "preorder", "launch", "releasing", "out now",
    "eshop", "playstation store", "psn", "xbox store", "steam",
    "game pass", "switch online", "bundle", "controller",
    "switch", "nintendo", "ps5", "ps4", "playstation",
    "xbox", "series x", "series s",
    "dlc", "expansion", "update", "patch",
    "restock", "back in stock",
    "review", "hands-on", "impressions",  # for guide synthesis
]

INCLUDE_KEYWORDS_ZH = [
    "优惠", "打折", "折扣", "特价", "促销", "免费",
    "预购", "首发", "新品",
]

EXCLUDE_KEYWORDS = [
    "food", "restaurant", "dining", "recipe",
    "insurance", "loan", "mortgage", "property",
    "contest", "giveaway",  # too region-specific
    "movie", "tv show", "anime",  # off-topic
    # Non-gaming merch that Slickdeals' loose search surfaces — these slip
    # through because generic words like "deal"/"off"/"save" match any listing.
    "tool chest", "rolling tool", "air conditioner", "mini split",
    "fleece hoodie", "trail running shoe", "running shoe",
    "reading light", "supertank printer", "vinyl",
    "suction cup", "air duster", "compressed air",
    "collectible figure", "action figure",  # toys, not games
    # Apparel / footwear that Slickdeals surfaces alongside "gaming" searches
    "shoes", "sneakers", "hiking shoes", "golf shoes", "bralette",
    "athletic shoes", "apparel", "jacket", " hoodie", "sock",
    # Home / kitchen / tools / non-gaming electronics
    "coffee", "ground coffee", "stuffing mix", "grocery",
    "borescope", "socket set", "right angle attachment",
    "tool organizer", "deep drawer", "water bottle",
    "insulated stainless", "smart tv", '4k uhd', "led smart tv",
    # Travel / loyalty / subscriptions (non-gaming)
    "vpn", "rewards offer", "elite night credit", "hotel",
    "subscription plan",  # generic sub plans (Surfshark, etc.)
]


def matches_keywords(title, excerpt=""):
    text = f"{title} {excerpt}".lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            return False
    for kw in INCLUDE_KEYWORDS_EN:
        if kw.lower() in text:
            return True
    for kw in INCLUDE_KEYWORDS_ZH:
        if kw in text:
            return True
    return False


def detect_deal_type(title, excerpt=""):
    text = f"{title} {excerpt}".lower()
    if any(kw in text for kw in ["free", "giveaway", "免费"]):
        return "free"
    if any(kw in text for kw in ["1-for-1", "buy one get one", "bogo", "买一送一"]):
        return "1fl"
    return "deal"


def upgrade_image_url(url):
    """Try to get higher quality images from common CDN patterns."""
    if not url:
        return url
    # WordPress thumbnail → full size
    url = re.sub(r'-\d+x\d+\.(jpg|png|webp)', r'.\1', url)
    return url


def strip_html(text):
    """Remove HTML tags from text."""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = html.unescape(clean)
    return clean.strip()


def extract_excerpt(entry):
    """Get a clean text excerpt from the RSS entry."""
    # Try summary first
    raw = entry.get("summary", "") or entry.get("description", "")
    if not raw:
        raw = entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
    text = strip_html(raw)
    # Truncate
    if len(text) > 200:
        text = text[:197].rsplit(" ", 1)[0] + "..."
    return text


def extract_image(entry):
    """Extract first image from RSS entry."""
    # 1. media_thumbnail / media_content
    for key in ("media_thumbnail", "media_content"):
        media = entry.get(key, [])
        if media and isinstance(media, list) and media[0].get("url"):
            return upgrade_image_url(media[0]["url"])
    # 2. Enclosures
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return upgrade_image_url(enc["href"])
    # 3. Parse from summary HTML
    raw = entry.get("summary", "") or ""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw)
    if m:
        return upgrade_image_url(m.group(1))
    return None


def parse_date(entry):
    """Parse entry date to ISO format."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass
    # Fallback: string parsing
    for field in ("published", "updated"):
        date_str = entry.get(field, "")
        if date_str:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def make_id(entry):
    """Generate stable unique ID from entry."""
    raw = entry.get("id", "") or entry.get("link", "") or entry.get("title", "")
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    return {"deals": []}


def save_cache(cache):
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def main():
    dry_run = "--dry-run" in sys.argv
    list_only = "--list" in sys.argv

    cache = load_cache()

    if list_only:
        rss = [d for d in cache["deals"] if d.get("source_type") == "rss"]
        print(f"\nRSS deals in cache: {len(rss)}")
        for d in sorted(rss, key=lambda x: x.get("published_at", ""), reverse=True)[:20]:
            print(f"  [{d.get('source_name','')}] {d.get('title','')[:70]}")
        return

    existing_ids = {d["id"] for d in cache["deals"]}
    print(f"Fetching RSS feeds from {len(FEEDS)} sources...", file=sys.stderr)
    print(f"Existing cached IDs: {len(existing_ids)}", file=sys.stderr)

    all_new = []
    for feed_config in FEEDS:
        try:
            feed = feedparser.parse(feed_config["url"])
            if not feed.entries:
                print(f"  ⚠ {feed_config['name']}: no entries", file=sys.stderr)
                continue

            count = 0
            skipped = 0
            for entry in feed.entries[:feed_config["max_entries"]]:
                title = strip_html(entry.get("title", ""))
                excerpt = extract_excerpt(entry)
                link = entry.get("link", "")

                if not title:
                    skipped += 1
                    continue

                # Keyword filter
                if not matches_keywords(title, excerpt):
                    skipped += 1
                    continue

                deal_id = make_id(entry)
                if deal_id in existing_ids:
                    skipped += 1
                    continue

                deal = {
                    "id": deal_id,
                    "title": title,
                    "excerpt": excerpt,
                    "image": extract_image(entry),
                    "source_type": "rss",
                    "source_name": feed_config["name"],
                    "source_url": link,
                    "source_favicon": feed_config["favicon"],
                    "source_color": feed_config["color"],
                    "deal_type": detect_deal_type(title, excerpt),
                    "country": "SG",
                    "published_at": parse_date(entry),
                    "translation_zh": "",
                    "excerpt_zh": "",
                }
                all_new.append(deal)
                existing_ids.add(deal_id)
                count += 1

            print(f"  ✓ {feed_config['name']}: {count} deals from {len(feed.entries)} entries ({skipped} skipped)", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠ {feed_config['name']}: {e}", file=sys.stderr)

    print(f"\nTotal candidate deals: {len(all_new)}", file=sys.stderr)

    if dry_run:
        for d in all_new:
            print(f"  [NEW] [{d['source_name']}] {d['title'][:70]}")
        return

    before = len(cache["deals"])
    cache["deals"].extend(all_new)
    save_cache(cache)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"RSS Fetch Complete", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  New deals added:    {len(all_new)}", file=sys.stderr)
    print(f"  Cache:              {before} → {len(cache['deals'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
