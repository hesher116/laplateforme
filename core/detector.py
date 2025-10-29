"""
Site detector - визначення типу сайту та технологій
"""

import asyncio
import re
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from utils.logger import get_logger


class SiteDetector:
    """Детектор типу сайту та використовуваних технологій"""
    
    def __init__(self, url: str):
        """
        Args:
            url: URL сайту для аналізу
        """
        self.url = url.rstrip('/')
        self.domain = urlparse(url).netloc
        self.logger = get_logger()
    
    async def detect(self) -> Dict[str, Any]:
        """
        Виявити тип сайту та технології
        
        Returns:
            Словник з результатами детекції
        """
        self.logger.info(f"Детекція технологій для {self.url}")
        
        results = {
            'url': self.url,
            'domain': self.domain,
            'has_api': False,
            'api_type': None,
            'api_endpoints': [],
            'js_rendering': 'unknown',
            'framework': None,
            'protection': None,
            'has_sitemap': False,
            'robots_txt': None
        }
        
        # Паралельно виконати всі перевірки
        await asyncio.gather(
            self._detect_api(results),
            self._detect_js_rendering(results),
            self._detect_framework(results),
            self._detect_protection(results),
            self._check_sitemap(results),
            self._check_robots(results),
            return_exceptions=True
        )
        
        return results
    
    async def _detect_api(self, results: Dict[str, Any]):
        """Виявити API endpoints"""
        try:
            async with aiohttp.ClientSession() as session:
                # Перевірити типові API endpoints
                api_paths = [
                    '/api',
                    '/api/v1',
                    '/api/products',
                    '/graphql',
                    '/rest/v1',
                    '/_next/data',  # Next.js
                ]
                
                for path in api_paths:
                    try:
                        url = f"{self.url}{path}"
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                            if response.status == 200:
                                content_type = response.headers.get('Content-Type', '')
                                
                                if 'json' in content_type.lower():
                                    results['has_api'] = True
                                    results['api_endpoints'].append(url)
                                    
                                    # Визначити тип API
                                    if 'graphql' in path:
                                        results['api_type'] = 'GraphQL'
                                    elif 'rest' in path or 'api' in path:
                                        results['api_type'] = 'REST'
                    except Exception:
                        continue
                
                # Також перевірити через браузер (перехоплення Network requests)
                if not results['has_api']:
                    api_info = await self._detect_api_via_browser()
                    if api_info:
                        results.update(api_info)
        
        except Exception as e:
            self.logger.debug(f"Помилка детекції API: {e}")
    
    async def _detect_api_via_browser(self) -> Optional[Dict[str, Any]]:
        """Виявити API через перехоплення запитів браузера"""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                api_requests = []
                
                # Перехоплювати запити
                async def handle_request(request):
                    if any(keyword in request.url.lower() for keyword in ['api', 'json', 'graphql']):
                        api_requests.append({
                            'url': request.url,
                            'method': request.method,
                            'resource_type': request.resource_type
                        })
                
                page.on('request', handle_request)
                
                # Завантажити головну сторінку
                await page.goto(self.url, wait_until='networkidle', timeout=10000)
                
                await browser.close()
                
                if api_requests:
                    # Аналізувати знайдені API запити
                    json_requests = [r for r in api_requests if 'json' in r['url'] or r['resource_type'] == 'fetch']
                    
                    if json_requests:
                        return {
                            'has_api': True,
                            'api_type': 'REST' if not any('graphql' in r['url'] for r in json_requests) else 'GraphQL',
                            'api_endpoints': [r['url'] for r in json_requests[:5]]
                        }
        
        except Exception as e:
            self.logger.debug(f"Помилка детекції API через браузер: {e}")
        
        return None
    
    async def _detect_js_rendering(self, results: Dict[str, Any]):
        """Виявити чи використовується JS рендеринг"""
        try:
            # Порівняти контент без JS та з JS
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    html_no_js = await response.text()
            
            # Завантажити з JS
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(self.url, wait_until='networkidle', timeout=15000)
                html_with_js = await page.content()
                await browser.close()
            
            # Порівняти
            soup_no_js = BeautifulSoup(html_no_js, 'lxml')
            soup_with_js = BeautifulSoup(html_with_js, 'lxml')
            
            # Порівняти кількість елементів
            elements_no_js = len(soup_no_js.find_all())
            elements_with_js = len(soup_with_js.find_all())
            
            difference = abs(elements_with_js - elements_no_js) / elements_no_js if elements_no_js > 0 else 0
            
            if difference < 0.1:  # < 10% різниці
                results['js_rendering'] = 'none'
            elif difference < 0.3:  # 10-30%
                results['js_rendering'] = 'partial'
                results['js_percentage'] = int(difference * 100)
            else:  # > 30%
                results['js_rendering'] = 'full'
                results['js_percentage'] = int(difference * 100)
        
        except Exception as e:
            self.logger.debug(f"Помилка детекції JS: {e}")
            results['js_rendering'] = 'unknown'
    
    async def _detect_framework(self, results: Dict[str, Any]):
        """Виявити фреймворк/CMS"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    html = await response.text()
                    headers = response.headers
            
            # Аналізувати HTML
            soup = BeautifulSoup(html, 'lxml')
            
            # Перевірити мета-теги
            generator = soup.find('meta', attrs={'name': 'generator'})
            if generator:
                results['framework'] = generator.get('content', 'Unknown')
                return
            
            # Перевірити характерні ознаки фреймворків
            frameworks = {
                'React': ['react', '__NEXT_DATA__', '_next'],
                'Vue.js': ['vue', 'v-app', 'data-v-'],
                'Angular': ['ng-', 'angular', 'ng-version'],
                'WordPress': ['wp-content', 'wp-includes'],
                'Magento': ['magento', 'mage'],
                'Shopify': ['shopify', 'cdn.shopify'],
                'PrestaShop': ['prestashop', 'ps_'],
                'WooCommerce': ['woocommerce', 'wc-'],
            }
            
            html_lower = html.lower()
            for framework, patterns in frameworks.items():
                if any(pattern in html_lower for pattern in patterns):
                    results['framework'] = framework
                    return
            
            # Перевірити X-Powered-By header
            if 'X-Powered-By' in headers:
                results['framework'] = headers['X-Powered-By']
        
        except Exception as e:
            self.logger.debug(f"Помилка детекції фреймворка: {e}")
    
    async def _detect_protection(self, results: Dict[str, Any]):
        """Виявити анти-бот захист"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    html = await response.text()
                    headers = response.headers
            
            # Перевірити Cloudflare
            if 'cf-ray' in headers or 'cloudflare' in html.lower():
                results['protection'] = 'Cloudflare'
                return
            
            # Перевірити reCAPTCHA
            if 'recaptcha' in html.lower() or 'grecaptcha' in html.lower():
                results['protection'] = 'reCAPTCHA'
                return
            
            # Перевірити інші
            protection_keywords = {
                'Akamai': ['akamai'],
                'Imperva': ['imperva', 'incapsula'],
                'DataDome': ['datadome'],
                'PerimeterX': ['perimeterx', 'px-'],
            }
            
            html_lower = html.lower()
            for protection, keywords in protection_keywords.items():
                if any(kw in html_lower for kw in keywords):
                    results['protection'] = protection
                    return
            
            results['protection'] = 'none'
        
        except Exception as e:
            self.logger.debug(f"Помилка детекції захисту: {e}")
    
    async def _check_sitemap(self, results: Dict[str, Any]):
        """Перевірити наявність sitemap"""
        try:
            async with aiohttp.ClientSession() as session:
                sitemap_urls = [
                    f"{self.url}/sitemap.xml",
                    f"{self.url}/sitemap_index.xml",
                ]
                
                for sitemap_url in sitemap_urls:
                    try:
                        async with session.get(sitemap_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                            if response.status == 200:
                                results['has_sitemap'] = True
                                results['sitemap_url'] = sitemap_url
                                return
                    except Exception:
                        continue
        
        except Exception as e:
            self.logger.debug(f"Помилка перевірки sitemap: {e}")
    
    async def _check_robots(self, results: Dict[str, Any]):
        """Перевірити robots.txt"""
        try:
            async with aiohttp.ClientSession() as session:
                robots_url = f"{self.url}/robots.txt"
                async with session.get(robots_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        robots_content = await response.text()
                        results['robots_txt'] = robots_url
                        
                        # Перевірити чи є Sitemap в robots.txt
                        sitemap_match = re.search(r'Sitemap:\s*(.+)', robots_content, re.IGNORECASE)
                        if sitemap_match:
                            results['has_sitemap'] = True
                            results['sitemap_url'] = sitemap_match.group(1).strip()
        
        except Exception as e:
            self.logger.debug(f"Помилка перевірки robots.txt: {e}")


def recommend_scraping_approach(detection_result: Dict[str, Any]) -> str:
    """
    Рекомендувати підхід до парсингу на основі детекції
    
    Args:
        detection_result: Результат детекції сайту
    
    Returns:
        Рекомендований підхід: 'api', 'static', 'dynamic', 'hybrid'
    """
    # Якщо є API - використовувати його
    if detection_result.get('has_api'):
        return 'api'
    
    # Якщо повний JS рендеринг - dynamic
    if detection_result.get('js_rendering') == 'full':
        return 'dynamic'
    
    # Якщо статичний або частковий JS - hybrid
    if detection_result.get('js_rendering') in ['none', 'partial']:
        if detection_result.get('js_rendering') == 'none':
            return 'static'
        else:
            return 'hybrid'
    
    # За замовчуванням - hybrid
    return 'hybrid'



