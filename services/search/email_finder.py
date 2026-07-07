"""
全网邮箱搜索引擎
通过多种渠道搜索公司相关邮箱，区分职位邮箱和公共邮箱
"""
import re
import time
import json
import requests
from typing import List, Dict, Optional
from urllib.parse import urlparse


class EmailFinder:
    """全网邮箱搜索引擎 - 通过搜索引擎+网站爬取获取公司邮箱"""

    # 公共邮箱前缀列表
    PUBLIC_PREFIXES = {
        'info', 'sales', 'support', 'contact', 'service', 'help', 'admin',
        'marketing', 'hello', 'office', 'general', 'inquiries', 'enquiries',
        'business', 'orders', 'careers', 'hr', 'press', 'media', 'advertising',
        'partners', 'team', 'webmaster', 'noreply', 'no-reply', 'customerservice',
        'customerservices', 'techsupport', 'billing', 'account', 'feedback',
        'jobs', 'recruitment', 'newsletter', 'subscribe', 'abuse', 'postmaster',
        'hostmaster', 'web', 'mail', 'contactus', 'contact-us', 'about',
        'main', 'service', 'services', 'order', 'orders', 'invoice', 'pay',
        'payment', 'booking', 'reservation', 'reservations'
    }

    # 职位关键词映射
    ROLE_KEYWORDS = {
        'ceo': 'CEO / 首席执行官',
        'chief executive': 'CEO / 首席执行官',
        'founder': '创始人',
        'co-founder': '联合创始人',
        'cofounder': '联合创始人',
        'owner': '公司所有人',
        'president': '总裁',
        'managing director': '董事总经理',
        'director': '总监',
        'manager': '经理',
        'sales manager': '销售经理',
        'account manager': '客户经理',
        'business development': '业务拓展',
        'bd': '业务拓展',
        'procurement': '采购',
        'purchasing': '采购',
        'buyer': '采购',
        'sourcing': '采购',
        'supply chain': '供应链',
        'operations': '运营',
        'project manager': '项目经理',
        'engineer': '工程师',
        'technical': '技术',
        'cto': 'CTO / 技术总监',
        'cfo': 'CFO / 财务总监',
        'vp': '副总裁',
        'vice president': '副总裁',
        'head of': '负责人',
        'lead': '主管',
        'coordinator': '协调员',
        'representative': '代表',
        'specialist': '专员',
        'consultant': '顾问',
        'agent': '代理',
        'distributor': '经销商',
    }

    def __init__(self, config=None):
        self.config = config or {}
        self.user_agent = self.config.get('user_agent', 'NiteoSolar-LeadBot/1.0')
        self.max_search_results = self.config.get('email_search_max_results', 10)
        self.delay = self.config.get('email_search_delay', 1)
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.user_agent})

    def find_emails(self, company_name: str, website: str = '', country: str = '') -> List[Dict]:
        """
        全网搜索公司相关邮箱
        返回: [{email, type, role, source, confidence}, ...]
        """
        # 前置校验
        if not company_name or len(company_name) < 3:
            print(f"[EmailFinder] 拒绝无效公司名: '{company_name}'")
            return []

        if website:
            from services.search.result_validator import ResultValidator
            validator = ResultValidator()
            if validator.is_blacklisted_domain(website):
                print(f"[EmailFinder] 拒绝黑名单域名: {website}")
                return []

        all_emails = []
        seen = set()

        domain = self._extract_domain(website) if website else ''

        # 渠道1: 搜索引擎搜索 "company name" email
        if company_name:
            search_emails = self._search_engine_emails(company_name, domain, country)
            for e in search_emails:
                key = e['email'].lower()
                if key not in seen:
                    seen.add(key)
                    all_emails.append(e)

        # 渠道2: 搜索引擎搜索 "domain.com" email contact
        if domain:
            time.sleep(self.delay)
            domain_emails = self._search_domain_emails(domain)
            for e in domain_emails:
                key = e['email'].lower()
                if key not in seen:
                    seen.add(key)
                    all_emails.append(e)

        # 渠道3: 如果网站存在，深度爬取
        if website and website.startswith('http'):
            time.sleep(self.delay)
            crawl_emails = self._deep_crawl_emails(website)
            for e in crawl_emails:
                key = e['email'].lower()
                if key not in seen:
                    seen.add(key)
                    all_emails.append(e)

        # 渠道4: Hunter.io API（如果配置了API Key）
        try:
            from services.search.hunter_api import create_hunter_searcher
            hunter = create_hunter_searcher()
            if hunter.is_available() and domain:
                time.sleep(self.delay)
                hunter_emails = hunter.find_all_emails(website)
                for e in hunter_emails:
                    key = e['email'].lower()
                    if key not in seen:
                        seen.add(key)
                        all_emails.append(e)
                if hunter_emails:
                    print(f"[EmailFinder] Hunter.io 补充 {len(hunter_emails)} 个邮箱")
        except Exception as e:
            print(f"[EmailFinder] Hunter.io 搜索异常: {e}")

        # 分类和推断职位
        for e in all_emails:
            self._classify_email(e)

        # 按置信度和类型排序
        all_emails.sort(key=lambda x: (x.get('confidence', 0) * -1, x['type'] != 'role'))

        return all_emails[:15]  # 最多返回15个

    def _search_engine_emails(self, company_name: str, domain: str, country: str) -> List[Dict]:
        """通过搜索引擎搜索邮箱"""
        emails = []

        queries = [
            f'"{company_name}" email contact',
        ]
        if domain:
            queries.append(f'site:{domain} email')
            queries.append(f'"@{domain}" email')
        if country:
            queries.append(f'"{company_name}" {country} email')

        for query in queries[:2]:  # 限制搜索次数
            try:
                from ddgs import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=self.max_search_results))
                    for r in results:
                        text = f"{r.get('title', '')} {r.get('body', '')}"
                        found = self._extract_emails_from_text(text)
                        for email in found:
                            emails.append({
                                'email': email,
                                'type': 'unknown',
                                'role': '',
                                'source': f"search: {query[:40]}",
                                'confidence': 0.6,
                                'context': text[:200]
                            })
            except Exception:
                pass

        return emails

    def _search_domain_emails(self, domain: str) -> List[Dict]:
        """搜索特定域名的邮箱"""
        emails = []
        query = f'"@{domain}" email'
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=self.max_search_results))
                for r in results:
                    text = f"{r.get('title', '')} {r.get('body', '')}"
                    found = self._extract_emails_from_text(text)
                    for email in found:
                        if domain in email.lower():
                            emails.append({
                                'email': email,
                                'type': 'unknown',
                                'role': '',
                                'source': f"domain search: {domain}",
                                'confidence': 0.7,
                                'context': text[:200]
                            })
        except Exception:
            pass
        return emails

    def _deep_crawl_emails(self, website: str) -> List[Dict]:
        """深度爬取网站多个页面提取邮箱"""
        emails = []
        domain = self._extract_domain(website)
        if not domain:
            return emails

        # 要爬取的页面路径
        paths = ['', '/contact', '/contact-us', '/about', '/about-us',
                 '/team', '/staff', '/people', '/careers', '/jobs']

        headers = {'User-Agent': self.user_agent}
        all_texts = []
        homepage_checked = False

        for path in paths:
            url = website.rstrip('/') + path
            try:
                resp = self.session.get(url, headers=headers, timeout=10, allow_redirects=True)
                if resp.status_code == 200:
                    text = self._html_to_text(resp.text)
                    all_texts.append((url, text))

                    # 首页爬取后快速检测：如果是聚合器/目录站，提前终止
                    if not homepage_checked and path == '':
                        homepage_checked = True
                        from services.search.result_validator import ResultValidator
                        validator = ResultValidator()
                        title_match = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.IGNORECASE | re.DOTALL)
                        title = title_match.group(1).strip() if title_match else ''
                        is_agg, reason = validator.detect_aggregator(title, text[:500], website)
                        if is_agg:
                            print(f"[EmailFinder] 检测到聚合页，提前终止爬取: {reason}")
                            break

                    # 提取邮箱
                    found = self._extract_emails_from_text(text)
                    for email in found:
                        if domain in email.lower():
                            emails.append({
                                'email': email,
                                'type': 'unknown',
                                'role': '',
                                'source': f"website: {path or 'homepage'}",
                                'confidence': 0.85,
                                'context': text[:300]
                            })
                time.sleep(0.5)
            except Exception:
                continue

        # 尝试从页面内容推断职位
        for e in emails:
            e['role'] = self._infer_role_from_context(e['email'], all_texts)

        return emails

    def _extract_emails_from_text(self, text: str) -> List[str]:
        """从文本中提取邮箱"""
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(pattern, text)
        seen = set()
        filtered = []
        for e in emails:
            e = e.lower().strip()
            # 过滤图片和样式文件
            if e not in seen and not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js', '.webp')):
                seen.add(e)
                filtered.append(e)
        return filtered

    def _classify_email(self, email_info: Dict):
        """分类邮箱：公共邮箱 vs 职位邮箱"""
        email = email_info['email'].lower()
        prefix = email.split('@')[0] if '@' in email else ''

        # 检查是否为公共邮箱
        if prefix in self.PUBLIC_PREFIXES:
            email_info['type'] = 'public'
            return

        # 检查前缀是否包含职位关键词
        for kw, role_name in self.ROLE_KEYWORDS.items():
            if kw in prefix:
                email_info['type'] = 'role'
                if not email_info.get('role'):
                    email_info['role'] = role_name
                return

        # 如果前缀是名字（如 john.smith, jsmith），认为是职位邮箱
        if self._looks_like_name(prefix):
            email_info['type'] = 'role'
            if not email_info.get('role'):
                email_info['role'] = '未知职位'
            return

        # 默认分类
        if email_info['type'] == 'unknown':
            email_info['type'] = 'role'  # 优先假设为职位邮箱

    def _infer_role_from_context(self, email: str, all_texts: List[tuple]) -> str:
        """从页面上下文推断邮箱持有人的职位"""
        for url, text in all_texts:
            # 找到邮箱附近的文本
            idx = text.lower().find(email.lower())
            if idx >= 0:
                # 取邮箱前后200字符
                context = text[max(0, idx - 200):min(len(text), idx + 200)]
                # 在上下文中查找职位关键词
                for kw, role_name in self.ROLE_KEYWORDS.items():
                    if kw in context.lower():
                        return role_name
        return ''

    def _looks_like_name(self, prefix: str) -> bool:
        """判断邮箱前缀是否像人名"""
        # 名字模式: john.smith, j.smith, jsmith, john_smith
        if '.' in prefix and len(prefix.split('.')) == 2:
            parts = prefix.split('.')
            if all(len(p) >= 2 for p in parts):
                return True
        # 首字母+姓: jsmith, kjohnson
        if len(prefix) >= 3 and prefix[0].isalpha() and prefix[1:].isalpha():
            return True
        return False

    def _extract_domain(self, website: str) -> str:
        """提取域名"""
        if not website:
            return ''
        try:
            parsed = urlparse(website)
            domain = parsed.netloc.replace('www.', '')
            return domain
        except Exception:
            return ''

    def _html_to_text(self, html: str) -> str:
        """将HTML转为纯文本"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            # 移除script和style
            for tag in soup.find_all(['script', 'style', 'noscript']):
                tag.decompose()
            return soup.get_text(separator=' ', strip=True)
        except ImportError:
            text = re.sub(r'<[^>]+>', ' ', html)
            return re.sub(r'\s+', ' ', text).strip()
