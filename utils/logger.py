"""
Logging utilities with structured logging
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from loguru import logger
import yaml


class ScraperLogger:
    """Кастомний логер для скрапера"""
    
    def __init__(self, log_dir: str = "output", site_name: Optional[str] = None):
        self.log_dir = Path(log_dir)
        self.site_name = site_name
        self.logger = logger
        
    def setup(self, level: str = "INFO"):
        """Налаштувати логер"""
        # Видалити дефолтний handler
        self.logger.remove()
        
        # Console handler (тільки INFO і вище)
        self.logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level=level,
            colorize=True
        )
        
        # File handler для детальних логів
        if self.site_name:
            log_file = self.log_dir / f"{self.site_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            self.logger.add(
                log_file,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                level="DEBUG",
                rotation="100 MB",
                retention="7 days",
                encoding="utf-8"
            )
        
        return self.logger


def setup_logger(level: str = "INFO", site_name: Optional[str] = None) -> logger:
    """
    Швидке налаштування логера
    
    Args:
        level: Рівень логування (DEBUG, INFO, WARNING, ERROR)
        site_name: Назва сайту для логування в окремий файл
    
    Returns:
        Налаштований логер
    """
    scraper_logger = ScraperLogger(site_name=site_name)
    return scraper_logger.setup(level)


def get_logger():
    """Отримати поточний логер"""
    return logger


def load_config(config_path: str = "config.yaml") -> dict:
    """Завантажити конфігурацію"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)



