#!/usr/bin/env python3
"""
RSS Feed Fetcher for SG Game Deals.

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
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(SCRIPT_DIR, "deals_cache.json")

# ─── Feed Sources ───
# Each feed: (source_name, url, brand_color, deal_type_default, language)
# deal_type: "1fl" (1-for-1), "deal" (promo/discount), "free" (freebie)
# language: "en" or "zh" — affects which keyword filters apply
FEEDS = [
    {
        "name": "Slickdeals Gaming",
        "url": "https://slickdeals.net/newsearch.php?mode=frontpage&searchtext=gaming+OR+switch+OR+ps5+OR+xbox&rss=1",
        "color": "#3b82f6",
        "lang": "en",
        "default_type": "deal",
        "favicon": "https://www.google.com/s2/favicons?domain=slickdeals.net&sz=64",
        "max_entries": 30,
    },
    {
        "name": "Slickdeals Video Games",
        "url": "https://slickdeals.net/newsearch.php?mode=frontpage&searchtext=video+games+OR+nintendo+OR+playstation&rss=1",
        "color": "#8b5cf6",
        "lang": "en",
        "default_type": "deal",
        "favicon": "https://www.google.com/s2/favicons?domain=slickdeals.net&sz=64",
        "max_entries": 30,
    },
    {
        "name": "IGN Deals",
        "url": "https://feeds.ign.com/ign-articles-all",
        "color": "#ef4444",
        "lang": "en",
        "default_type": "deal",
        "favicon": "https://www.google.com/s2/favicons?domain=ign.com&sz=64",
        "max_entries": 40,
    },
]

# ─── Keyword Filters ───
# Only keep entries that match gaming deal-related keywords.
# This filters out non-deal posts (general news, reviews without deals, etc.)

INCLUDE_KEYWORDS_EN = [
    "switch", "nintendo", "ps5", "ps4", "playstation",
    "xbox", "series x", "series s",
    "game", "gaming", "console", "controller",
    "steam", "eshop", "playstation store", "psn",
    "deal", "deals", "discount", "sale", "offer",
    "bundle", "off", "save", "lowest",
    "$", "price", "promo",
    "cartridge", "digital download",
]

INCLUDE_KEYWORDS_ZH = [
    "游戏", "主机", "打折", "折扣", "特价", "特卖",
    "免费", "赠送", "送",
    "优惠", "促销", "闪购", "抢购",
    "限时", "礼包",
]

EXCLUDE_KEYWORDS = [
    "fixed deposit", "savings account", "interest rate",
    "insurance", "loan", "mortgage",
    "property", "condo launch", "new launch",
    "food", "restaurant", "dining", "meal",
    "giveaway winner", "congratulations",
    "定期存款", "利率", "保险", "食物", "餐厅",
]


def matches_keywords(title, summary, lang):
    """Check if entry matches gaming deal keywords. Returns True if it's a deal."""
    text = (title + " " + summary).lower()

    # Check excludes first
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            return False

    # Check includes
    keywords = INCLUDE_KEYWORDS_EN
    if lang == "zh":
        keywords = keywords + INCLUDE_KEYWORDS_ZH

    for kw in keywords:
        if kw.lower() in text:
            return True

    return False


def detect_deal_type(title, summary):
    """Auto-detect deal type from text."""
    text = (title + " " + summary).lower()
    if any(kw in text for kw in ["free", "giveaway", "免费", "赠送"]):
        return "free"
    return "deal"


def clean_html(raw_html):
    """Strip HTML tags, decode entities, clean whitespace."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    # Remove script, style, emoji images
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    for img in soup.find_all("img"):
        src = img.get("src", "")
        # Remove WordPress emoji images
        if "s.w.org/images/core/emoji" in src:
            img.decompose()
    text = soup.get_text(separator=" ", strip=True)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def upgrade_image_url(url):
    """Upgrade thumbnail URLs to higher resolution versions."""
    if not url:
        return url
    # Blogger/Google: /s72-c/ → /s640/ (72px → 640px)
    if "blogger.googleusercontent.com" in url or "googleusercontent.com" in url:
        url = re.sub(r'/s\d+-c?/', '/s640/', url)
        url = re.sub(r'/s\d+/', '/s640/', url)
        return url
    # WordPress thumbnails: -150x150, -300x200, -550x292, etc → strip for full-size
    # Matches patterns like image-550x292.jpg, image-300x200.png
    url = re.sub(r'-\d+x\d+(\.(jpg|jpeg|png|webp|gif))', r'\1', url, flags=re.IGNORECASE)
    return url


def get_best_image(entry):
    """Extract the best available image URL from a feed entry, upgraded to high-res."""
    # 1. media_content
    if 'media_content' in entry:
        for mc in entry.media_content:
            url = mc.get('url', '')
            if url and 's.w.org/images/core/emoji' not in url:
                return upgrade_image_url(url)
    # 2. media_thumbnail
    if 'media_thumbnail' in entry:
        for mt in entry.media_thumbnail:
            url = mt.get('url', '')
            if url and 's.w.org/images/core/emoji' not in url:
                return upgrade_image_url(url)
    # 3. enclosures
    if 'enclosures' in entry:
        for en in entry.enclosures:
            if 'image' in en.get('type', ''):
                return upgrade_image_url(en.get('href', ''))
    # 4. First <img> in content/summary
    content = ""
    if 'content' in entry:
        content = entry.content[0].get('value', '')
    elif 'summary' in entry:
        content = entry.summary
    imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    for img_url in imgs:
        if 's.w.org/images/core/emoji' not in img_url:
            return upgrade_image_url(img_url)
    return None


def get_excerpt(raw_html, max_chars=200):
    """Extract a clean text excerpt from HTML content."""
    text = clean_html(raw_html)
    if len(text) > max_chars:
        # Cut at word boundary
        cut = text[:max_chars].rsplit(' ', 1)[0]
        return cut + "..."
    return text


def parse_date(entry):
    """Parse feed entry date to ISO 8601 string."""
    for field in ('published_parsed', 'updated_parsed'):
        if field in entry and entry[field]:
            dt = datetime(*entry[field][:6], tzinfo=timezone.utc)
            return dt.isoformat()
    # Fallback: try parsing string directly
    for field in ('published', 'updated'):
        if field in entry:
            try:
                dt = datetime.fromisoformat(entry[field].replace('Z', '+00:00'))
                return dt.isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def generate_id(entry):
    """Generate a unique ID for dedup. Uses link hash."""
    link = entry.get('link', '') or entry.get('id', '')
    if link:
        return hashlib.md5(link.encode()).hexdigest()[:16]
    return hashlib.md5(entry.get('title', '').encode()).hexdigest()[:16]


def fetch_feed(feed_config):
    """Fetch and parse a single RSS feed. Returns list of deal entries."""
    name = feed_config["name"]
    url = feed_config["url"]
    lang = feed_config["lang"]
    default_type = feed_config["default_type"]

    try:
        d = feedparser.parse(url)
        if d.bozo and not d.entries:
            print(f"  ⚠ {name}: feed parsed but no entries", file=sys.stderr)
            return []

        deals = []
        max_entries = feed_config.get("max_entries", 50)
        for entry in d.entries[:max_entries]:
            title = entry.get('title', '')
            if not title:
                continue

            # Get content for keyword matching
            raw_content = ""
            if 'content' in entry:
                raw_content = entry.content[0].get('value', '')
            elif 'summary' in entry:
                raw_content = entry.summary

            summary = get_excerpt(raw_content, max_chars=300)

            # Filter by keywords
            if not matches_keywords(title, summary, lang):
                continue

            # Extract structured data
            deal = {
                "id": generate_id(entry),
                "source_type": "rss",
                "source_name": name,
                "source_url": entry.get('link', ''),
                "source_color": feed_config["color"],
                "source_favicon": feed_config["favicon"],
                "source_lang": lang,
                "title": clean_html(title),
                "excerpt": summary,
                "image": get_best_image(entry),
                "deal_type": detect_deal_type(title, summary),
                "country": "SG",
                "published_at": parse_date(entry),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "translation_zh": "",
            }
            deals.append(deal)

        print(f"  ✓ {name}: {len(deals)} deals from {len(d.entries)} entries", file=sys.stderr)
        return deals

    except Exception as e:
        print(f"  ✗ {name}: {e}", file=sys.stderr)
        return []


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    return {"deals": []}


def save_cache(cache):
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def merge_rss_deals(cache, new_deals, max_age_days=7):
    """
    Merge RSS deals into cache, skipping duplicates by ID.
    Only keep deals from the last max_age_days.
    Returns (cache, num_new, num_skipped).
    """
    existing_ids = {d["id"] for d in cache["deals"]}
    existing_links = {
        d.get("source_url", "") or d.get("url", "")
        for d in cache["deals"]
    }
    num_new = 0
    num_skipped = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    for deal in new_deals:
        if deal["id"] in existing_ids or deal["source_url"] in existing_links:
            num_skipped += 1
            continue
        # Check age
        try:
            pub_date = datetime.fromisoformat(deal["published_at"].replace("Z", "+00:00"))
            if pub_date < cutoff:
                continue
        except Exception:
            pass

        cache["deals"].append(deal)
        existing_ids.add(deal["id"])
        existing_links.add(deal["source_url"])
        num_new += 1

    return cache, num_new, num_skipped


def list_rss_deals(cache):
    """Print all RSS-sourced deals in the cache."""
    rss_deals = [d for d in cache["deals"] if d.get("source_type") == "rss"]
    if not rss_deals:
        print("No RSS deals in cache.")
        return
    print(f"\n{'='*80}")
    print(f"RSS Deals in Cache: {len(rss_deals)}")
    print(f"{'='*80}")
    for d in sorted(rss_deals, key=lambda x: x.get("published_at", ""), reverse=True):
        print(f"\n  [{d['source_name']}] {d['title'][:70]}")
        print(f"    type: {d['deal_type']}  lang: {d['source_lang']}  img: {'✓' if d.get('image') else '✗'}")
        print(f"    link: {d['source_url'][:70]}")


def main():
    dry_run = "--dry-run" in sys.argv
    list_only = "--list" in sys.argv

    cache = load_cache()

    if list_only:
        list_rss_deals(cache)
        return

    print(f"Fetching RSS feeds from {len(FEEDS)} sources...", file=sys.stderr)
    all_new = []
    for feed_cfg in FEEDS:
        deals = fetch_feed(feed_cfg)
        all_new.extend(deals)

    print(f"\nTotal candidate deals: {len(all_new)}", file=sys.stderr)

    if dry_run:
        print("\n[DRY RUN] Deals that would be added:", file=sys.stderr)
        existing_ids = {d["id"] for d in cache["deals"]}
        existing_links = {d.get("source_url", "") or d.get("url", "") for d in cache["deals"]}
        for d in all_new:
            is_dup = d["id"] in existing_ids or d["source_url"] in existing_links
            tag = "DUP" if is_dup else "NEW"
            print(f"  [{tag}] [{d['source_name']}] {d['title'][:70]}")
        return

    before = len(cache["deals"])
    cache, num_new, num_skipped = merge_rss_deals(cache, all_new)
    save_cache(cache)

    rss_count = len([d for d in cache["deals"] if d.get("source_type") == "rss"])
    twitter_count = len([d for d in cache["deals"] if d.get("source_type") != "rss"])

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"RSS Fetch Complete", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  New deals added:    {num_new}", file=sys.stderr)
    print(f"  Duplicates skipped: {num_skipped}", file=sys.stderr)
    print(f"  Cache before:       {before}", file=sys.stderr)
    print(f"  Cache after:        {len(cache['deals'])} (Twitter: {twitter_count}, RSS: {rss_count})", file=sys.stderr)


if __name__ == "__main__":
    main()
