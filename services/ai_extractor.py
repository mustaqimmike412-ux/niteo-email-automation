#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 内容筛选和提取模块
使用 DeepSeek API 自动处理客户数据：
  1. 从非结构化文本中提取联系人信息（姓名、职位、邮箱）
  2. 筛选和分类客户数据
  3. 智能识别邮箱类型（个人/公共）
  4. 数据清洗和标准化
"""

import json
import re
from typing import List, Dict, Optional, Tuple
from services.llm_client import LLMEmailClient


class AIExtractor:
    """基于 DeepSeek API 的智能数据提取器"""

    def __init__(self, api_key=None, base_url=None, model=None):
        self.llm = LLMEmailClient(api_key=api_key, base_url=base_url, model=model)

    def is_available(self):
        return self.llm.is_available()

    # ==================== 1. 联系人信息提取 ====================

    def extract_contacts_from_text(self, text: str, customer_name: str = "") -> List[Dict]:
        """
        从非结构化文本中提取联系人信息
        支持格式：
          - 姓名：XXX 职位：XXX 邮箱：xxx@xxx.com
          - Name, Title, email@domain.com
          - 混合中英文格式

        Returns:
            [{"contact_name": str, "job_title": str, "email": str, "email_type": str}, ...]
        """
        if not text or len(text.strip()) < 5:
            return []

        system_prompt = """You are a data extraction specialist. Extract contact information from the provided text.

Rules:
1. Extract ALL contacts found in the text
2. For each contact, identify: name, job title, email address
3. Determine email type: "personal" (has person's name) or "public" (generic like info@, sales@)
4. If name is missing but email looks personal, try to infer name from email prefix
5. Output ONLY valid JSON array, no markdown, no explanation

Output format:
[
  {"contact_name": "Full Name", "job_title": "Job Title", "email": "email@domain.com", "email_type": "personal|public"},
  ...
]

Special handling:
- Chinese format "姓名：XXX 职位：XXX 邮箱：XXX" → extract accordingly
- English format "Name - Title - email" → extract accordingly
- If job title is missing, use ""
- If contact_name cannot be determined, use """""

        user_prompt = f"""Customer Company: {customer_name or 'Unknown'}

Text to extract contacts from:
---
{text[:8000]}
---

Extract all contacts and output JSON array."""

        content, error = self.llm._call(
            system_prompt, user_prompt,
            max_tokens=2000, temperature=0.1, label='extract_contacts'
        )

        if error or not content:
            return []

        try:
            # 清理可能的 markdown 包裹
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            result = json.loads(content.strip())
            if isinstance(result, list):
                # 验证和清理结果
                cleaned = []
                for item in result:
                    if isinstance(item, dict) and item.get('email'):
                        email = item['email'].strip().lower()
                        if self._is_valid_email(email):
                            cleaned.append({
                                'contact_name': item.get('contact_name', '').strip(),
                                'job_title': item.get('job_title', '').strip(),
                                'email': email,
                                'email_type': item.get('email_type', 'personal').strip().lower()
                            })
                return cleaned
            return []
        except (json.JSONDecodeError, Exception):
            return []

    # ==================== 2. 客户数据筛选和分类 ====================

    def classify_customer_data(self, customer_data: Dict) -> Dict:
        """
        基于客户信息智能分类

        Args:
            customer_data: {
                'customer_name': str,
                'country': str,
                'company_info': str,
                'website': str,
                'emails': list
            }

        Returns:
            {
                'industry': str,
                'business_model': str,
                'potential_score': int (1-10),
                'priority': str ('high'|'medium'|'low'),
                'tags': list,
                'reasoning': str
            }
        """
        system_prompt = """You are a senior B2B sales intelligence analyst specializing in solar/renewable energy industry. Analyze the customer data and provide detailed classification.

Output ONLY valid JSON, no markdown:
{
  "industry": "primary industry (solar|wind|energy_storage|renewable_energy|automation|security|outdoor|agriculture|consumer_electronics|distributor|other)",
  "business_model": "distributor|manufacturer|brand_owner|installer|retailer|wholesaler|integrator|unknown",
  "potential_score": 1-10,
  "priority": "high|medium|low",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "reasoning": "brief explanation in Chinese",
  "recommendation": "suggested approach for outreach in Chinese"
}

Rules for potential_score:
- 10: Solar/renewable energy company with clear procurement needs, large scale, multiple personal contacts
- 8-9: Solar-related manufacturer/distributor with good contact info
- 6-7: Renewable energy or related industry, potential for cross-selling
- 4-5: General industry, unclear solar relevance
- 1-3: Low relevance, minimal contact info

Rules for priority:
- high: potential_score >= 7 AND has personal email contacts
- medium: potential_score 4-6 OR has only public emails
- low: potential_score <= 3

Rules for tags:
- Include: industry keywords (solar, wind, battery, etc.)
- Include: business type (manufacturer, distributor, etc.)
- Include: geography tag if notable
- Include: product keywords if available
- Include: "high_priority" if score >= 8

Rules for reasoning:
- Explain the industry classification basis
- Mention why this score was given
- Note any red flags or positive signals
- Keep under 100 characters

Rules for recommendation:
- Suggest best outreach strategy
- Mention which products to pitch
- Note cultural/region-specific tips if applicable"""

        emails_summary = ""
        if customer_data.get('emails'):
            personal_count = sum(1 for e in customer_data['emails'] if e.get('email_type') == 'personal')
            public_count = len(customer_data['emails']) - personal_count
            emails_summary = f"个人邮箱: {personal_count}, 公共邮箱: {public_count}"

        user_prompt = f"""Customer Name: {customer_data.get('customer_name', 'Unknown')}
Country: {customer_data.get('country', 'Unknown')}
Website: {customer_data.get('website', 'N/A')}
Company Info: {customer_data.get('company_info', 'N/A')[:1000]}
{emails_summary}

Analyze and classify this customer."""

        content, error = self.llm._call(
            system_prompt, user_prompt,
            max_tokens=800, temperature=0.3, label='classify_customer'
        )

        if error or not content:
            return self._default_classification()

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            result = json.loads(content.strip())
            if isinstance(result, dict):
                return {
                    'industry': result.get('industry', 'other'),
                    'business_model': result.get('business_model', 'unknown'),
                    'potential_score': min(10, max(1, int(result.get('potential_score', 5)))),
                    'priority': result.get('priority', 'medium'),
                    'tags': result.get('tags', []),
                    'reasoning': result.get('reasoning', ''),
                    'recommendation': result.get('recommendation', '')
                }
        except (json.JSONDecodeError, Exception):
            pass

        return self._default_classification()

    # ==================== 3. 邮箱类型智能识别 ====================

    def detect_email_type(self, email: str, contact_name: str = "") -> str:
        """
        智能识别邮箱类型
        Returns: 'personal' 或 'public'
        """
        email = email.lower().strip()
        prefix = email.split('@')[0] if '@' in email else email

        # 明显的公共邮箱关键词
        public_keywords = [
            'info', 'sales', 'support', 'contact', 'admin', 'hello', 'team',
            'service', 'help', 'marketing', 'office', 'general', 'enquiries',
            'inquiry', 'business', 'customerservice', 'feedback', 'hr',
            'careers', 'jobs', 'press', 'media', 'partners', 'abuse',
            'webmaster', 'postmaster', 'hostmaster', 'noc', 'security',
            'billing', 'account', 'accounts', 'finance', 'legal', 'privacy'
        ]

        # 检查前缀是否匹配公共关键词
        if prefix in public_keywords:
            return 'public'

        # 如果提供了联系人姓名，且邮箱前缀包含姓名信息，判定为个人邮箱
        if contact_name and len(contact_name) > 2:
            name_parts = contact_name.lower().split()
            if len(name_parts) >= 2:
                first, last = name_parts[0], name_parts[-1]
                # 检查前缀是否包含姓名首字母或全名
                if first in prefix or last in prefix:
                    return 'personal'
                # 检查首字母+姓氏格式
                if prefix == f"{first[0]}{last}" or prefix == f"{first[0]}.{last}":
                    return 'personal'

        # 使用 AI 进行最终判断
        system_prompt = """You are an email classification expert. Determine if an email address is personal or public.

Rules:
- "personal": Contains a person's name or initials (e.g., john.doe@, jsmith@, michael@)
- "public": Generic role-based email (e.g., info@, sales@, support@, hello@)
- Output ONLY: "personal" or "public" (no explanation)"""

        user_prompt = f"""Email: {email}
Contact Name (if known): {contact_name or 'Unknown'}

Classify this email as "personal" or "public"."""

        content, error = self.llm._call(
            system_prompt, user_prompt,
            max_tokens=50, temperature=0.1, label='detect_email_type'
        )

        if error or not content:
            # 默认规则：如果包含点号且看起来像名字，判定为个人
            if '.' in prefix and len(prefix) > 4:
                parts = prefix.split('.')
                if len(parts) == 2 and len(parts[0]) > 1 and len(parts[1]) > 1:
                    return 'personal'
            return 'public'

        result = content.strip().lower()
        if 'personal' in result:
            return 'personal'
        return 'public'

    # ==================== 4. 数据清洗和标准化 ====================

    def clean_contact_name(self, name: str) -> str:
        """
        清洗和标准化联系人姓名
        """
        if not name:
            return ""

        name = name.strip()

        # 移除常见前缀/后缀
        prefixes = ['mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sir', 'madam']
        suffixes = ['jr.', 'sr.', 'ii', 'iii', 'iv', 'ph.d', 'mba']

        name_lower = name.lower()
        for prefix in prefixes:
            if name_lower.startswith(prefix + ' '):
                name = name[len(prefix):].strip()
                break

        for suffix in suffixes:
            if name_lower.endswith(' ' + suffix):
                name = name[:-(len(suffix))].strip()
                break

        # 标准化大小写
        name = ' '.join(word.capitalize() for word in name.split())

        return name

    def clean_job_title(self, title: str) -> str:
        """
        清洗和标准化职位名称
        """
        if not title:
            return ""

        title = title.strip()

        # 常见职位映射
        title_mapping = {
            'ceo': 'CEO',
            'cto': 'CTO',
            'cfo': 'CFO',
            'coo': 'COO',
            'vp': 'VP',
            'svp': 'SVP',
            'evp': 'EVP',
            'gm': 'General Manager',
            'hr': 'HR Manager',
            'it': 'IT Manager',
        }

        title_lower = title.lower()
        if title_lower in title_mapping:
            return title_mapping[title_lower]

        # 标准化大小写
        words = title.split()
        if len(words) > 0:
            # 保留常见大写缩写
            common_acronyms = ['ceo', 'cto', 'cfo', 'coo', 'vp', 'hr', 'it', 'pr', 'rd']
            cleaned = []
            for word in words:
                word_lower = word.lower()
                if word_lower in common_acronyms:
                    cleaned.append(word.upper())
                else:
                    cleaned.append(word.capitalize())
            title = ' '.join(cleaned)

        return title

    # ==================== 5. 批量处理客户数据 ====================

    def process_customer_batch(self, customers: List[Dict]) -> List[Dict]:
        """
        批量处理客户数据，提取和标准化所有信息

        Args:
            customers: 原始客户数据列表

        Returns:
            处理后的客户数据列表
        """
        processed = []

        for customer in customers:
            processed_customer = {
                'customer_name': customer.get('customer_name', '').strip(),
                'country': customer.get('country', '').strip(),
                'address': customer.get('address', '').strip(),
                'website': customer.get('website', '').strip(),
                'company_info': customer.get('company_info', '').strip(),
                'emails': []
            }

            # 处理邮箱
            raw_emails = customer.get('emails', [])
            for email_data in raw_emails:
                email_addr = email_data.get('email_address', '').strip().lower()
                if not email_addr or not self._is_valid_email(email_addr):
                    continue

                # 清洗姓名和职位
                contact_name = self.clean_contact_name(
                    email_data.get('contact_name', '')
                )
                job_title = self.clean_job_title(
                    email_data.get('job_title', '')
                )

                # 检测邮箱类型
                email_type = email_data.get('email_type', '')
                if not email_type or email_type not in ['personal', 'public']:
                    email_type = self.detect_email_type(email_addr, contact_name)

                processed_customer['emails'].append({
                    'email_address': email_addr,
                    'email_type': email_type,
                    'contact_name': contact_name,
                    'job_title': job_title,
                    'source': email_data.get('source', 'import')
                })

            # AI 分类客户
            if processed_customer['customer_name']:
                classification = self.classify_customer_data(processed_customer)
                processed_customer['classification'] = classification

            processed.append(processed_customer)

        return processed

    # ==================== 6. 从 Excel/文本中提取所有信息 ====================

    def extract_from_unstructured_text(self, text: str) -> Dict:
        """
        从完全非结构化的文本中提取客户信息
        适用于：网页内容、邮件签名、聊天记录等

        Returns:
            {
                'customer_name': str,
                'contacts': [{"name", "title", "email", "email_type"}],
                'country': str,
                'website': str,
                'business_info': str
            }
        """
        if not text or len(text.strip()) < 10:
            return {}

        system_prompt = """You are a data extraction specialist. Extract structured customer information from unstructured text.

Output ONLY valid JSON, no markdown:
{
  "customer_name": "company name or empty",
  "contacts": [
    {"name": "contact name", "title": "job title", "email": "email address", "email_type": "personal|public"}
  ],
  "country": "country or region",
  "website": "website URL or empty",
  "business_info": "brief business description"
}

Rules:
- Extract ALL contacts found in the text
- If email type is unclear, use "personal" for named individuals, "public" for generic emails
- country: infer from context (domain, address, phone code)
- Keep business_info concise (under 100 characters)
- If information is not found, use empty string """""

        user_prompt = f"""Extract customer information from this text:

---
{text[:10000]}
---

Output JSON with extracted information."""

        content, error = self.llm._call(
            system_prompt, user_prompt,
            max_tokens=1500, temperature=0.2, label='extract_unstructured'
        )

        if error or not content:
            return {}

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            result = json.loads(content.strip())
            if isinstance(result, dict):
                # 清理联系人
                cleaned_contacts = []
                for contact in result.get('contacts', []):
                    email = contact.get('email', '').strip().lower()
                    if email and self._is_valid_email(email):
                        cleaned_contacts.append({
                            'name': self.clean_contact_name(contact.get('name', '')),
                            'title': self.clean_job_title(contact.get('title', '')),
                            'email': email,
                            'email_type': contact.get('email_type', 'personal').lower()
                        })
                result['contacts'] = cleaned_contacts
                return result
        except (json.JSONDecodeError, Exception):
            pass

        return {}

    # ==================== 辅助方法 ====================

    def _is_valid_email(self, email: str) -> bool:
        """验证邮箱格式"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def classify_customers_batch(self, customers_data: List[Dict]) -> List[Dict]:
        """
        批量分类客户 - 一次API调用处理多个客户，大幅减少API调用次数

        Args:
            customers_data: 客户数据列表，每项包含 customer_name, country, company_info, website, emails

        Returns:
            分类结果列表，与输入顺序一致
        """
        if not customers_data:
            return []

        # 构建批量分类的prompt
        system_prompt = """You are a senior B2B sales intelligence analyst. Analyze multiple customers at once and provide classification for each.

Output ONLY valid JSON array, no markdown:
[
  {
    "industry": "solar|wind|energy_storage|renewable_energy|automation|security|outdoor|agriculture|consumer_electronics|distributor|other",
    "business_model": "distributor|manufacturer|brand_owner|installer|retailer|wholesaler|integrator|unknown",
    "potential_score": 1-10,
    "priority": "high|medium|low",
    "tags": ["tag1", "tag2", "tag3"],
    "reasoning": "brief explanation in Chinese",
    "recommendation": "suggested approach in Chinese"
  },
  ...
]

Rules for potential_score:
- 10: Solar/renewable energy company with clear procurement needs, large scale, multiple personal contacts
- 8-9: Solar-related manufacturer/distributor with good contact info
- 6-7: Renewable energy or related industry, potential for cross-selling
- 4-5: General industry, unclear solar relevance
- 1-3: Low relevance, minimal contact info

Rules for priority:
- high: potential_score >= 7 AND has personal email contacts
- medium: potential_score 4-6 OR has only public emails
- low: potential_score <= 3

Output exactly the same number of results as input customers, in the same order."""

        # 构建客户摘要列表
        customer_summaries = []
        for i, customer in enumerate(customers_data):
            emails_summary = ""
            if customer.get('emails'):
                personal_count = sum(1 for e in customer['emails'] if e.get('email_type') == 'personal')
                public_count = len(customer['emails']) - personal_count
                emails_summary = f"个人邮箱: {personal_count}, 公共邮箱: {public_count}"

            summary = f"""Customer #{i+1}:
Name: {customer.get('customer_name', 'Unknown')}
Country: {customer.get('country', 'Unknown')}
Website: {customer.get('website', 'N/A')}
Company Info: {customer.get('company_info', 'N/A')[:300]}
{emails_summary}"""
            customer_summaries.append(summary)

        separator = '\n---\n'
        user_prompt = f"""Analyze and classify these {len(customers_data)} customers:

{separator.join(customer_summaries)}

Output JSON array with exactly {len(customers_data)} classification results, in the same order as the input customers."""

        content, error = self.llm._call(
            system_prompt, user_prompt,
            max_tokens=2000, temperature=0.3, label='classify_batch'
        )

        if error or not content:
            # 如果批量调用失败，返回默认分类
            return [self._default_classification() for _ in customers_data]

        try:
            # 清理可能的 markdown 包裹
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            result = json.loads(content.strip())
            if isinstance(result, list) and len(result) == len(customers_data):
                classifications = []
                for item in result:
                    if isinstance(item, dict):
                        classifications.append({
                            'industry': item.get('industry', 'other'),
                            'business_model': item.get('business_model', 'unknown'),
                            'potential_score': min(10, max(1, int(item.get('potential_score', 5)))),
                            'priority': item.get('priority', 'medium'),
                            'tags': item.get('tags', []),
                            'reasoning': item.get('reasoning', ''),
                            'recommendation': item.get('recommendation', '')
                        })
                    else:
                        classifications.append(self._default_classification())
                return classifications
            elif isinstance(result, dict) and 'classifications' in result:
                # 有些模型可能返回嵌套格式
                nested = result['classifications']
                if isinstance(nested, list) and len(nested) == len(customers_data):
                    classifications = []
                    for item in nested:
                        if isinstance(item, dict):
                            classifications.append({
                                'industry': item.get('industry', 'other'),
                                'business_model': item.get('business_model', 'unknown'),
                                'potential_score': min(10, max(1, int(item.get('potential_score', 5)))),
                                'priority': item.get('priority', 'medium'),
                                'tags': item.get('tags', []),
                                'reasoning': item.get('reasoning', ''),
                                'recommendation': item.get('recommendation', '')
                            })
                        else:
                            classifications.append(self._default_classification())
                    return classifications
        except (json.JSONDecodeError, Exception):
            pass

        # 解析失败，返回默认分类
        return [self._default_classification() for _ in customers_data]

    def _default_classification(self) -> Dict:
        """默认分类结果"""
        return {
            'industry': 'other',
            'business_model': 'unknown',
            'potential_score': 5,
            'priority': 'medium',
            'tags': [],
            'reasoning': '无法自动分类，使用默认值',
            'recommendation': '建议手动审核该客户信息'
        }


# ==================== 便捷函数 ====================

def create_extractor() -> AIExtractor:
    """创建 AIExtractor 实例"""
    return AIExtractor()


def quick_extract_contacts(text: str, customer_name: str = "") -> List[Dict]:
    """快速提取联系人（便捷函数）"""
    extractor = create_extractor()
    if not extractor.is_available():
        return []
    return extractor.extract_contacts_from_text(text, customer_name)


def quick_classify_customer(customer_data: Dict) -> Dict:
    """快速分类客户（便捷函数）"""
    extractor = create_extractor()
    if not extractor.is_available():
        return AIExtractor()._default_classification()
    return extractor.classify_customer_data(customer_data)
