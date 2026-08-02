#!/usr/bin/env python3
"""
Build index.html — the single source of truth for assembly.

Reads:
  - scripts/posts.json         → blog post metadata (manifest)
  - scripts/deals_cache.json   → tweet/rss data for deal cards
  - index_template.html        → HTML skeleton with placeholders

Generates:
  - index.html                 → fully assembled page
  - sitemap.xml                → for Google/SE crawlers
  - robots.txt                 → allow all + sitemap reference

The cron agent NEVER touches index.html or index_template.html.
It only writes:
  1. posts/YYYY-MM-DD-slug.html  (the full blog post)
  2. scripts/posts.json          (append one metadata entry)
  3. scripts/deals_cache.json    (via add_deals.py / rss_fetcher.py)

Then runs: python3 scripts/build_index.py && git add -A && git commit && git push
"""
import sys
import os
import re
import json
import html as html_module
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE = os.path.join(PROJECT_DIR, "index_template.html")
OUTPUT = os.path.join(PROJECT_DIR, "index.html")
POSTS_MANIFEST = os.path.join(SCRIPT_DIR, "posts.json")
SITEMAP = os.path.join(PROJECT_DIR, "sitemap.xml")
ROBOTS = os.path.join(PROJECT_DIR, "robots.txt")

BASE_URL = "https://quicktestsg.github.io/sg-game-deals"
CSS_VERSION = "1"
DEALS_PREVIEW_COUNT = 6
POSTS_PREVIEW_COUNT = 4

sys.path.insert(0, SCRIPT_DIR)
from gen_deals import load_cache, generate_all_cards, get_countries


# ── Country labels ──
COUNTRY_LABELS = {
    "SG": {"en": "Singapore", "zh": "新加坡"},
    "MY": {"en": "Malaysia", "zh": "马来西亚"},
    "TH": {"en": "Thailand", "zh": "泰国"},
    "JP": {"en": "Japan", "zh": "日本"},
    "KR": {"en": "Korea", "zh": "韩国"},
    "TW": {"en": "Taiwan", "zh": "台湾"},
    "HK": {"en": "Hong Kong", "zh": "香港"},
    "US": {"en": "USA", "zh": "美国"},
    "UK": {"en": "UK", "zh": "英国"},
    "AU": {"en": "Australia", "zh": "澳洲"},
}


# ── Date formatting ──
def format_post_date(date_str):
    """ISO date (2026-07-31) → 'July 31, 2026'"""
    dt = datetime.fromisoformat(date_str)
    return dt.strftime("%B %-d, %Y")


def escape_attr(text):
    """Escape text for use in HTML attribute value."""
    return text.replace('"', '&quot;')


# ── Country pills HTML ──
def generate_country_pills(countries):
    """Generate country filter pills HTML."""
    pills = []
    for code in countries:
        labels = COUNTRY_LABELS.get(code, {"en": code, "zh": code})
        en = labels["en"]
        zh = labels["zh"]
        pills.append(
            f'        <button class="country-pill" data-country="{code}" '
            f'data-en="{escape_attr(en)}" data-zh="{escape_attr(zh)}">{en}</button>'
        )
    return "\n".join(pills)


# ── Post card HTML generation ──
def generate_post_card(post):
    """Generate a single post card <div> for the lists."""
    slug = post["slug"]
    country = post.get("country", "SG")
    href = f"posts/{post['date']}-{slug}.html"
    date_display = format_post_date(post["date"])
    read_time = post.get("read_time", 5)
    title_en = escape_attr(post["title_en"])
    title_zh = escape_attr(post.get("title_zh", post["title_en"]))
    excerpt_en = escape_attr(post["excerpt_en"])
    excerpt_zh = escape_attr(post.get("excerpt_zh", post["excerpt_en"]))
    short_en = post["excerpt_en"]
    if len(short_en) > 200:
        short_en = short_en[:197].rsplit(" ", 1)[0] + "."

    return f"""        <div class="post-item fade-in" data-country="{country}">
            <a href="{href}" class="post-item-inner">
                <div class="post-meta">
                    <span class="post-date">{date_display}</span>
                    <span class="post-dot"></span>
                    <span class="post-read">{read_time} min read</span>
                    <span class="post-dot"></span>
                    <span class="post-country">{country}</span>
                </div>
                <h2 class="post-title" data-en="{title_en}" data-zh="{title_zh}">{post['title_en']}</h2>
                <p class="post-excerpt" data-en="{excerpt_en}" data-zh="{excerpt_zh}">{short_en}</p>
                <span class="post-arrow">→</span>
            </a>
        </div>"""


def generate_post_cards(posts, limit=None):
    """Generate HTML for post cards, newest first."""
    sorted_posts = sorted(posts, key=lambda p: p["date"], reverse=True)
    if limit:
        sorted_posts = sorted_posts[:limit]
    return "\n\n".join(generate_post_card(p) for p in sorted_posts)


# ── Sitemap generation ──
def generate_sitemap(posts, cache):
    """Generate sitemap.xml for Google/SE crawlers."""
    from datetime import datetime, timezone

    urls = [
        {"loc": f"{BASE_URL}/", "priority": "1.0", "changefreq": "daily"},
        {"loc": f"{BASE_URL}/about.html", "priority": "0.5", "changefreq": "monthly"},
        {"loc": f"{BASE_URL}/advertise.html", "priority": "0.5", "changefreq": "monthly"},
    ]
    for post in posts:
        urls.append({
            "loc": f"{BASE_URL}/posts/{post['date']}-{post['slug']}.html",
            "priority": "0.8",
            "changefreq": "weekly",
            "lastmod": post["date"],
        })

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for u in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{u['loc']}</loc>")
        if "lastmod" in u:
            lines.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        lines.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        lines.append(f"    <priority>{u['priority']}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines)


def generate_robots():
    """Generate robots.txt referencing the sitemap."""
    return (
        "User-agent: *\n"
        "Allow: /\n"
        f"\nSitemap: {BASE_URL}/sitemap.xml\n"
    )


# ── JSON-LD structured data for AI SEO ──
def generate_jsonld(posts, cache):
    """Generate JSON-LD structured data for Google Rich Results + AI search."""
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. Website schema with search action
    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "GG Deals",
        "url": f"{BASE_URL}/",
        "description": "Daily-updated gaming deals — Nintendo Switch drops, PS5 restocks, Xbox sales, Steam bargains and Game Pass additions.",
        "inLanguage": ["en", "zh"],
    }

    # 2. Blog/CollectionPage schema
    blog_schema = {
        "@context": "https://schema.org",
        "@type": "Blog",
        "name": "GG Deals",
        "url": f"{BASE_URL}/",
        "description": "Global gaming deals — Switch drops, PS5 restocks, Xbox sales, Steam bargains and Game Pass additions, updated daily.",
        "publisher": {
            "@type": "Organization",
            "name": "GG Deals",
            "url": f"{BASE_URL}/",
        },
        "blogPost": [],
    }

    for post in sorted(posts, key=lambda p: p["date"], reverse=True)[:10]:
        blog_schema["blogPost"].append({
            "@type": "BlogPosting",
            "headline": post["title_en"],
            "url": f"{BASE_URL}/posts/{post['date']}-{post['slug']}.html",
            "datePublished": post["date"],
            "author": {"@type": "Organization", "name": "GG Deals"},
            "description": post.get("excerpt_en", ""),
            "inLanguage": "en",
        })

    # 3. FAQ schema for AI discovery — natural language Q&A
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "Where to find the best Nintendo Switch deals?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "The best Nintendo Switch deals come from a few sources: Nintendo eShop regional pricing (the South Africa, Mexico and Turkey eShops are often cheaper than the US/EU stores for the exact same game), retail clearance on physical cartridges, and seasonal sales like Black Friday and the eShop Big Ol' Super Sale. GG Deals curates the latest Switch game drops and cartridge deals daily — check the Today's Deals section for what's hot right now."
                }
            },
            {
                "@type": "Question",
                "name": "When do PS5 games go on sale?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "PlayStation Store runs predictable sale cycles: 'Days of Play' (May-June), 'Season of Sale' (March), Black Friday/Cyber Monday (late November), and the Holiday Sale (December-January). First-party titles typically drop 40-60% during these windows, and PS Plus members get an extra 10-20% off. Older AAA games hit their lowest prices during Black Friday. Follow GG Deals for PS5 restock alerts and sale notifications."
                }
            },
            {
                "@type": "Question",
                "name": "How to get cheap games on Steam and eShop?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "For Steam, wait for the four seasonal sales (Spring, Summer, Autumn, Winter) where wishlist games drop 30-80%, and grab free games every Thursday from the Epic Games Store. For the Nintendo eShop, create accounts in cheaper regions (South Africa, Mexico, Turkey) and fund them with region-appropriate gift cards — the same game can cost 30-50% less than the US eShop. Xbox Game Pass is also excellent value, offering 100+ games for a monthly fee. GG Deals tracks all of these daily."
                }
            },
            {
                "@type": "Question",
                "name": "什么是游戏打折季？哪里可以找到最便宜的游戏？",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "游戏打折季是各大平台定期举办的促销活动：Steam 每年有春、夏、秋、冬四次大促，PlayStation Store 有 Days of Play（5-6月）和黑五大促（11月），Nintendo eShop 也有区域性闪购和 Black Friday 折扣。此外，eShop 跨区购买（南非、墨西哥、土耳其区）通常比美区便宜 30-50%，Epic 每周四还送免费游戏。GG Deals 每天为你精选全平台最划算的游戏优惠。"
                }
            },
        ]
    }

    # Combine all schemas
    schemas = json.dumps([website_schema, blog_schema, faq_schema], ensure_ascii=False, indent=2)
    return f'<script type="application/ld+json">{schemas}</script>'


# ── Main build ──
def main():
    # Read template
    with open(TEMPLATE, "r") as f:
        template = f.read()

    # Bump CSS version
    template = re.sub(r'style\.css\?v=\d+', f'style.css?v={CSS_VERSION}', template)
    template = re.sub(r'app\.js\?v=\d+', f'app.js?v={CSS_VERSION}', template)

    # ── POSTS ──
    with open(POSTS_MANIFEST, "r") as f:
        posts = json.load(f)

    print(f"Loaded {len(posts)} posts from manifest", file=sys.stderr)

    posts_preview_html = generate_post_cards(posts, limit=POSTS_PREVIEW_COUNT)
    posts_full_html = generate_post_cards(posts)

    template = template.replace("<!-- POSTS_PREVIEW -->", posts_preview_html)
    template = template.replace("<!-- POSTS_FULL -->", posts_full_html)

    # ── DEALS ──
    cache = load_cache()
    print(f"Loaded {len(cache['deals'])} deals from cache", file=sys.stderr)

    cards = generate_all_cards(cache)
    deals_html = "\n\n".join(cards)

    template = template.replace("<!-- DEALS_INSERT -->", deals_html)

    preview_cards = cards[:DEALS_PREVIEW_COUNT]
    deals_preview_html = "\n\n".join(preview_cards)
    template = template.replace("<!-- DEALS_PREVIEW -->", deals_preview_html)

    # ── COUNTRY PILLS ──
    countries = get_countries(cache)
    country_pills_html = generate_country_pills(countries)
    template = template.replace("<!-- COUNTRY_PILLS -->", country_pills_html)

    # ── JSON-LD structured data (SEO) ──
    jsonld = generate_jsonld(posts, cache)
    template = template.replace("<!-- JSON_LD -->", jsonld)

    # ── Deal count for meta description ──
    template = template.replace("DEAL_COUNT", str(len(cache['deals'])))

    # Write output — with generated-file warning
    warning = (
        "<!-- ⚠️ AUTO-GENERATED by scripts/build_index.py — DO NOT EDIT MANUALLY.  "
        "Edit scripts/posts.json or scripts/deals_cache.json, then rebuild. "
        "This file is overwritten on every build. -->\n"
    )
    with open(OUTPUT, "w") as f:
        f.write(warning + template)

    # ── Generate sitemap.xml ──
    sitemap_content = generate_sitemap(posts, cache)
    with open(SITEMAP, "w") as f:
        f.write(sitemap_content)

    # ── Generate robots.txt ──
    robots_content = generate_robots()
    with open(ROBOTS, "w") as f:
        f.write(robots_content)

    post_count = len(posts)
    deal_count = len(cache['deals'])
    print(f"\n✅ Built index.html: {post_count} posts ({POSTS_PREVIEW_COUNT} preview), "
          f"{deal_count} deals ({DEALS_PREVIEW_COUNT} preview), "
          f"{len(countries)} countries", file=sys.stderr)
    print(f"   CSS version: v={CSS_VERSION}", file=sys.stderr)
    print(f"   Sitemap: {len(posts) + 2} URLs", file=sys.stderr)
    print(f"   robots.txt written", file=sys.stderr)


if __name__ == "__main__":
    main()
