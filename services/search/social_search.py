"""
社交平台搜索器
通过site:运算符间接搜索Facebook/Instagram/TikTok公开页面
"""
import time
from typing import List
from services.search.base import BaseSearcher, SearchResult


class SocialSearcher(BaseSearcher):
    """社交平台搜索器（间接搜索）"""

    def __init__(self, config=None):
        super().__init__(config)
        self.target_platform = config.get('_target_social_platform', 'facebook') if config else 'facebook'

    def is_available(self) -> bool:
        # 社交平台搜索依赖WebSearcher，WebSearcher(DuckDuckGo)默认可用
        return True

    def search(self, query: str, location: str = '', max_results: int = 20) -> List[SearchResult]:
        """通过site:运算符间接搜索社交平台"""
        if self.target_platform == 'facebook':
            site = 'site:facebook.com'
        elif self.target_platform == 'instagram':
            site = 'site:instagram.com'
        elif self.target_platform == 'tiktok':
            site = 'site:tiktok.com'
        else:
            return []

        # 构造搜索查询
        search_query = f"{query} {location} {site}".strip()

        # 使用WebSearcher执行搜索
        from services.search.web_search import WebSearcher
        web_searcher = WebSearcher(self.config)

        try:
            results = web_searcher.search(search_query, '', max_results)
        except Exception as e:
            print(f"[SocialSearcher] {self.target_platform}搜索失败: {e}")
            return []

        # 转换平台标识
        social_results = []
        for r in results:
            # 过滤掉非目标平台的结果
            url = r.source_url.lower()
            if self.target_platform not in url:
                continue

            # 尝试提取页面中的商家信息
            raw = dict(r.raw_data)
            raw['social_platform'] = self.target_platform

            # 尝试从URL或标题中提取名称
            if not raw.get('name'):
                raw['name'] = self._extract_name_from_url(r.source_url) or raw.get('title', '')

            social_results.append(SearchResult(
                platform=self.target_platform,
                source_url=r.source_url,
                raw_data=raw
            ))

        return social_results

    def _extract_name_from_url(self, url: str) -> str:
        """从社交平台URL中提取名称"""
        if not url:
            return ''
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path.strip('/')
            parts = path.split('/')
            for p in parts:
                if p and p not in ('pages', 'groups', 'profile', 'user'):
                    # 将横线替换为空格，首字母大写
                    name = p.replace('-', ' ').replace('_', ' ')
                    return ' '.join(word.capitalize() for word in name.split())
        except Exception:
            pass
        return ''
