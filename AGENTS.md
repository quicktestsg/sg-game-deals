# AGENTS.md — SG Game Deals Operating Manual

> **Read this before touching anything.** This file is injected into every agent session working in this repo.

## Architecture: Modular Build System

```
Content Sources (Agent edits these)          Build (Agent runs this)         Output (NEVER touch)
─────────────────────────────────         ──────────────────────────      ─────────────────────
scripts/posts.json                         python3 scripts/build_index.py  →  index.html
  ↳ post metadata (date, title, slug)                                         (AUTO-GENERATED)

posts/YYYY-MM-DD-slug.html                                                   ⚠️ DO NOT EDIT
  ↳ full article HTML (images, i18n)

scripts/deals_cache.json
  ↳ tweet data + translations + deal_type + country
```

## The Golden Rule

**`index.html` is AUTO-GENERATED. NEVER edit it directly.**

It is rebuilt from scratch on every `python3 scripts/build_index.py` run. Any manual edit will be lost.

---

## How to Add a Blog Post (Guide)

### 1. Write the post file

Create `posts/YYYY-MM-DD-slug.html`. Study an existing post for the exact structure:
- Nav is **OUTSIDE** the `.wrap` div
- Use images with proper `<figure>` and attribution captions
- Full **i18n**: every element has `data-en` / `data-zh` attributes
- Neon gaming design matching `style.css` (blue/purple/cyan gradient theme)
- Content focus: gaming deal guides, where to buy cheap games, console restock alerts, eShop/PSN sale roundups, credit card gaming promos

### 2. Add metadata to `scripts/posts.json`

Prepend one entry to the JSON array:

```json
{
  "date": "2026-08-01",
  "slug": "your-slug",
  "country": "SG",
  "title_en": "English Title",
  "title_zh": "中文标题",
  "read_time": 5,
  "excerpt_en": "1-2 sentence English excerpt for the listing card.",
  "excerpt_zh": "1-2句中文摘要。"
}
```

### 3. Rebuild and push

```bash
python3 scripts/build_index.py
git add -A && git commit -m "Daily post: TITLE" && git push
```

**That's it.** The build script handles all sorting, card generation, preview selection, country pills, and assembly.

---

## How to Fetch Deals (Two Sources)

### Source 1: RSS Feeds (PRIMARY — zero tokens, pure script)

`scripts/rss_fetcher.py` fetches from gaming deal aggregators via their RSS feeds:

| Source | Focus |
|--------|-------|
| Slickdeals Gaming | General gaming + console deals |
| Slickdeals Video Games | Nintendo + PlayStation deals |
| IGN Deals | Game industry deals + news |

```bash
# Fetch all feeds (handles dedup, keyword filtering, age cutoff automatically)
python3 scripts/rss_fetcher.py

# Preview without saving
python3 scripts/rss_fetcher.py --dry-run

# List cached RSS deals
python3 scripts/rss_fetcher.py --list
```

The script auto-detects deal types (free, promo), filters by gaming keywords, removes non-deals, and only keeps entries from the last 7 days. RSS deals use a different card format — branded with the source site's favicon and name, with an excerpt instead of tweet text. Every card links back to the source.

**Legal compliance:** RSS feeds are explicitly published for syndication. We show title + short excerpt + link back. We do NOT republish full articles. The AI agent writes original synthesized content using deal facts (prices, dates) as raw intel.

### Source 2: Twitter/X (supplement)

`scripts/twitter_fetcher.py` searches gaming deal accounts:

| Account | Query | Color |
|---------|-------|-------|
| @Shopee_SG | gaming / Switch / Nintendo / PS5 | #ee4d2d |
| @qisahn | all posts | #3b82f6 |

```bash
python3 scripts/twitter_fetcher.py              # Fetch since last run
python3 scripts/twitter_fetcher.py --dry-run    # Preview only
python3 scripts/twitter_fetcher.py --list       # Show cached
python3 scripts/twitter_fetcher.py --reset      # Reset last-run date
```

---

## Selection Criteria for Deals

Pick tweets/entries that are **actual gaming deals** worth sharing:
- ✅ Nintendo Switch game drops & cartridge deals
- ✅ PS5 console restocks & game sales
- ✅ Xbox Series X|S deals and Game Pass promos
- ✅ PC game sales (Steam, Epic, GOG)
- ✅ eShop / PSN / Xbox Store digital sales
- ✅ Gaming peripherals: controllers, headsets, keyboards
- ✅ Flash sales at Qisahn, GameXtreme, Shopee, Lazada, Amazon SG
- ✅ Credit card gaming promos (DBS, UOB, OCBC Shopee/Lazada vouchers)
- ✅ Free game giveaways (Epic free games, PS Plus games)
- ❌ Skip: food/restaurant deals, banking/finance promos, insurance, property, spam

---

## Image Attribution Rule

**Every deal card with an image must cite its source.** The tweet URL or RSS link in the "View source" link serves as attribution. For blog post images, always use:

```html
<figure>
  <img src="URL" alt="Description" />
  <figcaption>Photo: Source Name</figcaption>
</figure>
```

---

## File Reference

| File | Editable? | Purpose |
|------|-----------|---------|
| `scripts/posts.json` | ✅ Yes | Post metadata manifest |
| `posts/*.html` | ✅ Yes | Full article pages (images, i18n) |
| `scripts/deals_cache.json` | ✅ Yes | Cached tweet + RSS data + translations |
| `scripts/build_index.py` | ⚠️ Careful | The build engine |
| `scripts/rss_fetcher.py` | ⚠️ Careful | RSS feed fetcher |
| `scripts/twitter_fetcher.py` | ⚠️ Careful | Twitter/X deal fetcher |
| `scripts/gen_deals.py` | ⚠️ Careful | Tweet + RSS card generator |
| `index_template.html` | ⚠️ Structure only | HTML skeleton with placeholders |
| `index.html` | ❌ NEVER | Auto-generated |
| `style.css` | ✅ Yes | Shared styles (neon gaming theme) |
| `app.js` | ✅ Yes | Theme toggle, tab switching, i18n, country filter |

---

## Cron Schedule

| Time (SGT) | Job |
|------------|-----|
| **08:00** | Write daily guide post + fetch new deals |
| **20:00** | Fetch new deals only (catch afternoon/evening promos) |

---

## Do NOT

- **Do NOT** edit `index.html` — it's generated and will be overwritten.
- **Do NOT** add post/deal HTML to `index_template.html` — use the JSON manifests.
- **Do NOT** touch `posts/*.html` unless writing/editing that specific article.
- **Do NOT** use first person "I" — posts are anonymous.
- **Do NOT** post non-gaming deals — this is a gaming deals blog.
- **Do NOT** forget image attribution — always cite the source.
- **Do NOT** add deals without Chinese translations — every deal needs a `translation_zh`.
