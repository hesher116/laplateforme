"""
Product counter - швидкий підрахунок товарів на сайті
"""

import asyncio
import time
from typing import Dict, Any, List, Set
from urllib.parse import urljoin, urlparse
import re

import aiohttp
from bs4 import BeautifulSoup
import pandas as pd

from utils.logger import get_logger


class ProductCounter:
    """Швидкий підрахунок товарів без завантаження деталей"""
    
    def __init__(self, url: str, max_depth: int = 10, timeout: int = 60):
        """
        Args:
            url: Базовий URL сайту
            max_depth: Максимальна глибина сканування
            timeout: Timeout в секундах
        """
        self.base_url = url.rstrip('/')
        self.domain = urlparse(url).netloc
        self.max_depth = max_depth
        self.timeout = timeout
        self.logger = get_logger()
        
        self.product_urls: Set[str] = set()
        self.category_urls: Set[str] = set()
        self.visited_urls: Set[str] = set()
        
        self.start_time = None
        
    async def count(self) -> Dict[str, Any]:
        """
        Підрахувати товари на сайті
        
        Returns:
            Словник з результатами підрахунку
        """
        self.start_time = time.time()
        self.logger.info(f"Початок підрахунку товарів на {self.base_url}")
        
        try:
            # Спочатку перевірити sitemap
            sitemap_count = await self._check_sitemap()
            
            if sitemap_count > 0:
                self.logger.info(f"Знайдено {sitemap_count} товарів через sitemap")
                result = {
                    'total_products': sitemap_count,
                    'categories': len(self.category_urls),
                    'scan_time': time.time() - self.start_time,
                    'method': 'sitemap',
                    'product_urls': list(self.product_urls)[:100]  # Перші 100 для прикладу
                }
            else:
                # Якщо sitemap не знайдено, сканувати сайт
                result = await self._crawl_site()
            
            return result
            
        except Exception as e:
            self.logger.error(f"Помилка підрахунку: {e}", exc_info=True)
            raise
    
    async def _check_sitemap(self) -> int:
        """
        Перевірити sitemap.xml для підрахунку
        
        Returns:
            Кількість товарів знайдених в sitemap
        """
        sitemap_urls = [
            f"{self.base_url}/sitemap.xml",
            f"{self.base_url}/sitemap_products.xml",
            f"{self.base_url}/product-sitemap.xml",
            f"{self.base_url}/sitemap_index.xml",
        ]
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            for sitemap_url in sitemap_urls:
                try:
                    async with session.get(sitemap_url) as response:
                        if response.status == 200:
                            content = await response.text()
                            count = await self._parse_sitemap(content, session)
                            if count > 0:
                                return count
                except Exception:
                    continue
        
        return 0
    
    async def _parse_sitemap(self, content: str, session: aiohttp.ClientSession) -> int:
        """Парсити sitemap XML"""
        from xml.etree import ElementTree as ET
        
        try:
            root = ET.fromstring(content)
            
            # Визначити namespace
            ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            # Перевірити чи це sitemap index
            sitemaps = root.findall('.//ns:sitemap/ns:loc', ns)
            if sitemaps:
                # Це sitemap index, завантажити дочірні sitemaps
                for sitemap in sitemaps[:10]:  # Обмежити до 10
                    try:
                        async with session.get(sitemap.text) as response:
                            if response.status == 200:
                                sub_content = await response.text()
                                count = await self._parse_sitemap(sub_content, session)
                                if count > 0:
                                    return count
                    except Exception:
                        continue
            
            # Парсити URLs
            urls = root.findall('.//ns:url/ns:loc', ns)
            
            # Парсити URLs та фільтрувати продуктові
            for url_elem in urls:
                url = url_elem.text
                
                # Використати метод визначення продукту
                if self._is_product_url(url):
                    self.product_urls.add(url)
            
            return len(self.product_urls)
            
        except Exception as e:
            self.logger.debug(f"Помилка парсингу sitemap: {e}")
            return 0
    
    async def _crawl_site(self) -> Dict[str, Any]:
        """Сканувати сайт для підрахунку товарів"""
        self.logger.info("Sitemap не знайдено, сканую сайт...")
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            # Почати з головної сторінки
            await self._crawl_page(self.base_url, session, depth=0)
        
        return {
            'total_products': len(self.product_urls),
            'categories': len(self.category_urls),
            'scan_time': time.time() - self.start_time,
            'method': 'crawl',
            'product_urls': list(self.product_urls)[:100]
        }
    
    async def _crawl_page(self, url: str, session: aiohttp.ClientSession, depth: int):
        """Рекурсивно сканувати сторінку"""
        if depth > self.max_depth or url in self.visited_urls:
            return
        
        if time.time() - self.start_time > self.timeout:
            return
        
        self.visited_urls.add(url)
        
        try:
            async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as response:
                if response.status != 200:
                    return
                
                html = await response.text()
                soup = BeautifulSoup(html, 'lxml')
                
                # Знайти всі посилання
                links = soup.find_all('a', href=True)
                
                self.logger.debug(f"Знайдено {len(links)} посилань на {url}")
                
                tasks = []
                for link in links[:200]:  # Обмежити кількість для швидкості
                    href = link['href']
                    
                    # Пропустити якорі та javascript
                    if href.startswith('#') or href.startswith('javascript:'):
                        continue
                    
                    absolute_url = urljoin(url, href)
                    
                    # Перевірити чи це той самий домен
                    parsed = urlparse(absolute_url)
                    if parsed.netloc and parsed.netloc != self.domain:
                        continue
                    
                    # Нормалізувати URL (видалити фрагменти)
                    absolute_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    if parsed.query:
                        absolute_url += f"?{parsed.query}"
                    
                    # Визначити чи це продукт чи категорія
                    if self._is_product_url(absolute_url):
                        self.product_urls.add(absolute_url)
                        self.logger.debug(f"Знайдено товар: {absolute_url}")
                    elif self._is_category_url(absolute_url):
                        self.category_urls.add(absolute_url)
                        # Продовжити сканування категорії
                        if absolute_url not in self.visited_urls and len(self.visited_urls) < 100:
                            tasks.append(self._crawl_page(absolute_url, session, depth + 1))
                
                # Виконати завдання паралельно (обмежено)
                if tasks:
                    await asyncio.gather(*tasks[:5], return_exceptions=True)
        
        except Exception as e:
            self.logger.debug(f"Помилка сканування {url}: {e}")
    
    def _is_product_url(self, url: str) -> bool:
        """Визначити чи це URL продукту"""
        # Для pointp.fr товари мають структуру: /p/категорія/назва-ref-код-Aідентифікатор
        # Приклад: /p/outillage-quincaillerie/tenaille-russe-225-ref-l-xl20109-A6508045
        
        # Перевірити чи це товар pointp.fr
        if '/p/' in url and '-A' in url:
            return True
        
        # Загальні паттерни для інших сайтів
        if re.search(r'/p/[^/]+/[^/]+-ref-[^-]+-A\d+', url):
            return True
        
        return False
    
    def _is_category_url(self, url: str) -> bool:
        """Визначити чи це URL категорії"""
        # Для pointp.fr:
        # - Категорії верхнього рівня: /materiel-de-chantier (без слешів всередині)
        # - Списки товарів: /c/decoupeuses-beton/x2snv2_dig_2030978
        
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        
        # Якщо це /c/ - це список товарів
        if '/c/' in path:
            return True
        
        # Якщо це шлях без підкатегорій (тільки одна частина після domain)
        # Наприклад: /materiel-de-chantier
        parts = [p for p in path.split('/') if p]
        if len(parts) == 1 and not path.endswith(('.html', '.htm', '.php')):
            return True
        
        return False
    
    def save_results(self, result: Dict[str, Any], output_path: str):
        """Зберегти результати в CSV"""
        if 'product_urls' in result and result['product_urls']:
            df = pd.DataFrame({
                'product_url': result['product_urls']
            })
            df['product_id'] = df['product_url'].apply(lambda x: x.split('/')[-1])
            df.to_csv(output_path, index=False, encoding='utf-8')
            self.logger.info(f"Результати збережено в {output_path}")

