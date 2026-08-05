#!/usr/bin/env python3
"""
Fetch tweet/post data via syndication API and generate native HTML cards
for the GG Deals design system.

INCREMENTAL MODE:
- Deals are stored persistently in deals_cache.json
- Only NEW tweet/post URLs need to be fetched — existing ones reuse cached data
- Dedup by tweet ID — if a tweet is already in the cache, it's skipped
- The cron job only needs to pass new URLs; old deals stay
"""
import json
import urllib.request
import re
import sys
import html
import os
from datetime import datetime, timezone, timedelta

# ── Paths ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(SCRIPT_DIR, "deals_cache.json")

# ── New tweets to add (set by cron job or manual run) ──
# Format: list of (url, label, badge_color, deal_type, country) tuples
# deal_type: "1fl" (1-for-1), "deal" (discount/promo), "free" (freebie)
# country: "SG", "MY", etc.
# Leave empty to just rebuild from cache
NEW_TWEETS = []


def load_cache():
    """Load the persistent deals cache. Returns dict with 'deals' list."""
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    return {"deals": []}


def save_cache(cache):
    """Save the persistent deals cache."""
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def extract_tweet_id(url):
    match = re.search(r'/status/(\d+)', url)
    return match.group(1) if match else None


def fetch_tweet_data(tweet_id):
    """Fetch structured tweet data from Twitter's syndication API."""
    url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=a"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def format_count(n):
    """Format like/reply counts (1234 -> 1.2K)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def format_date(date_str):
    """Format ISO date to 'Jul 25' style, converted to SGT (UTC+8).
    Returns '' for missing/unparseable dates so build never crashes.
    """
    if not date_str or not date_str.strip():
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return ""
    sgt = dt + timedelta(hours=8)
    return sgt.strftime("%b %-d")


def process_text(text):
    """Convert tweet text to HTML — linkify URLs and @mentions."""
    text = html.escape(text)
    # Linkify @mentions
    text = re.sub(
        r'@(\w+)',
        r'<a href="https://x.com/\1" target="_blank" rel="noopener">@\1</a>',
        text
    )
    return text


def get_best_photo(tweet):
    """Get the highest quality photo from tweet, including card preview images."""
    # 1. Direct photos attached to the tweet
    photos = tweet.get("photos", [])
    if photos:
        photo = photos[0]
        url = photo.get("url", "")
        if "pbs.twimg.com" in url:
            return url.replace("normal", "large")
        return url
    # 2. Media array (videos/photos)
    for media in tweet.get("media", []):
        if media.get("type") == "photo":
            url = media.get("media_url_https", "")
            return url.replace("normal", "large") if "pbs.twimg.com" in url else url
    # 3. Card preview image (most deal tweets use link cards)
    card = tweet.get("card", {})
    if card:
        bv = card.get("binding_values", {})
        # Try largest available sizes
        for key in ("thumbnail_image_original",
                     "photo_image_full_size_original",
                     "thumbnail_image_x_large",
                     "summary_photo_image_x_large",
                     "photo_image_full_size_large",
                     "thumbnail_image_large"):
            val = bv.get(key, {})
            img_url = val.get("image_value", {}).get("url", "")
            if img_url:
                return img_url
    return None


def get_video_poster(tweet):
    """Get video thumbnail."""
    video = tweet.get("video", {})
    if video:
        return video.get("poster", "")
    for media in tweet.get("media", []):
        if media.get("type") == "video":
            return media.get("media_url_https", "")
    return None


def escape_attr(text):
    """Escape text for use in an HTML attribute value (quotes)."""
    return text.replace('"', '&quot;')


def generate_card(url, label, badge_color, data, translation_zh="", deal_type="deal", country="SG"):
    """Generate a native HTML card for a tweet/deal."""
    user = data.get("user", {})
    name = html.escape(user.get("name", ""))
    handle = user.get("screen_name", "")
    avatar = user.get("profile_image_url_https", "").replace("_normal", "_bigger")
    verified = user.get("is_blue_verified", False)

    raw_text = data.get("text", "")
    text_en = process_text(raw_text)

    # Use provided translation, or fall back to English
    text_zh = process_text(translation_zh) if translation_zh else text_en

    attr_en = escape_attr(text_en)
    attr_zh = escape_attr(text_zh)

    date_str = format_date(data.get("created_at", ""))

    likes = format_count(data.get("favorite_count", 0))
    replies = format_count(data.get("reply_count", 0))
    retweets = format_count(data.get("retweet_count", 0))

    photo = get_best_photo(data)
    video_poster = get_video_poster(data)
    media_url = photo or video_poster

    media_html = ""
    if media_url:
        media_html = f'''
        <div class="deal-media" data-full="{media_url}">
            <img src="{media_url}" alt="" loading="lazy" />
        </div>'''

    verified_html = ""
    if verified:
        verified_html = '<svg class="verified-badge" width="16" height="16" viewBox="0 0 22 22" fill="none"><path d="M20.396 11c-.018-.646-.215-1.275-.57-1.816-.354-.54-.852-.972-1.438-1.246.223-.607.27-1.264.14-1.897-.131-.634-.437-1.218-.882-1.687-.47-.445-1.053-.75-1.687-.882-.633-.13-1.29-.083-1.897.14-.273-.587-.704-1.086-1.245-1.44S11.647 1.62 11 1.604c-.646.017-1.273.213-1.813.568s-.972.854-1.245 1.44c-.608-.223-1.267-.272-1.902-.14-.635.13-1.22.436-1.69.882-.445.47-.749 1.055-.878 1.688-.13.633-.08 1.29.144 1.896-.587.274-1.087.705-1.443 1.245-.356.54-.555 1.17-.574 1.817.02.647.218 1.276.574 1.817.356.54.856.972 1.443 1.245-.224.606-.274 1.263-.144 1.896.13.634.433 1.218.877 1.688.47.443 1.054.747 1.687.878.633.132 1.29.084 1.897-.136.274.586.705 1.084 1.246 1.439.54.354 1.17.551 1.816.569.647-.016 1.276-.213 1.817-.567s.972-.854 1.245-1.44c.604.239 1.266.296 1.903.164.636-.132 1.22-.447 1.68-.907.46-.46.776-1.044.908-1.681s.075-1.299-.165-1.903c.586-.274 1.084-.705 1.439-1.246.354-.54.551-1.17.569-1.816zM9.662 14.85l-3.429-3.428 1.293-1.302 2.072 2.072 4.4-4.794 1.347 1.246z" fill="currentColor"/></svg>'

    # Deal type tag
    tag_class = f"deal-tag-{deal_type}"
    tag_labels_en = {"1fl": "1-for-1", "deal": "PROMO", "free": "FREE"}
    tag_labels_zh = {"1fl": "买一送一", "deal": "优惠", "free": "免费"}
    tag_label = tag_labels_en.get(deal_type, "DEAL")
    tag_label_zh = tag_labels_zh.get(deal_type, "优惠")

    return f'''        <article class="deal-card fade-in" data-country="{country}">
            <div class="deal-header">
                <img src="{avatar}" alt="" class="deal-avatar" loading="lazy" />
                <div class="deal-author">
                    <span class="deal-name">{name}{verified_html}</span>
                    <span class="deal-handle">@{handle} · {date_str} · {country}</span>
                </div>
                <span class="deal-tag {tag_class}" data-en="{tag_label}" data-zh="{tag_label_zh}">{tag_label}</span>
            </div>
            <div class="deal-body" data-en="{attr_en}" data-zh="{attr_zh}">{text_en}</div>{media_html}
            <div class="deal-footer">
                <a href="{url}" target="_blank" rel="noopener" class="deal-stat">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 1.999l-8.12 8.12L12 13.87l-2.88-2.75L1 1.999M1 9.999l6.12 6.12L11 19.87l2.88-2.75L23 9.999"/></svg>
                    {replies}
                </a>
                <a href="{url}" target="_blank" rel="noopener" class="deal-stat">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 014-4h14M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 01-4 4H3"/></svg>
                    {retweets}
                </a>
                <a href="{url}" target="_blank" rel="noopener" class="deal-stat">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/></svg>
                    {likes}
                </a>
                <a href="{url}" target="_blank" rel="noopener" class="deal-open">
                    View source →
                </a>
            </div>
        </article>'''


def add_deals_to_cache(new_deals, cache):
    """
    Add new deals to cache, skipping duplicates.
    new_deals: list of (url, label, color, deal_type, country) tuples
    Returns: (updated_cache, num_new, num_skipped)
    """
    existing_ids = {t["id"] for t in cache["deals"]}
    num_new = 0
    num_skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    for item in new_deals:
        url, label, color, deal_type, country = item
        tweet_id = extract_tweet_id(url)
        if not tweet_id:
            print(f"  SKIP — could not extract ID from {url}", file=sys.stderr)
            continue
        if tweet_id in existing_ids:
            num_skipped += 1
            print(f"  DEDUP {label} — {tweet_id} already in cache", file=sys.stderr)
            continue
        try:
            data = fetch_tweet_data(tweet_id)
            cache["deals"].append({
                "id": tweet_id,
                "url": url,
                "label": label,
                "color": color,
                "deal_type": deal_type,
                "country": country,
                "fetched_at": now,
                "translation_zh": "",
                "tweet_data": data,
            })
            existing_ids.add(tweet_id)
            num_new += 1
            print(f"  NEW {label} — {data.get('text', '')[:60]}...", file=sys.stderr)
        except Exception as e:
            print(f"  FAIL {label} — {url}: {e}", file=sys.stderr)

    cache["deals"] = _sort_by_date(cache["deals"])
    return cache, num_new, num_skipped


def _sort_by_date(deals):
    """Sort deals by date descending (newest first).
    Handles both Twitter deals (tweet_data.created_at) and RSS deals (published_at).
    """
    def get_date(entry):
        if entry.get("source_type") == "rss":
            return entry.get("published_at", "")
        created = entry.get("tweet_data", {}).get("created_at", "")
        return created or entry.get("published_at", "") or ""
    return sorted(deals, key=get_date, reverse=True)


def generate_rss_card(entry):
    """Generate a native HTML card for an RSS-sourced deal.
    Matches the existing deal-card design but branded with the source site's
    favicon and name instead of Twitter avatar/handle.
    """
    import html as html_module

    source_name = html_module.escape(entry.get("source_name", ""))
    source_url = entry.get("source_url", "")
    favicon = entry.get("source_favicon", "")
    color = entry.get("source_color", "#f59e0b")
    title = entry.get("title", "")
    excerpt = entry.get("excerpt", "")
    image = entry.get("image")
    deal_type = entry.get("deal_type", "deal")
    country = entry.get("country", "SG")
    translation_zh = entry.get("translation_zh", "")

    # Format date
    published_at = entry.get("published_at", "")
    date_str = ""
    if published_at:
        try:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            sgt = dt + timedelta(hours=8)
            date_str = sgt.strftime("%b %-d")
        except Exception:
            date_str = ""

    # Deal type tags
    tag_class = f"deal-tag-{deal_type}"
    tag_labels_en = {"1fl": "1-for-1", "deal": "PROMO", "free": "FREE"}
    tag_labels_zh = {"1fl": "买一送一", "deal": "优惠", "free": "免费"}
    tag_label = tag_labels_en.get(deal_type, "DEAL")
    tag_label_zh = tag_labels_zh.get(deal_type, "优惠")

    excerpt_zh = entry.get("excerpt_zh", "")

    # Content with i18n
    title_en = html_module.escape(title)
    title_zh = html_module.escape(translation_zh) if translation_zh else title_en
    excerpt_en = html_module.escape(excerpt)
    excerpt_zh_escaped = html_module.escape(excerpt_zh) if excerpt_zh else excerpt_en

    # Media
    media_html = ""
    if image:
        media_html = f'''
        <div class="deal-media" data-full="{image}">
            <img src="{image}" alt="" loading="lazy" />
        </div>'''

    return f'''        <article class="deal-card fade-in" data-country="{country}">
            <div class="deal-header">
                <img src="{favicon}" alt="" class="deal-avatar" loading="lazy" />
                <div class="deal-author">
                    <span class="deal-name">{source_name}</span>
                    <span class="deal-handle">{date_str} · {country} · via RSS</span>
                </div>
                <span class="deal-tag {tag_class}" data-en="{tag_label}" data-zh="{tag_label_zh}">{tag_label}</span>
            </div>
            <div class="deal-body" data-en="{title_en}" data-zh="{title_zh}">{title_en}</div>
            <div class="deal-excerpt" data-en="{excerpt_en}" data-zh="{excerpt_zh_escaped}" style="padding: 0 20px 8px; font-size: 13px; color: var(--text-secondary); line-height: 1.5;">{excerpt_en}</div>{media_html}
            <div class="deal-footer">
                <span class="deal-source">Source: {source_name}</span>
                <a href="{source_url}" target="_blank" rel="noopener" class="deal-open">
                    View source →
                </a>
            </div>
        </article>'''


def generate_sponsored_card(entry):
    """Generate a sponsored deal card with branded styling.
    
    Entry fields:
      - brand_name:    Display name (e.g. "Hokkaido-ya")
      - brand_avatar:  Logo/image URL
      - title:         Deal headline
      - excerpt:       Short description
      - cta_url:       Click-through link
      - cta_text:      Button label (e.g. "Order Now", "Claim Deal")
      - image:         Optional image URL
      - deal_type:     "1fl", "deal", "free"
      - country:       "SG", etc.
      - date:          Display date string
      - end_date:      Optional expiry date (e.g. "Aug 31")
    """
    import html as html_module

    brand = html_module.escape(entry.get("brand_name", ""))
    brand_avatar = entry.get("brand_avatar", "")
    title = entry.get("title", "")
    excerpt = entry.get("excerpt", "")
    cta_url = entry.get("cta_url", "#")
    cta_text = entry.get("cta_text", "View Deal")
    image = entry.get("image")
    deal_type = entry.get("deal_type", "deal")
    country = entry.get("country", "SG")
    date_str = entry.get("date", "")
    end_date = entry.get("end_date", "")

    # i18n
    title_zh = entry.get("title_zh", title)
    excerpt_zh = entry.get("excerpt_zh", excerpt)
    cta_zh = entry.get("cta_text_zh", cta_text)

    # Tag
    tag_class = f"deal-tag-{deal_type}"
    tag_labels_en = {"1fl": "1-for-1", "deal": "PROMO", "free": "FREE"}
    tag_labels_zh = {"1fl": "买一送一", "deal": "优惠", "free": "免费"}
    tag_label = tag_labels_en.get(deal_type, "DEAL")
    tag_label_zh = tag_labels_zh.get(deal_type, "优惠")

    avatar_html = ""
    if brand_avatar:
        avatar_html = f'<img src="{brand_avatar}" alt="" class="deal-avatar" loading="lazy" />'
    else:
        avatar_html = f'<div class="deal-avatar" style="background: var(--gradient); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:800; font-size:16px;">{brand[0] if brand else "S"}</div>'

    media_html = ""
    if image:
        media_html = f'''
        <div class="deal-media" data-full="{image}">
            <img src="{image}" alt="" loading="lazy" />
        </div>'''

    end_badge = ""
    if end_date:
        end_badge = f' · <span style="color: var(--accent-2); font-weight:600;">Ends {end_date}</span>'

    return f'''        <article class="deal-card deal-card-sponsored fade-in" data-country="{country}">
            <div class="deal-header">
                {avatar_html}
                <div class="deal-author">
                    <span class="deal-name">{brand}</span>
                    <span class="deal-handle">{date_str} · {country}{end_badge}</span>
                </div>
                <span class="deal-tag deal-tag-sponsored" data-en="{tag_label}" data-zh="{tag_label_zh}">{tag_label}</span>
            </div>
            <div class="deal-body" data-en="{html_module.escape(title)}" data-zh="{html_module.escape(title_zh)}">{html_module.escape(title)}</div>
            <div class="deal-excerpt" data-en="{html_module.escape(excerpt)}" data-zh="{html_module.escape(excerpt_zh)}" style="padding: 0 20px 8px; font-size: 13px; color: var(--text-secondary); line-height: 1.5;">{html_module.escape(excerpt)}</div>{media_html}
            <div class="deal-footer">
                <span class="deal-source">Sponsored</span>
                <a href="{cta_url}" target="_blank" rel="noopener nofollow sponsored" class="deal-open">
                    {cta_text} →
                </a>
            </div>
        </article>'''


def generate_all_cards(cache):
    """Generate HTML cards for all cached deals.
    
    Sponsored deals (entry["sponsored"] == True) always appear first,
    then organic deals sorted newest-first by date.
    Dispatches between Twitter deals, RSS deals, and sponsored deals.
    """
    all_deals = cache["deals"]
    
    # Split sponsored vs organic
    sponsored = [e for e in all_deals if e.get("sponsored")]
    organic = [e for e in all_deals if not e.get("sponsored")]
    
    # Sort organic by date (newest first)
    organic_sorted = _sort_by_date(organic)
    
    cards = []
    
    # Sponsored cards first
    for entry in sponsored:
        card = generate_sponsored_card(entry)
        cards.append(card)
    
    # Then organic deals
    for entry in organic_sorted:
        if entry.get("source_type") == "rss":
            card = generate_rss_card(entry)
        elif "tweet_data" in entry and entry["tweet_data"]:
            card = generate_card(
                entry["url"],
                entry["label"],
                entry["color"],
                entry["tweet_data"],
                entry.get("translation_zh", ""),
                entry.get("deal_type", "deal"),
                entry.get("country", "SG"),
            )
        else:
            continue  # Skip entries with no data
        cards.append(card)
    return cards


def get_countries(cache):
    """Return sorted list of unique countries from cache."""
    countries = set()
    for entry in cache["deals"]:
        countries.add(entry.get("country", "SG"))
    return sorted(countries)


def main():
    """Standalone: rebuild cards from cache (no new deals to add)."""
    cache = load_cache()
    print(f"Loaded {len(cache['deals'])} deals from cache", file=sys.stderr)
    cards = generate_all_cards(cache)
    print(f"Generated {len(cards)} cards", file=sys.stderr)
    print("\n\n".join(cards))


if __name__ == "__main__":
    main()
