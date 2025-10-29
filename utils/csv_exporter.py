"""
CSV export utilities
"""

import csv
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

import pandas as pd


class CSVExporter:
    """Експорт даних товарів в CSV"""
    
    def __init__(self, output_path: str):
        """
        Args:
            output_path: Шлях до вихідного CSV файлу
        """
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.fieldnames = [
            'product_id',
            'name',
            'url',
            'price',
            'category',
            'pdf_url',
            'pdf_downloaded',
            'pdf_filename',
            'status',
            'scraped_at'
        ]
        
        # Створити файл з заголовками якщо не існує
        if not self.output_path.exists():
            self._init_file()
    
    def _init_file(self):
        """Ініціалізувати CSV файл з заголовками"""
        with open(self.output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writeheader()
    
    def add_product(self, product: Dict[str, Any]):
        """
        Додати один товар до CSV
        
        Args:
            product: Словник з даними товару
        """
        # Доповнити відсутні поля
        row = {field: product.get(field, '') for field in self.fieldnames}
        
        # Додати timestamp якщо не вказано
        if not row.get('scraped_at'):
            row['scraped_at'] = datetime.now().isoformat()
        
        # Записати в файл
        with open(self.output_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writerow(row)
    
    def add_products_batch(self, products: List[Dict[str, Any]]):
        """
        Додати пакет товарів до CSV
        
        Args:
            products: Список словників з даними товарів
        """
        if not products:
            return
        
        with open(self.output_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            
            for product in products:
                row = {field: product.get(field, '') for field in self.fieldnames}
                if not row.get('scraped_at'):
                    row['scraped_at'] = datetime.now().isoformat()
                writer.writerow(row)
    
    def update_product(self, product_id: str, updates: Dict[str, Any]):
        """
        Оновити існуючий товар в CSV
        
        Args:
            product_id: ID товару для оновлення
            updates: Словник з оновленнями
        """
        # Прочитати весь файл
        df = pd.read_csv(self.output_path)
        
        # Оновити потрібний рядок
        mask = df['product_id'] == product_id
        for key, value in updates.items():
            if key in df.columns:
                df.loc[mask, key] = value
        
        # Записати назад
        df.to_csv(self.output_path, index=False, encoding='utf-8')
    
    def get_stats(self) -> Dict[str, int]:
        """
        Отримати статистику по CSV файлу
        
        Returns:
            Словник зі статистикою
        """
        if not self.output_path.exists():
            return {
                'total': 0,
                'success': 0,
                'errors': 0,
                'pdf_downloaded': 0
            }
        
        df = pd.read_csv(self.output_path)
        
        return {
            'total': len(df),
            'success': len(df[df['status'] == 'success']),
            'errors': len(df[df['status'] == 'error']),
            'pdf_downloaded': len(df[df['pdf_downloaded'] == True])
        }
    
    def export_errors(self, error_file: str):
        """
        Експортувати тільки помилки в окремий файл
        
        Args:
            error_file: Шлях до файлу з помилками
        """
        if not self.output_path.exists():
            return
        
        df = pd.read_csv(self.output_path)
        errors_df = df[df['status'] == 'error']
        
        if not errors_df.empty:
            errors_df.to_csv(error_file, index=False, encoding='utf-8')


def merge_csv_files(input_files: List[str], output_file: str):
    """
    Об'єднати кілька CSV файлів в один
    
    Args:
        input_files: Список шляхів до вхідних CSV файлів
        output_file: Шлях до вихідного файлу
    """
    dfs = []
    for file in input_files:
        if Path(file).exists():
            dfs.append(pd.read_csv(file))
    
    if dfs:
        combined = pd.concat(dfs, ignore_index=True)
        # Видалити дублікати по product_id
        combined = combined.drop_duplicates(subset=['product_id'], keep='first')
        combined.to_csv(output_file, index=False, encoding='utf-8')



