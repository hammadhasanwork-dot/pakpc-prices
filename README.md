# PakPC Prices v2 — Full Product + Image Scraper

## Why you now get ALL products with REAL images

### The key insight: Most Pakistani shops use Shopify or WooCommerce

These platforms expose **free public APIs** that return every product — with real CDN images.

| Platform | API Endpoint | What you get |
|---|---|---|
| **Shopify** | `/products.json?limit=250&page=N` | Every product, all images, prices, stock — no auth needed |
| **WooCommerce** | `/wp-json/wc/store/v1/products?per_page=100` | Same — fully public |
| **Custom HTML** | BeautifulSoup selectors | Scraped from page HTML |

---

## Shops and their methods

| Shop | Platform | Method | Expected Products |
|---|---|---|---|
| PakByte | Shopify | `products.json` | 500–800 |
| Zestro Gaming | Shopify | `products.json` | 200–400 |
| PC Fanatics | Shopify | `products.json` | 300–500 |
| TechMatched | Shopify | `products.json` | 100–300 |
| PakDukaan | Shopify | `products.json` | 200–400 |
| TechArc | Shopify | `products.json` | 100–200 |
| ZAH Computers | WooCommerce | Store API | 300–600 |
| Al Burhan | WooCommerce | Store API | 100–300 |
| SU Tech & Games | WooCommerce | Store API | 200–400 |
| RB Tech & Games | WooCommerce | Store API | 100–300 |
| Paklap | Magento | HTML scraping | 50–150/category |
| Sigma Computers | WooCommerce | HTML scraping | 50–100/category |
| CZone | Custom | HTML scraping | 50–100/category |
| Shophive | OpenCart | HTML scraping | 50–100/category |
| IndusTech | Magento | HTML scraping | 50–100/category |

**Total: 2,000–5,000+ products with images, auto-updated every 6 hours.**

---

## Deploy in 5 Steps (free, ~10 minutes)

### 1. Create GitHub repo
- Go to github.com → New Repository → name: `pakpc-prices` → **Public** → Create

### 2. Upload files
Upload everything in this folder to the repo root.

### 3. Enable GitHub Pages
Settings → Pages → Source: Deploy from branch → Branch: `main`, Folder: `/` → Save

Your site: `https://YOUR_USERNAME.github.io/pakpc-prices`

### 4. Run first scrape
Actions tab → "Scrape Prices" → Run workflow → Wait ~5 minutes

### 5. Done!
The site now shows real data. The workflow runs every 6 hours automatically.

---

## How images work

**Shopify shops**: Images come from Shopify's CDN (cdn.shopify.com). Each product has 1–10 photos. The scraper takes the first one and resizes it to 400px for performance.

**WooCommerce shops**: Images come from the shop's WordPress media library. Usually 1 image per product.

**HTML-scraped shops**: Images are scraped from the `<img>` tags in product listings.

**Fallback**: If an image fails to load (404, removed, etc.), the website automatically shows a category emoji instead. You'll never see broken image icons.

---

## What to do if a shop's scraper stops working

Shops occasionally redesign their website. For:

- **Shopify shops**: Almost never breaks — the API is stable
- **WooCommerce shops**: Rarely breaks
- **HTML-scraped shops**: May need selector updates

To fix HTML selectors, inspect the shop's page in Chrome → right-click product name → Inspect → find CSS class → update in `scripts/scraper.py`.

---

## Adding a new shop

### If it's Shopify:
```python
{
    "id": "newshop",
    "name": "New Shop",
    "url": "https://newshop.pk",
    "city": "Karachi",
    "method": "shopify",
    "categories": None,  # None = all categories
},
```

### If it's WooCommerce:
```python
{
    "id": "newshop",
    "name": "New Shop",
    "url": "https://newshop.pk",
    "city": "Lahore",
    "method": "woo",
},
```

To check if a site is Shopify: visit `https://theshop.pk/products.json` — if you see JSON, it's Shopify.
To check WooCommerce: visit `https://theshop.pk/wp-json/wc/store/v1/products` — if you see JSON, it's WooCommerce.
