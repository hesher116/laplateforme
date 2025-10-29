"""
Scraping orchestrator - керування процесом парсингу
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import yaml

from core.analyzer import SiteAnalyzer
from scrapers.hybrid_scraper import HybridScraper
from utils.logger import setup_logger, get_logger
from utils.progress import ProgressTracker
from utils.csv_exporter import CSVExporter
from utils.checkpoint import CheckpointManager
from utils.deduplicator import ProductDeduplicator


class ScrapingOrchestrator:
    """Оркестратор парсингу - керує всім процесом"""
    
    def __init__(
        self,
        url: str,
        config_path: Optional[str] = None,
        resume: bool = False,
        workers: Optional[int] = None
    ):
        """
        Args:
            url: URL сайту для парсингу
            config_path: Шлях до конфігураційного файлу (опціонально)
            resume: Продовжити перерваний парсинг
            workers: Кількість паралельних потоків (override конфігу)
        """
        self.url = url.rstrip('/')
        self.config_path = config_path
        self.resume = resume
        self.workers_override = workers
        
        # Назва сайту
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        self.site_name = domain.replace('www.', '').replace('.', '_')
        
        # Налаштувати логер
        self.logger = setup_logger(site_name=self.site_name)
        
        # Завантажити або створити конфігурацію
        self.config = self._load_config()
        
        # Output директорія
        timestamp = datetime.now().strftime('%Y-%m-%d')
        self.output_dir = Path("output") / f"{self.site_name}_{timestamp}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Створити піддиректорії
        (self.output_dir / "data" / "json").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "data" / "html").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "pdf").mkdir(parents=True, exist_ok=True)
        
        # Ініціалізувати компоненти
        self.csv_exporter = CSVExporter(self.output_dir / "products.csv")
        self.checkpoint_manager = CheckpointManager(self.site_name)
        self.deduplicator = ProductDeduplicator(
            checkpoint_file=self.output_dir / "seen_products.json"
        )
        
        self.progress_tracker: Optional[ProgressTracker] = None
        self.scraper: Optional[HybridScraper] = None
    
    def _load_config(self) -> Dict[str, Any]:
        """Завантажити конфігурацію"""
        # Якщо вказано config_path - завантажити
        if self.config_path and Path(self.config_path).exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            self.logger.info(f"Конфігурацію завантажено з {self.config_path}")
            return config
        
        # Спробувати знайти автоматично
        auto_config_path = Path("sites") / f"{self.site_name}.yaml"
        if auto_config_path.exists():
            with open(auto_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            self.logger.info(f"Конфігурацію завантажено з {auto_config_path}")
            return config
        
        # Завантажити дефолтну конфігурацію
        with open("config.yaml", 'r', encoding='utf-8') as f:
            global_config = yaml.safe_load(f)
        
        self.logger.warning("Конфігурація сайту не знайдена, використовую дефолтну")
        
        return {
            'site_name': self.site_name,
            'base_url': self.url,
            'settings': global_config['default_scraping'],
            'analysis': {
                'recommended_approach': 'hybrid'
            }
        }
    
    def get_estimated_stats(self) -> Dict[str, Any]:
        """Отримати оцінені статистики перед запуском"""
        analysis = self.config.get('analysis', {})
        settings = self.config.get('settings', {})
        
        return {
            'total_products': analysis.get('total_products', 'Невідомо'),
            'approach': analysis.get('recommended_approach', 'hybrid'),
            'estimated_time': 'Невідомо (запустіть analyze спочатку)',
            'workers': self.workers_override or settings.get('parallel_workers', 50)
        }
    
    async def run(self) -> Dict[str, Any]:
        """
        Запустити парсинг
        
        Returns:
            Результати парсингу
        """
        start_time = time.time()
        self.logger.info(f"🚀 Запуск парсингу для {self.url}")
        
        try:
            # Якщо режим відновлення - завантажити checkpoint
            if self.resume and self.checkpoint_manager.exists():
                self.logger.info("Продовження з checkpoint...")
                checkpoint_data = self.checkpoint_manager.load()
                start_count = checkpoint_data.get('processed_count', 0)
            else:
                start_count = 0
            
            # Створити скрапер
            approach = self.config.get('analysis', {}).get('recommended_approach', 'hybrid')
            workers = self.workers_override or self.config['settings'].get('parallel_workers', 50)
            
            self.logger.info(f"Підхід: {approach}, Паралельні потоки: {workers}")
            
            self.scraper = HybridScraper(
                base_url=self.url,
                config=self.config,
                output_dir=self.output_dir,
                csv_exporter=self.csv_exporter,
                deduplicator=self.deduplicator,
                checkpoint_manager=self.checkpoint_manager,
                workers=workers
            )
            
            # Отримати загальну кількість товарів
            total_products = await self.scraper.get_total_products()
            
            # Створити progress tracker
            self.progress_tracker = ProgressTracker(
                total_items=total_products,
                update_interval=180  # 3 хвилини
            )
            
            # Запустити парсинг
            result = await self.scraper.scrape(self.progress_tracker)
            
            # Фінальний прогрес
            self.progress_tracker.finish()
            
            # Обчислити статистику
            elapsed_time = time.time() - start_time
            avg_speed = result['success_count'] / (elapsed_time / 60) if elapsed_time > 0 else 0
            
            # Експортувати помилки окремо
            if result['error_count'] > 0:
                self.csv_exporter.export_errors(self.output_dir / "errors.csv")
            
            # Очистити checkpoint після успішного завершення
            if result['error_count'] == 0:
                self.checkpoint_manager.clear()
            
            # Підсумки
            final_result = {
                'success_count': result['success_count'],
                'error_count': result['error_count'],
                'total_count': result['total_count'],
                'total_time': self._format_time(elapsed_time),
                'avg_speed': avg_speed,
                'output_dir': str(self.output_dir),
                'csv_file': str(self.output_dir / "products.csv"),
                'pdf_count': result.get('pdf_count', 0),
                'json_count': result.get('json_count', 0),
                'error_file': str(self.output_dir / "errors.csv") if result['error_count'] > 0 else None
            }
            
            self.logger.info(f"✅ Парсинг завершено: {result['success_count']}/{result['total_count']} успішно")
            
            return final_result
        
        except Exception as e:
            self.logger.error(f"💥 Критична помилка парсингу: {e}", exc_info=True)
            raise
    
    def _format_time(self, seconds: float) -> str:
        """Форматувати час"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}год {minutes}хв {secs}с"
        elif minutes > 0:
            return f"{minutes}хв {secs}с"
        else:
            return f"{secs}с"



