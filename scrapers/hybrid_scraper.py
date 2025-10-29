"""
Hybrid scraper - комбінований підхід (API + Scrapy + Playwright)
"""

import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path
import time

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from scrapers.base_scraper import BaseScraper
from utils.progress import ProgressTracker
from utils.checkpoint import PeriodicCheckpoint


class HybridScraper(BaseScraper):
    """Гібридний скрапер - автоматично вибирає найкращий метод"""
    
    def __init__(self, *args, workers: int = 50, **kwargs):
        """
        Args:
            workers: Кількість паралельних воркерів
        """
        super().__init__(*args, **kwargs)
        self.workers = workers
        self.semaphore = asyncio.Semaphore(workers)
        
        # Визначити метод парсингу
        self.approach = self.config.get('analysis', {}).get('recommended_approach', 'hybrid')
        self.logger.info(f"Ініціалізація гібридного скрапера (підхід: {self.approach})")
    
    async def get_total_products(self) -> int:
        """Отримати загальну кількість товарів"""
        return self.config.get('analysis', {}).get('total_products', 0)
    
    async def get_product_urls(self) -> List[str]:
        """Отримати список всіх URL товарів"""
        self.logger.info("Збираю список URL товарів...")
        
        # Спробувати різні методи
        urls = []
        
        # 1. Спробувати API
        if self.config.get('analysis', {}).get('has_api'):
            urls = await self._get_urls_from_api()
            if urls:
                self.logger.info(f"Знайдено {len(urls)} товарів через API")
                return urls
        
        # 2. Спробувати sitemap
        if self.config.get('analysis', {}).get('has_sitemap'):
            urls = await self._get_urls_from_sitemap()
            if urls:
                self.logger.info(f"Знайдено {len(urls)} товарів через sitemap")
                return urls
        
        # 3. Краулинг сайту
        urls = await self._get_urls_from_crawling()
        self.logger.info(f"Знайдено {len(urls)} товарів через краулинг")
        
        return urls
    
    async def _get_urls_from_api(self) -> List[str]:
        """Отримати URLs через API"""
        api_endpoints = self.config.get('analysis', {}).get('api_endpoints', [])
        
        if not api_endpoints:
            return []
        
        # Тут має бути специфічна логіка для конкретного API
        # Поки повертаємо порожній список
        return []
    
    async def _get_urls_from_sitemap(self) -> List[str]:
        """Отримати URLs з sitemap"""
        sitemap_url = self.config.get('analysis', {}).get('sitemap_url')
        
        if not sitemap_url:
            return []
        
        try:
            from xml.etree import ElementTree as ET
            
            async with aiohttp.ClientSession() as session:
                async with session.get(sitemap_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        root = ET.fromstring(content)
                        
                        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                        urls = []
                        
                        for url_elem in root.findall('.//ns:url/ns:loc', ns):
                            url = url_elem.text
                            # Фільтрувати тільки продуктові URLs
                            if self._is_product_url(url):
                                urls.append(url)
                        
                        return urls
        
        except Exception as e:
            self.logger.error(f"Помилка читання sitemap: {e}")
        
        return []
    
    async def _get_urls_from_crawling(self) -> List[str]:
        """Отримати URLs через краулинг"""
        # Використати ProductCounter для швидкого краулингу
        from core.counter import ProductCounter
        
        counter = ProductCounter(self.base_url, max_depth=10)
        result = await counter.count()
        
        return result.get('product_urls', [])
    
    def _is_product_url(self, url: str) -> bool:
        """Перевірити чи це URL продукту"""
        import re
        
        # Для pointp.fr
        if '/p/' in url and '-A' in url:
            return True
        
        # Загальні паттерни
        if re.search(r'/p/[^/]+/[^/]+-ref-[^-]+-A\d+', url):
            return True
        
        return False
    
    async def scrape(self, progress_tracker: ProgressTracker) -> Dict[str, Any]:
        """
        Запустити парсинг всіх товарів
        
        Args:
            progress_tracker: Трекер прогресу
        
        Returns:
            Результати парсингу
        """
        self.logger.info("🚀 Початок парсингу товарів")
        
        # Отримати список URLs
        product_urls = await self.get_product_urls()
        
        if not product_urls:
            self.logger.error("Не знайдено жодного товару!")
            return {
                'total_count': 0,
                'success_count': 0,
                'error_count': 0
            }
        
        self.stats['total'] = len(product_urls)
        
        # Налаштувати periodic checkpoint
        periodic_checkpoint = PeriodicCheckpoint(
            self.checkpoint_manager,
            save_every=1000
        )
        
        # Створити задачі для парсингу
        tasks = []
        for url in product_urls:
            task = self._scrape_product_with_tracking(
                url,
                progress_tracker,
                periodic_checkpoint
            )
            tasks.append(task)
        
        # Виконати всі задачі паралельно
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Фінальний checkpoint
        periodic_checkpoint.force_save({
            'processed_count': self.stats['success'] + self.stats['errors'],
            'success_count': self.stats['success'],
            'error_count': self.stats['errors'],
            'total_count': self.stats['total']
        })
        
        return {
            'total_count': self.stats['total'],
            'success_count': self.stats['success'],
            'error_count': self.stats['errors'],
            'pdf_count': self.stats['pdf_downloaded'],
            'json_count': self.stats['success']
        }
    
    async def _scrape_product_with_tracking(
        self,
        url: str,
        progress_tracker: ProgressTracker,
        periodic_checkpoint: PeriodicCheckpoint
    ):
        """Парсити товар з трекінгом прогресу"""
        async with self.semaphore:  # Обмеження паралельних з'єднань
            try:
                # Затримка між запитами
                delay = self.settings.get('delay_between_requests', 0.1)
                if delay > 0:
                    await asyncio.sleep(delay)
                
                # Парсити товар
                product_data = await self.scrape_product(url)
                
                if product_data:
                    # Зберегти в CSV
                    self.csv_exporter.add_product(product_data)
                    
                    # Оновити дедуплікатор
                    self.deduplicator.add(product_data['product_id'], product_data['url'])
                    
                    # Оновити статистику
                    self.stats['success'] += 1
                    progress_tracker.increment(success=True)
                    
                    # Checkpoint
                    periodic_checkpoint.increment({
                        'processed_count': self.stats['success'] + self.stats['errors'],
                        'success_count': self.stats['success'],
                        'error_count': self.stats['errors']
                    })
                else:
                    self.stats['errors'] += 1
                    progress_tracker.increment(success=False, error_msg=f"Не вдалося парсити {url}")
            
            except Exception as e:
                self.stats['errors'] += 1
                error_msg = f"Помилка парсингу {url}: {str(e)}"
                self.logger.error(error_msg)
                progress_tracker.log_error(error_msg)
                progress_tracker.increment(success=False, error_msg=error_msg)
    
    async def scrape_product(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Парсити один товар
        
        Args:
            url: URL товару
        
        Returns:
            Дані товару
        """
        # Витягти product_id
        product_id = self.extract_product_id(url)
        
        # Перевірити чи потрібно обробляти
        if not self.should_process_product(product_id, url):
            return None
        
        # Визначити метод парсингу
        js_rendering = self.config.get('analysis', {}).get('js_rendering', 'unknown')
        
        # Спробувати парсити
        for attempt in range(self.settings.get('max_retries', 3)):
            try:
                if js_rendering == 'full':
                    # Використати Playwright для повного JS
                    product_data = await self._scrape_with_playwright(url, product_id)
                else:
                    # Використати aiohttp для статичного/часткового JS
                    product_data = await self._scrape_with_aiohttp(url, product_id)
                
                if product_data:
                    # Завантажити PDF якщо є
                    if product_data.get('pdf_url') and self.settings.get('download_pdf', True):
                        pdf_path = await self.download_pdf(product_data['pdf_url'], product_id)
                        product_data['pdf_downloaded'] = pdf_path is not None
                        product_data['pdf_filename'] = Path(pdf_path).name if pdf_path else None
                    else:
                        product_data['pdf_downloaded'] = False
                        product_data['pdf_filename'] = None
                    
                    # Зберегти дані товару
                    save_format = self.settings.get('save_format', 'json')
                    await self.save_product_data(product_data, format=save_format)
                    
                    product_data['status'] = 'success'
                    return product_data
            
            except Exception as e:
                self.logger.debug(f"Спроба {attempt + 1} не вдалась для {url}: {e}")
                if attempt < self.settings.get('max_retries', 3) - 1:
                    # Експоненційна затримка
                    await asyncio.sleep(2 ** attempt)
        
        # Якщо всі спроби невдалі
        return {
            'product_id': product_id,
            'url': url,
            'status': 'error',
            'error': 'Failed after all retries'
        }
    
    async def _scrape_with_aiohttp(self, url: str, product_id: str) -> Optional[Dict[str, Any]]:
        """Парсити за допомогою aiohttp (швидко)"""
        timeout = aiohttp.ClientTimeout(total=self.settings.get('timeout', 30))
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {'User-Agent': self.get_user_agent()}
            
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                
                # Парсити HTML
                return self._parse_html(html, url, product_id)
    
    async def _scrape_with_playwright(self, url: str, product_id: str) -> Optional[Dict[str, Any]]:
        """Парсити за допомогою Playwright (повільніше, але для JS)"""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                await page.goto(url, wait_until='networkidle', timeout=30000)
                html = await page.content()
                
                await browser.close()
                
                return self._parse_html(html, url, product_id)
        
        except Exception as e:
            self.logger.debug(f"Playwright помилка для {url}: {e}")
            return None
    
    def _parse_html(self, html: str, url: str, product_id: str) -> Dict[str, Any]:
        """
        Парсити HTML сторінку товару
        
        Args:
            html: HTML контент
            url: URL товару
            product_id: ID товару
        
        Returns:
            Дані товару
        """
        soup = BeautifulSoup(html, 'lxml')
        
        # Отримати селектори з конфігу
        selectors = self.config.get('selectors', {})
        
        # Витягти дані
        product_data = {
            'product_id': product_id,
            'url': url,
            'name': self._extract_text(soup, selectors.get('product_title')),
            'price': self._extract_text(soup, selectors.get('product_price')),
            'category': self._extract_category(soup),
            'pdf_url': self._extract_pdf_url(soup, url),
        }
        
        return product_data
    
    def _extract_text(self, soup: BeautifulSoup, selector: Optional[str]) -> str:
        """Витягти текст за селектором"""
        if not selector:
            return ''
        
        try:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)
        except Exception:
            pass
        
        return ''
    
    def _extract_category(self, soup: BeautifulSoup) -> str:
        """Витягти категорію товару"""
        # Спробувати знайти breadcrumbs
        breadcrumbs = soup.select('.breadcrumb a, .breadcrumbs a, [class*="breadcrumb"] a')
        
        if breadcrumbs and len(breadcrumbs) > 1:
            return breadcrumbs[-1].get_text(strip=True)
        
        return ''
    
    def _extract_pdf_url(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """Витягти URL PDF файлу"""
        from urllib.parse import urljoin
        
        # Шукати посилання на PDF
        pdf_link = soup.find('a', href=lambda x: x and x.endswith('.pdf'))
        
        if pdf_link:
            href = pdf_link.get('href')
            return urljoin(base_url, href)
        
        return None

