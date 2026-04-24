#!/usr/bin/env python3
"""
PakPC Price Tracker - Master Scraper
====================================
Strategy per shop:
  - Shopify stores  → /products.json?limit=250&page=N  (free public API, real images)
  - WooCommerce     → /wp-json/wc/store/products?per_page=100&page=N (public store API)
  - Custom/HTML     → requests + BeautifulSoup with shop-specific selectors

Run:  python scripts/scraper.py
Output: data/prices.json  +  data/price_history.json
"""

import json, time, re, os, hashlib, logging, random
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

try:
    import requests
    from bs4 import BeautifulSoup
    LIBS_OK = True
except ImportError:
    LIBS_OK = False
    log.warning("requests/bs4 missing – pip install requests beautifulsoup4 lxml")

# ── CONSTANTS ──────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
SESSION = None

# Mapping product title keywords → category
CAT_MAP = {
    "rtx": "gpu", "radeon": "gpu", "rx 6": "gpu", "rx 7": "gpu", "rx 9": "gpu",
    "gtx": "gpu", "geforce": "gpu", "graphic card": "gpu", "graphics card": "gpu",
    "ryzen": "cpu", "core i": "cpu", "i3-": "cpu", "i5-": "cpu", "i7-": "cpu",
    "i9-": "cpu", "processor": "cpu", "threadripper": "cpu",
    "ddr4": "ram", "ddr5": "ram", "ram": "ram", "dimm": "ram",
    "ssd": "storage", "nvme": "storage", "m.2": "storage", "hard drive": "storage",
    "hdd": "storage", "seagate": "storage", "western digital": "storage",
    "monitor": "monitor", "display": "monitor", " hz": "monitor",
    "keyboard": "keyboard", "keycap": "keyboard", "mechanical": "keyboard",
    "mouse": "mouse", "gaming mouse": "mouse",
    "headset": "headset", "headphone": "headset", "earphone": "headset",
    "aio": "cooler", "cooler": "cooler", "cooling": "cooler", "fan": "cooler",
    "psu": "psu", "power supply": "psu", " watt": "psu",
    "case": "case", "casing": "case", "tower": "case",
    "motherboard": "motherboard", "mobo": "motherboard", "b650": "motherboard",
    "z790": "motherboard", "b760": "motherboard", "x670": "motherboard",
}

BRAND_LIST = [
    "ASUS","MSI","Gigabyte","ASRock","EVGA","Zotac","ZOTAC","Sapphire","XFX","PowerColor",
    "Samsung","WD","Seagate","Kingston","Crucial","Corsair","G.Skill","HyperX","TeamGroup",
    "AMD","Intel","NVIDIA","Logitech","Razer","SteelSeries","HyperX","Cooler Master",
    "NZXT","be quiet!","Lian Li","Fractal","Phanteks","Thermaltake","DeepCool","Deepcool",
    "Thermalright","ID-Cooling","Arctic","Noctua","Redragon","Fantech","A4Tech","Dareu",
    "T-DAGGER","PNY","Inno3D","Palit","Manli","INNO3D","MaxSUN","EASE",
]

OUT_FILE = "data/prices.json"
HIST_FILE = "data/price_history.json"


# ── HELPERS ────────────────────────────────────────────────────────────────────
def get_session():
    global SESSION
    if SESSION is None:
        SESSION = requests.Session()
        SESSION.headers.update(HEADERS)
    return SESSION

def safe_get(url, timeout=18, retries=2):
    s = get_session()
    for attempt in range(retries):
        try:
            r = s.get(url, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            log.warning(f"  attempt {attempt+1} failed for {url}: {e}")
            time.sleep(3)
    return None

def parse_pkr(text):
    """Extract integer price from strings like 'Rs. 115,000' / 'PKR 84,999'"""
    if not text:
        return None
    nums = re.findall(r"[\d,]+", str(text).replace("\u00a0",""))
    for n in nums:
        clean = n.replace(",","")
        if 3 <= len(clean) <= 8:
            try:
                v = int(clean)
                if 500 <= v <= 50_000_000:   # realistic PKR range
                    return v
            except ValueError:
                pass
    return None

def guess_category(title):
    tl = title.lower()
    for kw, cat in CAT_MAP.items():
        if kw in tl:
            return cat
    return "other"

def guess_brand(title):
    tu = title.upper()
    for b in BRAND_LIST:
        if b.upper() in tu:
            return b
    return title.split()[0] if title else ""

def make_id(shop_id, title):
    h = hashlib.md5(f"{shop_id}:{title.lower().strip()}".encode()).hexdigest()[:8]
    return f"{shop_id}_{h}"

def polite_delay(mn=1.5, mx=3.5):
    time.sleep(random.uniform(mn, mx))


# ── SHOPIFY SCRAPER ────────────────────────────────────────────────────────────
def scrape_shopify(shop_id, base_url, allowed_categories=None):
    """
    Uses Shopify's public /products.json endpoint.
    Returns all products with REAL images from the store CDN.
    Handles pagination automatically.
    """
    products = []
    page = 1
    per_page = 250   # Shopify max

    while True:
        url = f"{base_url.rstrip('/')}/products.json?limit={per_page}&page={page}"
        log.info(f"  Shopify page {page}: {url}")
        r = safe_get(url)
        if not r:
            break
        try:
            data = r.json()
        except Exception as e:
            log.warning(f"  JSON parse error: {e}")
            break

        batch = data.get("products", [])
        if not batch:
            break

        for p in batch:
            title = p.get("title", "")
            if not title:
                continue

            cat = guess_category(title)
            if allowed_categories and cat not in allowed_categories:
                continue

            # Price: use first available variant
            price = None
            for v in p.get("variants", []):
                raw = v.get("price") or v.get("compare_at_price")
                price = parse_pkr(raw)
                if price:
                    break

            if not price:
                continue

            # Compare-at price (original before sale)
            old_price = None
            for v in p.get("variants", []):
                cap = v.get("compare_at_price")
                if cap:
                    old_price = parse_pkr(cap)
                    if old_price and old_price <= price:
                        old_price = None
                    break

            # Real product image from Shopify CDN
            img = None
            images = p.get("images", [])
            if images:
                src = images[0].get("src","")
                # Use medium size for performance
                img = re.sub(r"_\d+x\d+\.", "_400x.", src) if src else src

            # Stock status
            in_stock = any(
                v.get("available", True) for v in p.get("variants", [])
            )
            low_stock = in_stock and all(
                (v.get("inventory_quantity") or 99) <= 3
                for v in p.get("variants", [])
            )

            handle = p.get("handle","")
            product_url = f"{base_url.rstrip('/')}/products/{handle}" if handle else base_url

            products.append({
                "id": make_id(shop_id, title),
                "name": title[:90],
                "brand": guess_brand(title),
                "category": cat,
                "price": price,
                "oldPrice": old_price,
                "inStock": in_stock,
                "lowStock": low_stock,
                "img": img,
                "url": product_url,
            })

        log.info(f"    → {len(batch)} fetched, {len(products)} total so far")

        if len(batch) < per_page:
            break   # last page
        page += 1
        polite_delay(1, 2.5)

    return products


# ── WOOCOMMERCE SCRAPER ────────────────────────────────────────────────────────
def scrape_woo(shop_id, base_url, allowed_categories=None):
    """
    Uses WooCommerce Store API (v1) – public, no auth required.
    Endpoint: /wp-json/wc/store/v1/products
    """
    products = []
    page = 1
    per_page = 100

    while True:
        url = f"{base_url.rstrip('/')}/wp-json/wc/store/v1/products?per_page={per_page}&page={page}"
        log.info(f"  WooCommerce page {page}: {url}")
        r = safe_get(url)
        if not r:
            break
        try:
            batch = r.json()
        except Exception:
            break

        if not batch or not isinstance(batch, list):
            break

        for p in batch:
            title = p.get("name","")
            if not title:
                continue

            cat = guess_category(title)
            if allowed_categories and cat not in allowed_categories:
                continue

            price = parse_pkr(p.get("prices",{}).get("price"))
            if not price:
                price = parse_pkr(p.get("price",""))
            if not price:
                continue

            old_raw = p.get("prices",{}).get("regular_price")
            old_price = parse_pkr(old_raw) if old_raw else None
            if old_price and old_price <= price:
                old_price = None

            img = None
            imgs = p.get("images",[])
            if imgs:
                img = imgs[0].get("src") or imgs[0].get("thumbnail")

            in_stock = p.get("is_in_stock", True)
            slug = p.get("slug","")
            product_url = f"{base_url.rstrip('/')}/product/{slug}" if slug else base_url

            products.append({
                "id": make_id(shop_id, title),
                "name": title[:90],
                "brand": guess_brand(title),
                "category": cat,
                "price": price,
                "oldPrice": old_price,
                "inStock": in_stock,
                "lowStock": False,
                "img": img,
                "url": product_url,
            })

        log.info(f"    → {len(batch)} fetched, {len(products)} total so far")
        if len(batch) < per_page:
            break
        page += 1
        polite_delay(1, 2)

    return products


# ── HTML SCRAPER (generic fallback) ───────────────────────────────────────────
def scrape_html(shop_id, pages_config):
    """
    pages_config: list of (category, url, selectors_dict)
    selectors_dict keys: card, name, price, img, link, stock
    """
    products = []

    for category, url, sel in pages_config:
        log.info(f"  HTML scraping {category}: {url}")
        r = safe_get(url)
        if not r:
            continue
        soup = BeautifulSoup(r.text, "lxml")

        # Try multiple card selectors
        cards = []
        for s in (sel.get("card","") or "").split("|"):
            cards = soup.select(s.strip())
            if cards:
                break

        log.info(f"    found {len(cards)} cards")

        for card in cards[:50]:  # cap per page
            try:
                # Name
                name_el = None
                for s in (sel.get("name","") or "").split("|"):
                    name_el = card.select_one(s.strip())
                    if name_el:
                        break
                if not name_el:
                    continue
                name = name_el.get_text(" ", strip=True)[:90]
                if len(name) < 4:
                    continue

                # Price
                price_el = None
                for s in (sel.get("price","") or "").split("|"):
                    price_el = card.select_one(s.strip())
                    if price_el:
                        break
                if not price_el:
                    continue
                price = parse_pkr(price_el.get_text(strip=True))
                if not price:
                    continue

                # Image
                img = None
                for s in (sel.get("img","") or "").split("|"):
                    img_el = card.select_one(s.strip())
                    if img_el:
                        img = img_el.get("src") or img_el.get("data-src") or img_el.get("data-lazy-src")
                        if img and img.startswith("//"):
                            img = "https:" + img
                        elif img and img.startswith("/"):
                            img = urljoin(url, img)
                        break

                # Link
                product_url = url
                for s in (sel.get("link","") or "").split("|"):
                    link_el = card.select_one(s.strip())
                    if link_el:
                        href = link_el.get("href","")
                        if href:
                            product_url = urljoin(url, href)
                        break

                # Stock
                in_stock = True
                stock_text = card.get_text(" ", strip=True).lower()
                if any(x in stock_text for x in ["out of stock","sold out","unavailable"]):
                    in_stock = False

                products.append({
                    "id": make_id(shop_id, name),
                    "name": name,
                    "brand": guess_brand(name),
                    "category": category,
                    "price": price,
                    "oldPrice": None,
                    "inStock": in_stock,
                    "lowStock": False,
                    "img": img,
                    "url": product_url,
                })
            except Exception as e:
                log.debug(f"    card error: {e}")
                continue

        polite_delay(2, 4)

    return products


# ── SHOP DEFINITIONS ──────────────────────────────────────────────────────────
# Each entry: (id, name, url, city, method, config)
# method: "shopify" | "woo" | "html"
SHOPS_CONFIG = [

    # ── SHOPIFY STORES (public products.json – all products + real images) ────
    {
        "id": "pakbyte",
        "name": "PakByte",
        "url": "https://www.pakbyte.pk",
        "city": "Karachi",
        "method": "shopify",
        "categories": ["gpu","cpu","ram","storage","monitor","keyboard","mouse","headset","cooler","psu","case","motherboard"],
    },
    {
        "id": "zestro",
        "name": "Zestro Gaming",
        "url": "https://zestrogaming.com",
        "city": "Rawalpindi / Karachi",
        "method": "shopify",
        "categories": ["gpu","cpu","ram","storage","monitor","keyboard","mouse","headset","cooler","psu","case","motherboard"],
    },
    {
        "id": "pcfanatics",
        "name": "PC Fanatics",
        "url": "https://pcfanatics.pk",
        "city": "Lahore",
        "method": "shopify",
        "categories": ["gpu","cpu","ram","storage","monitor","keyboard","mouse","headset","cooler","psu","case","motherboard"],
    },
    {
        "id": "techmatched",
        "name": "TechMatched",
        "url": "https://techmatched.pk",
        "city": "Nationwide",
        "method": "shopify",
        "categories": ["gpu","cpu","ram","storage","monitor","keyboard","mouse","headset","cooler"],
    },
    {
        "id": "pakdukaan",
        "name": "PakDukaan",
        "url": "https://www.pakdukaan.pk",
        "city": "Nationwide",
        "method": "shopify",
        "categories": ["gpu","cpu","ram","storage","keyboard","mouse","headset"],
    },
    {
        "id": "techarc",
        "name": "TechArc",
        "url": "https://techarc.pk",
        "city": "Nationwide",
        "method": "shopify",
        "categories": ["gpu","cpu","ram","storage","monitor","keyboard","mouse"],
    },

    # ── WOOCOMMERCE STORES ────────────────────────────────────────────────────
    {
        "id": "zah",
        "name": "ZAH Computers",
        "url": "https://zahcomputers.pk",
        "city": "Karachi",
        "method": "woo",
        "categories": ["gpu","cpu","ram","storage","keyboard","mouse","headset","cooler","motherboard"],
    },
    {
        "id": "alburhan",
        "name": "Al Burhan Computers",
        "url": "https://alb.net.pk",
        "city": "Karachi (Hyderi)",
        "method": "woo",
        "categories": ["gpu","cpu","ram","storage","cooler","psu","motherboard"],
    },
    {
        "id": "sutech",
        "name": "SU Tech & Games",
        "url": "https://sutechngames.com",
        "city": "Karachi",
        "method": "woo",
        "categories": ["gpu","cpu","ram","storage","keyboard","mouse","headset","cooler","psu","case","motherboard"],
    },
    {
        "id": "rbtechgames",
        "name": "RB Tech & Games",
        "url": "https://rbtechngames.com",
        "city": "Karachi",
        "method": "woo",
        "categories": ["gpu","cpu","ram","storage","keyboard","mouse"],
    },

    # ── HTML SCRAPING (custom selectors per site) ─────────────────────────────
    {
        "id": "paklap",
        "name": "Paklap",
        "url": "https://www.paklap.pk",
        "city": "Nationwide",
        "method": "html",
        "pages": [
            ("gpu",  "https://www.paklap.pk/accessories/computer-accessories/graphic-cards.html", {
                "card":  ".product-item|.item",
                "name":  ".product-name|.name|h2|h3",
                "price": ".price|.product-price",
                "img":   "img.product-image|img",
                "link":  "a.product-item-link|a",
            }),
            ("cpu",  "https://www.paklap.pk/accessories/computer-accessories/processors.html", {
                "card":  ".product-item|.item",
                "name":  ".product-name|h2",
                "price": ".price",
                "img":   "img",
                "link":  "a.product-item-link|a",
            }),
            ("ram",  "https://www.paklap.pk/accessories/computer-accessories/memory-ram.html", {
                "card":  ".product-item|.item",
                "name":  ".product-name|h2",
                "price": ".price",
                "img":   "img",
                "link":  "a",
            }),
            ("storage", "https://www.paklap.pk/accessories/computer-accessories/solid-state-drives.html", {
                "card":  ".product-item|.item",
                "name":  ".product-name|h2",
                "price": ".price",
                "img":   "img",
                "link":  "a",
            }),
            ("monitor", "https://www.paklap.pk/accessories/computer-accessories/monitors.html", {
                "card":  ".product-item|.item",
                "name":  ".product-name|h2",
                "price": ".price",
                "img":   "img",
                "link":  "a",
            }),
            ("keyboard", "https://www.paklap.pk/accessories/computer-accessories/keyboard.html", {
                "card":  ".product-item|.item",
                "name":  ".product-name|h2",
                "price": ".price",
                "img":   "img",
                "link":  "a",
            }),
            ("mouse", "https://www.paklap.pk/accessories/computer-accessories/mouse.html", {
                "card":  ".product-item|.item",
                "name":  ".product-name|h2",
                "price": ".price",
                "img":   "img",
                "link":  "a",
            }),
        ],
    },
    {
        "id": "sigma",
        "name": "Sigma Computers",
        "url": "https://www.sigma-computers.com",
        "city": "Karachi",
        "method": "html",
        "pages": [
            ("gpu",  "https://www.sigma-computers.com/graphic-cards/", {
                "card":  "li.product|.woocommerce-LoopProduct-link|.product",
                "name":  ".woocommerce-loop-product__title|h2",
                "price": ".price|.woocommerce-Price-amount",
                "img":   "img",
                "link":  "a.woocommerce-LoopProduct-link|a",
            }),
            ("cpu",  "https://www.sigma-computers.com/processors/", {
                "card":  "li.product|.product",
                "name":  ".woocommerce-loop-product__title|h2",
                "price": ".price|.woocommerce-Price-amount",
                "img":   "img",
                "link":  "a",
            }),
            ("ram",  "https://www.sigma-computers.com/memory/", {
                "card":  "li.product|.product",
                "name":  "h2",
                "price": ".price|.woocommerce-Price-amount",
                "img":   "img",
                "link":  "a",
            }),
            ("motherboard", "https://www.sigma-computers.com/motherboards/", {
                "card":  "li.product|.product",
                "name":  "h2",
                "price": ".price|.woocommerce-Price-amount",
                "img":   "img",
                "link":  "a",
            }),
            ("cooler", "https://www.sigma-computers.com/cpu-coolers/", {
                "card":  "li.product|.product",
                "name":  "h2",
                "price": ".price|.woocommerce-Price-amount",
                "img":   "img",
                "link":  "a",
            }),
        ],
    },
    {
        "id": "czone",
        "name": "CZone",
        "url": "https://www.czone.com.pk",
        "city": "Karachi",
        "method": "html",
        "pages": [
            ("gpu", "https://www.czone.com.pk/graphic-cards-price-in-pakistan/ct-2004.aspx", {
                "card":  ".product-box|.product|div[class*='product']",
                "name":  ".product-name|h3|h4|[class*='name']",
                "price": "[class*='price']|.price",
                "img":   "img",
                "link":  "a",
            }),
            ("cpu", "https://www.czone.com.pk/processors-price-in-pakistan/ct-2003.aspx", {
                "card":  ".product-box|.product",
                "name":  ".product-name|h3",
                "price": "[class*='price']",
                "img":   "img",
                "link":  "a",
            }),
            ("ram", "https://www.czone.com.pk/memory-ram-price-in-pakistan/ct-2008.aspx", {
                "card":  ".product-box|.product",
                "name":  ".product-name|h3",
                "price": "[class*='price']",
                "img":   "img",
                "link":  "a",
            }),
            ("storage", "https://www.czone.com.pk/solid-state-drives-price-in-pakistan/ct-2026.aspx", {
                "card":  ".product-box|.product",
                "name":  ".product-name|h3",
                "price": "[class*='price']",
                "img":   "img",
                "link":  "a",
            }),
        ],
    },
    {
        "id": "shophive",
        "name": "Shophive",
        "url": "https://www.shophive.com",
        "city": "Lahore",
        "method": "html",
        "pages": [
            ("gpu", "https://www.shophive.com/graphic-cards", {
                "card":  ".product-layout|.product-thumb|[class*='product']",
                "name":  ".name|h4|h3",
                "price": ".price|[class*='price']",
                "img":   "img",
                "link":  "a",
            }),
            ("cpu", "https://www.shophive.com/processors", {
                "card":  ".product-layout|.product-thumb",
                "name":  ".name|h4",
                "price": ".price",
                "img":   "img",
                "link":  "a",
            }),
            ("monitor", "https://www.shophive.com/monitors", {
                "card":  ".product-layout|.product-thumb",
                "name":  ".name|h4",
                "price": ".price",
                "img":   "img",
                "link":  "a",
            }),
            ("keyboard", "https://www.shophive.com/keyboard", {
                "card":  ".product-layout|.product-thumb",
                "name":  ".name|h4",
                "price": ".price",
                "img":   "img",
                "link":  "a",
            }),
        ],
    },
    {
        "id": "industech",
        "name": "IndusTech",
        "url": "https://www.industech.pk",
        "city": "Nationwide",
        "method": "html",
        "pages": [
            ("gpu", "https://www.industech.pk/graphic-cards", {
                "card":  ".product-item-info|.item|[class*='product']",
                "name":  ".product-name|.product-item-name|h2|h3",
                "price": ".price|[class*='price']",
                "img":   "img.product-image-photo|img",
                "link":  "a.product-item-link|a",
            }),
            ("cpu", "https://www.industech.pk/processors", {
                "card":  ".product-item-info|.item",
                "name":  ".product-name|.product-item-name|h2",
                "price": ".price",
                "img":   "img",
                "link":  "a",
            }),
            ("storage", "https://www.industech.pk/solid-state-drives", {
                "card":  ".product-item-info|.item",
                "name":  ".product-item-name|h2",
                "price": ".price",
                "img":   "img",
                "link":  "a",
            }),
        ],
    },
]


# ── PRICE HISTORY ─────────────────────────────────────────────────────────────
def load_history():
    if os.path.exists(HIST_FILE):
        try:
            with open(HIST_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_history(h):
    os.makedirs("data", exist_ok=True)
    with open(HIST_FILE, "w") as f:
        json.dump(h, f)

def enrich(products, history):
    out = []
    for p in products:
        pid = p["id"]
        hist = history.get(pid, [])
        cur = p["price"]

        if hist and not p.get("oldPrice"):
            last = hist[-1]
            if last != cur:
                p["oldPrice"] = last
        if p.get("oldPrice") and p["oldPrice"] == cur:
            p["oldPrice"] = None

        hist.append(cur)
        history[pid] = hist[-60:]  # keep 60 data points
        p["history"] = history[pid][-12:]  # send last 12 to frontend
        out.append(p)
    return out


# ── DEDUP ─────────────────────────────────────────────────────────────────────
def dedup(products):
    seen = {}
    for p in products:
        if p["id"] not in seen:
            seen[p["id"]] = p
    return list(seen.values())


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    if not LIBS_OK:
        log.error("Install deps: pip install requests beautifulsoup4 lxml")
        create_demo_json()
        return

    os.makedirs("data", exist_ok=True)
    history = load_history()
    output = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "shops": [],
    }
    total = 0

    for shop in SHOPS_CONFIG:
        sid = shop["id"]
        log.info(f"\n{'='*50}")
        log.info(f"  {shop['name']}  [{shop['method'].upper()}]  {shop['url']}")
        log.info(f"{'='*50}")

        raw = []
        try:
            if shop["method"] == "shopify":
                raw = scrape_shopify(sid, shop["url"], shop.get("categories"))
            elif shop["method"] == "woo":
                raw = scrape_woo(sid, shop["url"], shop.get("categories"))
            elif shop["method"] == "html":
                raw = scrape_html(sid, shop.get("pages", []))
        except Exception as e:
            log.error(f"  FAILED: {e}")

        raw = dedup(raw)
        enriched = enrich(raw, history)

        # Filter out products with no name or price
        enriched = [p for p in enriched if p["name"] and p["price"]]

        log.info(f"  ✓ {len(enriched)} products scraped for {shop['name']}")
        total += len(enriched)

        output["shops"].append({
            "id": sid,
            "name": shop["name"],
            "url": shop["url"],
            "city": shop.get("city",""),
            "verified": True,
            "products": enriched,
        })

        polite_delay(3, 6)

    save_history(history)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(f"\n✅  Done — {total} products across {len(output['shops'])} shops → {OUT_FILE}")


# ── DEMO FALLBACK ─────────────────────────────────────────────────────────────
def create_demo_json():
    """Writes a minimal demo prices.json so the website loads even without scraping."""
    demo = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "shops": [
            {
                "id":"pakbyte","name":"PakByte","url":"https://www.pakbyte.pk","city":"Karachi","verified":True,
                "products":[
                    {"id":"pb_gpu1","name":"ZOTAC GAMING GeForce RTX 4060 8GB Twin Edge OC","brand":"ZOTAC","category":"gpu","price":115000,"oldPrice":122000,"inStock":True,"lowStock":False,"img":"https://cdn.shopify.com/s/files/1/0533/2089/files/rtx4060.jpg","url":"https://www.pakbyte.pk/products/rtx-4060","history":[125000,122000,118000,115000]},
                    {"id":"pb_cpu1","name":"AMD Ryzen 5 5600X Desktop Processor","brand":"AMD","category":"cpu","price":36000,"oldPrice":42000,"inStock":True,"lowStock":False,"img":"https://cdn.shopify.com/s/files/1/0533/2089/files/ryzen5.jpg","url":"https://www.pakbyte.pk/products/ryzen-5-5600x","history":[42000,39000,37000,36000]},
                ]
            }
        ]
    }
    os.makedirs("data", exist_ok=True)
    with open(OUT_FILE, "w") as f:
        json.dump(demo, f, indent=2)
    log.info(f"Demo JSON written to {OUT_FILE}")


if __name__ == "__main__":
    main()
