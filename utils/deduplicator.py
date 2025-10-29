"""
Deduplication utilities to ensure unique products
"""

from typing import Set, Dict, Any, Optional
from pathlib import Path
import hashlib
import json


class ProductDeduplicator:
    """Видалення дублікатів товарів"""
    
    def __init__(self, checkpoint_file: Optional[str] = None):
        """
        Args:
            checkpoint_file: Файл для збереження унікальних ID
        """
        self.seen_ids: Set[str] = set()
        self.seen_urls: Set[str] = set()
        self.checkpoint_file = Path(checkpoint_file) if checkpoint_file else None
        
        if self.checkpoint_file and self.checkpoint_file.exists():
            self._load_checkpoint()
    
    def is_duplicate(self, product_id: str, url: str) -> bool:
        """
        Перевірити чи товар вже оброблено
        
        Args:
            product_id: ID товару
            url: URL товару
        
        Returns:
            True якщо дублікат, False якщо новий
        """
        # Перевірити по ID
        if product_id in self.seen_ids:
            return True
        
        # Перевірити по URL
        if url in self.seen_urls:
            return True
        
        return False
    
    def add(self, product_id: str, url: str):
        """
        Додати товар до списку оброблених
        
        Args:
            product_id: ID товару
            url: URL товару
        """
        self.seen_ids.add(product_id)
        self.seen_urls.add(url)
    
    def add_batch(self, products: list):
        """
        Додати пакет товарів
        
        Args:
            products: Список словників з 'product_id' та 'url'
        """
        for product in products:
            self.add(product.get('product_id', ''), product.get('url', ''))
    
    def save_checkpoint(self):
        """Зберегти checkpoint"""
        if not self.checkpoint_file:
            return
        
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'seen_ids': list(self.seen_ids),
            'seen_urls': list(self.seen_urls)
        }
        
        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load_checkpoint(self):
        """Завантажити checkpoint"""
        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.seen_ids = set(data.get('seen_ids', []))
                self.seen_urls = set(data.get('seen_urls', []))
        except Exception:
            pass
    
    def get_count(self) -> int:
        """Отримати кількість унікальних товарів"""
        return len(self.seen_ids)
    
    def clear(self):
        """Очистити всі дані"""
        self.seen_ids.clear()
        self.seen_urls.clear()


def extract_product_id_from_url(url: str) -> Optional[str]:
    """
    Спробувати витягти ID товару з URL
    
    Args:
        url: URL товару
    
    Returns:
        ID товару або None
    """
    import re
    
    # Для pointp.fr: /p/категорія/назва-ref-код-Aідентифікатор
    # Приклад: /p/outillage-quincaillerie/tenaille-russe-225-ref-l-xl20109-A6508045
    # Беремо A-код як ідентифікатор: A6508045
    
    # Спробувати витягти A-код
    match = re.search(r'-A(\d+)', url)
    if match:
        return match.group(1)
    
    # Спробувати витягти ref-код (між ref- та -A)
    match = re.search(r'-ref-([^-]+)-A', url)
    if match:
        return match.group(1).replace('-', '')
    
    # Загальні паттерни для інших сайтів
    patterns = [
        r'/product[s]?[/-](\d+)',
        r'/item[s]?[/-](\d+)',
        r'/p/(\d+)',
        r'[?&]id=(\d+)',
        r'/(\d{5,})',
        r'-(\d{5,})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def generate_product_id(product_data: Dict[str, Any]) -> str:
    """
    Згенерувати унікальний ID для товару на основі його даних
    
    Args:
        product_data: Дані товару
    
    Returns:
        Унікальний ID
    """
    # Спробувати витягти з URL
    url = product_data.get('url', '')
    product_id = extract_product_id_from_url(url)
    
    if product_id:
        return product_id
    
    # Якщо є явний SKU/артикул
    if 'sku' in product_data:
        return str(product_data['sku'])
    
    if 'article' in product_data:
        return str(product_data['article'])
    
    # Остання опція - хеш від URL
    return hashlib.md5(url.encode()).hexdigest()[:12]

