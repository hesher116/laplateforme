# -*- coding: utf-8 -*-
"""
Laplateforme.com Resume Scraper

Intelligently collects missed products by checking all categories while deduplicating
against existing data. Preserves progress on interruption.
"""

import asyncio
from playwright.async_api import async_playwright
import aiohttp
import aiofiles
import csv
import json
import re
from pathlib import Path
from datetime import datetime
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class MissedProductsScraper:
    def __init__(self, output_dir="output/laplateforme_missed_elements", existing_dir="output/laplateforme", start_category=1):
        self.output_dir = Path(output_dir)
        self.existing_dir = Path(existing_dir)
        self.start_category = start_category
        
        self.pdf_dir = self.output_dir / "pdf"
        self.data_dir = self.output_dir / "data" / "json"
        
        # Create dirs
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.products = []
        self.product_ids = set()
        self.existing_product_ids = set()  # IDs from first scraping run
        self.product_first_category = {}
        self.errors = []
        self.duplicates_in_category = 0
        self.skipped_existing = 0  # Count products skipped because they exist
        
        self.csv_file = self.output_dir / "products.csv"
        self.errors_file = self.output_dir / "errors.csv"
        self.log_file = self.output_dir / "scraping.log"
        
        self.start_time = None
        self.estimated_total = 5000  # Remaining categories
        self.category_start_time = None
        self.products_at_category_start = 0
        
        # Load existing product IDs
        self._load_existing_product_ids()
        
        # Load already scraped products from current run (to preserve progress)
        self._load_current_progress()
    
    def _load_existing_product_ids(self):
        """Load product IDs from existing laplateforme scraping"""
        existing_csv = self.existing_dir / "products.csv"
        
        if existing_csv.exists():
            try:
                with open(existing_csv, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f, delimiter=';')
                    for row in reader:
                        product_id = row.get('product_id', '')
                        if product_id:
                            self.existing_product_ids.add(product_id)
                
                print(f"✓ Loaded {len(self.existing_product_ids)} existing product IDs from {existing_csv}")
                print(f"  These products will be skipped during scraping\n")
            except Exception as e:
                print(f"⚠️ Could not load existing products: {e}")
                print(f"  Continuing without deduplication...\n")
    
    def _load_current_progress(self):
        """Load already scraped products from current run to preserve progress"""
        current_csv = self.csv_file
        
        if current_csv.exists():
            try:
                with open(current_csv, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f, delimiter=';')
                    for row in reader:
                        product_id = row.get('product_id', '')
                        if product_id:
                            self.products.append(row)
                            self.product_ids.add(product_id)
                            # Also add to existing IDs so we don't scrape it again
                            self.existing_product_ids.add(product_id)
                
                print(f"✓ Loaded {len(self.products)} products from previous run")
                print(f"  Progress preserved, continuing from where we left off\n")
            except Exception as e:
                print(f"⚠️ Could not load previous progress: {e}\n")
    
    def log(self, msg):
        """Log with FORCED flush"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {msg}"
        print(log_msg, flush=True)
        sys.stdout.flush()
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + '\n')
    
    def get_stats(self):
        """Get current speed and ETA"""
        if not self.start_time:
            return "", ""
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed < 10:
            return "", ""
        
        products_count = len(self.products)
        speed = products_count / elapsed * 60
        
        remaining = self.estimated_total - products_count
        if speed > 0 and remaining > 0:
            eta_minutes = remaining / speed
            eta_hours = eta_minutes / 60
            if eta_hours < 1:
                eta_str = f"{eta_minutes:.0f}min"
            else:
                eta_str = f"{eta_hours:.1f}h"
        else:
            eta_str = "N/A"
        
        return f"{speed:.1f}/min", eta_str
    
    async def scrape_product(self, page, product_url, category_name=''):
        """Scrape single product"""
        try:
            # Extract ID
            match = re.search(r'/catalogue/produit/(\d+)', product_url)
            if not match:
                raise Exception("Cannot extract ID")
            
            product_id = match.group(1)
            
            # Load page
            await page.goto(product_url, wait_until='domcontentloaded', timeout=5000)
            await asyncio.sleep(0.5)
            
            # Extract dataLayer
            data_layer = await page.evaluate('() => window.dataLayer')
            
            if not data_layer:
                raise Exception("No dataLayer")
            
            # Merge dataLayer
            product_data = {}
            for item in data_layer:
                if isinstance(item, dict):
                    product_data.update(item)
            
            # Extract category from breadcrumbs if not provided
            if not category_name:
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
                        category_name = breadcrumbs[-1]  # Last breadcrumb is usually the category
                except:
                    pass
            
            # Format prices
            ecommerce_data = product_data.get('ecommerce', {})
            raw_price_main = ecommerce_data.get('value', product_data.get('price', ''))
            if raw_price_main:
                try:
                    price_float = float(raw_price_main)
                    formatted_price_main = f"{price_float:.2f}".replace('.', ',')
                except:
                    formatted_price_main = str(raw_price_main).replace('.', ',')
            else:
                formatted_price_main = ''
            
            raw_price_ht = product_data.get('product_unitprice_ht', '')
            if raw_price_ht:
                try:
                    price_ht_float = float(raw_price_ht)
                    formatted_price_ht = f"{price_ht_float:.2f}".replace('.', ',')
                except:
                    formatted_price_ht = str(raw_price_ht).replace('.', ',')
            else:
                formatted_price_ht = ''
            
            # Get category - prefer dataLayer, then breadcrumbs, then provided
            category = product_data.get('product_category', '') or category_name or ''
            
            # Build product
            product = {
                'product_id': product_id,
                'name': product_data.get('product_name', ''),
                'url': product_url,
                'price': formatted_price_main,
                'product_unitprice_ht': formatted_price_ht,
                'brand': product_data.get('product_brand', ''),
                'sku': product_data.get('product_sku', product_id),
                'category': category,
                'pdf_url': f"https://www.laplateforme.com/catalogue/pdf/product/false/{product_id}",
                'pdf_downloaded': 'no',
                'status': 'success'
            }
            
            # Save JSON
            json_file = self.data_dir / f"{product_id}.json"
            async with aiofiles.open(json_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(product_data, ensure_ascii=False, indent=2))
            
            # Download PDF
            pdf_path = self.pdf_dir / f"{product_id}.pdf"
            if await self.download_pdf(product['pdf_url'], pdf_path):
                product['pdf_downloaded'] = 'yes'
            
            return product
            
        except Exception as e:
            raise Exception(str(e)[:100])
    
    async def download_pdf(self, pdf_url, pdf_path):
        """Download PDF"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(pdf_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        content = await response.read()
                        if len(content) > 100:
                            async with aiofiles.open(pdf_path, 'wb') as f:
                                await f.write(content)
                            return True
            return False
        except:
            return False
    
    def save_csv(self):
        """Save CSV"""
        if self.products:
            for attempt in range(3):
                try:
                    with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=self.products[0].keys(), delimiter=';')
                        writer.writeheader()
                        writer.writerows(self.products)
                    break
                except PermissionError:
                    if attempt < 2:
                        import time
                        time.sleep(0.5)
                    else:
                        self.log(f"    ⚠️ CSV locked (Excel open?), skipping save")
        
        if self.errors:
            for attempt in range(3):
                try:
                    with open(self.errors_file, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=['url', 'error', 'timestamp'], delimiter=';')
                        writer.writeheader()
                        writer.writerows(self.errors)
                    break
                except PermissionError:
                    if attempt == 2:
                        pass
    
    async def scrape(self, limit=None):
        """Main scraping - check ALL categories for missed products"""
        start_time = datetime.now()
        self.start_time = start_time
        
        self.log("="*80)
        self.log("💎 LAPLATEFORME.COM - MISSED PRODUCTS SCRAPER 💎")
        self.log("="*80)
        self.log(f"Output: {self.output_dir}")
        self.log(f"Existing products loaded: {len(self.existing_product_ids)}")
        self.log(f"Already scraped (current run): {len(self.products)}")
        if limit:
            self.log(f"Limit: {limit} products")
        self.log("\nMode: Sequential (ALL categories, with deduplication)")
        self.log("")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
            
            # Get categories
            self.log("Finding categories...")
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
                
                total_categories = len(categories)
                self.log(f"Found {total_categories} categories to check\n")
                    
            finally:
                await finder_page.close()
            
            # Create pages
            product_finder = await context.new_page()
            scraper_page = await context.new_page()
            
            try:
                for cat_i, cat_url in enumerate(categories, 1):
                    if limit and len(self.products) >= limit:
                        self.log(f"\n✓ Reached limit!")
                        break
                    
                    self.log(f"{'='*80}")
                    self.log(f"[Category {cat_i}/{total_categories}]")
                    self.log(f"{cat_url}")
                    self.log(f"{'='*80}")
                    
                    # Track category time
                    self.category_start_time = datetime.now()
                    self.products_at_category_start = len(self.products)
                    skipped_at_start = self.skipped_existing
                    
                    # Find products
                    cat_product_urls = []
                    self.duplicates_in_category = 0
                    
                    try:
                        await product_finder.goto(cat_url, wait_until='domcontentloaded', timeout=12000)
                        await asyncio.sleep(1.0)
                        
                        # Scroll to load lazy products
                        await product_finder.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        await asyncio.sleep(0.8)
                        
                        page_num = 1
                        while True:
                            links = await product_finder.query_selector_all('a[href*="/catalogue/produit/"]')
                            new_products = 0
                            duplicates_on_page = 0
                            skipped_on_page = set()  # Track unique skipped IDs per page
                            seen_on_page = set()  # Track unique IDs found on this page
                            
                            for link in links:
                                href = await link.get_attribute('href')
                                if href and '/catalogue/produit/' in href:
                                    match = re.search(r'/catalogue/produit/(\d+)', href)
                                    if match:
                                        product_id = match.group(1)
                                        
                                        # Skip if already processed on this page
                                        if product_id in seen_on_page:
                                            continue
                                        seen_on_page.add(product_id)
                                        
                                        # Check if exists in old scraping
                                        if product_id in self.existing_product_ids:
                                            skipped_on_page.add(product_id)
                                            self.skipped_existing += 1
                                            continue
                                        
                                        # Check if already in current run
                                        if product_id not in self.product_ids:
                                            if not href.startswith('http'):
                                                href = 'https://www.laplateforme.com' + href
                                            cat_product_urls.append(href)
                                            self.product_ids.add(product_id)
                                            self.product_first_category[product_id] = f"Cat {cat_i}: {cat_url[:60]}"
                                            new_products += 1
                                        else:
                                            first_cat_info = self.product_first_category.get(product_id, '')
                                            if first_cat_info and f"Cat {cat_i}:" not in first_cat_info:
                                                duplicates_on_page += 1
                                                self.duplicates_in_category += 1
                            
                            if new_products > 0 or len(skipped_on_page) > 0:
                                msg = f"  Page {page_num}: +{new_products} new"
                                if len(skipped_on_page) > 0:
                                    msg += f", skipped {len(skipped_on_page)} existing"
                                self.log(msg)
                            
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
                        
                        skipped_in_cat = self.skipped_existing - skipped_at_start
                        self.log(f"  → Found {len(cat_product_urls)} NEW products in {page_num} pages")
                        if skipped_in_cat > 0:
                            self.log(f"  → Skipped {skipped_in_cat} products (already in laplateforme)")
                        if self.duplicates_in_category > 0:
                            self.log(f"  → Skipped {self.duplicates_in_category} cross-category duplicates")
                        
                    except Exception as e:
                        self.log(f"  ✗ ERROR: {str(e)[:60]}")
                        continue
                    
                    if not cat_product_urls:
                        self.log(f"  → No new products in this category, skipping\n")
                        continue
                    
                    # Extract category name from URL
                    category_name = ''
                    try:
                        # Extract category name from URL path
                        # URL format: /catalogue/categorie/category-path/ID
                        url_parts = [p for p in cat_url.split('/') if p]
                        if 'categorie' in url_parts:
                            cat_idx = url_parts.index('categorie')
                            if cat_idx + 1 < len(url_parts):
                                # Get all parts after 'categorie' before the ID (last numeric part)
                                cat_parts = []
                                for part in url_parts[cat_idx + 1:]:
                                    if part.isdigit():
                                        break
                                    cat_parts.append(part)
                                if cat_parts:
                                    # Use last meaningful part or join if multiple
                                    category_name = cat_parts[-1].replace('-', ' ').title()
                    except:
                        pass
                    
                    # SCRAPE SEQUENTIALLY
                    self.log(f"  Scraping {len(cat_product_urls)} products...")
                    
                    for i, url in enumerate(cat_product_urls, 1):
                        if limit and len(self.products) >= limit:
                            break
                        
                        try:
                            product = await self.scrape_product(scraper_page, url, category_name)
                            self.products.append(product)
                            
                            total = len(self.products)
                            sku = product['sku']
                            status_icon = "✓" if product['pdf_downloaded'] == 'yes' else "✗"
                            name_short = product['name'][:35].ljust(35)
                            price_main = product['price'].rjust(7)
                            price_ht = product['product_unitprice_ht'].rjust(7)
                            
                            self.log(f"[{str(total).rjust(5)}] [{sku.ljust(6)}] {status_icon} {name_short} | {price_main} / {price_ht} | PDF: {status_icon}")
                            
                            # Save after every product
                            self.save_csv()
                            
                        except Exception as e:
                            self.errors.append({
                                'url': url,
                                'error': str(e),
                                'timestamp': datetime.now().isoformat()
                            })
                            self.log(f"[{str(len(self.products)+1).rjust(5)}] ✗ ERROR: {str(e)[:60]}")
                    
                    # Category stats
                    cat_duration = (datetime.now() - self.category_start_time).total_seconds()
                    products_in_cat = len(self.products) - self.products_at_category_start
                    cat_speed = (products_in_cat / cat_duration * 60) if cat_duration > 0 else 0
                    
                    self.log(f"\n  ✓ Category done!")
                    self.log(f"    Category stats: {products_in_cat} products | {cat_duration:.0f}s | {cat_speed:.1f}/min")
                    self.log(f"    Global total:   {len(self.products)} NEW products | {self.skipped_existing} skipped existing | {len(self.errors)} errors")
                    self.log("")
                    
            finally:
                await product_finder.close()
                await scraper_page.close()
                await context.close()
                await browser.close()
        
        # Final save
        self.save_csv()
        
        # Summary
        duration = (datetime.now() - start_time).total_seconds()
        avg_speed = (len(self.products) / duration * 60) if (self.products and duration > 0) else 0
        
        self.log("\n" + "="*80)
        self.log("🎉 SCRAPING COMPLETE! 🎉")
        self.log("="*80)
        self.log(f"NEW products scraped: {len(self.products)}")
        self.log(f"Skipped (existing):   {self.skipped_existing}")
        self.log(f"Errors:               {len(self.errors)}")
        self.log(f"Duration:             {duration:.0f}s ({duration/60:.1f}min / {duration/3600:.1f}h)")
        self.log(f"Average speed:        {avg_speed:.1f} products/min")
        
        # Count files
        pdf_count = len(list(self.pdf_dir.glob('*.pdf')))
        json_count = len(list(self.data_dir.glob('*.json')))
        
        self.log(f"\nFiles created:")
        self.log(f"  PDFs:      {pdf_count}")
        self.log(f"  JSONs:     {json_count}")
        self.log(f"  CSV rows:  {len(self.products)}")
        
        self.log(f"\nOutput files:")
        self.log(f"  CSV:    {self.csv_file}")
        self.log(f"  PDFs:   {self.pdf_dir}/")
        self.log(f"  JSONs:  {self.data_dir}/")
        
        if self.errors:
            self.log(f"  Errors: {self.errors_file}")
        
        self.log("\n" + "="*80)
        self.log("✅ ALL DONE!")
        self.log("="*80)


async def main():
    scraper = MissedProductsScraper(
        output_dir="output/laplateforme_missed_elements",
        existing_dir="output/laplateforme",
        start_category=1
    )
    await scraper.scrape(limit=None)


if __name__ == '__main__':
    asyncio.run(main())

