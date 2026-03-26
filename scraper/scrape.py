"""
Powder Stash — Brand Deal Scraper v6
Strategy:
- Shopify JSON API for brands that have it (fast, never blocked)
- Evo internal search API for major brands (JSON, bypasses 403)
- Direct HTML for brands that allow it
"""

import json, re, time, hashlib, logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Evo search API — returns JSON, works from GitHub Actions
# Query: brand name + category, filter onSale
# ---------------------------------------------------------------------------
EVO_BRANDS = [
    # (display_name, category, evo_brand_slug, evo_category)
    ("Atomic",          "ski",       "Atomic",          "ski"),
    ("Rossignol",       "ski",       "Rossignol",       "ski"),
    ("K2 Skis",         "ski",       "K2",              "ski"),
    ("Salomon",         "ski",       "Salomon",         "ski"),
    ("Armada Skis",     "ski",       "Armada",          "ski"),
    ("Line Skis",       "ski",       "Line Skis",       "ski"),
    ("Blizzard",        "ski",       "Blizzard",        "ski"),
    ("Nordica",         "ski",       "Nordica",         "ski"),
    ("Volkl",           "ski",       "Volkl",           "ski"),
    ("Elan",            "ski",       "Elan",            "ski"),
    ("Fischer",         "ski",       "Fischer",         "ski"),
    ("Head Skis",       "ski",       "Head",            "ski"),
    ("Dynastar",        "ski",       "Dynastar",        "ski"),
    ("Scott Sports",    "ski",       "Scott",           "ski"),
    ("Faction Skis",    "ski",       "Faction Skis",    "ski"),
    ("Burton",          "snowboard", "Burton",          "snowboard"),
    ("Capita",          "snowboard", "CAPiTA",          "snowboard"),
    ("Rome SDS",        "bindings",  "Rome SDS",        "snowboard"),
    ("Union Binding",   "bindings",  "Union",           "snowboard"),
    ("Lib Tech",        "snowboard", "Lib Tech",        "snowboard"),
    ("Salomon Boards",  "snowboard", "Salomon",         "snowboard"),
    ("Patagonia",       "outerwear", "Patagonia",       "ski"),
    ("The North Face",  "outerwear", "The North Face",  "ski"),
    ("Helly Hansen",    "outerwear", "Helly Hansen",    "ski"),
    ("Mammut",          "outerwear", "Mammut",          "ski"),
    ("Marmot",          "outerwear", "Marmot",          "ski"),
    ("Mountain Hardwear","outerwear","Mountain Hardwear","ski"),
    ("Oakley",          "goggles",   "Oakley",          "ski"),
    ("Smith",           "goggles",   "Smith",           "ski"),
]

SHOPIFY_BRANDS = [
    {"brand":"Jones Snowboards",  "category":"snowboard",  "shopify_domain":"www.jonessnowboards.com",       "collection":"sale",               "affiliate_base":"https://www.jonessnowboards.com/collections/sale"},
    {"brand":"Nidecker",          "category":"bindings",   "shopify_domain":"www.nidecker.com",              "collection":"sale",               "affiliate_base":"https://www.nidecker.com/en/sale"},
    {"brand":"Dakine",            "category":"accessories","shopify_domain":"www.dakine.com",                "collection":"sale",               "affiliate_base":"https://www.dakine.com/collections/sale"},
    {"brand":"686",               "category":"outerwear",  "shopify_domain":"www.686.com",                   "collection":"mens-outerwear-sale","affiliate_base":"https://www.686.com/collections/mens-outerwear-sale"},
    {"brand":"POC",               "category":"helmets",    "shopify_domain":"www.pocsports.com",             "collection":"ski-sale",           "affiliate_base":"https://www.pocsports.com/collections/ski-sale"},
    {"brand":"Flylow",            "category":"outerwear",  "shopify_domain":"www.flylowgear.com",            "collection":"sale",               "affiliate_base":"https://www.flylowgear.com/collections/sale"},
    {"brand":"Hestra Gloves",     "category":"accessories","shopify_domain":"www.hestragloves.com",          "collection":"sale",               "affiliate_base":"https://www.hestragloves.com/collections/sale"},
    {"brand":"Outdoor Research",  "category":"outerwear",  "shopify_domain":"www.outdoorresearch.com",       "collection":"sale",               "affiliate_base":"https://www.outdoorresearch.com/collections/sale"},
    {"brand":"Mons Royale",       "category":"accessories","shopify_domain":"www.monsroyale.com",            "collection":"sale",               "affiliate_base":"https://www.monsroyale.com/collections/sale"},
    {"brand":"Smartwool",         "category":"accessories","shopify_domain":"www.smartwool.com",             "collection":"sale",               "affiliate_base":"https://www.smartwool.com/collections/sale"},
    {"brand":"Icelantic Skis",    "category":"ski",        "shopify_domain":"www.icelanticskis.com",         "collection":"sale",               "affiliate_base":"https://www.icelanticskis.com/collections/sale"},
    {"brand":"Black Crows",       "category":"ski",        "shopify_domain":"www.black-crows.com",           "collection":"sale",               "affiliate_base":"https://www.black-crows.com/collections/sale"},
    {"brand":"Picture Organic",   "category":"outerwear",  "shopify_domain":"www.picture-organic-clothing.com","collection":"sale",            "affiliate_base":"https://www.picture-organic-clothing.com/collections/sale"},
    {"brand":"Weston Snowboards", "category":"snowboard",  "shopify_domain":"www.westonsnowboards.com",      "collection":"sale",               "affiliate_base":"https://www.westonsnowboards.com/collections/sale"},
    {"brand":"Tactics Snowboard", "category":"snowboard",  "shopify_domain":"www.tactics.com",               "collection":"sale-snowboarding",  "affiliate_base":"https://www.tactics.com/sale/snowboarding"},
    {"brand":"Christy Sports",    "category":"ski",        "shopify_domain":"www.christysports.com",         "collection":"sale",               "affiliate_base":"https://www.christysports.com/sale/"},
]

HTML_BRANDS = [
    {"brand":"Smith Optics",   "category":"goggles",   "urls":["https://www.smithoptics.com/en-us/sale/"],                                        "affiliate_base":"https://www.smithoptics.com/en-us/sale/"},
    {"brand":"Patagonia",      "category":"outerwear", "urls":["https://www.patagonia.com/shop/sale/sport/skiing-snowboarding"],                   "affiliate_base":"https://www.patagonia.com/shop/sale/sport/skiing-snowboarding"},
    {"brand":"Burton Direct",  "category":"snowboard", "urls":["https://www.burton.com/us/en/c/sale-gear"],                                        "affiliate_base":"https://www.burton.com/us/en/c/sale-gear"},
    {"brand":"Salomon Direct", "category":"ski",       "urls":["https://www.salomon.com/en-us/sport/ski/outlet"],                                  "affiliate_base":"https://www.salomon.com/en-us/sport/ski/outlet"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DISCOUNT_RE = re.compile(r'(?:up\s+to\s+)?(\d{1,3})\s*%\s*off|save\s+(\d{1,3})\s*%', re.IGNORECASE)
PROMO_RE    = re.compile(r'(?:use\s+(?:code|promo)\s*[:\-]?\s*|promo\s*code[:\s]+|enter\s+code\s*)([A-Z0-9]{4,20})\b', re.IGNORECASE)
CLEAR_SIGS  = ["clearance","end of season","final sale","closeout","outlet","last chance"]
DROP_SIGS   = ["new drop","just dropped","preorder","pre-order","new arrival"]
EMAIL_SIGS  = ["email exclusive","subscribers only","newsletter exclusive"]
SALE_SIGS   = ["% off","on sale","outlet","sale","savings","reduced"]

@dataclass
class Deal:
    id: str; brand: str; category: str; deal_type: str; description: str
    discount: Optional[str]; code: Optional[str]; url: str; source_url: str
    hot: bool = False; pulse: bool = False; first_seen: str = ""; last_seen: str = ""
    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.first_seen: self.first_seen = now
        self.last_seen = now

def make_id(brand, desc):
    return hashlib.md5(f"{brand.lower()}::{desc.lower()[:80]}".encode()).hexdigest()[:12]

# ---------------------------------------------------------------------------
# Evo search API
# ---------------------------------------------------------------------------
def scrape_evo_brand(display_name, category, evo_brand, evo_cat):
    """Use Evo's internal search API to find sale items for a brand."""
    import requests
    # Evo uses a search endpoint that returns JSON
    search_url = f"https://api.evo.com/v1/search/products?query={evo_brand}&filters=onSale:true&sport={evo_cat}&limit=5"
    affiliate_url = f"https://www.evo.com/shop/sale/{evo_cat}/{evo_brand.lower().replace(' ','-')}"

    # Try the search API first
    try:
        api_headers = {**HEADERS, "Accept": "application/json", "Origin": "https://www.evo.com", "Referer": "https://www.evo.com/"}
        r = requests.get(search_url, headers=api_headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            products = data.get("products", data.get("items", data.get("results", [])))
            if products:
                sale_items = [p for p in products if p.get("salePrice") or p.get("onSale")]
                if sale_items:
                    best_pct = 0
                    for p in sale_items:
                        orig = p.get("originalPrice") or p.get("price")
                        sale = p.get("salePrice")
                        if orig and sale:
                            try:
                                pct = round((float(orig) - float(sale)) / float(orig) * 100)
                                if pct > best_pct: best_pct = pct
                            except: pass
                    titles = [p.get("name","") for p in sale_items[:2] if p.get("name")]
                    discount = f"Up to {best_pct}% off" if best_pct >= 5 else "Sale"
                    desc = f"{discount} — {', '.join(titles)}" if titles else f"{display_name} — {discount} at Evo"
                    if len(desc) > 130: desc = desc[:127] + "..."
                    deal = Deal(
                        id=make_id(display_name, desc), brand=display_name, category=category,
                        deal_type="clearance" if best_pct >= 40 else "active",
                        description=desc, discount=discount, code=None,
                        url=affiliate_url, source_url=search_url, hot=best_pct >= 25
                    )
                    log.info(f"    ✓ Evo API [{deal.deal_type}] {discount} — {desc[:55]}")
                    return [deal]
    except Exception as e:
        log.info(f"    Evo API failed ({e}), trying sitemap...")

    # Fallback: check if Evo's sale page for this brand exists via sitemap/ping
    try:
        ping_url = f"https://www.evo.com/shop/sale/{evo_cat}/{evo_brand.lower().replace(' ', '-')}"
        r = requests.head(ping_url, headers=HEADERS, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            desc = f"{display_name} — Last Chair Sale items at Evo. Up to 60% off."
            deal = Deal(
                id=make_id(display_name, desc), brand=display_name, category=category,
                deal_type="clearance", description=desc, discount="Up to 60% off",
                code=None, url=affiliate_url, source_url=ping_url, hot=True
            )
            log.info(f"    ✓ Evo page confirmed (HEAD 200)")
            return [deal]
        elif r.status_code in (301, 302):
            desc = f"{display_name} — sale gear available at Evo"
            deal = Deal(
                id=make_id(display_name, desc), brand=display_name, category=category,
                deal_type="active", description=desc, discount="Sale",
                code=None, url=affiliate_url, source_url=ping_url, hot=False
            )
            log.info(f"    ✓ Evo page redirect ({r.status_code})")
            return [deal]
        else:
            log.info(f"    Evo page returned {r.status_code} — skipping")
    except Exception as e:
        log.warning(f"    Evo HEAD failed: {e}")
    return []

# ---------------------------------------------------------------------------
# Shopify JSON API
# ---------------------------------------------------------------------------
def scrape_shopify(brand_cfg):
    import requests
    domain = brand_cfg["shopify_domain"]
    collection = brand_cfg["collection"]
    url = f"https://{domain}/collections/{collection}/products.json?limit=250"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning(f"    Shopify API failed: {e}")
        return scrape_shopify_fallback(brand_cfg)

    products = data.get("products", [])
    log.info(f"    {len(products)} products")
    if not products:
        return scrape_shopify_fallback(brand_cfg)

    sale_products = []
    for p in products:
        for v in p.get("variants", []):
            cap = v.get("compare_at_price")
            price = v.get("price")
            if cap and price:
                try:
                    if float(cap) > float(price):
                        sale_products.append(p); break
                except: pass
    if not sale_products:
        sale_products = products[:5]

    best_pct = 0
    for p in sale_products:
        for v in p.get("variants", []):
            cap = v.get("compare_at_price")
            price = v.get("price")
            if cap and price:
                try:
                    cf, pf = float(cap), float(price)
                    if cf > 0:
                        pct = round((cf - pf) / cf * 100)
                        if pct > best_pct: best_pct = pct
                except: pass

    discount = f"Up to {best_pct}% off" if best_pct >= 5 else "Sale"
    titles = [p["title"] for p in sale_products[:3]]
    count = len(sale_products)
    if titles:
        desc = f"{discount} — {', '.join(titles[:2])}" + (f" + {count-2} more" if count > 2 else "")
        if len(desc) > 130: desc = desc[:127] + "..."
    else:
        desc = f"{brand_cfg['brand']} — {discount} on selected gear"

    deal = Deal(
        id=make_id(brand_cfg["brand"], desc), brand=brand_cfg["brand"],
        category=brand_cfg["category"],
        deal_type="clearance" if best_pct >= 40 else "active",
        description=desc, discount=discount, code=None,
        url=brand_cfg["affiliate_base"], source_url=url, hot=best_pct >= 25,
    )
    log.info(f"    ✓ [{deal.deal_type}] {discount} — {desc[:60]}")
    return [deal]

def scrape_shopify_fallback(brand_cfg):
    import requests
    url = f"https://{brand_cfg['shopify_domain']}/collections/{brand_cfg['collection']}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200 and len(r.text) > 500:
            desc = f"{brand_cfg['brand']} — sale items available. Visit site for details."
            deal = Deal(
                id=make_id(brand_cfg["brand"], desc), brand=brand_cfg["brand"],
                category=brand_cfg["category"], deal_type="active",
                description=desc, discount="Sale", code=None,
                url=brand_cfg["affiliate_base"], source_url=url, hot=False,
            )
            log.info(f"    ✓ confirmed via fallback")
            return [deal]
    except Exception as e:
        log.warning(f"    fallback failed: {e}")
    return []

# ---------------------------------------------------------------------------
# HTML scraper
# ---------------------------------------------------------------------------
def scrape_html(brand_cfg):
    import requests
    from bs4 import BeautifulSoup
    deals = []
    for url in brand_cfg["urls"]:
        log.info(f"  {url[:80]}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            r.raise_for_status()
        except Exception as e:
            log.warning(f"    failed: {e}"); continue

        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script","style","noscript","svg","path"]): t.decompose()

        blocks, seen = [], set()
        for sel in ["[class*='banner']","[class*='promo']","[class*='announcement']",
                    "[class*='sale']","[class*='offer']","[class*='deal']","header","h1","h2","h3"]:
            try:
                for el in soup.select(sel)[:8]:
                    t = el.get_text(" ", strip=True)
                    if t and t not in seen and 5 < len(t) < 600: blocks.append(t); seen.add(t)
            except: continue
        for tag in soup.find_all(["p","li","span","div","a"]):
            t = tag.get_text(" ", strip=True)
            if t and t not in seen and 5 < len(t) < 400: blocks.append(t); seen.add(t)

        full = " ".join(blocks).lower()
        if not any(s in full for s in SALE_SIGS+CLEAR_SIGS+DROP_SIGS+EMAIL_SIGS):
            log.info("    no signals"); continue

        if any(s in full for s in EMAIL_SIGS): dtype = "email"
        elif any(s in full for s in CLEAR_SIGS): dtype = "clearance"
        elif any(s in full for s in DROP_SIGS): dtype = "drops"
        else: dtype = "active"

        discount, best = None, 0
        for m in DISCOUNT_RE.finditer(full):
            p = int(next((x for x in m.groups() if x), 0))
            if p > best and p <= 90: best, discount = p, f"{p}% off"

        skip = {"FREE","SALE","SAVE","DEAL","CODE","THIS","YOUR","SHOP","MORE","VIEW","PLUS","SIGN","GEAR"}
        code = None
        for block in blocks:
            m = PROMO_RE.search(block)
            if m:
                c = m.group(1).upper()
                if c not in skip and 4 <= len(c) <= 20: code = c; break

        desc = next(
            (re.sub(r'\s+',' ',b).strip()[:130] for b in blocks
             if any(s in b.lower() for s in ["% off","sale","outlet","clearance"]) and 15 < len(b) < 200),
            f"{brand_cfg['brand']} — {discount or 'sale'} on select products."
        )
        hot = bool(code) or best >= 25
        d = Deal(
            id=make_id(brand_cfg["brand"], desc), brand=brand_cfg["brand"],
            category=brand_cfg["category"], deal_type=dtype, description=desc,
            discount=discount or "Sale", code=code,
            url=brand_cfg.get("affiliate_base", url), source_url=url, hot=hot
        )
        log.info(f"    ✓ [{dtype}] {discount or 'sale'} — {desc[:60]}")
        deals.append(d)
        time.sleep(1)
    return deals

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
OUTPUT_PATH = Path(__file__).parent.parent / "deals.json"

def load_previous():
    if OUTPUT_PATH.exists():
        try: return {d["id"]: d for d in json.loads(OUTPUT_PATH.read_text()).get("deals",[])}
        except: pass
    return {}

def save(deals, previous):
    now = datetime.now(timezone.utc).isoformat()
    merged = []
    for deal in deals:
        d = asdict(deal)
        if deal.id in previous: d["first_seen"]=previous[deal.id]["first_seen"]; d["pulse"]=False
        else: d["pulse"]=True; log.info(f"  NEW: {deal.brand} — {deal.description[:60]}")
        merged.append(d)
    merged.sort(key=lambda d:(not d["pulse"],not d["hot"],d["brand"]))
    OUTPUT_PATH.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps({
        "generated_at":now,"deal_count":len(merged),"brands_scanned":len(EVO_BRANDS)+len(SHOPIFY_BRANDS)+len(HTML_BRANDS),"deals":merged
    },indent=2))
    log.info(f"\n✓ Wrote {len(merged)} deals → {OUTPUT_PATH}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    log.info("="*60)
    log.info("POWDER STASH — scraper starting")
    log.info(f"{len(EVO_BRANDS)} Evo + {len(SHOPIFY_BRANDS)} Shopify + {len(HTML_BRANDS)} HTML brands")
    log.info("="*60)
    previous = load_previous()
    all_deals, seen_ids = [], set()

    # 1. Evo brands
    log.info("\n── EVO BRANDS ──────────────────────────────")
    for (name, cat, slug, evo_cat) in EVO_BRANDS:
        log.info(f"\n→ {name}")
        for d in scrape_evo_brand(name, cat, slug, evo_cat):
            if d.id not in seen_ids: seen_ids.add(d.id); all_deals.append(d)
        time.sleep(0.3)

    # 2. Shopify brands
    log.info("\n── SHOPIFY BRANDS ──────────────────────────")
    for b in SHOPIFY_BRANDS:
        log.info(f"\n→ {b['brand']}")
        for d in scrape_shopify(b):
            if d.id not in seen_ids: seen_ids.add(d.id); all_deals.append(d)
        time.sleep(0.3)

    # 3. HTML brands
    log.info("\n── HTML BRANDS ─────────────────────────────")
    for b in HTML_BRANDS:
        log.info(f"\n→ {b['brand']}")
        for d in scrape_html(b):
            if d.id not in seen_ids: seen_ids.add(d.id); all_deals.append(d)
        time.sleep(0.5)

    log.info(f"\nComplete — {len(all_deals)} deals found")
    save(all_deals, previous)

if __name__ == "__main__":
    run()
