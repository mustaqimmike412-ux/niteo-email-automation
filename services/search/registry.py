"""
搜索器注册表（策略模式）

搜索模式选择逻辑：
- google_places: 优先使用 Google Places API（需API Key），无Key时自动降级为Chrome爬虫
- web_search: 优先使用 DuckDuckGo（免费），可配置为Chrome爬虫

降级策略：
1. google_places → API Key存在 → GooglePlacesSearcher（官方API）
2. google_places → API Key不存在 → ChromeMapsScraper（Chrome爬虫）
3. web_search → 默认 → WebSearcher + DuckDuckGo（免费库）
4. web_search → 配置chrome_scraper → ChromeSearchScraper（Chrome爬虫）
"""
import logging
from typing import List, Dict, Optional
from services.search.base import BaseSearcher

logger = logging.getLogger(__name__)


class SearcherRegistry:
    """搜索器注册表，管理所有平台搜索器"""

    def __init__(self):
        self._searchers: Dict[str, type] = {}
        self._register_defaults()

    def _register_defaults(self):
        """注册默认搜索器（延迟导入避免循环依赖）"""
        from services.search.google_places import GooglePlacesSearcher
        from services.search.web_search import WebSearcher

        self._searchers = {
            'google_places': GooglePlacesSearcher,
            'web_search': WebSearcher,
        }
        
        # 缓存导入供get_searcher使用
        self._GooglePlacesSearcher = GooglePlacesSearcher
        self._WebSearcher = WebSearcher

    def get_searcher(self, platform: str, config: dict = None) -> BaseSearcher:
        """
        获取指定平台的搜索器实例
        
        智能降级：如果首选搜索器不可用，自动尝试备用方案
        """
        cfg = dict(config) if config else {}
        
        # === Google Maps 降级逻辑 ===
        if platform == 'google_places':
            from services.search.google_places import GooglePlacesSearcher
            api_searcher = GooglePlacesSearcher(cfg)
            if api_searcher.is_available():
                logger.info("[Registry] 使用 Google Places API (官方)")
                return api_searcher
            
            # API不可用，尝试Chrome爬虫
            logger.info("[Registry] Google Places API不可用，降级为Chrome爬虫")
            try:
                from services.search.chrome_scraper import ChromeMapsScraper
                chrome_searcher = ChromeMapsScraper(cfg)
                if chrome_searcher.is_available():
                    logger.info("[Registry] 使用 ChromeMapsScraper (Chrome爬虫)")
                    return chrome_searcher
                else:
                    logger.warning("[Registry] Chrome爬虫Playwright未安装")
            except ImportError:
                logger.warning("[Registry] chrome_scraper模块导入失败")
            
            # 最终回退：返回不可用的API搜索器（调用search会返回空列表）
            logger.warning("[Registry] 所有Google Maps搜索方案均不可用")
            return api_searcher
        
        # === 网页搜索降级逻辑 ===
        if platform == 'web_search':
            from services.search.web_search import WebSearcher
            use_chrome = cfg.get('web_search_use_chrome', False)
            
            if use_chrome:
                # 用户主动选择Chrome爬虫
                try:
                    from services.search.chrome_scraper import ChromeSearchScraper
                    chrome_searcher = ChromeSearchScraper(cfg)
                    if chrome_searcher.is_available():
                        logger.info("[Registry] 使用 ChromeSearchScraper (Chrome爬虫)")
                        return chrome_searcher
                except ImportError:
                    logger.warning("[Registry] chrome_scraper模块导入失败")
            
            # 默认使用WebSearcher（DuckDuckGo）
            web_searcher = WebSearcher(cfg)
            if web_searcher.is_available():
                logger.info(f"[Registry] 使用 WebSearcher (引擎: {web_searcher.engine})")
                return web_searcher
            
            # DuckDuckGo不可用时，尝试Chrome爬虫
            logger.info("[Registry] WebSearcher不可用，降级为Chrome爬虫")
            try:
                from services.search.chrome_scraper import ChromeSearchScraper
                chrome_searcher = ChromeSearchScraper(cfg)
                if chrome_searcher.is_available():
                    logger.info("[Registry] 使用 ChromeSearchScraper (Chrome爬虫降级)")
                    return chrome_searcher
            except ImportError:
                pass
            
            return web_searcher
        
        # === 通用逻辑 ===
        cls = self._searchers.get(platform)
        if not cls:
            raise ValueError(f"Unknown platform: {platform}")
        
        return cls(cfg)

    def list_available(self) -> List[str]:
        """返回当前配置下可用的平台列表"""
        available = []
        for name in self._searchers:
            try:
                searcher = self.get_searcher(name)
                if searcher.is_available():
                    available.append(name)
            except Exception:
                pass
        return available

    def list_all(self) -> List[str]:
        """返回所有已注册的平台名称"""
        return list(self._searchers.keys())

    def get_platform_info(self) -> List[dict]:
        """获取所有平台的详细信息"""
        info = []
        for name in self._searchers:
            try:
                searcher = self.get_searcher(name)
                actual_type = type(searcher).__name__
                info.append({
                    'platform': name,
                    'available': searcher.is_available(),
                    'searcher_type': actual_type,
                    'rate_limit_delay': searcher.rate_limit_delay(),
                })
            except Exception as e:
                info.append({
                    'platform': name,
                    'available': False,
                    'error': str(e),
                })
        return info
