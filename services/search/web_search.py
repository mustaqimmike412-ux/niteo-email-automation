"""
网页搜索代理
优先DuckDuckGo，支持配置切换为SerpAPI或Google Custom Search
"""
import re
import requests
from typing import List
from urllib.parse import urljoin, urlparse
from services.search.base import BaseSearcher, SearchResult


class WebSearcher(BaseSearcher):
    """网页搜索代理"""

    # URL路径黑名单：排除搜索结果页、标签页、分类页等
    URL_PATH_BLACKLIST = {
        '/search?', '/tag/', '/category/', '/author/',
        '/page/', '/pages/', '/post/', '/posts/',
        '/product-category/', '/shop/', '/store/',
    }
    # 文件扩展名黑名单：排除下载链接
    FILE_EXT_BLACKLIST = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar'}

    def __init__(self, config=None):
        super().__init__(config)
        self.engine = 'duckduckgo'
        self.serpapi_key = ''
        self.google_api_key = ''
        self.google_cx = ''

        import os, json
        cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'config', 'search_config.json'
        )
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            self.engine = cfg.get('web_search_engine', 'duckduckgo')
            self.serpapi_key = cfg.get('serpapi_key', '')
            self.google_api_key = cfg.get('google_custom_search_api_key', '')
            self.google_cx = cfg.get('google_custom_search_cx', '')

        # config参数可覆盖
        if config:
            self.engine = config.get('web_search_engine', self.engine)
            self.serpapi_key = config.get('serpapi_key', self.serpapi_key)
            self.google_api_key = config.get('google_custom_search_api_key', self.google_api_key)
            self.google_cx = config.get('google_custom_search_cx', self.google_cx)

    def is_available(self) -> bool:
        if self.engine == 'duckduckgo':
            return True  # 免费，无需API Key
        if self.engine == 'serpapi':
            return bool(self.serpapi_key)
        if self.engine == 'google':
            return bool(self.google_api_key) and bool(self.google_cx)
        return False

    def search(self, query: str, location: str = '', max_results: int = 20) -> List[SearchResult]:
        if not self.is_available():
            return []

        search_query = f"{query} {location}".strip() if location else query

        if self.engine == 'duckduckgo':
            return self._search_duckduckgo(search_query, max_results)
        elif self.engine == 'serpapi':
            return self._search_serpapi(search_query, max_results)
        elif self.engine == 'google':
            return self._search_google(search_query, max_results)
        return []

    def _search_duckduckgo(self, query: str, max_results: int) -> List[SearchResult]:
        """使用DuckDuckGo搜索"""
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
        except ImportError:
            print("[WebSearcher] ddgs未安装，尝试: pip install ddgs")
            return []
        except Exception as e:
            print(f"[WebSearcher] DuckDuckGo搜索失败: {e}")
            return []

        search_results = []
        for r in results:
            href = r.get('href', '')
            raw = {
                'name': r.get('title', ''),
                'website': href,
                'description': r.get('body', ''),
            }
            search_results.append(SearchResult(
                platform='web_search',
                source_url=href,
                raw_data=raw
            ))
        return self._clean_search_results(search_results)

    def _search_serpapi(self, query: str, max_results: int) -> List[SearchResult]:
        """使用SerpAPI搜索"""
        url = "https://serpapi.com/search"
        params = {
            'q': query,
            'engine': 'google',
            'api_key': self.serpapi_key,
            'num': min(max_results, 100),
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[WebSearcher] SerpAPI搜索失败: {e}")
            return []

        results = []
        for r in data.get('organic_results', []):
            link = r.get('link', '')
            raw = {
                'name': r.get('title', ''),
                'website': link,
                'description': r.get('snippet', ''),
            }
            results.append(SearchResult(
                platform='web_search',
                source_url=link,
                raw_data=raw
            ))
        return self._clean_search_results(results)

    def _search_google(self, query: str, max_results: int) -> List[SearchResult]:
        """使用Google Custom Search JSON API"""
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'q': query,
            'key': self.google_api_key,
            'cx': self.google_cx,
            'num': min(max_results, 10),  # API限制单次最多10
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[WebSearcher] Google Custom Search失败: {e}")
            return []

        results = []
        for item in data.get('items', []):
            link = item.get('link', '')
            raw = {
                'name': item.get('title', ''),
                'website': link,
                'description': item.get('snippet', ''),
            }
            results.append(SearchResult(
                platform='web_search',
                source_url=link,
                raw_data=raw
            ))
        return self._clean_search_results(results)

    def _is_valid_url(self, url: str) -> bool:
        """URL清洗：排除黑名单路径和文件下载链接"""
        if not url:
            return False
        url_lower = url.lower()
        # 检查路径黑名单
        for bad_path in self.URL_PATH_BLACKLIST:
            if bad_path in url_lower:
                return False
        # 检查文件扩展名黑名单
        for ext in self.FILE_EXT_BLACKLIST:
            if url_lower.endswith(ext):
                return False
        return True

    def _clean_search_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """清洗搜索结果，过滤无效URL"""
        cleaned = []
        for r in results:
            href = r.raw_data.get('website', '') or r.source_url
            if self._is_valid_url(href):
                cleaned.append(r)
            else:
                print(f"[WebSearcher] 过滤无效URL: {href}")
        return cleaned

    def extract_emails_from_text(self, text: str) -> List[str]:
        """从文本中提取邮箱地址"""
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(pattern, text)
        # 去重并过滤常见假阳性
        seen = set()
        filtered = []
        for e in emails:
            e = e.lower().strip()
            if e not in seen and not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.css')):
                seen.add(e)
                filtered.append(e)
        return filtered
