"""
Progress tracking and display utilities
"""

import time
from datetime import datetime, timedelta
from typing import Optional
from threading import Lock

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    DownloadColumn,
    TransferSpeedColumn
)
from rich.live import Live
from rich.table import Table
from rich.panel import Panel


class ProgressTracker:
    """Трекер прогресу парсингу з ETA та статистикою"""
    
    def __init__(self, total_items: int, update_interval: int = 180):
        """
        Args:
            total_items: Загальна кількість товарів
            update_interval: Інтервал оновлення в секундах (180 = 3 хвилини)
        """
        self.total_items = total_items
        self.update_interval = update_interval
        self.processed_items = 0
        self.success_count = 0
        self.error_count = 0
        self.start_time = time.time()
        self.last_update = time.time()
        self.errors = []
        self.lock = Lock()
        
        self.console = Console()
        
    def increment(self, success: bool = True, error_msg: Optional[str] = None):
        """
        Інкрементувати лічильник
        
        Args:
            success: Чи успішно оброблено товар
            error_msg: Повідомлення помилки якщо є
        """
        with self.lock:
            self.processed_items += 1
            if success:
                self.success_count += 1
            else:
                self.error_count += 1
                if error_msg:
                    self.errors.append({
                        'timestamp': datetime.now().isoformat(),
                        'message': error_msg
                    })
            
            # Перевірити чи потрібно оновити display
            if time.time() - self.last_update >= self.update_interval:
                self.display()
                self.last_update = time.time()
    
    def get_stats(self) -> dict:
        """Отримати поточну статистику"""
        elapsed = time.time() - self.start_time
        speed = self.processed_items / elapsed if elapsed > 0 else 0
        remaining = self.total_items - self.processed_items
        eta_seconds = remaining / speed if speed > 0 else 0
        
        return {
            'processed': self.processed_items,
            'total': self.total_items,
            'success': self.success_count,
            'errors': self.error_count,
            'percentage': (self.processed_items / self.total_items * 100) if self.total_items > 0 else 0,
            'speed': speed * 60,  # items per minute
            'elapsed': elapsed,
            'eta_seconds': eta_seconds,
            'eta': str(timedelta(seconds=int(eta_seconds)))
        }
    
    def display(self):
        """Відобразити прогрес"""
        stats = self.get_stats()
        
        # Створити таблицю статистики
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="cyan")
        table.add_column("Value", style="bold")
        
        # Прогрес
        progress_bar = "█" * int(stats['percentage'] / 2) + "░" * (50 - int(stats['percentage'] / 2))
        table.add_row(
            "Прогрес:",
            f"{progress_bar} {stats['percentage']:.1f}% ({stats['processed']:,}/{stats['total']:,})"
        )
        
        # Швидкість
        table.add_row("Швидкість:", f"{stats['speed']:.0f} items/min")
        
        # ETA
        table.add_row("Залишилось:", f"~{stats['eta']}")
        
        # Успішність
        success_rate = (stats['success'] / stats['processed'] * 100) if stats['processed'] > 0 else 0
        table.add_row("Успішність:", f"{success_rate:.1f}% ({stats['success']:,} успішно, {stats['errors']} помилок)")
        
        # Час роботи
        elapsed_str = str(timedelta(seconds=int(stats['elapsed'])))
        table.add_row("Час роботи:", elapsed_str)
        
        self.console.print("\n")
        self.console.print(Panel(table, title="📊 Прогрес парсингу", border_style="cyan"))
    
    def log_error(self, error_msg: str):
        """
        Логувати помилку в реальному часі
        
        Args:
            error_msg: Повідомлення помилки
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.print(f"[red]❌ [{timestamp}] Помилка:[/red] {error_msg}")
    
    def finish(self):
        """Фінальне відображення результатів"""
        stats = self.get_stats()
        self.console.print("\n" + "="*70)
        self.display()


class SimpleProgress:
    """Простий прогрес-бар для швидких операцій"""
    
    def __init__(self, description: str = "Processing"):
        self.description = description
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=Console()
        )
    
    def __enter__(self):
        self.progress.__enter__()
        return self.progress
    
    def __exit__(self, *args):
        self.progress.__exit__(*args)


def create_download_progress() -> Progress:
    """Створити прогрес-бар для завантаження файлів"""
    return Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=Console()
    )



