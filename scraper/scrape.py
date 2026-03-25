"""
Powder Stash — Brand Deal Scraper
Monitors ski/snowboard brand pages for active promos, clearance sales, and new drops.
Writes results to public/deals.json for the frontend to consume.

Run locally:  python scraper/scrape.py
Run on CI:    triggered by GitHub Actions on a schedule
"""

import json
import re
import time
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Brand definitions
# Each entry tells the scraper WHERE to look and WHAT to look for.
# Add new brands here — no code changes needed elsewhere.
# ---------------------------------------------------------------------------

BRANDS = [
    # ── BOARDS & SKIS ──────────────────────────────────────────────────────
    {
        "brand": "Burton",
        "category": "snowboard",
        "urls": [
            "https://www.burton.com/us/en/c/sale",
            "https://www.burton.com/us/en/c/mens-snowboard-outerwear",
        ],
        "affiliate_base": "https://www.burton.com/us/en/c/sale",  # replace with your affiliate URL once approved
    },
    {
        "brand": "Jones Snowboards",
        "category": "snowboard",
        "urls": ["https://www.jonessnowboards.com/collections/sale"],
        "affiliate_base": "https://www.jonessnowboards.com/collections/sale",
    },
    {
        "brand": "Capita",
        "category": "snowboard",
        "urls": ["https://www.capitasnowboarding.com/collections/sale"],
        "affiliate_base": "https://www.capitasnowboarding.com/collections/sale",
    },
    {
        "brand": "Rome SDS",
        "category": "bindings",
        "urls": ["https://www.romesnowboards.com/collections/sale"],
        "affiliate_base": "https://www.romesnowboards.com/collections/sale",
    },
    {
        "brand": "K2 Skis",
        "category": "ski",
        "urls": ["https://www.k2skis.com/en/sale", "https://www.k2skis.com/en/skis"],
        "affiliate_base": "https://www.k2skis.com/en/sale",
    },
    {
        "brand": "Line Skis",
        "category": "ski",
        "urls": ["https://www.lineskis.com/collections/sale"],
        "affiliate_base": "https://www.lineskis.com/collections/sale",
    },
    {
        "brand": "Armada Skis",
        "category": "ski",
        "urls": ["https://www.armadaskis.com/collections/sale"],
        "affiliate_base": "https://www.armadaskis.com/collections/sale",
    },
    {
        "brand": "Völkl",
        "category": "ski",
        "urls": ["https://www.volkl.com/en-us/sale"],
        "affiliate_base": "https://www.volkl.com/en-us/sale",
    },

    # ── BOOTS ──────────────────────────────────────────────────────────────
    {
        "brand": "Salomon",
        "category": "boots",
        "urls": [
            "https://www.salomon.com/en-us/sale/ski",
            "https://www.salomon.com/en-us/sport/ski/ski-boots.html",
        ],
        "affiliate_base": "https://www.salomon.com/en-us/sale/ski",
    },
    {
        "brand": "Nidecker",
        "category": "bindings",
        "urls": ["https://www.nidecker.com/en/sale"],
        "affiliate_base": "https://www.nidecker.com/en/sale",
    },

    # ── BINDINGS ───────────────────────────────────────────────────────────
    {
        "brand": "Union Binding",
        "category": "bindings",
        "urls": ["https://www.unionbindingco.com/collections/sale"],
        "affiliate_base": "https://www.unionbindingco.com/collections/sale",
    },

    # ── OUTERWEAR ──────────────────────────────────────────────────────────
    {
        "brand": "Patagonia",
        "category": "outerwear",
        "urls": ["https://www.patagonia.com/shop/sale/sport/skiing-snowboarding"],
        "affiliate_base": "https://www.patagonia.com/shop/sale/sport/skiing-snowboarding",
    },
    {
        "brand": "686",
        "category": "outerwear",
        "urls": ["https://www.686.com/collections/sale"],
        "affiliate_base": "https://www.686.com/collections/sale",
    },

    # ── HELMETS & GOGGLES ──────────────────────────────────────────────────
    {
        "brand": "POC",
        "category": "helmets",
        "urls": ["https://www.pocsports.com/collections/ski-sale"],
        "affiliate_base": "https://www.pocsports.com/collections/ski-sale",
    },
    {
        "brand": "Smith Optics",
        "category": "goggles",
        "urls": ["https://www.smithoptics.com/en_US/sale/"],
        "affiliate_base": "https://www.smithoptics.com/en_US/sale/",
    },
    {
        "brand": "Oakley",
        "category": "goggles",
        "urls": ["https://www.oakley.com/en-us/category/snow?prefn1=isOnSale&prefv1=true"],
        "affiliate_base": "https://www.oakley.com/en-us/category/snow",
    },

    # ── ACCESSORIES ────────────────────────────────────────────────────────
    {
        "brand": "Dakine",
        "category": "accessories",
        "urls": ["https://www.dakine.com/collections/sale"],
        "affiliate_base": "https://www.dakine.com/collections/sale",
    },

    # ── RETAILERS ──────────────────────────────────────────────────────────
    {
        "brand": "REI",
        "category": "accessories",
        "urls": [
            "https://www.rei.com/c/ski-gear?origin=web&sort=percentOff%7Cdesc",
            "https://www.rei.com/c/snowboarding?origin=web&sort=percentOff%7Cdesc",
        ],
        "affiliate_base": "https://www.rei.com/c/ski-gear?sort=percentOff%7Cdesc",
    },
    {
        "brand": "Evo",
        "category": "ski",
        "urls": ["https://www.evo.com/sale/ski"],
        "affiliate_base": "https://www.evo.com/sale/ski",
    },
    {
        "brand": "Backcountry",
        "category": "ski",
        "urls": ["https://www.backcountry.com/ski-sale"],
        "affiliate_base": "https://www.backcountry.com/ski-sale",
    },
]

# ---------------------------------------------------------------------------
# Signals — patterns that indicate a live deal
# ---------------------------------------------------------------------------

# Promo code patterns (e.g. "Use code SHRED30", "Enter POWDER20 at checkout")
PROMO_CODE_RE = re.compile(
    r'\b(?:use\s+(?:code|promo|coupon)\s*[:\-]?\s*|code[:\s]+|promo[:\s]+|coupon[:\s]+)'
    r'([A-Z0-9]{4,20})\b',
    re.IGNORECASE
)

# Discount percentage patterns (e.g. "30% off", "Save 40%", "Up to 50% off")
DISCOUNT_RE = re.compile(
    r'(?:up\s+to\s+)?(\d{1,3})\s*%\s*off|save\s+(\d{1,3})\s*%',
    re.IGNORECASE
)

# Deal-type signals
CLEARANCE_SIGNALS = ["clearance", "end of season", "last chance", "while supplies last", "final sale"]
DROP_SIGNALS = ["new drop", "just dropped", "now available", "preorder", "pre-order", "new arrival"]
EMAIL_SIGNALS = ["email", "subscribe", "sign up", "newsletter", "exclusive offer"]
SALE_SIGNALS = ["% off", "sale", "deal", "promo", "savings", "reduced", "markdown"]

# ---------------------------------------------------------------------------
# Deal dataclass
# ---------------------------------------------------------------------------

@dataclass
class Deal:
    id: str                          # stable hash for deduplication
    brand: str
    category: str
    deal_type: str                   # "active" | "clearance" | "drops" | "email"
    description: str
    discount: Optional[str]
    code: Optional[str]
    url: str                         # affiliate URL (or direct if not set)
    source_url: str                  # page this was found on
    hot: bool = False
    pulse: bool = False              # True if first seen in this run
    first_seen: str = ""
    last_seen: str = ""

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.first_seen:
            self.first_seen = now
        self.last_seen = now

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fetch(url: str) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Deal extraction
# ---------------------------------------------------------------------------

def extract_text_blocks(soup: BeautifulSoup) -> list[str]:
    """
    Pull meaningful text blocks from the page.
    Focus on banners, headers, promo bars, sale sections.
    """
    blocks = []

    # Priority selectors — banners, announcement bars, promo sections
    priority_selectors = [
        "[class*='banner']", "[class*='promo']", "[class*='announcement']",
        "[class*='sale']", "[class*='offer']", "[class*='deal']",
        "[class*='discount']", "[class*='promotion']", "[class*='alert']",
        "[id*='banner']", "[id*='promo']", "[id*='sale']",
        "header", "nav", ".site-header", "#shopify-section-announcement-bar",
        # Shopify common patterns
        ".announcement-bar", ".promo-bar", ".top-bar",
    ]

    seen = set()
    for sel in priority_selectors:
        for el in soup.select(sel)[:10]:
            t = el.get_text(" ", strip=True)
            if t and t not in seen and len(t) > 8:
                blocks.append(t)
                seen.add(t)

    # Also grab all visible text paragraphs / headings
    for tag in soup.find_all(["h1", "h2", "h3", "p", "li", "span", "div"]):
        t = tag.get_text(" ", strip=True)
        if t and t not in seen and 8 < len(t) < 400:
            blocks.append(t)
            seen.add(t)

    return blocks


def make_id(brand: str, description: str) -> str:
    raw = f"{brand.lower()}::{description.lower()[:80]}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def analyse_page(brand_cfg: dict, url: str, soup: BeautifulSoup) -> list[Deal]:
    """Analyse a single page and return any deals found."""
    found: list[Deal] = []
    blocks = extract_text_blocks(soup)
    full_text = " ".join(blocks).lower()

    # Quick bail — does this page mention any sale signals at all?
    if not any(s in full_text for s in SALE_SIGNALS + CLEARANCE_SIGNALS + DROP_SIGNALS):
        log.info(f"    no signals found on {url}")
        return found

    # Determine deal type
    if any(s in full_text for s in CLEARANCE_SIGNALS):
        deal_type = "clearance"
    elif any(s in full_text for s in DROP_SIGNALS):
        deal_type = "drops"
    elif any(s in full_text for s in EMAIL_SIGNALS) and "%" in full_text:
        deal_type = "email"
    else:
        deal_type = "active"

    # Extract discount %
    discount = None
    dm = DISCOUNT_RE.search(full_text)
    if dm:
        pct = dm.group(1) or dm.group(2)
        discount = f"{pct}% off"

    # Extract promo code — search original-case blocks
    code = None
    for block in blocks:
        cm = PROMO_CODE_RE.search(block)
        if cm:
            code = cm.group(1).upper()
            break

    # Build a short description from the most informative block
    desc = ""
    for block in blocks:
        bl = block.lower()
        if any(s in bl for s in SALE_SIGNALS + CLEARANCE_SIGNALS + DROP_SIGNALS):
            # Clean it up
            desc = re.sub(r'\s+', ' ', block).strip()
            if len(desc) > 120:
                desc = desc[:117] + "..."
            break

    if not desc:
        desc = f"Sale detected on {brand_cfg['brand']} — visit site for details"

    # Hot = big discount (30%+) or has a promo code
    hot = bool(code) or (discount is not None and int(re.search(r'\d+', discount).group()) >= 30)

    deal = Deal(
        id=make_id(brand_cfg["brand"], desc),
        brand=brand_cfg["brand"],
        category=brand_cfg["category"],
        deal_type=deal_type,
        description=desc,
        discount=discount or ("Sale" if deal_type == "clearance" else None),
        code=code,
        url=brand_cfg.get("affiliate_base", url),
        source_url=url,
        hot=hot,
    )
    found.append(deal)
    log.info(f"    ✓ deal found: [{deal_type}] {discount or ''} {code or ''} — {desc[:60]}")
    return found

# ---------------------------------------------------------------------------
# Persistence — merge with previous run to preserve first_seen / pulse flags
# ---------------------------------------------------------------------------

OUTPUT_PATH = Path(__file__).parent.parent / "deals.json"


def load_previous() -> dict[str, dict]:
    """Load previously saved deals keyed by id."""
    if OUTPUT_PATH.exists():
        try:
            data = json.loads(OUTPUT_PATH.read_text())
            return {d["id"]: d for d in data.get("deals", [])}
        except Exception:
            pass
    return {}


def save(deals: list[Deal], previous: dict[str, dict]):
    """Merge with previous run and write deals.json."""
    now = datetime.now(timezone.utc).isoformat()
    merged = []

    current_ids = {d.id for d in deals}

    for deal in deals:
        d = asdict(deal)
        if deal.id in previous:
            # Preserve original first_seen, clear pulse flag
            d["first_seen"] = previous[deal.id]["first_seen"]
            d["pulse"] = False
        else:
            # Brand new deal — mark as pulse
            d["pulse"] = True
            log.info(f"  ★ NEW deal: {deal.brand} — {deal.description[:50]}")
        merged.append(d)

    # Sort: pulse first, then hot, then by brand
    merged.sort(key=lambda d: (not d["pulse"], not d["hot"], d["brand"]))

    output = {
        "generated_at": now,
        "deal_count": len(merged),
        "brands_scanned": len(BRANDS),
        "deals": merged,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    log.info(f"\n✓ Wrote {len(merged)} deals → {OUTPUT_PATH}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    log.info("=" * 60)
    log.info("POWDER STASH — scraper starting")
    log.info(f"Scanning {len(BRANDS)} brands across {sum(len(b['urls']) for b in BRANDS)} URLs")
    log.info("=" * 60)

    previous = load_previous()
    all_deals: list[Deal] = []

    for brand_cfg in BRANDS:
        log.info(f"\n→ {brand_cfg['brand']}")
        for url in brand_cfg["urls"]:
            log.info(f"  fetching {url}")
            soup = fetch(url)
            if soup is None:
                continue
            deals = analyse_page(brand_cfg, url, soup)
            all_deals.extend(deals)
            time.sleep(1.5)   # be polite — 1.5s between requests

    # Deduplicate by id (same brand may appear across multiple URLs)
    seen_ids: set[str] = set()
    unique_deals: list[Deal] = []
    for d in all_deals:
        if d.id not in seen_ids:
            seen_ids.add(d.id)
            unique_deals.append(d)

    log.info(f"\n{'='*60}")
    log.info(f"Scan complete — {len(unique_deals)} unique deals found")
    save(unique_deals, previous)


if __name__ == "__main__":
    run()
