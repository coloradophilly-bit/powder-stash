"""
Powder Stash — Brand Deal Scraper (Playwright edition)
Writes results to deals.json at repo root.
"""

import json, re, time, hashlib, logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

BRANDS = [
    {"brand":"Burton",          "category":"outerwear",   "urls":["https://www.burton.com/us/en/c/mens-sale",        "https://www.burton.com/us/en/c/womens-sale"],          "affiliate_base":"https://www.burton.com/us/en/c/mens-sale"},
    {"brand":"Jones Snowboards","category":"snowboard",   "urls":["https://www.jonessnowboards.com/collections/sale"],"affiliate_base":"https://www.jonessnowboards.com/collections/sale"},
    {"brand":"Capita",          "category":"snowboard",   "urls":["https://www.capitasnowboarding.com/collections/on-sale"],"affiliate_base":"https://www.capitasnowboarding.com/collections/on-sale"},
    {"brand":"Rome SDS",        "category":"bindings",    "urls":["https://www.romesnowboards.com/collections/on-sale"],"affiliate_base":"https://www.romesnowboards.com/collections/on-sale"},
    {"brand":"K2 Skis",         "category":"ski",         "urls":["https://www.k2snow.com/en-us/skis/sale"],          "affiliate_base":"https://www.k2snow.com/en-us/skis/sale"},
    {"brand":"Line Skis",       "category":"ski",         "urls":["https://www.lineskis.com/en-us/collections/sale"], "affiliate_base":"https://www.lineskis.com/en-us/collections/sale"},
    {"brand":"Armada Skis",     "category":"ski",         "urls":["https://www.armadaskis.com/en-us/collections/sale"],"affiliate_base":"https://www.armadaskis.com/en-us/collections/sale"},
    {"brand":"Salomon",         "category":"boots",       "urls":["https://www.salomon.com/en-us/sport/ski/outlet"],  "affiliate_base":"https://www.salomon.com/en-us/sport/ski/outlet"},
    {"brand":"Union Binding",   "category":"bindings",    "urls":["https://unionbindingco.com/collections/sale"],     "affiliate_base":"https://unionbindingco.com/collections/sale"},
    {"brand":"Patagonia",       "category":"outerwear",   "urls":["https://www.patagonia.com/shop/sale/sport/skiing-snowboarding"],"affiliate_base":"https://www.patagonia.com/shop/sale/sport/skiing-snowboarding"},
    {"brand":"686",             "category":"outerwear",   "urls":["https://www.686.com/collections/mens-outerwear-sale","https://www.686.com/collections/womens-outerwear-sale"],"affiliate_base":"https://www.686.com/collections/mens-outerwear-sale"},
    {"brand":"POC",             "category":"helmets",     "urls":["https://www.pocsports.com/collections/ski"],       "affiliate_base":"https://www.pocsports.com/collections/ski"},
    {"brand":"Smith Optics",    "category":"goggles",     "urls":["https://www.smithoptics.com/en-us/sale/"],         "affiliate_base":"https://www.smithoptics.com/en-us/sale/"},
    {"brand":"Oakley",          "category":"goggles",     "urls":["https://www.oakley.com/en-us/category/snow-goggles"],"affiliate_base":"https://www.oakley.com/en-us/category/snow-goggles"},
    {"brand":"Dakine",          "category":"accessories", "urls":["https://www.dakine.com/collections/sale"],         "affiliate_base":"https://www.dakine.com/collections/sale"},
    {"brand":"REI",             "category":"accessories", "urls":["https://www.rei.com/c/ski-gear"],                  "affiliate_base":"https://www.rei.com/c/ski-gear"},
    {"brand":"Evo",             "category":"ski",         "urls":["https://www.evo.com/outlet/ski"],                  "affiliate_base":"https://www.evo.com/outlet/ski"},
    {"brand":"Backcountry",     "category":"ski",         "urls":["https://www.backcountry.com/ski"],                 "affiliate_base":"https://www.backcountry.com/ski"},
    {"brand":"Christy Sports",  "category":"ski",         "urls":["https://www.christysports.com/sale/"],             "affiliate_base":"https://www.christysports.com/sale/"},
]

PROMO_CODE_RE  = re.compile(r'(?:use\s+(?:code|promo|coupon)\s*[:\-]?\s*|promo\s*code[:\s]+|enter\s+code\s*)([A-Z0-9]{4,20})\b', re.IGNORECASE)
DISCOUNT_RE    = re.compile(r'(?:up\s+to\s+)?(\d{1,3})\s*%\s*off|save\s+(\d{1,3})\s*%|(\d{1,3})%\s+off', re.IGNORECASE)
CLEARANCE_SIGS = ["clearance","end of season","last chance","final sale","season end","closeout"]
DROP_SIGS      = ["new drop","just dropped","preorder","pre-order","new arrival","just arrived"]
EMAIL_SIGS     = ["email exclusive","subscribers only","newsletter exclusive","sign up.*off"]
SALE_SIGS      = ["% off","on sale","outlet","sale","promo","savings","reduced","discounted","markdown"]

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
    """Playwright first, requests fallback."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width":1280,"height":800},
                ignore_https_errors=True,
            )
            page = ctx.new_page()
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}", lambda r: r.abort())
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(3000)
            except Exception:
                pass
            html = page.content()
            browser.close()
            log.info(f"    Playwright OK ({len(html):,} chars)")
            return html
    except Exception as e:
        log.warning(f"    Playwright failed: {e}")
    try:
        import requests as req
        r = req.get(url, headers={"User-Agent":"Mozilla/5.0","Accept-Language":"en-US,en;q=0.9"}, timeout=20, allow_redirects=True)
        r.raise_for_status()
        log.info(f"    requests OK ({len(r.text):,} chars)")
        return r.text
    except Exception as e:
        log.warning(f"    requests failed: {e}")
        return None

def extract_blocks(html: str) -> list:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script","style","noscript","svg","path"]): tag.decompose()
    blocks, seen = [], set()
    priority = ["[class*='banner']","[class*='promo']","[class*='announcement']","[class*='sale']",
                "[class*='offer']","[class*='deal']","[class*='discount']","[class*='notification']",
                "[class*='strip']","[class*='bar']","header",".announcement-bar",".promo-bar",
                "#shopify-section-announcement-bar","[class*='alert']","[class*='ribbon']"]
    for sel in priority:
        try:
            for el in soup.select(sel)[:8]:
                t = el.get_text(" ", strip=True)
                if t and t not in seen and 5 < len(t) < 600: blocks.append(t); seen.add(t)
        except: continue
    for tag in soup.find_all(["h1","h2","h3","h4","p","li","span","div","a","strong"]):
        t = tag.get_text(" ", strip=True)
        if t and t not in seen and 5 < len(t) < 500: blocks.append(t); seen.add(t)
    return blocks

def make_id(brand, desc):
    return hashlib.md5(f"{brand.lower()}::{desc.lower()[:80]}".encode()).hexdigest()[:12]

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
        if pct > best_pct and pct <= 90: best_pct, discount = pct, f"{pct}% off"
    code = None
    skip = {"FREE","SALE","SAVE","DEAL","CODE","HERE","THIS","THAT","YOUR","WITH","SHOP","MORE","VIEW","PLUS","SIGN","BEST","FAST"}
    for block in blocks:
        m = PROMO_CODE_RE.search(block)
        if m:
            c = m.group(1).upper()
            if c not in skip and 4 <= len(c) <= 20: code = c; break
    desc = ""
    for block in blocks:
        bl = block.lower()
        if any(s in bl for s in ["% off","sale","outlet","clearance","promo"]):
            cleaned = re.sub(r'\s+', ' ', block).strip()
            if 15 < len(cleaned) < 140: desc = cleaned; break
    if not desc:
        desc = f"{brand_cfg['brand']} — {discount or 'sale'} on select products. Visit site for details."
    hot = bool(code) or best_pct >= 25
    d = Deal(id=make_id(brand_cfg["brand"], desc), brand=brand_cfg["brand"], category=brand_cfg["category"],
             deal_type=deal_type, description=desc, discount=discount or "Sale", code=code,
             url=brand_cfg.get("affiliate_base", url), source_url=url, hot=hot)
    log.info(f"    ✓ [{deal_type}] {discount or 'sale'} {('code:'+code) if code else ''} — {desc[:60]}")
    return [d]

# Write to repo root so GitHub Pages can serve it
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
    OUTPUT_PATH.write_text(json.dumps({"generated_at":now,"deal_count":len(merged),"brands_scanned":len(BRANDS),"deals":merged}, indent=2))
    log.info(f"\n✓ Wrote {len(merged)} deals → {OUTPUT_PATH}")

def run():
    log.info("="*60); log.info("POWDER STASH — scraper starting"); log.info(f"Scanning {len(BRANDS)} brands"); log.info("="*60)
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
            time.sleep(1.5)
    log.info(f"\n{'='*60}\nComplete — {len(all_deals)} deals found")
    save(all_deals, previous)

if __name__ == "__main__":
    run()
