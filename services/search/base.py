"""
Searcher抽象基类和统一搜索结果数据结构
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    """统一搜索结果数据结构"""
    platform: str
    source_url: str
    raw_data: dict
    # 标准化字段
    company_name: str = ''
    website: str = ''
    phone: str = ''
    address: str = ''
    country: str = ''
    email: str = ''
    industry_type: str = ''
    business_model: str = ''
    # 验证相关字段
    confidence_score: float = 0.0
    validation_status: str = 'pending'   # pending | validated | rejected | needs_review
    validation_reason: str = ''
    probe_data: dict = field(default_factory=dict)

    def __post_init__(self):
        # 从raw_data自动填充标准化字段
        if not self.company_name:
            self.company_name = self.raw_data.get('name', '')
        if not self.website:
            self.website = self.raw_data.get('website', '')
        if not self.phone:
            self.phone = self.raw_data.get('phone', '')
        if not self.address:
            self.address = self.raw_data.get('address', '')
        if not self.country:
            self.country = self.raw_data.get('country', '')
        if not self.email:
            self.email = self.raw_data.get('email', '')
        if not self.industry_type:
            self.industry_type = self.raw_data.get('industry', '')
        if not self.business_model:
            self.business_model = self.raw_data.get('business_model', '')

    def to_dict(self) -> dict:
        return {
            'platform': self.platform,
            'source_url': self.source_url,
            'raw_data': self.raw_data,
            'company_name': self.company_name,
            'website': self.website,
            'phone': self.phone,
            'address': self.address,
            'country': self.country,
            'email': self.email,
            'industry_type': self.industry_type,
            'business_model': self.business_model,
        }


class BaseSearcher(ABC):
    """搜索器抽象基类（策略模式）"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.platform_name = self.__class__.__name__.lower().replace('searcher', '')

    @abstractmethod
    def search(self, query: str, location: str = '', max_results: int = 20) -> List[SearchResult]:
        """执行搜索，返回标准化结果列表"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查搜索器是否可用（API Key配置等）"""
        pass

    def rate_limit_delay(self) -> float:
        """请求间隔（秒），子类可覆盖"""
        return self.config.get('request_delay_seconds', 2.0)

    def _normalize_website(self, url: str) -> str:
        """归一化网站URL，用于去重"""
        if not url:
            return ''
        url = url.strip().lower()
        if url.startswith('http://'):
            url = url[7:]
        elif url.startswith('https://'):
            url = url[8:]
        if url.startswith('www.'):
            url = url[4:]
        return url.rstrip('/')

    def post_filter_results(self, results: List[SearchResult], query: str, validator) -> List[SearchResult]:
        """
        结果返回前执行验证过滤（Layer 1+2+5）
        由 ResultValidator.run_pre_crawl_validation 执行实际过滤
        """
        if validator and hasattr(validator, 'run_pre_crawl_validation'):
            return validator.run_pre_crawl_validation(results, query)
        return results
