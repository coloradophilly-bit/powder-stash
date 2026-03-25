"""
Powder Stash — Brand Deal Scraper (Playwright edition)
Uses a headless browser to handle JavaScript-rendered pages.

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
from dataclasses import dataclass, asdict
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

BRANDS = [
    {"brand": "Burton",          "category": "outerwear",    "urls": ["https://www.burton.com/us/en/c/sale"],                                          "affiliate_base": "https://www.burton.com/us/en/c/sale"},
    {"brand": "Jones Snowboards","category": "snowboard",    "urls": ["https://www.jonessnowboards.com/collections/sale"],                             "affiliate_base": "https://www.jonessnowboards.com/collections/sale"},
    {"brand": "Capita",          "category": "snowboard",    "urls": ["https://www.capitasnowboarding.com/collections/sale"],                          "affiliate_base": "https://www.capitasnowboarding.com/collections/sale"},
    {"brand": "Rome SDS",        "category": "bindings",     "urls": ["https://www.romesnowboards.com/collections/sale"],                              "affiliate_base": "https://www.romesnowboards.com/collections/sale"},
    {"brand": "K2 Skis",         "category": "ski",          "urls": ["https://www.k2skis.com/en/sale"],                                               "affiliate_base": "https://www.k2skis.com/en/sale"},
    {"brand": "Line Skis",       "category": "ski",          "urls": ["https://www.lineskis.com/collections/sale"],                                    "affiliate_base": "https://www.lineskis.com/collections/sale"},
    {"brand": "Armada Skis",     "category": "ski",          "urls": ["https://www.armadaskis.com/collections/sale"],                                  "affiliate_base": "https://www.armadaskis.com/collections/sale"},
    {"brand": "Salomon",         "category": "boots",        "urls": ["https://www.salomon.com/en-us/sale/ski"],                                       "affiliate_base": "https://www.salomon.com/en-us/sale/ski"},
    {"brand": "Nidecker",        "category": "bindings",     "urls": ["https://www.nidecker.com/en/sale"],                                             "affiliate_base": "https://www.nidecker.com/en/sale"},
    {"brand": "Union Binding",   "category": "bindings",     "urls": ["https://www.unionbindingco.com/collections/sale"],                              "affiliate_base": "https://www.unionbindingco.com/collections/sale"},
    {"brand": "Patagonia",       "category": "outerwear",    "urls": ["https://www.patagonia.com/shop/sale/sport/skiing-snowboarding"],                 "affiliate_base": "https://www.patagonia.com/shop/sale/sport/skiing-snowboarding"},
    {"brand": "686",             "category": "outerwear",    "urls": ["https://www.686.com/collections/sale"],                                         "affiliate_base": "https://www.686.com/collections/sale"},
    {"brand": "POC",             "category": "helmets",      "urls": ["https://www.pocsports.com/collections/ski-sale"],                               "affiliate_base": "https://www.pocsports.com/collections/ski-sale"},
    {"brand": "Smith Optics",    "category": "goggles",      "urls": ["https://www.smithoptics.com/en_US/sale/"],                                      "affiliate_base": "https://www.smithoptics.com/en_US/sale/"},
    {"brand": "Oakley",          "category": "goggles",      "urls": ["https://www.oakley.com/en-us/category/snow?prefn1=isOnSale&prefv1=true"],        "affiliate_base": "https://www.oakley.com/en-us/category/snow"},
    {"brand": "Dakine",          "category": "accessories",  "urls": ["https://www.dakine.com/collections/sale"],                                      "affiliate_base": "https://www.dakine.com/collections/sale"},
    {"brand": "REI",             "category": "accessories",  "urls": ["https://www.rei.com/c/ski-gear?origin=web&sort=percentOff%7Cdesc"],              "affiliate_base": "https://www.rei.com/c/ski-gear?sort=percentOff%7Cdesc"},
    {"brand": "Evo",             "category": "ski",          "urls": ["https://www.evo.com/sale/ski"],                                                 "affiliate_base": "https://www.evo.com/sale/ski"},
    {"brand": "Backcountry",     "category": "ski",          "urls": ["https://www.backcountry.com/ski-sale"],                                         "affiliate_base": "https://www.backcountry.com/ski-sale"},
]

PROMO_CODE_RE   = re.compile(r'(?:use\s+(?:code|promo|coupon)\s*[:\-]?\s*|promo\s*code[:\s]+|coupon[:\s]+|enter\s+code\s*)([A-Z0-9]{4,20})\b', re.IGNORECASE)
DISCOUNT_RE     = re.compile(r'(?:up\s+to\s+)?(\d{1,3})\s*%\s*off|save\s+(\d{1,3})\s*%|(\d{1,3})%\s+off', re.IGNORECASE)
CLEARANCE_SIGS  = ["clearance","end of season","last chance","while supplies last","final sale","season end"]
DROP_SIGS       = ["new drop","just dropped","now available","preorder","pre-order","new arrival","new release"]
EMAIL_SIGS      = ["email exclusive","subscribers only","sign up for","newsletter exclusive"]
SALE_SIGS       = ["% off","sale","deal","promo","savings","reduced","markdown","discounted"]

@dataclass
class Deal:
    id: str
    brand: str
    category: str
    deal_type: str
    description: str
    discount: Optional[str]
    code: Optional[str]
    url: str
    source_url: str
    hot: bool = False
    pulse: bool = False
    first_seen: str = ""
    last_seen: str = ""
    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.first_seen: self.first_seen = now
        self.last_seen = now

def fetch(url: str) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4}", lambda r: r.abort())
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3500)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        log.warning(f"  Playwright failed: {e}")
        try:
            import requests as req
            r = req.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
            r.raise_for_status()
            return r.text
        except Exception as e2:
            log.warning(f"  requests also failed: {e2}")
            return None

def extract_blocks(html: str) -> list:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script","style","noscript","svg","path"]): tag.decompose()
    blocks, seen = [], set()
    for sel in ["[class*='banner']","[class*='promo']","[class*='announcement']","[class*='sale']",
                "[class*='offer']","[class*='deal']","[class*='discount']","[class*='notification']",
                "[class*='strip']","[class*='bar']","[id*='banner']","[id*='promo']","[id*='sale']",
                "header",".announcement-bar",".promo-bar",".top-bar","#shopify-section-announcement-bar"]:
        try:
            for el in soup.select(sel)[:5]:
                t = el.get_text(" ", strip=True)
                if t and t not in seen and len(t) > 6: blocks.append(t); seen.add(t)
        except Exception: continue
    for tag in soup.find_all(["h1","h2","h3","h4","p","li","span","div","a"]):
        t = tag.get_text(" ", strip=True)
        if t and t not in seen and 6 < len(t) < 500: blocks.append(t); seen.add(t)
    return blocks

def make_id(brand, desc): return hashlib.md5(f"{brand.lower()}::{desc.lower()[:80]}".encode()).hexdigest()[:12]

def analyse(brand_cfg, url, html) -> list:
    blocks = extract_blocks(html)
    full = " ".join(blocks).lower()
    if not any(s in full for s in SALE_SIGS + CLEARANCE_SIGS + DROP_SIGS + EMAIL_SIGS):
        log.info(f"    no signals"); return []
    if any(s in full for s in EMAIL_SIGS): deal_type = "email"
    elif any(s in full for s in CLEARANCE_SIGS): deal_type = "clearance"
    elif any(s in full for s in DROP_SIGS): deal_type = "drops"
    else: deal_type = "active"
    discount, best_pct = None, 0
    for m in DISCOUNT_RE.finditer(full):
        pct = int(next((x for x in m.groups() if x), 0))
        if pct > best_pct: best_pct, discount = pct, f"{pct}% off"
    code = None
    skip = {"FREE","SALE","SAVE","DEAL","CODE","HERE","THIS","THAT","YOUR","WITH","SHOP","MORE","VIEW","PLUS"}
    for block in blocks:
        m = PROMO_CODE_RE.search(block)
        if m:
            c = m.group(1).upper()
            if c not in skip and len(c) >= 4: code = c; break
    desc = ""
    for block in blocks:
        if any(s in block.lower() for s in SALE_SIGS + CLEARANCE_SIGS + DROP_SIGS):
            desc = re.sub(r'\s+', ' ', block).strip()[:130]; break
    if not desc:
        desc = f"{brand_cfg['brand']} — {discount or 'sale'} on select products"
    hot = bool(code) or best_pct >= 25
    d = Deal(id=make_id(brand_cfg["brand"], desc), brand=brand_cfg["brand"], category=brand_cfg["category"],
             deal_type=deal_type, description=desc, discount=discount or "Sale", code=code,
             url=brand_cfg.get("affiliate_base", url), source_url=url, hot=hot)
    log.info(f"    ✓ [{deal_type}] {discount or 'sale'} {('code:'+code) if code else ''} — {desc[:55]}")
    return [d]

OUTPUT_PATH = Path(__file__).parent.parent / "deals.json"

def load_previous():
    if OUTPUT_PATH.exists():
        try: return {d["id"]: d for d in json.loads(OUTPUT_PATH.read_text()).get("deals", [])}
        except: pass
    return {}

def save(deals, previous):
    now = datetime.now(timezone.utc).isoformat()
    merged = []
    for deal in deals:
        d = asdict(deal)
        if deal.id in previous:
            d["first_seen"] = previous[deal.id]["first_seen"]; d["pulse"] = False
        else:
            d["pulse"] = True; log.info(f"  ★ NEW: {deal.brand} — {deal.description[:50]}")
        merged.append(d)
    merged.sort(key=lambda d: (not d["pulse"], not d["hot"], d["brand"]))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps({"generated_at": now, "deal_count": len(merged), "brands_scanned": len(BRANDS), "deals": merged}, indent=2))
    log.info(f"\n✓ Wrote {len(merged)} deals → {OUTPUT_PATH}")

def run():
    log.info("="*60); log.info("POWDER STASH — scraper starting"); log.info("="*60)
    previous = load_previous()
    all_deals, seen_ids = [], set()
    for brand_cfg in BRANDS:
        log.info(f"\n→ {brand_cfg['brand']}")
        for url in brand_cfg["urls"]:
            log.info(f"  {url}")
            html = fetch(url)
            if not html: continue
            for d in analyse(brand_cfg, url, html):
                if d.id not in seen_ids: seen_ids.add(d.id); all_deals.append(d)
            time.sleep(2)
    log.info(f"\n{'='*60}\nComplete — {len(all_deals)} deals found")
    save(all_deals, previous)

if __name__ == "__main__":
    run()
