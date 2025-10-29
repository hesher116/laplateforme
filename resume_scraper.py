# -*- coding: utf-8 -*-
"""
Resume scraper - continues from where stable scraper left off
"""

import asyncio
from laplateforme_scraper_stable import LaplatefFormeStableScraper
import csv
import sys


class LaplatefFormeResumeScraper(LaplatefFormeStableScraper):
    def __init__(self, output_dir="output/laplateforme"):
        super().__init__(output_dir)
        self.log("🔄 RESUME MODE ACTIVATED!")
        self.load_existing_data()

    def load_existing_data(self):
        """Load existing products from CSV with SEMICOLON delimiter"""
        if self.csv_file.exists():
            self.log(f"Loading: {self.csv_file}")
            with open(self.csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    self.products.append(row)
                    product_id = row['product_id']
                    self.product_ids.add(product_id)
                    # Track category (mark as "Previous")
                    self.product_first_category[product_id] = "Previous run"
            self.log(f"✓ Loaded {len(self.products)} products")
        
        if self.errors_file.exists():
            self.log(f"Loading: {self.errors_file}")
            with open(self.errors_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    self.errors.append(row)
            self.log(f"✓ Loaded {len(self.errors)} errors")
        
        self.log(f"\n📊 Will continue from {len(self.products)} products")
        self.log("All already scraped products will be skipped automatically\n")


async def main():
    scraper = LaplatefFormeResumeScraper()
    await scraper.scrape(limit=None)


if __name__ == '__main__':
    asyncio.run(main())
