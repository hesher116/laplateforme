# 🕷️ Laplateforme Scraper

Professional web scraper for [laplateforme.com](https://www.laplateforme.com/) - French construction materials e-commerce platform.

## 📋 Overview

High-performance asynchronous scraper that extracts product data, PDFs, and technical specifications from laplateforme.com. Built with Playwright for reliable JavaScript rendering and handles large-scale data collection with automatic deduplication and resume capabilities.

## ✨ Features

- **Comprehensive Data Extraction**: Product details, prices, brands, SKUs, categories
- **PDF Downloads**: Automatic technical specification sheet downloads
- **Smart Deduplication**: Prevents duplicate products across categories
- **Resume Capability**: Continue from where you left off after interruption
- **Change Detection**: Detects new products, removed products, and price changes
- **Structured Output**: CSV, JSON, and organized PDF storage
- **Progress Tracking**: Real-time logging with unified format
- **Error Handling**: Robust retry logic and error logging

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Virtual environment (recommended)

### Installation

```bash
# Clone repository
git clone git@github.com:hesher116/laplateforme.git
cd laplateforme

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Usage

**Full Scraping (from scratch):**
```bash
python laplateforme_scraper_stable.py
```

**Resume Scraping (collect missed products):**
```bash
python resume_missed_scraper.py
```

The resume scraper automatically:
- Loads existing product IDs to prevent duplicates
- Continues from previous progress if interrupted
- Checks ALL categories for missed products
- Saves new products to separate directory

**Check for Changes (new/removed products, price changes):**
```bash
python check_changes.py
```

The change detector:
- Compares current catalog with existing data
- Detects new products, removed products, and price changes
- Saves changes to CSV file

## 📁 Output Structure

```
output/
├── laplateforme/                    # Main scraping results
│   ├── products.csv                 # Product catalog
│   ├── errors.csv                   # Error log
│   ├── scraping.log                 # Detailed execution log
│   ├── pdf/                         # Technical specification PDFs
│   │   ├── {product_id}.pdf
│   │   └── ...
│   └── data/json/                   # Full product data
│       ├── {product_id}.json
│       └── ...
├── laplateforme_missed_elements/    # Resume scraping results
│   └── (same structure as above)
└── changes/                         # Change detection results
    ├── changes.csv                  # Detected changes (NEW/REMOVED/PRICE_CHANGE)
    └── changes.log                  # Detection log
```

## 📊 Output Format

### CSV (products.csv)
Semicolon-delimited with comma as decimal separator (Excel-compatible):

| Field | Description |
|-------|-------------|
| product_id | Unique product identifier |
| name | Product name |
| url | Product page URL |
| price | Main price (€HT) |
| product_unitprice_ht | Unit price (€HT) |
| brand | Manufacturer brand |
| sku | Stock keeping unit |
| category | Product category |
| pdf_url | Technical sheet URL |
| pdf_downloaded | PDF download status (yes/no) |
| status | Scraping status |

### JSON (data/json/)
Complete product data extracted from site's dataLayer, including all available metadata.

## ⚙️ Configuration

All configuration is hardcoded in the scripts for simplicity. Key settings:

- **Timeout**: 5 seconds per product page (5000ms)
- **PDF Downloads**: Enabled by default
- **Processing**: Sequential (stable, reliable)
- **Retries**: Automatic error handling with logging

## 🔧 Technical Details

### Architecture
- **Async/Await**: Efficient I/O handling with asyncio
- **Playwright**: JavaScript rendering for dynamic content
- **Sequential Processing**: Stable, predictable execution
- **CSV Sync**: Real-time updates after each product

### Key Components

**laplateforme_scraper_stable.py**
- Main scraper for complete site crawling
- Category discovery and pagination handling
- Cross-category duplicate detection
- Real-time CSV updates

**resume_missed_scraper.py**
- Intelligent resume functionality
- Checks ALL categories for missed products
- Deduplication against existing data
- Progress preservation on interruption

**check_changes.py**
- Change detection system
- Compares current catalog with existing data
- Detects new products, removed products, price changes
- Exports changes to CSV

## 📈 Performance

- **Speed**: ~15-20 products/minute (sequential, stable, ~3 seconds per product)
- **Reliability**: Automatic retry on failures
- **Memory**: Efficient streaming, no full dataset in memory
- **Scale**: Handles 25,000+ products without issues

## 🛡️ Best Practices

1. **Run During Off-Peak Hours**: Reduce server load
2. **Monitor Logs**: Check `scraping.log` for issues
3. **Close Excel**: CSV updates may fail if file is open
4. **Use Resume Script**: For interrupted sessions or updates

## 📝 Example Workflow

```bash
# Initial full scrape
python laplateforme_scraper_stable.py

# ... scraper runs for several hours ...
# Results: 17,584 products in output/laplateforme/

# Later, collect any missed products
python resume_missed_scraper.py

# ... checks all categories, skips existing products ...
# Results: New products in output/laplateforme_missed_elements/

# Periodically check for changes
python check_changes.py

# ... compares current catalog with existing data ...
# Results: changes.csv with NEW/REMOVED/PRICE_CHANGE products
```

## 🐛 Troubleshooting

**"No dataLayer" errors**: Some products may lack structured data - logged in errors.csv

**CSV locked**: Close Excel/LibreOffice before running scraper

**Playwright timeout**: Increase timeout value in script (currently 5000ms) or check internet connection

**Memory issues**: Script is optimized for low memory usage, but ensure 2GB+ RAM available

## 📄 License

This project is provided as-is for educational purposes. Please respect laplateforme.com's robots.txt and terms of service.

## 🙏 Acknowledgments

Built with:
- [Playwright](https://playwright.dev/) - Browser automation
- [aiohttp](https://docs.aiohttp.org/) - Async HTTP client
- [aiofiles](https://github.com/Tinche/aiofiles) - Async file operations

---

**Note**: This scraper is designed for personal use and data analysis. Always respect website terms of service and implement appropriate rate limiting.

