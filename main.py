#!/usr/bin/env python3
"""
Multi-Site Scraper - Інтелектуальний багатосайтовий скрапер
CLI точка входу
"""

import sys
import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from core.analyzer import SiteAnalyzer
from core.counter import ProductCounter
from core.orchestrator import ScrapingOrchestrator
from utils.logger import setup_logger, get_logger

console = Console()
logger = None


def print_banner():
    """Вивести банер програми"""
    banner = Text()
    banner.append("🕷️  Multi-Site Scraper\n", style="bold cyan")
    banner.append("Інтелектуальний багатосайтовий парсер\n", style="dim")
    console.print(Panel(banner, border_style="cyan"))


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """
    Multi-Site Scraper - інструмент для парсингу великих e-commerce сайтів
    
    Використання:
        python main.py count <url>      # Швидкий підрахунок товарів
        python main.py analyze <url>    # Аналіз структури сайту
        python main.py scrape <url>     # Запуск парсингу
    """
    global logger
    logger = setup_logger()
    print_banner()


@cli.command()
@click.argument('url')
@click.option('--max-depth', default=10, help='Максимальна глибина сканування')
@click.option('--timeout', default=60, help='Timeout в секундах')
@click.option('--output', default=None, help='Файл для збереження результатів')
def count(url: str, max_depth: int, timeout: int, output: str):
    """
    Швидкий підрахунок товарів на сайті
    
    Приклад:
        python main.py count https://www.pointp.fr/
    """
    console.print(f"\n[cyan]🔍 Швидкий підрахунок товарів на:[/cyan] [bold]{url}[/bold]\n")
    
    try:
        counter = ProductCounter(url, max_depth=max_depth, timeout=timeout)
        result = asyncio.run(counter.count())
        
        # Вивести результати
        console.print(Panel(
            f"[green]✓[/green] Знайдено товарів: [bold cyan]{result['total_products']:,}[/bold cyan]\n"
            f"[green]✓[/green] Категорій: [bold]{result['categories']:,}[/bold]\n"
            f"[green]✓[/green] Час сканування: [bold]{result['scan_time']:.1f}с[/bold]",
            title="📊 Результати підрахунку",
            border_style="green"
        ))
        
        # Зберегти результати якщо вказано output
        if output:
            counter.save_results(result, output)
            console.print(f"[dim]Результати збережено в: {output}[/dim]")
        
        # Оцінка часу парсингу
        estimated_time = result['total_products'] / 300  # ~300 товарів/хв в середньому
        hours = int(estimated_time / 60)
        minutes = int(estimated_time % 60)
        console.print(f"\n[yellow]⏱️  Оцінений час парсингу:[/yellow] [bold]~{hours}год {minutes}хв[/bold]")
        
    except Exception as e:
        console.print(f"[red]❌ Помилка:[/red] {str(e)}")
        logger.error(f"Помилка підрахунку: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('url')
@click.option('--save-config', is_flag=True, help='Зберегти конфігурацію для сайту')
@click.option('--quick', is_flag=True, help='Швидкий аналіз (без глибокої перевірки)')
def analyze(url: str, save_config: bool, quick: bool):
    """
    Аналіз структури та технологій сайту
    
    Приклад:
        python main.py analyze https://www.pointp.fr/
        python main.py analyze https://www.pointp.fr/ --save-config
    """
    console.print(f"\n[cyan]🔬 Аналізую сайт:[/cyan] [bold]{url}[/bold]\n")
    
    try:
        analyzer = SiteAnalyzer(url, quick_mode=quick)
        result = asyncio.run(analyzer.analyze())
        
        # Вивести результати аналізу
        _display_analysis_results(result)
        
        # Зберегти конфігурацію якщо потрібно
        if save_config:
            config_path = analyzer.save_config(result)
            console.print(f"\n[green]✓[/green] Конфігурацію збережено: [bold]{config_path}[/bold]")
            console.print("[dim]Відредагуйте файл за потребою перед запуском scrape[/dim]")
        
    except Exception as e:
        console.print(f"[red]❌ Помилка:[/red] {str(e)}")
        logger.error(f"Помилка аналізу: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('url')
@click.option('--config', default=None, help='Шлях до конфігураційного файлу сайту')
@click.option('--resume', is_flag=True, help='Продовжити перерваний парсинг')
@click.option('--workers', default=None, type=int, help='Кількість паралельних потоків')
def scrape(url: str, config: str, resume: bool, workers: int):
    """
    Запуск парсингу сайту
    
    Приклад:
        python main.py scrape https://www.pointp.fr/
        python main.py scrape https://www.pointp.fr/ --config sites/pointp_fr.yaml
        python main.py scrape https://www.pointp.fr/ --resume
    """
    console.print(f"\n[cyan]🚀 Запускаю парсинг:[/cyan] [bold]{url}[/bold]\n")
    
    if resume:
        console.print("[yellow]⏮️  Режим відновлення - продовжую з останнього checkpoint[/yellow]\n")
    
    try:
        orchestrator = ScrapingOrchestrator(
            url=url,
            config_path=config,
            resume=resume,
            workers=workers
        )
        
        # Підтвердження перед запуском
        if not resume:
            stats = orchestrator.get_estimated_stats()
            console.print(Panel(
                f"[cyan]Товарів до обробки:[/cyan] [bold]{stats['total_products']:,}[/bold]\n"
                f"[cyan]Підхід:[/cyan] [bold]{stats['approach']}[/bold]\n"
                f"[cyan]Оцінений час:[/cyan] [bold]{stats['estimated_time']}[/bold]\n"
                f"[cyan]Паралельні потоки:[/cyan] [bold]{stats['workers']}[/bold]",
                title="📋 План парсингу",
                border_style="cyan"
            ))
            
            if not click.confirm('\nРозпочати парсинг?', default=True):
                console.print("[yellow]Скасовано користувачем[/yellow]")
                return
        
        # Запуск парсингу
        console.print("\n[green]▶️  Парсинг розпочато...[/green]\n")
        result = asyncio.run(orchestrator.run())
        
        # Вивести підсумки
        _display_scraping_results(result)
        
    except KeyboardInterrupt:
        console.print("\n\n[yellow]⏸️  Парсинг зупинено користувачем[/yellow]")
        console.print("[dim]Використайте --resume для продовження[/dim]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]❌ Критична помилка:[/red] {str(e)}")
        logger.error(f"Помилка парсингу: {e}", exc_info=True)
        sys.exit(1)


def _display_analysis_results(result: dict):
    """Відобразити результати аналізу"""
    # Основна інформація
    info_text = (
        f"[cyan]Сайт:[/cyan] [bold]{result['site_name']}[/bold]\n"
        f"[cyan]Товарів знайдено:[/cyan] [bold cyan]~{result['total_products']:,}[/bold cyan]\n"
    )
    
    # API
    api_status = "✓" if result['has_api'] else "✗"
    api_color = "green" if result['has_api'] else "red"
    info_text += f"[{api_color}]{api_status}[/{api_color}] API виявлено: "
    if result['has_api']:
        info_text += f"[bold]{result['api_type']}[/bold]\n"
    else:
        info_text += "[dim]Ні[/dim]\n"
    
    # JS рендеринг
    js_level = result['js_rendering']
    js_text = f"[cyan]JS рендеринг:[/cyan] "
    if js_level == "none":
        js_text += "[green]Статичний[/green]"
    elif js_level == "partial":
        js_text += f"[yellow]Частковий ({result.get('js_percentage', 0)}%)[/yellow]"
    else:
        js_text += "[red]Повний[/red]"
    info_text += js_text + "\n"
    
    # Sitemap
    sitemap_status = "✓" if result['has_sitemap'] else "✗"
    sitemap_color = "green" if result['has_sitemap'] else "yellow"
    info_text += f"[{sitemap_color}]{sitemap_status}[/{sitemap_color}] Sitemap: "
    info_text += "[bold]Так[/bold]\n" if result['has_sitemap'] else "[dim]Ні[/dim]\n"
    
    # Захист
    protection = result.get('protection', 'none')
    if protection != 'none':
        info_text += f"[red]⚠️[/red] Захист: [bold]{protection}[/bold]\n"
    else:
        info_text += "[green]✓[/green] Захист: [dim]Не виявлено[/dim]\n"
    
    console.print(Panel(info_text, title="📊 РЕЗУЛЬТАТИ АНАЛІЗУ", border_style="cyan"))
    
    # Рекомендації
    console.print(Panel(
        f"[cyan]Рекомендований підхід:[/cyan] [bold green]{result['recommended_approach']}[/bold green]\n"
        f"[cyan]Оцінений час:[/cyan] [bold]{result['estimated_time']}[/bold]",
        title="💡 РЕКОМЕНДАЦІЇ",
        border_style="green"
    ))


def _display_scraping_results(result: dict):
    """Відобразити результати парсингу"""
    success_rate = (result['success_count'] / result['total_count'] * 100) if result['total_count'] > 0 else 0
    
    console.print("\n" + "="*60)
    console.print(Panel(
        f"[green]✓[/green] Успішно оброблено: [bold green]{result['success_count']:,}[/bold green]\n"
        f"[red]✗[/red] Помилок: [bold]{result['error_count']:,}[/bold]\n"
        f"[cyan]📊[/cyan] Успішність: [bold]{success_rate:.1f}%[/bold]\n"
        f"[cyan]⏱️[/cyan] Загальний час: [bold]{result['total_time']}[/bold]\n"
        f"[cyan]⚡[/cyan] Середня швидкість: [bold]{result['avg_speed']:.0f} items/min[/bold]",
        title="🎉 ПАРСИНГ ЗАВЕРШЕНО",
        border_style="green"
    ))
    
    # Деталі
    console.print(f"\n[cyan]📁 Результати збережено в:[/cyan] [bold]{result['output_dir']}[/bold]")
    console.print(f"   [dim]├── CSV файл: {result['csv_file']}[/dim]")
    console.print(f"   [dim]├── PDF файлів: {result['pdf_count']:,}[/dim]")
    console.print(f"   [dim]└── JSON карток: {result['json_count']:,}[/dim]")
    
    if result['error_count'] > 0:
        console.print(f"\n[yellow]⚠️  Перевірте файл помилок:[/yellow] [bold]{result['error_file']}[/bold]")


if __name__ == '__main__':
    try:
        cli()
    except Exception as e:
        console.print(f"\n[red]💥 Критична помилка:[/red] {str(e)}")
        sys.exit(1)



