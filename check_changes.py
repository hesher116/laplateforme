# -*- coding: utf-8 -*-
"""
Laplateforme.com Change Detector

Detects changes in product catalog:
- New products added
- Products removed
- Price changes
"""

import asyncio
from playwright.async_api import async_playwright
import csv
import json
from pathlib import Path
from datetime import datetime
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class ChangeDetector:
    def __init__(self, existing_dir="output/laplateforme", output_dir="output/changes"):
        self.existing_dir = Path(existing_dir)
        self.output_dir = Path(output_dir)
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.changes_file = self.output_dir / "changes.csv"
        self.log_file = self.output_dir / "changes.log"
        
        self.existing_products = {}  # product_id -> product_data
        self.current_products = {}  # product_id -> product_data
        self.changes = []  # List of changes
        
        self.new_products = []
        self.removed_products = []
        self.price_changes = []
        
    def log(self, msg):
        """Log message to console and file with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {msg}"
        print(log_msg, flush=True)
        sys.stdout.flush()
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + '\n')
    
    def load_existing_products(self):
        """Load existing products from previous scraping"""
        existing_csv = self.existing_dir / "products.csv"
        
        if not existing_csv.exists():
            self.log("⚠️ No existing products.csv found")
            return
        
        try:
            # Read file content and handle BOM
            with open(existing_csv, 'rb') as f:
                raw_content = f.read()
                # Remove BOM if present
                if raw_content.startswith(b'\xef\xbb\xbf'):
                    raw_content = raw_content[3:]
                content = raw_content.decode('utf-8')
            
            # Parse CSV manually to handle BOM in headers
            import io
            csv_file = io.StringIO(content)
            reader = csv.DictReader(csv_file, delimiter=';')
            
            # Clean fieldnames - remove BOM and any invisible characters
            if reader.fieldnames:
                original_fieldnames = list(reader.fieldnames)
                cleaned_fieldnames = []
                for field in original_fieldnames:
                    # Remove BOM, strip whitespace and non-printable chars
                    clean = field.lstrip('\ufeff').lstrip('?').strip()
                    clean = ''.join(c for c in clean if c.isprintable() or c in ('_', '-'))
                    cleaned_fieldnames.append(clean)
                
                # Update reader's fieldnames
                reader.fieldnames = cleaned_fieldnames
            else:
                self.log("⚠️ No fieldnames found in CSV")
                return
            
            row_count = 0
            for row in reader:
                # Skip empty rows
                if not row or not any(str(v).strip() for v in row.values() if v):
                    continue
                
                # Get product_id - should now work with cleaned fieldnames
                product_id = str(row.get('product_id', '')).strip()
                
                if product_id:
                    # Convert price strings with comma to float
                    price_str = str(row.get('price', '')).replace(',', '.').strip()
                    price_ht_str = str(row.get('product_unitprice_ht', '')).replace(',', '.').strip()
                    
                    try:
                        price = float(price_str) if price_str and price_str != '' else 0.0
                    except (ValueError, TypeError):
                        price = 0.0
                    
                    try:
                        price_ht = float(price_ht_str) if price_ht_str and price_ht_str != '' else 0.0
                    except (ValueError, TypeError):
                        price_ht = 0.0
                    
                    # Get all fields directly - reader now uses cleaned fieldnames
                    def get_field(name):
                        return str(row.get(name, '')).strip()
                    
                    self.existing_products[product_id] = {
                        'product_id': product_id,
                        'name': get_field('name'),
                        'url': get_field('url'),
                        'price': price,
                        'product_unitprice_ht': price_ht,
                        'brand': get_field('brand'),
                        'sku': get_field('sku'),
                        'category': get_field('category')
                    }
                    row_count += 1
            
            self.log(f"✓ Loaded {len(self.existing_products)} existing products from {row_count} rows processed")
        except Exception as e:
            self.log(f"✗ Error loading existing products: {e}")
            import traceback
            self.log(f"  Details: {traceback.format_exc()[:200]}")
    
    async def scrape_current_product(self, page, product_url):
        """Scrape single product to get current data"""
        try:
            import re
            match = re.search(r'/catalogue/produit/(\d+)', product_url)
            if not match:
                return None
            
            product_id = match.group(1)
            
            await page.goto(product_url, wait_until='domcontentloaded', timeout=5000)
            await asyncio.sleep(0.5)
            
            data_layer = await page.evaluate('() => window.dataLayer')
            if not data_layer:
                return None
            
            # Merge dataLayer
            product_data = {}
            for item in data_layer:
                if isinstance(item, dict):
                    product_data.update(item)
            
            # Extract category from breadcrumbs
            category_name = ''
            try:
                breadcrumbs = await page.evaluate('''() => {
                    const breadcrumbs = [];
                    const items = document.querySelectorAll('.breadcrumb a, nav[aria-label*="breadcrumb"] a, ol.breadcrumb a');
                    items.forEach(item => {
                        if (item.textContent.trim()) breadcrumbs.push(item.textContent.trim());
                    });
                    return breadcrumbs;
                }''')
                if breadcrumbs and len(breadcrumbs) > 1:
                    category_name = breadcrumbs[-1]
            except:
                pass
            
            ecommerce_data = product_data.get('ecommerce', {})
            price_main = ecommerce_data.get('value', product_data.get('price', 0))
            price_ht = product_data.get('product_unitprice_ht', 0)
            
            try:
                price_main = float(price_main) if price_main else 0.0
            except:
                price_main = 0.0
            
            try:
                price_ht = float(price_ht) if price_ht else 0.0
            except:
                price_ht = 0.0
            
            # Get category - prefer dataLayer, then breadcrumbs
            category = product_data.get('product_category', '') or category_name or ''
            
            return {
                'product_id': product_id,
                'name': product_data.get('product_name', ''),
                'url': product_url,
                'price': price_main,
                'product_unitprice_ht': price_ht,
                'brand': product_data.get('product_brand', ''),
                'sku': product_data.get('product_sku', product_id),
                'category': category
            }
        except Exception as e:
            return None
    
    async def check_changes(self):
        """Main function to check for changes"""
        start_time = datetime.now()
        
        self.log("="*80)
        self.log("🔍 LAPLATEFORME.COM - CHANGE DETECTOR 🔍")
        self.log("="*80)
        self.log(f"Existing products: {self.existing_dir}")
        self.log(f"Output: {self.output_dir}")
        self.log("")
        
        # Load existing products
        self.load_existing_products()
        
        if not self.existing_products:
            self.log("⚠️ No existing products to compare. Run full scraper first.")
            return
        
        self.log("Scanning current catalog...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
            
            # Get all categories
            finder_page = await context.new_page()
            try:
                await finder_page.goto('https://www.laplateforme.com/', wait_until='networkidle', timeout=30000)
                await asyncio.sleep(3)  # Wait for Angular.js to render
                
                # Scroll to load lazy content
                await finder_page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(1)
                await finder_page.evaluate('window.scrollTo(0, 0)')
                await asyncio.sleep(1)
                
                links = await finder_page.query_selector_all('a[href*="/catalogue/categorie/"]')
                categories = []
                for link in links:
                    href = await link.get_attribute('href')
                    if href and '/catalogue/categorie/' in href:
                        if not href.startswith('http'):
                            href = 'https://www.laplateforme.com' + href
                        categories.append(href)
                
                categories = list(set(categories))
                if len(categories) == 0:
                    self.log("⚠️ No categories found, trying alternative method...")
                    await asyncio.sleep(3)
                    links = await finder_page.query_selector_all('a[href*="/catalogue/categorie/"]')
                    for link in links:
                        href = await link.get_attribute('href')
                        if href and '/catalogue/categorie/' in href:
                            if not href.startswith('http'):
                                href = 'https://www.laplateforme.com' + href
                            categories.append(href)
                    categories = list(set(categories))
                
                self.log(f"Found {len(categories)} categories to check\n")
            finally:
                await finder_page.close()
            
            # Scan products from categories
            product_finder = await context.new_page()
            scraper_page = await context.new_page()
            
            try:
                current_product_urls = set()
                
                for cat_i, cat_url in enumerate(categories, 1):
                    self.log(f"{'='*80}")
                    self.log(f"[Category {cat_i}/{len(categories)}]")
                    self.log(f"{cat_url}")
                    self.log(f"{'='*80}")
                    
                    try:
                        await product_finder.goto(cat_url, wait_until='domcontentloaded', timeout=12000)
                        await asyncio.sleep(1.0)
                        await product_finder.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        await asyncio.sleep(0.8)
                        
                        page_num = 1
                        seen_on_page = set()
                        products_in_cat = 0
                        
                        while True:
                            links = await product_finder.query_selector_all('a[href*="/catalogue/produit/"]')
                            
                            for link in links:
                                href = await link.get_attribute('href')
                                if href and '/catalogue/produit/' in href:
                                    import re
                                    match = re.search(r'/catalogue/produit/(\d+)', href)
                                    if match:
                                        product_id = match.group(1)
                                        
                                        if product_id not in seen_on_page:
                                            seen_on_page.add(product_id)
                                            products_in_cat += 1
                                            if not href.startswith('http'):
                                                href = 'https://www.laplateforme.com' + href
                                            current_product_urls.add(href)
                            
                            # Next page
                            has_next = await product_finder.evaluate('''() => {
                                const btn = Array.from(document.querySelectorAll('[ng-click="nextPage()"]'))
                                    .find(el => el.offsetParent !== null);
                                if (btn) { btn.click(); return true; }
                                return false;
                            }''')
                            
                            if has_next:
                                try:
                                    await product_finder.wait_for_load_state('domcontentloaded', timeout=10000)
                                except:
                                    pass
                                await asyncio.sleep(0.8)
                                await product_finder.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                                await asyncio.sleep(0.7)
                                page_num += 1
                            else:
                                break
                        
                        self.log(f"  → Found {products_in_cat} products in {page_num} pages")
                        
                    except Exception as e:
                        self.log(f"  ✗ ERROR: {str(e)[:60]}")
                        continue
                
                self.log(f"\n✓ Scanned {len(current_product_urls)} current products")
                
                # Scrape products to get current data
                self.log(f"\nScraping product details...")
                total_urls = len(current_product_urls)
                
                for i, url in enumerate(current_product_urls, 1):
                    product = await self.scrape_current_product(scraper_page, url)
                    if product:
                        self.current_products[product['product_id']] = product
                    
                    if i % 100 == 0:
                        self.log(f"  Scraped {i}/{total_urls} products...")
                    elif i == total_urls:
                        self.log(f"  ✓ Scraped all {total_urls} products")
                
            finally:
                await product_finder.close()
                await scraper_page.close()
                await context.close()
                await browser.close()
        
        # Analyze changes
        self.log(f"\nAnalyzing changes...")
        self._analyze_changes()
        
        # Save results
        self._save_changes()
        
        # Summary
        duration = (datetime.now() - start_time).total_seconds()
        self.log("\n" + "="*80)
        self.log("🎉 CHANGE DETECTION COMPLETE! 🎉")
        self.log("="*80)
        self.log(f"New products:      {len(self.new_products)}")
        self.log(f"Removed products:   {len(self.removed_products)}")
        self.log(f"Price changes:      {len(self.price_changes)}")
        self.log(f"Duration:           {duration:.0f}s ({duration/60:.1f}min)")
        self.log(f"\nChanges saved to: {self.changes_file}")
        self.log("="*80)
    
    def _analyze_changes(self):
        """Analyze differences between existing and current products"""
        existing_ids = set(self.existing_products.keys())
        current_ids = set(self.current_products.keys())
        
        # New products
        new_ids = current_ids - existing_ids
        for product_id in new_ids:
            product = self.current_products[product_id]
            self.new_products.append({
                'type': 'NEW',
                'product_id': product_id,
                'name': product['name'],
                'url': product['url'],
                'price': product['price'],
                'product_unitprice_ht': product['product_unitprice_ht'],
                'brand': product['brand'],
                'sku': product['sku'],
                'category': product['category'],
                'old_price': '',
                'old_price_ht': '',
                'timestamp': datetime.now().isoformat(),
                'JSON_downloaded': 'no'
            })
        
        # Removed products
        removed_ids = existing_ids - current_ids
        for product_id in removed_ids:
            product = self.existing_products[product_id]
            self.removed_products.append({
                'type': 'REMOVED',
                'product_id': product_id,
                'name': product['name'],
                'url': product['url'],
                'price': product['price'],
                'product_unitprice_ht': product['product_unitprice_ht'],
                'brand': product['brand'],
                'sku': product['sku'],
                'category': product['category'],
                'old_price': '',
                'old_price_ht': '',
                'timestamp': datetime.now().isoformat(),
                'JSON_downloaded': 'no'
            })
        
        # Price changes
        common_ids = existing_ids & current_ids
        for product_id in common_ids:
            existing = self.existing_products[product_id]
            current = self.current_products[product_id]
            
            price_changed = False
            price_ht_changed = False
            
            if abs(existing['price'] - current['price']) > 0.01:
                price_changed = True
            
            if abs(existing['product_unitprice_ht'] - current['product_unitprice_ht']) > 0.01:
                price_ht_changed = True
            
            if price_changed or price_ht_changed:
                self.price_changes.append({
                    'type': 'PRICE_CHANGE',
                    'product_id': product_id,
                    'name': current['name'],
                    'url': current['url'],
                    'price': current['price'],
                    'product_unitprice_ht': current['product_unitprice_ht'],
                    'brand': current['brand'],
                    'sku': current['sku'],
                    'category': current['category'],
                    'old_price': existing['price'],
                    'old_price_ht': existing['product_unitprice_ht'],
                    'timestamp': datetime.now().isoformat(),
                    'JSON_downloaded': 'no'
                })
    
    def _save_changes(self):
        """Save changes to CSV"""
        all_changes = self.new_products + self.removed_products + self.price_changes
        
        if not all_changes:
            self.log("\n✓ No changes detected")
            return
        
        fieldnames = [
            'type', 'product_id', 'name', 'url', 'price', 'product_unitprice_ht',
            'brand', 'sku', 'category', 'old_price', 'old_price_ht', 'timestamp', 'JSON_downloaded'
        ]
        
        with open(self.changes_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            
            for change in all_changes:
                # Format prices with comma for Excel
                row = change.copy()
                if row['price']:
                    row['price'] = f"{row['price']:.2f}".replace('.', ',')
                if row['product_unitprice_ht']:
                    row['product_unitprice_ht'] = f"{row['product_unitprice_ht']:.2f}".replace('.', ',')
                if row.get('old_price') and isinstance(row['old_price'], (int, float)):
                    row['old_price'] = f"{row['old_price']:.2f}".replace('.', ',')
                if row.get('old_price_ht') and isinstance(row['old_price_ht'], (int, float)):
                    row['old_price_ht'] = f"{row['old_price_ht']:.2f}".replace('.', ',')
                
                writer.writerow(row)
        
        self.log(f"\n✓ Saved {len(all_changes)} changes to {self.changes_file}")


async def main():
    detector = ChangeDetector(
        existing_dir="output/laplateforme",
        output_dir="output/changes"
    )
    await detector.check_changes()


if __name__ == '__main__':
    asyncio.run(main())

