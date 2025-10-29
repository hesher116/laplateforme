"""
Site analyzer - повний аналіз сайту
"""

import asyncio
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlparse
import yaml

from core.detector import SiteDetector, recommend_scraping_approach
from core.counter import ProductCounter
from utils.logger import get_logger


class SiteAnalyzer:
    """Аналізатор сайту - об'єднує детекцію та підрахунок"""
    
    def __init__(self, url: str, quick_mode: bool = False):
        """
        Args:
            url: URL сайту
            quick_mode: Швидкий режим (без глибокого аналізу)
        """
        self.url = url.rstrip('/')
        self.quick_mode = quick_mode
        self.logger = get_logger()
        
        # Отримати назву сайту
        domain = urlparse(url).netloc
        self.site_name = domain.replace('www.', '').replace('.', '_')
    
    async def analyze(self) -> Dict[str, Any]:
        """
        Провести повний аналіз сайту
        
        Returns:
            Словник з результатами аналізу
        """
        self.logger.info(f"Початок аналізу сайту: {self.url}")
        
        # Створити детектор та каунтер
        detector = SiteDetector(self.url)
        counter = ProductCounter(self.url, max_depth=5 if self.quick_mode else 10)
        
        # Запустити паралельно
        self.logger.info("Виконую детекцію технологій...")
        detection_result, count_result = await asyncio.gather(
            detector.detect(),
            counter.count(),
            return_exceptions=True
        )
        
        # Обробити помилки
        if isinstance(detection_result, Exception):
            self.logger.error(f"Помилка детекції: {detection_result}")
            detection_result = {}
        
        if isinstance(count_result, Exception):
            self.logger.error(f"Помилка підрахунку: {count_result}")
            count_result = {'total_products': 0, 'categories': 0}
        
        # Об'єднати результати
        result = {
            'url': self.url,
            'site_name': self.site_name,
            'total_products': count_result.get('total_products', 0),
            'categories': count_result.get('categories', 0),
            'scan_time': count_result.get('scan_time', 0),
            'has_api': detection_result.get('has_api', False),
            'api_type': detection_result.get('api_type'),
            'api_endpoints': detection_result.get('api_endpoints', []),
            'js_rendering': detection_result.get('js_rendering', 'unknown'),
            'js_percentage': detection_result.get('js_percentage', 0),
            'framework': detection_result.get('framework'),
            'protection': detection_result.get('protection', 'none'),
            'has_sitemap': detection_result.get('has_sitemap', False),
            'sitemap_url': detection_result.get('sitemap_url'),
            'robots_txt': detection_result.get('robots_txt'),
        }
        
        # Додати рекомендації
        recommended_approach = recommend_scraping_approach(detection_result)
        result['recommended_approach'] = recommended_approach
        
        # Оцінити час парсингу
        estimated_time = self._estimate_scraping_time(
            result['total_products'],
            recommended_approach,
            result['js_rendering']
        )
        result['estimated_time'] = estimated_time
        
        self.logger.info(f"Аналіз завершено: {result['total_products']} товарів, підхід: {recommended_approach}")
        
        return result
    
    def _estimate_scraping_time(self, total_products: int, approach: str, js_rendering: str) -> str:
        """
        Оцінити час парсингу
        
        Args:
            total_products: Кількість товарів
            approach: Підхід до парсингу
            js_rendering: Тип JS рендерингу
        
        Returns:
            Оцінений час (строка)
        """
        # Швидкість в товарах/хвилину залежно від підходу
        speeds = {
            'api': 1000,
            'static': 500,
            'hybrid': 300,
            'dynamic': 100
        }
        
        speed = speeds.get(approach, 300)
        
        # Корекція для JS
        if js_rendering == 'full':
            speed *= 0.5
        elif js_rendering == 'partial':
            speed *= 0.7
        
        # Розрахувати час
        minutes = total_products / speed
        hours = int(minutes / 60)
        mins = int(minutes % 60)
        
        if hours == 0:
            return f"{mins} хвилин"
        elif hours < 24:
            return f"{hours} год {mins} хв"
        else:
            days = hours // 24
            hours = hours % 24
            return f"{days} днів {hours} год"
    
    def save_config(self, analysis_result: Dict[str, Any]) -> str:
        """
        Зберегти конфігурацію для сайту
        
        Args:
            analysis_result: Результати аналізу
        
        Returns:
            Шлях до збереженого файлу
        """
        config_dir = Path("sites")
        config_dir.mkdir(exist_ok=True)
        
        config_path = config_dir / f"{self.site_name}.yaml"
        
        # Створити конфігурацію
        config = {
            'site_name': self.site_name,
            'base_url': self.url,
            'analysis': {
                'total_products': analysis_result['total_products'],
                'has_api': analysis_result['has_api'],
                'api_endpoints': analysis_result['api_endpoints'],
                'js_rendering': analysis_result['js_rendering'],
                'recommended_approach': analysis_result['recommended_approach'],
                'has_sitemap': analysis_result['has_sitemap'],
                'sitemap_url': analysis_result.get('sitemap_url'),
                'framework': analysis_result.get('framework'),
                'protection': analysis_result.get('protection'),
            },
            'settings': {
                'save_format': 'json',  # json або html
                'download_pdf': True,
                'parallel_workers': self._recommend_workers(analysis_result['recommended_approach']),
                'delay_between_requests': 0.1,
                'max_retries': 3,
                'timeout': 30,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            'selectors': {
                # Буде заповнено вручну або автоматично під час першого запуску
                'product_title': None,
                'product_price': None,
                'product_id': None,
                'pdf_link': None,
            }
        }
        
        # Зберегти в YAML
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        self.logger.info(f"Конфігурацію збережено в {config_path}")
        
        return str(config_path)
    
    def _recommend_workers(self, approach: str) -> int:
        """Рекомендувати кількість воркерів"""
        workers_map = {
            'api': 100,
            'static': 50,
            'hybrid': 30,
            'dynamic': 10
        }
        return workers_map.get(approach, 50)



