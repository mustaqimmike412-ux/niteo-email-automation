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

        # 产品关键词搜索：不混入 location 文字
        # location 仅通过 DuckDuckGo 的 region 参数限定搜索区域
        search_query = query
        region = self._location_to_region(location) if location else 'wt-wt'

        if self.engine == 'duckduckgo':
            return self._search_duckduckgo(search_query, max_results, region)
        elif self.engine == 'serpapi':
            return self._search_serpapi(search_query, max_results, location)
        elif self.engine == 'google':
            return self._search_google(search_query, max_results)
        return []

    def _search_duckduckgo(self, query: str, max_results: int, region: str = 'wt-wt') -> List[SearchResult]:
        """使用DuckDuckGo搜索"""
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results, region=region))
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

    def _search_serpapi(self, query: str, max_results: int, location: str = '') -> List[SearchResult]:
        """使用SerpAPI搜索"""
        url = "https://serpapi.com/search"
        params = {
            'q': query,
            'engine': 'google',
            'api_key': self.serpapi_key,
            'num': min(max_results, 100),
        }
        if location:
            params['location'] = location
            params['gl'] = location  # geolocation
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

    @staticmethod
    def _location_to_region(location: str) -> str:
        """
        将用户输入的 location 转换为 DuckDuckGo 的 region 参数
        格式: XX-YY (语言-地区)
        参考: https://duckduckgo.com/duckduckgo-help-pages/results/param-depth/
        """
        if not location:
            return 'wt-wt'

        loc = location.lower().strip()
        mapping = {
            'usa': 'us-en', 'us': 'us-en', 'united states': 'us-en', 'america': 'us-en',
            'uk': 'uk-en', 'united kingdom': 'uk-en', 'britain': 'uk-en', 'england': 'uk-en',
            'germany': 'de-de', 'deutschland': 'de-de',
            'france': 'fr-fr',
            'china': 'cn-zh', 'chinese': 'cn-zh',
            'india': 'in-en',
            'japan': 'jp-jp',
            'australia': 'au-en',
            'canada': 'ca-en',
            'italy': 'it-it',
            'spain': 'es-es',
            'brazil': 'pt-br', 'brasil': 'pt-br',
            'mexico': 'mx-es',
            'south korea': 'kr-ko', 'korea': 'kr-ko',
            'netherlands': 'nl-nl',
            'turkey': 'tr-tr',
            'thailand': 'th-th',
            'vietnam': 'vi-vi',
            'indonesia': 'id-id',
            'malaysia': 'ms-ms',
            'singapore': 'sg-en',
            'uae': 'ae-ar', 'dubai': 'ae-ar',
            'saudi arabia': 'sa-ar',
            'russia': 'ru-ru',
            'poland': 'pl-pl',
            'switzerland': 'ch-de',
            'sweden': 'se-sv',
            'norway': 'no-no',
            'denmark': 'dk-da',
            'finland': 'fi-fi',
            'ireland': 'ie-en',
            'austria': 'at-de',
            'belgium': 'be-fr',
            'portugal': 'pt-pt',
            'argentina': 'ar-es',
            'south africa': 'za-en',
            'egypt': 'eg-ar',
            'philippines': 'tl-en',
            'colombia': 'co-es',
            'chile': 'cl-es',
            'israel': 'il-he',
            'new zealand': 'nz-en',
            'taiwan': 'tw-zh',
            'hong kong': 'hk-tzh',
            'europe': 'eu-en',
        }

        # 精确匹配
        if loc in mapping:
            return mapping[loc]

        # 模糊匹配
        for key, region in mapping.items():
            if key in loc or loc in key:
                return region

        return 'wt-wt'
