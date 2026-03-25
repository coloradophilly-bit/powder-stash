# Powder Stash ⛷️

Real-time ski & snowboard deal intelligence. Automatically scrapes brand promo pages every hour via GitHub Actions and serves a static frontend on GitHub Pages.

---

## How it works

```
GitHub Actions (hourly cron)
    └── scraper/scrape.py
            └── fetches 19+ brand sale/promo pages
            └── extracts discount %, promo codes, deal type
            └── writes public/deals.json
                    └── GitHub Pages serves index.html
                            └── frontend fetches deals.json at load time
```

No server. No database. Entirely free.

---

## Quick setup (15 minutes)

### 1. Fork or clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/powder-stash.git
cd powder-stash
```

### 2. Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` — Folder: `/public`
4. Save. Your site will be live at `https://YOUR_USERNAME.github.io/powder-stash`

### 3. Enable GitHub Actions

GitHub Actions is enabled by default on public repos. For private repos:
- Go to **Settings** → **Actions** → **General**
- Set "Allow all actions and reusable workflows"

The scraper runs automatically every hour via `.github/workflows/scrape.yml`.
To trigger it manually: **Actions** tab → **Scrape Deals** → **Run workflow**.

### 4. Grant Actions write permission (to commit deals.json)

1. Go to **Settings** → **Actions** → **General**
2. Scroll to "Workflow permissions"
3. Select **Read and write permissions**
4. Save

### 5. Run the scraper locally (optional)

```bash
cd scraper
pip install -r requirements.txt
python scrape.py
```

This writes `public/deals.json`. Open `public/index.html` in a browser to preview.

---

## Adding or editing brands

Open `scraper/scrape.py` and find the `BRANDS` list. Each entry looks like:

```python
{
    "brand": "Burton",
    "category": "snowboard",          # ski | snowboard | boots | bindings | outerwear | goggles | helmets | accessories
    "urls": [
        "https://www.burton.com/us/en/c/sale",
    ],
    "affiliate_base": "https://www.burton.com/us/en/c/sale",  # your affiliate link goes here
},
```

- `urls` — list of pages to scrape (the scraper checks all of them)
- `affiliate_base` — the URL shown on deal cards. Replace with your affiliate link once approved.

---

## Hooking up affiliate links

Once you're approved on an affiliate network, replace `affiliate_base` in each brand entry with your tracked URL.

### Which network covers which brands

| Network | Brands |
|---------|--------|
| **AvantLink** (avantlink.com) | REI, Evo, Backcountry, Christy Sports, many ski brands |
| **Impact.com** | Burton, Salomon, POC, Dakine, Smith Optics |
| **ShareASale** | 686, various mid-tier brands |
| **Direct programs** | Patagonia, Arc'teryx, some Salomon regions |

### AvantLink setup (recommended starting point — most ski/snowboard coverage)

1. Sign up at [avantlink.com](https://www.avantlink.com)
2. Apply to individual merchant programs (REI, Evo, Backcountry)
3. Once approved, use their link builder to generate tracked URLs
4. Paste into `affiliate_base` for each brand

### Impact.com setup

1. Sign up at [app.impact.com](https://app.impact.com)
2. Search for Burton, Salomon, Smith, Dakine in the marketplace
3. Apply to each program
4. Use their deep-link builder to generate tracked URLs

### Typical commission rates

| Brand / Retailer | Network | Commission |
|-----------------|---------|-----------|
| REI | AvantLink | 5% |
| Evo | AvantLink | 5–8% |
| Backcountry | AvantLink | 6% |
| Burton | Impact | 5% |
| Salomon | Impact | 4–7% |
| Dakine | Impact | 8% |
| POC | Impact | 8% |

> Rates vary and change — always check your network dashboard for current terms.

---

## Customising the scraper

The scraper looks for:
- **Promo codes** — regex matching "use code XXXX", "enter promo XXXX", etc.
- **Discounts** — "30% off", "save 40%", "up to 50% off"
- **Deal type** — clearance signals ("end of season", "final sale"), drop signals ("new drop", "preorder"), email signals

To tune what gets detected, edit these in `scraper/scrape.py`:

```python
PROMO_CODE_RE     # regex for promo codes
DISCOUNT_RE       # regex for discount percentages
CLEARANCE_SIGNALS # list of clearance keywords
DROP_SIGNALS      # list of new drop keywords
```

### Improving detection for specific brands

Some sites render content via JavaScript and won't be scraped by the basic `requests` approach. If a brand consistently returns empty results, upgrade to Playwright:

```bash
pip install playwright
playwright install chromium
```

Then replace the `fetch()` function for that brand with a Playwright headless browser call. See the [Playwright docs](https://playwright.dev/python/).

---

## File structure

```
powder-stash/
├── .github/
│   └── workflows/
│       └── scrape.yml          # GitHub Actions — runs hourly
├── scraper/
│   ├── scrape.py               # main scraper
│   └── requirements.txt        # Python deps
├── public/
│   ├── index.html              # frontend (served by GitHub Pages)
│   └── deals.json              # auto-generated by scraper
└── README.md
```

---

## Costs

| Service | Cost |
|---------|------|
| GitHub Pages | Free |
| GitHub Actions | Free (2,000 min/month on free tier; hourly runs ≈ 720 min/month) |
| Domain (optional) | ~$12/year |

Total: **$0** to start. Add a custom domain when you're ready.
