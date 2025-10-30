# 🕷️ Laplateforme Scraper

Professional web scraper for [laplateforme.com](https://www.laplateforme.com/) - French construction materials e-commerce platform.

## 📋 Overview

High-performance asynchronous scraper that extracts product data, PDFs, and technical specifications from laplateforme.com. Built with Playwright for reliable JavaScript rendering and handles large-scale data collection with automatic deduplication and resume capabilities.

## ✨ Features

- **Comprehensive Data Extraction**: Product details, prices, brands, SKUs, categories
- **PDF Downloads**: Automatic technical specification sheet downloads
- **Smart Deduplication**: Prevents duplicate products across categories
- **Resume Capability**: Continue from where you left off after interruption
- **Structured Output**: CSV, JSON, and organized PDF storage
- **Progress Tracking**: Real-time logging with speed metrics and ETAs
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
- Saves new products to separate directory

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
└── laplateforme_missed_elements/    # Resume scraping results
    └── (same structure as above)
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

Edit `config.yaml` to customize:

```yaml
default_scraping:
  parallel_workers: 50      # Sequential (set to 1 for reliability)
  delay_between_requests: 0.1
  max_retries: 3
  timeout: 30
  download_pdf: true
```

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

**resume_missed_scraper.py**
- Intelligent resume functionality
- Deduplication against existing data
- Progress preservation on interruption

**Utilities (utils/)**
- `deduplicator.py`: Product uniqueness validation
- `csv_exporter.py`: CSV formatting and export
- `logger.py`: Structured logging
- `checkpoint.py`: Progress state management

## 📈 Performance

- **Speed**: ~6-10 products/minute (sequential, stable)
- **Reliability**: Automatic retry on failures
- **Memory**: Efficient streaming, no full dataset in memory
- **Scale**: Handles 17,000+ products without issues

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
```

## 🐛 Troubleshooting

**"No dataLayer" errors**: Some products may lack structured data - logged in errors.csv

**CSV locked**: Close Excel/LibreOffice before running scraper

**Playwright timeout**: Increase `timeout` in config.yaml or check internet connection

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

