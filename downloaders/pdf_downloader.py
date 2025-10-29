"""
Async PDF downloader - асинхронне завантаження PDF файлів
"""

import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

import aiohttp
import aiofiles
from rich.progress import Progress, DownloadColumn, TransferSpeedColumn

from utils.logger import get_logger


class PDFDownloader:
    """Асинхронний завантажувач PDF файлів"""
    
    def __init__(
        self,
        output_dir: Path,
        workers: int = 100,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Args:
            output_dir: Директорія для збереження PDF
            workers: Кількість паралельних завантажень
            timeout: Timeout для кожного завантаження
            max_retries: Максимальна кількість повторів
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.workers = workers
        self.timeout = timeout
        self.max_retries = max_retries
        
        self.semaphore = asyncio.Semaphore(workers)
        self.logger = get_logger()
        
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'bytes_downloaded': 0
        }
    
    async def download_batch(
        self,
        pdf_items: List[Dict[str, str]],
        show_progress: bool = True
    ) -> Dict[str, Any]:
        """
        Завантажити пакет PDF файлів
        
        Args:
            pdf_items: Список словників {'product_id': '...', 'pdf_url': '...'}
            show_progress: Показувати прогрес
        
        Returns:
            Статистика завантаження
        """
        self.stats['total'] = len(pdf_items)
        self.logger.info(f"Початок завантаження {len(pdf_items)} PDF файлів...")
        
        start_time = time.time()
        
        # Створити задачі
        tasks = []
        for item in pdf_items:
            task = self._download_with_retry(
                pdf_url=item['pdf_url'],
                product_id=item['product_id']
            )
            tasks.append(task)
        
        # Виконати всі задачі
        await asyncio.gather(*tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        
        self.logger.info(
            f"Завантаження завершено: {self.stats['success']}/{self.stats['total']} успішно "
            f"за {elapsed:.1f}с"
        )
        
        return {
            **self.stats,
            'elapsed_time': elapsed,
            'avg_speed': self.stats['success'] / elapsed if elapsed > 0 else 0
        }
    
    async def download_single(
        self,
        pdf_url: str,
        product_id: str
    ) -> Optional[str]:
        """
        Завантажити один PDF файл
        
        Args:
            pdf_url: URL PDF файлу
            product_id: ID товару
        
        Returns:
            Шлях до збереженого файлу або None
        """
        return await self._download_with_retry(pdf_url, product_id)
    
    async def _download_with_retry(
        self,
        pdf_url: str,
        product_id: str
    ) -> Optional[str]:
        """Завантажити з повторними спробами"""
        async with self.semaphore:
            pdf_path = self.output_dir / f"{product_id}.pdf"
            
            # Перевірити чи вже існує
            if pdf_path.exists():
                self.stats['skipped'] += 1
                return str(pdf_path)
            
            # Спробувати завантажити
            for attempt in range(self.max_retries):
                try:
                    success = await self._download_file(pdf_url, pdf_path)
                    
                    if success:
                        self.stats['success'] += 1
                        return str(pdf_path)
                
                except Exception as e:
                    self.logger.debug(f"Спроба {attempt + 1} не вдалась для {pdf_url}: {e}")
                    
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Експоненційна затримка
            
            # Всі спроби невдалі
            self.stats['failed'] += 1
            self.logger.warning(f"Не вдалося завантажити PDF: {pdf_url}")
            return None
    
    async def _download_file(self, url: str, output_path: Path) -> bool:
        """Завантажити файл"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    
                    # Перевірити чи це дійсно PDF
                    if not content.startswith(b'%PDF'):
                        self.logger.warning(f"Файл не є PDF: {url}")
                        return False
                    
                    # Зберегти файл
                    async with aiofiles.open(output_path, 'wb') as f:
                        await f.write(content)
                    
                    self.stats['bytes_downloaded'] += len(content)
                    return True
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Отримати статистику"""
        return self.stats.copy()


async def download_pdfs_from_csv(
    csv_file: Path,
    output_dir: Path,
    workers: int = 100
) -> Dict[str, Any]:
    """
    Завантажити всі PDF з CSV файлу
    
    Args:
        csv_file: Шлях до CSV з колонками product_id, pdf_url
        output_dir: Директорія для збереження
        workers: Кількість паралельних завантажень
    
    Returns:
        Статистика завантаження
    """
    import pandas as pd
    
    # Прочитати CSV
    df = pd.read_csv(csv_file)
    
    # Відфільтрувати рядки з PDF
    df_with_pdf = df[df['pdf_url'].notna() & (df['pdf_url'] != '')]
    
    # Підготувати список для завантаження
    pdf_items = [
        {'product_id': row['product_id'], 'pdf_url': row['pdf_url']}
        for _, row in df_with_pdf.iterrows()
    ]
    
    # Завантажити
    downloader = PDFDownloader(output_dir, workers=workers)
    return await downloader.download_batch(pdf_items)



