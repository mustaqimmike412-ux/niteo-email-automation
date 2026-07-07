"""
Chrome浏览器爬虫 - 使用Playwright模拟浏览器操作
直接在Chrome中抓取Google Maps和Google搜索结果，无需API Key

支持的搜索模式：
1. google_maps - Google Maps商家搜索（抓取名称、地址、电话、网站、评分等）
2. google_search - Google网页搜索（抓取标题、链接、摘要）

使用方式：
    pip install playwright
    playwright install chromium

特点：
- 使用headless Chrome，无需打开浏览器窗口
- 自动处理Google的动态加载和反爬机制
- 支持滚动加载更多结果
- 提取邮箱和电话号码
"""

import re
import time
import random
import logging
from typing import List, Optional, Dict, Any
from urllib.parse import quote

from services.search.base import BaseSearcher, SearchResult

logger = logging.getLogger(__name__)


class ChromeMapsScraper(BaseSearcher):
    """
    Google Maps Chrome爬虫
    通过Playwright模拟浏览器访问Google Maps搜索商家信息
    
    提取字段：公司名、地址、电话、网站、评分、评论数、类别
    """

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}
        self.headless = config.get('chrome_headless', True)
        self.scroll_pause = config.get('scroll_pause_seconds', 1.5)
        self.max_scroll_rounds = config.get('max_scroll_rounds', 5)
        self._playwright = None
        self._browser = None

    def is_available(self) -> bool:
        """检查Playwright是否可用"""
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            logger.warning("Playwright未安装。请执行: pip install playwright && playwright install chromium")
            return False

    def search(self, query: str, location: str = '', max_results: int = 20) -> List[SearchResult]:
        """
        搜索Google Maps
        
        Args:
            query: 搜索关键词 (如 "solar panel distributor")
            location: 地区 (如 "California, USA")
            max_results: 最大结果数
        """
        if not self.is_available():
            logger.error("Playwright不可用，无法执行Chrome爬虫")
            return []

        search_text = f"{query} in {location}" if location else query
        search_url = f"https://www.google.com/maps/search/{quote(search_text)}"
        
        results = []
        try:
            results = self._scrape_maps(search_url, search_text, max_results)
        except Exception as e:
            logger.error(f"[ChromeMapsScraper] 爬取失败: {e}")
        finally:
            self._cleanup()
        
        return results

    def _scrape_maps(self, url: str, search_text: str, max_results: int) -> List[SearchResult]:
        """执行Google Maps爬取"""
        from playwright.sync_api import sync_playwright
        
        results = []
        seen_names = set()
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                locale='en-US',
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            logger.info(f"[ChromeMapsScraper] 正在搜索: {search_text}")
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # 检测Google验证码/人机验证
            self._check_captcha(page, search_text)
            
            # 等待搜索结果加载
            try:
                page.wait_for_selector('div[role="feed"]', timeout=15000)
            except Exception:
                # 尝试备选选择器
                try:
                    page.wait_for_selector('.m6QErb, .bfdhyf', timeout=8000)
                except Exception:
                    logger.warning("[ChromeMapsScraper] 等待搜索结果超时，尝试继续...")
            time.sleep(2)
            
            # 滚动加载更多结果
            current_count = 0
            for round_num in range(self.max_scroll_rounds):
                if current_count >= max_results:
                    break
                
                # 提取当前可见的结果 - 使用多种选择器兼容不同版本
                items = page.query_selector_all('div[role="feed"] > div > div[jsaction]')
                if not items:
                    items = page.query_selector_all('.m6QErb div.Nv2PK, .m6QErb div[style*="margin-bottom"]')
                if not items:
                    items = page.query_selector_all('[jsaction*="mouseover"] .Nv2PK')
                for item in items:
                    if current_count >= max_results:
                        break
                    
                    try:
                        result = self._parse_maps_item(item, page)
                        if result and result.get('name') and result['name'] not in seen_names:
                            seen_names.add(result['name'])
                            results.append(SearchResult(
                                platform='google_places',
                                source_url=result.get('maps_link', ''),
                                raw_data=result
                            ))
                            current_count += 1
                            logger.info(f"[ChromeMapsScraper] 获取到第{current_count}条: {result['name']}")
                    except Exception as e:
                        logger.debug(f"[ChromeMapsScraper] 解析单条结果失败: {e}")
                        continue
                
                if current_count >= max_results:
                    break
                
                # 滚动到底部加载更多
                logger.info(f"[ChromeMapsScraper] 滚动加载更多结果... (已获取{current_count}/{max_results})")
                feed = page.query_selector('div[role="feed"]')
                if feed:
                    feed.evaluate('el => el.scrollTop = el.scrollHeight')
                else:
                    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                time.sleep(self.scroll_pause + random.uniform(0.5, 1.5))
                
                # 尝试点击"更多结果"按钮（如果出现）
                try:
                    more_btn = page.query_selector('button[aria-label*="更多结果"], button[aria-label*="More results"]')
                    if more_btn and more_btn.is_visible():
                        more_btn.click()
                        time.sleep(2)
                except Exception:
                    pass
            
            browser.close()
        
        logger.info(f"[ChromeMapsScraper] 搜索完成，共获取{len(results)}条结果")
        return results

    def _parse_maps_item(self, item, page) -> Optional[Dict[str, Any]]:
        """解析单条Google Maps搜索结果"""
        result = {
            'name': '',
            'address': '',
            'phone': '',
            'website': '',
            'rating': '',
            'review_count': '',
            'category': '',
            'maps_link': '',
            'country': '',
            'email': '',
        }
        
        try:
            # 获取名称和链接
            name_el = item.query_selector('a[href*="maps"] h3')
            if name_el:
                result['name'] = name_el.inner_text().strip()
            
            link_el = item.query_selector('a[href*="maps"]')
            if link_el:
                href = link_el.get_attribute('href') or ''
                result['maps_link'] = href
                if 'maps.google.com' in href:
                    result['maps_link'] = href
            
            # 获取地址
            # Google Maps的侧边面板会显示详情
            all_text = item.inner_text()
            
            # 从item文本中提取信息
            lines = [l.strip() for l in all_text.split('\n') if l.strip()]
            
            # 尝试点击item获取详情面板
            try:
                item.click()
                time.sleep(1.5)
                
                # 从详情面板提取更多信息
                info_panel = page.query_selector('div[role="feed"] ~ div, #pane, .m6QErb')
                if not info_panel:
                    info_panel = page.query_selector('h1')  # fallback
                
                if info_panel:
                    # 获取评分
                    try:
                        rating_el = page.query_selector('span[role="img"] > span:first-child')
                        if rating_el:
                            result['rating'] = rating_el.inner_text().strip()
                    except Exception:
                        pass
                    
                    # 获取电话
                    try:
                        buttons = page.query_selector_all('button[data-tooltip], button[aria-label*="电话"], button[aria-label*="Phone"]')
                        for btn in buttons:
                            tooltip = btn.get_attribute('data-tooltip') or btn.get_attribute('aria-label') or ''
                            if tooltip and re.search(r'[\d\-\+\(\)\s]{7,}', tooltip):
                                result['phone'] = tooltip.strip()
                                break
                    except Exception:
                        pass
                    
                    # 获取网站
                    try:
                        website_els = page.query_selector_all('a[href^="http"]')
                        for el in website_els:
                            href = el.get_attribute('href') or ''
                            text = el.inner_text().strip()
                            # 排除google自身链接
                            if ('google.com' not in href and 
                                text and 
                                not text.startswith('+') and
                                '.' in href):
                                result['website'] = href
                                break
                    except Exception:
                        pass
                    
                    # 从详情面板文本提取邮箱
                    try:
                        panel_text = page.inner_text('body')
                        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', panel_text)
                        if emails:
                            result['email'] = emails[0]
                    except Exception:
                        pass
                    
                    # 从地址提取国家
                    try:
                        address_el = page.query_selector('button[data-tooltip*="复制地址"], h2 + div, [data-item-id="address"]')
                        if address_el:
                            result['address'] = address_el.inner_text().strip()
                    except Exception:
                        pass
                    
                    # 关闭详情面板回到列表
                    try:
                        close_btn = page.query_selector('button[aria-label*="关闭"], button[aria-label*="Close"]')
                        if close_btn:
                            close_btn.click()
                            time.sleep(0.5)
                    except Exception:
                        # 尝试按Escape
                        page.keyboard.press('Escape')
                        time.sleep(0.5)
                        
            except Exception as e:
                logger.debug(f"[ChromeMapsScraper] 点击详情面板失败: {e}")
            
            # 从all_text中提取未获取到的信息（fallback）
            if not result['rating']:
                rating_match = re.search(r'(\d+\.?\d*)\s*(?:星|★|/5)', all_text)
                if rating_match:
                    result['rating'] = rating_match.group(1)
            
            if not result['phone']:
                phone_match = re.search(r'[\+]?[\d\s\-\(\)]{10,15}', all_text)
                if phone_match:
                    result['phone'] = phone_match.group(0).strip()
            
        except Exception as e:
            logger.debug(f"[ChromeMapsScraper] _parse_maps_item异常: {e}")
            return None
        
        return result if result['name'] else None

    def _cleanup(self):
        """清理资源"""
        pass  # 使用with上下文管理器，自动清理

    def _check_captcha(self, page, search_text: str):
        """检测Google人机验证，如果遇到则等待或报错"""
        time.sleep(2)
        # 检测常见验证码元素
        captcha_selectors = [
            'form[action*="captcha"]',
            '#captcha',
            '.g-recaptcha',
            'iframe[src*="recaptcha"]',
            '#consent-bump',  # Cookie consent
        ]
        for sel in captcha_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    logger.warning(f"[ChromeMapsScraper] 检测到人机验证/权限弹窗: {sel}")
                    # 尝试点击同意按钮
                    try:
                        consent_btns = page.query_selector_all('button[aria-label*="Accept"], button[aria-label*="同意"], button[aria-label*="I agree"], form button')
                        for btn in consent_btns:
                            if btn.is_visible():
                                btn.click()
                                time.sleep(2)
                                logger.info("[ChromeMapsScraper] 已点击同意按钮")
                                break
                    except Exception:
                        pass
                    break
            except Exception:
                pass


class ChromeSearchScraper(BaseSearcher):
    """
    Google搜索 Chrome爬虫
    通过Playwright模拟浏览器在google.com搜索
    
    提取字段：标题、链接、摘要、邮箱
    """

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}
        self.headless = config.get('chrome_headless', True)
        self.scroll_pause = config.get('scroll_pause_seconds', 1.5)
        self.max_scroll_rounds = config.get('max_scroll_rounds', 3)

    def is_available(self) -> bool:
        """检查Playwright是否可用"""
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            logger.warning("Playwright未安装。请执行: pip install playwright && playwright install chromium")
            return False

    def search(self, query: str, location: str = '', max_results: int = 20) -> List[SearchResult]:
        """
        搜索Google网页搜索
        
        Args:
            query: 搜索关键词
            location: 地区（会添加到搜索词中）
            max_results: 最大结果数
        """
        if not self.is_available():
            logger.error("Playwright不可用，无法执行Chrome爬虫")
            return []

        search_text = f"{query} {location}".strip() if location else query
        search_url = f"https://www.google.com/search?q={quote(search_text)}&num={max_results}"
        
        results = []
        try:
            results = self._scrape_search(search_url, max_results)
        except Exception as e:
            logger.error(f"[ChromeSearchScraper] 爬取失败: {e}")
        
        return results

    def _scrape_search(self, url: str, max_results: int) -> List[SearchResult]:
        """执行Google搜索爬取"""
        from playwright.sync_api import sync_playwright
        
        results = []
        seen_urls = set()
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                locale='en-US',
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            logger.info(f"[ChromeSearchScraper] 正在搜索: {url}")
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # 等待搜索结果加载
            try:
                page.wait_for_selector('#search', timeout=15000)
            except Exception:
                logger.warning("[ChromeSearchScraper] 等待#search超时，尝试继续...")
            time.sleep(2)
            
            # 提取搜索结果
            for round_num in range(self.max_scroll_rounds):
                if len(results) >= max_results:
                    break
                
                # Google搜索结果的选择器
                result_elements = page.query_selector_all('#search .g, #search div[data-sokoban-container] .g, #rso > div > div')
                
                for el in result_elements:
                    if len(results) >= max_results:
                        break
                    
                    try:
                        result = self._parse_search_item(el)
                        if result and result.get('website') and result['website'] not in seen_urls:
                            seen_urls.add(result['website'])
                            results.append(SearchResult(
                                platform='web_search',
                                source_url=result['website'],
                                raw_data=result
                            ))
                            logger.info(f"[ChromeSearchScraper] 获取到第{len(results)}条: {result.get('name', '')}")
                    except Exception as e:
                        logger.debug(f"[ChromeSearchScraper] 解析搜索结果失败: {e}")
                        continue
                
                if len(results) >= max_results:
                    break
                
                # 点击"更多结果"或滚动
                logger.info(f"[ChromeSearchScraper] 获取更多结果... ({len(results)}/{max_results})")
                
                # 尝试点击"更多结果"分页
                try:
                    more_btn = page.query_selector('#pnnext, a[aria-label*="更多"], a[id="pnnext"]')
                    if more_btn and more_btn.is_visible():
                        more_btn.click()
                        page.wait_for_load_state('domcontentloaded', timeout=10000)
                        time.sleep(2)
                        continue
                except Exception:
                    pass
                
                # 滚动加载
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                time.sleep(self.scroll_pause)
            
            browser.close()
        
        logger.info(f"[ChromeSearchScraper] 搜索完成，共获取{len(results)}条结果")
        return results

    def _parse_search_item(self, el) -> Optional[Dict[str, Any]]:
        """解析单条Google搜索结果"""
        result = {
            'name': '',
            'website': '',
            'description': '',
            'email': '',
            'phone': '',
            'country': '',
        }
        
        try:
            # 获取标题和链接
            title_el = el.query_selector('h3')
            link_el = el.query_selector('a[href^="http"]')
            
            if title_el:
                result['name'] = title_el.inner_text().strip()
            if link_el:
                result['website'] = link_el.get_attribute('href') or ''
            
            # 获取摘要
            desc_el = el.query_selector('div[data-sncf], .VwiC3b, span[style*="-webkit-line-clamp"]')
            if desc_el:
                result['description'] = desc_el.inner_text().strip()
            
            # 从摘要中提取邮箱
            if result['description']:
                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', result['description'])
                if emails:
                    result['email'] = emails[0]
            
            # 从网站域名推断国家
            if result['website']:
                from urllib.parse import urlparse
                domain = urlparse(result['website']).netloc.lower()
                # 常见国家TLD
                country_tlds = {
                    '.uk': 'GB', '.de': 'DE', '.fr': 'FR', '.jp': 'JP',
                    '.au': 'AU', '.ca': 'CA', '.in': 'IN', '.br': 'BR',
                    '.it': 'IT', '.es': 'ES', '.nl': 'NL', '.mx': 'MX',
                }
                for tld, code in country_tlds.items():
                    if domain.endswith(tld):
                        result['country'] = code
                        break
            
        except Exception as e:
            logger.debug(f"[ChromeSearchScraper] _parse_search_item异常: {e}")
            return None
        
        return result if result['name'] and result['website'] else None
