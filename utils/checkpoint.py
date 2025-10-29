"""
Checkpoint system for resuming interrupted scraping
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime


class CheckpointManager:
    """Менеджер checkpoint'ів для відновлення парсингу"""
    
    def __init__(self, site_name: str, checkpoint_dir: str = "checkpoints"):
        """
        Args:
            site_name: Назва сайту
            checkpoint_dir: Папка для checkpoint файлів
        """
        self.site_name = site_name
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        self.checkpoint_file = self.checkpoint_dir / f"{site_name}_checkpoint.json"
        self.state: Dict[str, Any] = {}
        
        if self.checkpoint_file.exists():
            self.load()
    
    def save(self, state: Dict[str, Any]):
        """
        Зберегти checkpoint
        
        Args:
            state: Стан для збереження (processed_count, current_page, тощо)
        """
        self.state = {
            **state,
            'site_name': self.site_name,
            'last_updated': datetime.now().isoformat(),
            'checkpoint_version': '1.0'
        }
        
        # Зберегти в файл
        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
    
    def load(self) -> Dict[str, Any]:
        """
        Завантажити checkpoint
        
        Returns:
            Збережений стан
        """
        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                self.state = json.load(f)
            return self.state
        except Exception as e:
            print(f"Помилка завантаження checkpoint: {e}")
            return {}
    
    def update(self, updates: Dict[str, Any]):
        """
        Оновити checkpoint (додати нові дані без перезапису всього)
        
        Args:
            updates: Оновлення для стану
        """
        self.state.update(updates)
        self.state['last_updated'] = datetime.now().isoformat()
        
        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
    
    def exists(self) -> bool:
        """Перевірити чи існує checkpoint"""
        return self.checkpoint_file.exists()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Отримати значення зі стану"""
        return self.state.get(key, default)
    
    def clear(self):
        """Видалити checkpoint"""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
        self.state = {}
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Отримати прогрес парсингу
        
        Returns:
            Інформація про прогрес
        """
        return {
            'processed': self.get('processed_count', 0),
            'total': self.get('total_count', 0),
            'success': self.get('success_count', 0),
            'errors': self.get('error_count', 0),
            'last_updated': self.get('last_updated', 'N/A'),
            'percentage': self._calculate_percentage()
        }
    
    def _calculate_percentage(self) -> float:
        """Розрахувати відсоток виконання"""
        processed = self.get('processed_count', 0)
        total = self.get('total_count', 1)
        return (processed / total * 100) if total > 0 else 0
    
    def add_processed_items(self, items: List[str]):
        """
        Додати оброблені товари до checkpoint
        
        Args:
            items: Список ID оброблених товарів
        """
        processed = self.get('processed_items', [])
        processed.extend(items)
        self.update({'processed_items': processed})
    
    def is_processed(self, item_id: str) -> bool:
        """
        Перевірити чи товар вже оброблено
        
        Args:
            item_id: ID товару
        
        Returns:
            True якщо оброблено
        """
        processed = self.get('processed_items', [])
        return item_id in processed


class PeriodicCheckpoint:
    """Автоматичне збереження checkpoint кожні N товарів"""
    
    def __init__(self, manager: CheckpointManager, save_every: int = 1000):
        """
        Args:
            manager: CheckpointManager
            save_every: Зберігати checkpoint кожні N товарів
        """
        self.manager = manager
        self.save_every = save_every
        self.counter = 0
    
    def increment(self, state: Dict[str, Any]):
        """
        Інкрементувати лічильник і зберегти checkpoint при потребі
        
        Args:
            state: Поточний стан для збереження
        """
        self.counter += 1
        
        if self.counter % self.save_every == 0:
            self.manager.save(state)
    
    def force_save(self, state: Dict[str, Any]):
        """Примусово зберегти checkpoint"""
        self.manager.save(state)



