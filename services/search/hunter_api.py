"""
Hunter.io API 邮箱搜索服务
通过 Hunter API 获取目标公司的邮箱信息
"""
import requests
import json
import os
from typing import List, Dict, Optional
from urllib.parse import urlparse


class HunterAPISearcher:
    """Hunter.io 邮箱搜索器"""

    API_BASE = "https://api.hunter.io/v2"

    def __init__(self, api_key: str = ''):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NiteoSolar-LeadBot/1.0'
        })

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    def _get(self, endpoint: str, params: dict) -> Optional[dict]:
        """发送GET请求到Hunter API"""
        params['api_key'] = self.api_key
        url = f"{self.API_BASE}/{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.SSLError:
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                resp = self.session.get(url, params=params, timeout=15, verify=False)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                print(f"[HunterAPI] SSL重试失败: {e}")
                return None
        except Exception as e:
            print(f"[HunterAPI] 请求失败: {e}")
            return None

    def _extract_domain(self, website: str) -> str:
        """从URL提取域名"""
        if not website:
            return ''
        try:
            parsed = urlparse(website)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            return ''

    def domain_search(self, domain: str) -> List[Dict]:
        """
        搜索指定域名下的所有邮箱
        返回: [{email, type, role, source, confidence}, ...]
        """
        if not self.is_available():
            print("[HunterAPI] API Key 未配置，跳过")
            return []

        if not domain:
            return []

        print(f"[HunterAPI] 搜索域名: {domain}")
        data = self._get('domain-search', {'domain': domain})
        if not data or data.get('errors'):
            err = data.get('errors', [{}]) if data else [{}]
            print(f"[HunterAPI] domain-search 错误: {err}")
            return []

        emails = []
        pattern_emails = data.get('data', {}).get('emails', [])
        for pe in pattern_emails:
            email = pe.get('value', '')
            if not email:
                continue

            email_type = 'public'
            first_name = pe.get('first_name', '')
            last_name = pe.get('last_name', '')
            position = pe.get('position', '')
            department = pe.get('department', '')

            # 有姓名的认为是职位邮箱
            if first_name or last_name:
                email_type = 'role'
                role = position or department or ''
                if first_name and last_name:
                    role = f"{first_name} {last_name}" + (f" - {role}" if role else '')
                elif position:
                    role = position
            else:
                role = department or ''

            confidence = pe.get('confidence', 0) / 100.0
            if confidence <= 0:
                # 根据类型给默认置信度
                confidence = 0.8 if email_type == 'role' else 0.6

            emails.append({
                'email': email,
                'type': email_type,
                'role': role,
                'source': 'Hunter.io',
                'confidence': min(confidence, 1.0),
                'first_name': first_name,
                'last_name': last_name,
                'position': position,
                'department': department,
                'phone': pe.get('phone', ''),
                'linkedin': pe.get('linkedin', ''),
            })

        print(f"[HunterAPI] 找到 {len(emails)} 个邮箱")
        return emails

    def email_finder(self, domain: str = '', company_name: str = '',
                     first_name: str = '', last_name: str = '') -> List[Dict]:
        """
        通过 Hunter email-finder 端点精确搜索邮箱
        支持参数组合: domain+company, domain+first_name+last_name, company only
        """
        if not self.is_available():
            return []

        if not domain and not company_name:
            return []

        params = {}
        if domain:
            params['domain'] = domain
        if company_name:
            params['company'] = company_name
        if first_name:
            params['first_name'] = first_name
        if last_name:
            params['last_name'] = last_name

        desc = params.copy()
        print(f"[HunterAPI] email-finder: {desc}")

        data = self._get('email-finder', params)
        if not data or data.get('errors'):
            err = data.get('errors', [{}]) if data else [{}]
            print(f"[HunterAPI] email-finder 错误: {err}")
            return []

        result = data.get('data', {})
        email = result.get('email', '')
        if not email:
            return []

        first_name_ret = result.get('first_name', '') or first_name
        last_name_ret = result.get('last_name', '') or last_name
        position = result.get('position', '')
        confidence = result.get('score', 0) / 100.0 if result.get('score') else 0.7

        role = ''
        if first_name_ret and last_name_ret:
            role = f"{first_name_ret} {last_name_ret}"
            if position:
                role += f" - {position}"
        elif position:
            role = position

        return [{
            'email': email,
            'type': 'role',
            'role': role,
            'source': 'Hunter.io',
            'confidence': min(confidence, 1.0),
            'first_name': first_name_ret,
            'last_name': last_name_ret,
            'position': position,
        }]

    def find_all_emails(self, company_name: str, website: str = '',
                        first_name: str = '', last_name: str = '') -> List[Dict]:
        """
        综合搜索：domain-search + email-finder，返回去重后的邮箱列表
        注意：email-finder 端点要求 first_name + last_name（Free计划限制）
        """
        domain = self._extract_domain(website) if website else ''
        all_emails = []
        seen = set()

        # 渠道1: domain-search（批量搜索域名下所有邮箱）
        if domain:
            ds_emails = self.domain_search(domain)
            for e in ds_emails:
                key = e['email'].lower()
                if key not in seen:
                    seen.add(key)
                    all_emails.append(e)

        # 渠道2: email-finder（需要具体人名，Free计划限制）
        if first_name and last_name and domain:
            ef_emails = self.email_finder(domain=domain, first_name=first_name, last_name=last_name)
            for e in ef_emails:
                key = e['email'].lower()
                if key not in seen:
                    seen.add(key)
                    all_emails.append(e)

        # 按置信度排序
        all_emails.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        return all_emails

    def verify_email(self, email: str) -> Dict:
        """
        验证邮箱是否有效
        返回: {email, result, score, regex, disposable, webmail, etc}
        """
        if not self.is_available() or not email:
            return {}

        print(f"[HunterAPI] 验证邮箱: {email}")
        data = self._get('email-verifier', {'email': email})
        if not data or data.get('errors'):
            return {}

        return data.get('data', {})


def get_hunter_api_key() -> str:
    """从配置文件读取 Hunter API Key"""
    try:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'config', 'search_config.json'
        )
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            return cfg.get('hunter_api_key', '')
    except Exception:
        pass
    return ''


def create_hunter_searcher() -> HunterAPISearcher:
    """工厂函数：创建 Hunter 搜索器实例"""
    return HunterAPISearcher(api_key=get_hunter_api_key())
