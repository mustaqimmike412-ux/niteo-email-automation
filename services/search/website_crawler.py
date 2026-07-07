"""
网站内容爬取分析器
对搜索结果中的website进行二次爬取，提取详细信息
"""
import re
import time
from typing import Optional, List
from urllib.parse import urljoin, urlparse
import requests
from services.search.base import BaseSearcher, SearchResult


class WebsiteCrawler(BaseSearcher):
    """网站内容爬取分析器"""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}
        self.user_agent = config.get('user_agent', 'NiteoSolar-LeadBot/1.0')
        self.delay = config.get('crawl_delay_seconds', 2)
        self.max_pages = config.get('max_crawl_pages_per_domain', 3)

    def is_available(self) -> bool:
        return True

    def search(self, query: str, location: str = '', max_results: int = 20) -> List[SearchResult]:
        """WebsiteCrawler不直接参与搜索，只用于二次分析"""
        return []

    def quick_probe(self, url: str) -> Optional[dict]:
        """
        轻量级HTTP预检：仅获取title和meta description
        供 ResultValidator Layer 3 复用
        返回: {status_code, title, description, is_alive, error}
        """
        if not url or not url.startswith('http'):
            return None
        try:
            headers = {'User-Agent': self.user_agent}
            resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
            if resp.status_code >= 400:
                return {'status_code': resp.status_code, 'title': '', 'description': '',
                        'is_alive': False, 'error': f'HTTP {resp.status_code}'}

            # 提取title
            title_match = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else ''

            # 提取meta description
            desc_match = re.search(
                r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
                resp.text, re.IGNORECASE)
            if not desc_match:
                desc_match = re.search(
                    r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*name=["\']description["\']',
                    resp.text, re.IGNORECASE)
            description = desc_match.group(1).strip() if desc_match else ''

            return {'status_code': resp.status_code, 'title': title, 'description': description,
                    'is_alive': True, 'error': ''}
        except Exception as e:
            return {'status_code': 0, 'title': '', 'description': '',
                    'is_alive': False, 'error': str(e)}

    def is_likely_company_site(self, crawl_data: dict, expected_company_name: str = '') -> tuple:
        """
        基于爬取内容判断是否为真实公司官网
        返回 (是否通过, 置信度)
        """
        title = crawl_data.get('title', '')
        about_text = crawl_data.get('about_text', '')
        contact_text = crawl_data.get('contact_text', '')

        # 检测聚合器信号
        aggregator_signals = ['directory', 'list of', 'top 10', 'reviews', 'forum',
                              'community', 'compare', 'aggregator']
        title_lower = title.lower()
        for sig in aggregator_signals:
            if sig in title_lower:
                return False, 0.1

        # about_text 过短可能是聚合页
        total_text = len(about_text) + len(contact_text)
        if total_text < 100:
            return False, 0.2

        # 检查公司名称是否在页面内容中
        if expected_company_name and expected_company_name.lower() in about_text.lower():
            return True, 0.8

        # 检查是否有足够的联系信息（公司官网通常有）
        has_email = bool(crawl_data.get('emails'))
        has_phone = bool(crawl_data.get('phones'))
        if (has_email or has_phone) and total_text > 300:
            return True, 0.6

        return True, 0.4

    def crawl(self, url: str) -> Optional[dict]:
        """爬取单个网站，提取关键信息"""
        if not url or not url.startswith('http'):
            return None

        try:
            headers = {'User-Agent': self.user_agent}
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True, verify=True)
            resp.raise_for_status()
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            # SSL/连接错误：尝试关闭证书验证重试
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True, verify=False)
                resp.raise_for_status()
            except Exception:
                return None

            # 尝试用BeautifulSoup解析
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, 'html.parser')
            except ImportError:
                # 无bs4时回退到简单正则
                return self._simple_extract(url, resp.text)

            result = {
                'url': url,
                'title': '',
                'description': '',
                'emails': [],
                'phones': [],
                'about_text': '',
                'contact_text': '',
                'all_text': '',
                'products_text': '',
            }

            # Title
            title_tag = soup.find('title')
            if title_tag:
                result['title'] = title_tag.get_text(strip=True)

            # Meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                result['description'] = meta_desc.get('content', '')
            if not result['description']:
                meta_og = soup.find('meta', attrs={'property': 'og:description'})
                if meta_og:
                    result['description'] = meta_og.get('content', '')

            # 主页面正文内容（提取有意义的文本段落）
            main_text = self._extract_main_content(soup)
            result['all_text'] = main_text[:4000]

            # 提取邮箱和电话
            text = soup.get_text(separator=' ', strip=True)
            result['emails'] = self._extract_emails(text)
            result['phones'] = self._extract_phones(text)

            # 如果主页已有足够内容，提取about和contact信息
            # 如果about_text为空，从主页中查找about相关段落
            if not result['about_text'] and main_text:
                result['about_text'] = main_text[:3000]

            # 查找About页面
            about_url = self._find_about_page(soup, url)
            if about_url:
                try:
                    time.sleep(self.delay)
                    about_resp = requests.get(about_url, headers=headers, timeout=10)
                    if about_resp.status_code == 200:
                        about_soup = BeautifulSoup(about_resp.text, 'html.parser')
                        about_text = about_soup.get_text(separator=' ', strip=True)
                        # 去重：如果about页面内容比主页更多，使用about页面
                        if len(about_text) > len(result['about_text']):
                            result['about_text'] = about_text[:3000]
                        # 补充提取
                        result['emails'] = list(set(result['emails'] + self._extract_emails(about_text)))
                        result['phones'] = list(set(result['phones'] + self._extract_phones(about_text)))
                except Exception:
                    pass

            # 查找Contact页面
            contact_url = self._find_contact_page(soup, url)
            if contact_url and contact_url != about_url:
                try:
                    time.sleep(self.delay)
                    contact_resp = requests.get(contact_url, headers=headers, timeout=10)
                    if contact_resp.status_code == 200:
                        contact_soup = BeautifulSoup(contact_resp.text, 'html.parser')
                        contact_text = contact_soup.get_text(separator=' ', strip=True)
                        result['contact_text'] = contact_text[:2000]
                        result['emails'] = list(set(result['emails'] + self._extract_emails(contact_text)))
                        result['phones'] = list(set(result['phones'] + self._extract_phones(contact_text)))
                except Exception:
                    pass

            # 如果没有找到about信息但有all_text，用all_text
            if not result['about_text'] and result['all_text']:
                result['about_text'] = result['all_text'][:2000]

            return result

        except requests.RequestException as e:
            print(f"[WebsiteCrawler] 爬取失败 {url}: {e}")
            return None
        except Exception as e:
            print(f"[WebsiteCrawler] 解析失败 {url}: {e}")
            return None

    def _simple_extract(self, url: str, html: str) -> dict:
        """无BeautifulSoup时的简单正则提取"""
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ''

        desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', html, re.IGNORECASE)
        if not desc_match:
            desc_match = re.search(r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*name=["\']description["\']', html, re.IGNORECASE)
        description = desc_match.group(1).strip() if desc_match else ''

        text = re.sub(r'<[^>]+>', ' ', html)
        return {
            'url': url,
            'title': title,
            'description': description,
            'emails': self._extract_emails(text),
            'phones': self._extract_phones(text),
            'about_text': '',
            'contact_text': '',
        }

    def _extract_emails(self, text: str) -> List[str]:
        """提取邮箱"""
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(pattern, text)
        seen = set()
        filtered = []
        for e in emails:
            e = e.lower().strip()
            if e not in seen and not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.css')):
                seen.add(e)
                filtered.append(e)
        return filtered[:5]  # 最多返回5个

    def _extract_phones(self, text: str) -> List[str]:
        """提取电话号码（简单模式）"""
        # 匹配常见国际电话格式
        pattern = r'[\+]?[1-9]?[0-9]{7,15}'
        phones = re.findall(pattern, text)
        seen = set()
        filtered = []
        for p in phones:
            p = p.strip()
            if len(p) >= 7 and p not in seen:
                seen.add(p)
                filtered.append(p)
        return filtered[:3]

    def _find_about_page(self, soup, base_url: str) -> Optional[str]:
        """查找About页面链接"""
        keywords = ['about', 'about-us', 'aboutus', 'company']
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            text = a.get_text(strip=True).lower()
            for kw in keywords:
                if kw in href or kw in text:
                    return urljoin(base_url, a['href'])
        return None

    def _find_contact_page(self, soup, base_url: str) -> Optional[str]:
        """查找Contact页面链接"""
        keywords = ['contact', 'contact-us', 'contactus', 'get-in-touch']
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            text = a.get_text(strip=True).lower()
            for kw in keywords:
                if kw in href or kw in text:
                    return urljoin(base_url, a['href'])
        return None

    def _extract_main_content(self, soup) -> str:
        """提取页面有意义的正文内容，过滤导航、脚本、页脚等"""
        # 移除不需要的标签
        for tag in soup.find_all(['script', 'style', 'noscript', 'header', 'footer',
                                    'nav', 'aside', 'iframe', 'svg', 'form']):
            tag.decompose()

        # 优先提取特定区域
        main_sections = []
        for selector in ['main', 'article', '[role="main"]', '.content', '.main-content',
                         '#content', '#main', '.entry-content', '.post-content',
                         '.page-content', 'section']:
            elements = soup.select(selector)
            for el in elements:
                text = el.get_text(separator=' ', strip=True)
                if len(text) > 100:  # 只取有实质内容的区域
                    main_sections.append(text)

        # 如果找到main/article等区域，使用它们
        if main_sections:
            combined = ' '.join(main_sections)
            # 去除过长重复内容
            return combined[:4000]

        # 回退：提取body中所有段落
        body = soup.find('body')
        if body:
            paragraphs = []
            for tag in body.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li', 'td', 'span']):
                text = tag.get_text(strip=True)
                if len(text) > 20:  # 只保留有实质内容的文本
                    paragraphs.append(text)
            return ' '.join(paragraphs[:100])[:4000]

        return ''
