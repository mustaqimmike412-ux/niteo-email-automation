"""
Google Places API (New) 搜索器
使用 places:searchText 端点
"""
import requests
from typing import List
from services.search.base import BaseSearcher, SearchResult


class GooglePlacesSearcher(BaseSearcher):
    """Google Places API搜索器"""

    def __init__(self, config=None):
        super().__init__(config)
        self.api_key = config.get('api_key') if config else None
        if not self.api_key:
            # 优先从数据库读取
            try:
                from database.api_config_models import get_api_key
                db_key = get_api_key('Google Places')
                if db_key:
                    self.api_key = db_key
            except Exception:
                pass
        if not self.api_key:
            # 回退到 search_config.json
            import os, json
            cfg_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                'config', 'search_config.json'
            )
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self.api_key = cfg.get('google_places_api_key', '')

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, location: str = '', max_results: int = 20) -> List[SearchResult]:
        if not self.is_available():
            return []

        # 查询策略：location 不再直接拼接到 textQuery 中
        # 改为使用自然语言查询 "query in location"，Google 会理解地理语义
        # 避免 "solar USA" 这种直接拼接导致名称匹配偏差
        if location:
            text_query = f"{query} in {location}"
        else:
            text_query = query

        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "places.displayName,places.formattedAddress,"
                "places.websiteUri,places.nationalPhoneNumber,"
                "places.rating,places.businessStatus,places.addressComponents"
            )
        }
        payload = {
            "textQuery": text_query,
            "pageSize": min(max_results, 20)  # API限制单次最多20
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30, verify=True)
            resp.raise_for_status()
            data = resp.json()
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            # SSL/连接错误：在中国大陆访问 Google API 常见，尝试关闭证书验证重试
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                resp = requests.post(url, json=payload, headers=headers, timeout=30, verify=False)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e2:
                print(f"[GooglePlaces] API请求失败(SSL重试后): {e2}")
                return []
        except requests.RequestException as e:
            print(f"[GooglePlaces] API请求失败: {e}")
            return []
        except Exception as e:
            print(f"[GooglePlaces] 解析失败: {e}")
            return []

        results = []
        for place in data.get('places', []):
            website = place.get('websiteUri', '')
            raw = {
                'name': place.get('displayName', {}).get('text', ''),
                'address': place.get('formattedAddress', ''),
                'website': website,
                'phone': place.get('nationalPhoneNumber', ''),
                'rating': place.get('rating'),
                'business_status': place.get('businessStatus'),
            }

            # 标记可疑域名（将在validator中进一步处理）
            if website:
                from services.search.result_validator import ResultValidator
                validator = ResultValidator()
                if validator.is_blacklisted_domain(website):
                    raw['website_suspicious'] = True

            # 从addressComponents提取国家
            country = ''
            for comp in place.get('addressComponents', []):
                types = comp.get('types', [])
                if 'country' in types:
                    country = comp.get('shortText', '')
                    break
            raw['country'] = country

            results.append(SearchResult(
                platform='google_places',
                source_url=f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(text_query)}",
                raw_data=raw
            ))

        return results
