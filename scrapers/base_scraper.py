"""
Base scraper class - базовий клас для всіх скраперів
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path

from utils.logger import get_logger
from utils.csv_exporter import CSVExporter
from utils.deduplicator import ProductDeduplicator
from utils.checkpoint import CheckpointManager


class BaseScraper(ABC):
    """Базовий клас для всіх скраперів"""
    
    def __init__(
        self,
        base_url: str,
        config: Dict[str, Any],
        output_dir: Path,
        csv_exporter: CSVExporter,
        deduplicator: ProductDeduplicator,
        checkpoint_manager: CheckpointManager
    ):
        """
        Args:
            base_url: Базовий URL сайту
            config: Конфігурація
            output_dir: Директорія для виводу
            csv_exporter: CSV експортер
            deduplicator: Дедуплікатор
            checkpoint_manager: Менеджер checkpoint'ів
        """
        self.base_url = base_url.rstrip('/')
        self.config = config
        self.output_dir = output_dir
        self.csv_exporter = csv_exporter
        self.deduplicator = deduplicator
        self.checkpoint_manager = checkpoint_manager
        
        self.logger = get_logger()
        self.settings = config.get('settings', {})
        
        # Статистика
        self.stats = {
            'total': 0,
            'success': 0,
            'errors': 0,
            'pdf_downloaded': 0
        }
    
    @abstractmethod
    async def get_product_urls(self) -> List[str]:
        """
        Отримати список URL всіх товарів
        
        Returns:
            Список URLs товарів
        """
        pass
    
    @abstractmethod
    async def scrape_product(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Парсити один товар
        
        Args:
            url: URL товару
        
        Returns:
            Дані товару або None при помилці
        """
        pass
    
    async def download_pdf(self, pdf_url: str, product_id: str) -> Optional[str]:
        """
        Завантажити PDF файл
        
        Args:
            pdf_url: URL PDF файлу
            product_id: ID товару
        
        Returns:
            Шлях до збереженого файлу або None
        """
        import aiohttp
        import aiofiles
        
        try:
            pdf_path = self.output_dir / "pdf" / f"{product_id}.pdf"
            
            # Перевірити чи вже завантажено
            if pdf_path.exists():
                return str(pdf_path)
            
            timeout = aiohttp.ClientTimeout(total=self.settings.get('timeout', 30))
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(pdf_url) as response:
                    if response.status == 200:
                        async with aiofiles.open(pdf_path, 'wb') as f:
                            await f.write(await response.read())
                        
                        self.stats['pdf_downloaded'] += 1
                        return str(pdf_path)
        
        except Exception as e:
            self.logger.debug(f"Помилка завантаження PDF {pdf_url}: {e}")
        
        return None
    
    async def save_product_data(self, product_data: Dict[str, Any], format: str = 'json'):
        """
        Зберегти дані товару
        
        Args:
            product_data: Дані товару
            format: Формат збереження (json або html)
        """
        import json
        import aiofiles
        
        product_id = product_data.get('product_id', 'unknown')
        
        if format == 'json':
            json_path = self.output_dir / "data" / "json" / f"{product_id}.json"
            async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(product_data, ensure_ascii=False, indent=2))
        
        elif format == 'html':
            html_content = product_data.get('html', '')
            if html_content:
                html_path = self.output_dir / "data" / "html" / f"{product_id}.html"
                async with aiofiles.open(html_path, 'w', encoding='utf-8') as f:
                    await f.write(html_content)
    
    def should_process_product(self, product_id: str, url: str) -> bool:
        """
        Перевірити чи потрібно обробляти товар
        
        Args:
            product_id: ID товару
            url: URL товару
        
        Returns:
            True якщо потрібно обробляти
        """
        # Перевірити дублікати
        if self.deduplicator.is_duplicate(product_id, url):
            self.logger.debug(f"Пропускаю дублікат: {product_id}")
            return False
        
        # Перевірити checkpoint
        if self.checkpoint_manager.is_processed(product_id):
            self.logger.debug(f"Вже оброблено (checkpoint): {product_id}")
            return False
        
        return True
    
    def extract_product_id(self, url: str, product_data: Optional[Dict] = None) -> str:
        """
        Витягти ID товару
        
        Args:
            url: URL товару
            product_data: Дані товару (опціонально)
        
        Returns:
            ID товару
        """
        from utils.deduplicator import extract_product_id_from_url, generate_product_id
        
        # Спробувати витягти з URL
        product_id = extract_product_id_from_url(url)
        
        if product_id:
            return product_id
        
        # Спробувати витягти з даних
        if product_data:
            # Пошук в різних можливих полях
            for field in ['product_id', 'sku', 'id', 'article', 'code', 'reference']:
                if field in product_data and product_data[field]:
                    return str(product_data[field])
        
        # Остання опція - згенерувати
        return generate_product_id({'url': url})
    
    def get_user_agent(self) -> str:
        """Отримати User-Agent"""
        return self.settings.get(
            'user_agent',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )



