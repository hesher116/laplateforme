"""
Page downloader - завантаження HTML/JSON сторінок
"""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
import json

import aiohttp
import aiofiles
from bs4 import BeautifulSoup

from utils.logger import get_logger


class PageDownloader:
    """Завантажувач сторінок"""
    
    def __init__(
        self,
        output_dir: Path,
        format: str = 'json',
        timeout: int = 30
    ):
        """
        Args:
            output_dir: Директорія для збереження
            format: Формат збереження (json або html)
            timeout: Timeout для запитів
        """
        self.output_dir = Path(output_dir)
        self.format = format
        self.timeout = timeout
        self.logger = get_logger()
        
        # Створити піддиректорії
        (self.output_dir / "json").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "html").mkdir(parents=True, exist_ok=True)
    
    async def download_page(
        self,
        url: str,
        product_id: str,
        parse_to_json: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Завантажити та зберегти сторінку
        
        Args:
            url: URL сторінки
            product_id: ID товару
            parse_to_json: Парсити HTML в JSON
        
        Returns:
            Дані сторінки
        """
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        return None
                    
                    html = await response.text()
                    
                    # Зберегти HTML якщо потрібно
                    if self.format == 'html' or self.format == 'both':
                        await self._save_html(html, product_id)
                    
                    # Парсити в JSON якщо потрібно
                    if parse_to_json and (self.format == 'json' or self.format == 'both'):
                        data = self._parse_to_json(html, url, product_id)
                        await self._save_json(data, product_id)
                        return data
                    
                    return {'html': html, 'url': url, 'product_id': product_id}
        
        except Exception as e:
            self.logger.error(f"Помилка завантаження {url}: {e}")
            return None
    
    async def _save_html(self, html: str, product_id: str):
        """Зберегти HTML"""
        html_path = self.output_dir / "html" / f"{product_id}.html"
        
        async with aiofiles.open(html_path, 'w', encoding='utf-8') as f:
            await f.write(html)
    
    async def _save_json(self, data: Dict[str, Any], product_id: str):
        """Зберегти JSON"""
        json_path = self.output_dir / "json" / f"{product_id}.json"
        
        async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    
    def _parse_to_json(self, html: str, url: str, product_id: str) -> Dict[str, Any]:
        """
        Парсити HTML в структурований JSON
        
        Args:
            html: HTML контент
            url: URL сторінки
            product_id: ID товару
        
        Returns:
            Структуровані дані
        """
        soup = BeautifulSoup(html, 'lxml')
        
        # Базова структура
        data = {
            'product_id': product_id,
            'url': url,
            'title': self._extract_title(soup),
            'price': self._extract_price(soup),
            'description': self._extract_description(soup),
            'images': self._extract_images(soup),
            'specifications': self._extract_specifications(soup),
            'metadata': self._extract_metadata(soup)
        }
        
        return data
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Витягти заголовок"""
        # Спробувати різні селектори
        selectors = [
            'h1',
            '.product-name',
            '.product-title',
            '[itemprop="name"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)
        
        # Fallback на title тег
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text(strip=True)
        
        return ''
    
    def _extract_price(self, soup: BeautifulSoup) -> Optional[str]:
        """Витягти ціну"""
        price_selectors = [
            '.price',
            '.product-price',
            '[itemprop="price"]',
            '.price-value'
        ]
        
        for selector in price_selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)
        
        return None
    
    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Витягти опис"""
        desc_selectors = [
            '.product-description',
            '.description',
            '[itemprop="description"]'
        ]
        
        for selector in desc_selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)
        
        return ''
    
    def _extract_images(self, soup: BeautifulSoup) -> list:
        """Витягти зображення"""
        images = []
        
        # Шукати зображення товару
        img_tags = soup.select('.product-image img, .gallery img, [itemprop="image"]')
        
        for img in img_tags[:10]:  # Максимум 10 зображень
            src = img.get('src') or img.get('data-src')
            if src:
                images.append(src)
        
        return images
    
    def _extract_specifications(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Витягти характеристики/специфікації"""
        specs = {}
        
        # Шукати таблиці характеристик
        spec_tables = soup.select('.specifications table, .specs table, .product-specs table')
        
        for table in spec_tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    specs[key] = value
        
        return specs
    
    def _extract_metadata(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Витягти метадані"""
        metadata = {}
        
        # Meta tags
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            if meta.get('property'):
                metadata[meta['property']] = meta.get('content', '')
            elif meta.get('name'):
                metadata[meta['name']] = meta.get('content', '')
        
        return metadata



