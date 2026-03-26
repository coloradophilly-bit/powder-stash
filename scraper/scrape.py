"""
Powder Stash — Brand Deal Scraper
Uses Shopify JSON API for Shopify brands (fast, never blocked).
Falls back to requests+BeautifulSoup for non-Shopify brands.
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
    # ── SHOPIFY BRANDS (Shopify JSON API — reliable, never blocked) ────────
    {"brand":"Burton",           "category":"outerwear",   "type":"shopify", "shopify_domain":"www.burton.com",             "collection":"sale",              "affiliate_base":"https://www.burton.com/us/en/c/mens-sale"},
    {"brand":"Jones Snowboards", "category":"snowboard",   "type":"shopify", "shopify_domain":"www.jonessnowboards.com",    "collection":"sale",              "affiliate_base":"https://www.jonessnowboards.com/collections/sale"},
    {"brand":"Capita",           "category":"snowboard",   "type":"shopify", "shopify_domain":"www.capitasnowboarding.com", "collection":"on-sale",           "affiliate_base":"https://www.capitasnowboarding.com/collections/on-sale"},
    {"brand":"Rome SDS",         "category":"bindings",    "type":"shopify", "shopify_domain":"www.romesnowboards.com",     "collection":"on-sale",           "affiliate_base":"https://www.romesnowboards.com/collections/on-sale"},
    {"brand":"Line Skis",        "category":"ski",         "type":"shopify", "shopify_domain":"www.lineskis.com",           "collection":"sale",              "affiliate_base":"https://www.lineskis.com/en-us/collections/sale"},
    {"brand":"Armada Skis",      "category":"ski",         "type":"shopify", "shopify_domain":"www.armadaskis.com",         "collection":"sale",              "affiliate_base":"https://www.armadaskis.com/collections/sale"},
    {"brand":"686",              "category":"outerwear",   "type":"shopify", "shopify_domain":"www.686.com",                "collection":"sale",              "affiliate_base":"https://www.686.com/collections/sale"},
    {"brand":"Union Binding",    "category":"bindings",    "type":"shopify", "shopify_domain":"unionbindingco.com",         "collection":"sale",              "affiliate_base":"https://unionbindingco.com/collections/sale"},
    {"brand":"Nidecker",         "category":"bindings",    "type":"shopify", "shopify_domain":"www.nidecker.com",           "collection":"sale",              "affiliate_base":"https://www.nidecker.com/en/sale"},
    {"brand":"Dakine",           "category":"accessories", "type":"shopify", "shopify_domain":"www.dakine.com",             "collection":"sale",              "affiliate_base":"https://www.dakine.com/collections/sale"},
    {"brand":"POC",              "category":"helmets",     "type":"shopify", "shopify_domain":"www.pocsports.com",          "collection":"ski-sale",          "affiliate_base":"https://www.pocsports.com/collections/ski-sale"},
    {"brand":"Tactics",          "category":"snowboard",   "type":"shopify", "shopify_domain":"www.tactics.com",            "collection":"sale-snowboarding", "affiliate_base":"https://www.tactics.com/sale/snowboarding"},
    {"brand":"Christy Sports",   "category":"ski",         "type":"shopify", "shopify_domain":"www.christysports.com",      "collection":"sale",              "affiliate_base":"https://www.christysports.com/sale/"},

    # ── HTML BRANDS (requests + BeautifulSoup) ────────────────────────────
    {"brand":"Salomon",    "category":"boots",       "type":"html", "urls":["https://www.salomon.com/en-us/sport/ski/outlet"],              "affiliate_base":"https://www.salomon.com/en-us/sport/ski/outlet"},
    {"brand":"K2 Skis",    "category":"ski",         "type":"html", "urls":["https://www.k2snow.com/en-us/c/alpine-ski-sale"],              "affiliate_base":"https://www.k2snow.com/en-us/c/alpine-ski-sale"},
    {"brand":"Volkl",      "category":"ski",         "type":"html", "urls":["https://www.volkl.com/en-us/sport/alpine/on-sale"],            "affiliate_base":"https://www.volkl.com/en-us/sport/alpine/on-sale"},
    {"brand":"Oakley",     "category":"goggles",     "type":"html", "urls":["https://www.oakley.com/en-us/category/snow-goggles"],          "affiliate_base":"https://www.oakley.com/en-us/category/snow-goggles"},
    {"brand":"Smith",      "category":"goggles",     "type":"html", "urls":["https://www.smithoptics.com/en-us/sale/"],                     "affiliate_base":"https://www.smithoptics.com/en-us/sale/"},
    {"brand":"Patagonia",  "category":"outerwear",   "type":"html", "urls":["https://www.patagonia.com/shop/sale/sport/skiing-snowboarding"],"affiliate_base":"https://www.patagonia.com/shop/sale/sport/skiing-snowboarding"},
    {"brand":"REI",        "category":"accessories", "type":"html", "urls":["https://www.rei.com/c/ski-gear"],                              "affiliate_base":"https://www.rei.com/c/ski-gear"},
    {"brand":"Evo",        "category":"ski",         "type":"html", "urls":["https://www.evo.com/outlet/ski"],                              "affiliate_base":"https://www.evo.com/outlet/ski"},
    {"brand":"Backcountry","category":"ski",         "type":"html", "urls":["https://www.backcountry.com/ski"],                             "affiliate_base":"https://www.backcountry.com/ski"},
]

PROMO_RE    = re.compile(r'(?:use\s+(?:code|promo)\s*[:\-]?\s*|promo\s*code[:\s]+|enter\s+code\s*)([A-Z0-9]{4,20})\b', re.IGNORECASE)
DISCOUNT_RE = re.compile(r'(?:up\s+to\s+)?(\d{1,3})\s*%\s*off|save\s+(\d{1,3})\s*%', re.IGNORECASE)
CLEAR_SIGS  = ["clearance","end of season","last chance","final sale","closeout"]
DROP_SIGS   = ["new drop","just dropped","preorder","pre-order","new arrival"]
EMAIL_SIGS  = ["email exclusive","subscribers only","newsletter exclusive"]
SALE_SIGS   = ["% off","on sale","outlet","sale","promo","savings","reduced"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

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
    log.info(f"    Shopify API: {len(products)} products in collection")
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
                except (ValueError, TypeError): pass

    if not sale_products:
        sale_products = products[:5]

    log.info(f"    {len(sale_products)} sale products found")

    best_pct = 0
    for p in sale_products:
        for v in p.get("variants", []):
            cap = v.get("compare_at_price")
            price = v.get("price")
            if cap and price:
                try:
                    cap_f, price_f = float(cap), float(price)
                    if cap_f > 0:
                        pct = round((cap_f - price_f) / cap_f * 100)
                        if pct > best_pct: best_pct = pct
                except (ValueError, TypeError): pass

    discount = f"Up to {best_pct}% off" if best_pct >= 5 else "Sale"
    titles = [p["title"] for p in sale_products[:3]]
    if titles:
        desc = f"{discount} — {', '.join(titles[:2])}" + (" + more" if len(sale_products) > 2 else "")
        if len(desc) > 130: desc = desc[:127] + "..."
    else:
        desc = f"{brand_cfg['brand']} — {discount} on selected gear"

    hot = best_pct >= 25
    deal = Deal(
        id=make_id(brand_cfg["brand"], desc), brand=brand_cfg["brand"],
        category=brand_cfg["category"],
        deal_type="clearance" if best_pct >= 40 else "active",
        description=desc, discount=discount, code=None,
        url=brand_cfg["affiliate_base"], source_url=url, hot=hot,
    )
    log.info(f"    ✓ [{deal.deal_type}] {discount} — {desc[:55]}")
    return [deal]

def scrape_shopify_fallback(brand_cfg):
    import requests
    domain = brand_cfg["shopify_domain"]
    collection = brand_cfg["collection"]
    url = f"https://{domain}/collections/{collection}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        if len(r.text) > 1000:
            desc = f"{brand_cfg['brand']} — sale items available now"
            deal = Deal(
                id=make_id(brand_cfg["brand"], desc), brand=brand_cfg["brand"],
                category=brand_cfg["category"], deal_type="active",
                description=desc, discount="Sale", code=None,
                url=brand_cfg["affiliate_base"], source_url=url, hot=False,
            )
            log.info(f"    ✓ [active] sale page confirmed")
            return [deal]
    except Exception as e:
        log.warning(f"    fallback also failed: {e}")
    return []

def scrape_html(brand_cfg):
    import requests
    from bs4 import BeautifulSoup
    deals = []
    for url in brand_cfg["urls"]:
        log.info(f"  {url}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            r.raise_for_status()
            html = r.text
        except Exception as e:
            log.warning(f"    failed: {e}"); continue

        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script","style","noscript","svg"]): t.decompose()

        blocks, seen = [], set()
        for sel in ["[class*='banner']","[class*='promo']","[class*='announcement']",
                    "[class*='sale']","[class*='offer']","[class*='deal']","[class*='discount']",
                    "[class*='bar']","[class*='strip']","header"]:
            try:
                for el in soup.select(sel)[:6]:
                    t = el.get_text(" ", strip=True)
                    if t and t not in seen and 5 < len(t) < 600: blocks.append(t); seen.add(t)
            except: continue
        for tag in soup.find_all(["h1","h2","h3","p","li","span","div","a"]):
            t = tag.get_text(" ", strip=True)
            if t and t not in seen and 5 < len(t) < 500: blocks.append(t); seen.add(t)

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

        code, skip = None, {"FREE","SALE","SAVE","DEAL","CODE","HERE","THIS","YOUR","SHOP","MORE","VIEW","PLUS"}
        for block in blocks:
            m = PROMO_RE.search(block)
            if m:
                c = m.group(1).upper()
                if c not in skip and 4 <= len(c) <= 20: code = c; break

        desc = next((re.sub(r'\s+',' ',b).strip()[:130] for b in blocks
                     if any(s in b.lower() for s in ["% off","sale","outlet","clearance","promo"]) and len(b)>15),
                    f"{brand_cfg['brand']} — {discount or 'sale'} on select products.")
        hot = bool(code) or best >= 25
        d = Deal(id=make_id(brand_cfg["brand"],desc), brand=brand_cfg["brand"],
                 category=brand_cfg["category"], deal_type=dtype, description=desc,
                 discount=discount or "Sale", code=code,
                 url=brand_cfg.get("affiliate_base",url), source_url=url, hot=hot)
        log.info(f"    ✓ [{dtype}] {discount or 'sale'} {('code:'+code) if code else ''} — {desc[:55]}")
        deals.append(d)
        time.sleep(1.5)
    return deals

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
        else: d["pulse"]=True; log.info(f"  NEW: {deal.brand} — {deal.description[:50]}")
        merged.append(d)
    merged.sort(key=lambda d:(not d["pulse"],not d["hot"],d["brand"]))
    OUTPUT_PATH.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps({"generated_at":now,"deal_count":len(merged),"brands_scanned":len(BRANDS),"deals":merged},indent=2))
    log.info(f"\n✓ Wrote {len(merged)} deals → {OUTPUT_PATH}")

def run():
    log.info("="*60)
    log.info("POWDER STASH — scraper starting")
    log.info(f"{sum(1 for b in BRANDS if b['type']=='shopify')} Shopify brands, {sum(1 for b in BRANDS if b['type']=='html')} HTML brands")
    log.info("="*60)
    previous = load_previous()
    all_deals, seen_ids = [], set()
    for b in BRANDS:
        log.info(f"\n→ {b['brand']} [{b['type']}]")
        deals = scrape_shopify(b) if b["type"] == "shopify" else scrape_html(b)
        for d in deals:
            if d.id not in seen_ids: seen_ids.add(d.id); all_deals.append(d)
        time.sleep(1)
    log.info(f"\nComplete — {len(all_deals)} deals found")
    save(all_deals, previous)

if __name__ == "__main__":
    run()
