"""
AI搜索结果分析流水线
对原始搜索结果进行AI分析和标准化
使用DeepSeek API进行深度公司官网分析
"""
import json
from typing import List, Dict, Optional
from services.search.base import SearchResult
from services.llm_client import LLMEmailClient


class SearchAIEnricher:
    """对搜索结果进行AI分析和标准化"""

    def __init__(self):
        self.llm = LLMEmailClient()

    def is_available(self):
        return self.llm.is_available()

    def enrich_result(self, search_result: SearchResult) -> Optional[dict]:
        """
        AI分析单条搜索结果，提取/标准化公司信息
        返回分析结果字典，失败返回None
        """
        if not self.is_available():
            return None

        # 跳过已被标记为拒绝的结果
        if search_result.validation_status == 'rejected':
            print(f"[AIEnricher] 跳过已拒绝结果: {search_result.company_name}")
            return None

        raw = search_result.raw_data
        platform = search_result.platform

        # 构建原始数据摘要
        raw_summary = json.dumps(raw, ensure_ascii=False, indent=2)[:3000]

        system_prompt = """You are a professional B2B lead research analyst. Analyze the following raw business data and produce a DETAILED company profile.

CRITICAL: Even with limited data, produce as detailed an analysis as possible. Infer reasonable details from the company name, description, website URL, and industry context.

CRITICAL ACCURACY CHECK: If the provided data appears to be from a directory, forum, review site, aggregator, or social media profile rather than the company's official website, set confidence_score below 0.3 and mark has_solar_products as false. Only analyze genuine company websites.

Output ONLY valid JSON. JSON structure:
{
  "company_name": "",
  "website": "",
  "country": "",
  "address": "",
  "phone": "",
  "email": "",
  "industry_type": "distributor|manufacturer|brand_owner|installer|energy_storage|other",
  "business_model": "distributor|manufacturer|brand_owner|installer|unknown",
  "has_solar_products": true,
  "target_markets": ["市场1", "市场2"],
  "core_products": ["具体产品1", "具体产品2", "具体产品3"],
  "confidence_score": 0.0,
  "ai_summary": "3-5句中文分析：公司做什么、太阳能相关度、为什么值得开发",
  "company_profile": {
    "overview": "100-200字中文公司简介，根据已有信息推断",
    "business_scope": "业务范围描述",
    "product_lines": ["推断的产品线1", "产品线2"],
    "brands_distributed": ["品牌1"],
    "services": ["服务1"],
    "years_in_business": "unknown",
    "company_size": "Unknown"
  },
  "solar_relevance": {
    "sells_solar_panels": true,
    "solar_product_types": ["产品类型1"],
    "target_solar_segments": ["residential"],
    "oem_odm_capability": true,
    "competitive_advantages": ["优势1"]
  },
  "contact_intelligence": {
    "decision_maker_hints": "",
    "best_contact_method": "email",
    "partnership_potential": ""
  }
}

Rules:
- Infer reasonable company details from available data. Even a name + URL gives useful signals.
- company_profile.overview: Write 100-150 Chinese characters. ONLY include: company name, location/headquarters, main business scope, and 1-2 key products or services. Do NOT include company philosophy, mission, values, slogans, or vague marketing language. Be factual and informative but concise.
- core_products: List likely products based on company name, description, and industry.
- ai_summary: 3-5 sentences in Chinese.
- For truly unknown fields, use empty string or "unknown"."""

        user_prompt = f"""Platform: {platform}

Raw Data:
{raw_summary}

Analyze this business and output the JSON."""

        content, error = self.llm._call(
            system_prompt, user_prompt,
            max_tokens=2000, temperature=0.3,
            label=f'lead_enrich:{raw.get("name", "unknown")[:30]}',
            response_format={"type": "json_object"}
        )

        if error or not content:
            return None

        result = self._parse_json_safely(content)
        if result:
            if 'confidence_score' not in result:
                result['confidence_score'] = 0.5
            result['confidence_score'] = max(0.0, min(1.0, float(result.get('confidence_score', 0.5))))
            return result

        print(f"[AIEnricher] enrich_result JSON解析失败")
        return None

    def batch_enrich(self, results: List[SearchResult], batch_size: int = 5) -> List[Optional[dict]]:
        """
        批量分析搜索结果，控制API调用成本
        返回与results等长的分析结果列表（失败位置为None）
        """
        if not self.is_available():
            return [None] * len(results)

        enriched = []
        for i in range(0, len(results), batch_size):
            batch = results[i:i + batch_size]
            batch_enriched = self._enrich_batch(batch)
            enriched.extend(batch_enriched)

        return enriched

    def _enrich_batch(self, results: List[SearchResult]) -> List[Optional[dict]]:
        """分析一批结果（单条调用，可优化为真正的批量API调用）"""
        return [self.enrich_result(r) for r in results]

    def enrich_with_crawl(self, search_result: SearchResult, crawl_data: dict) -> Optional[dict]:
        """
        结合网站爬取数据进行深度AI分析
        生成包含完整公司简介、产品、业务模式的详细档案
        """
        if not self.is_available():
            return None

        # 跳过已被标记为拒绝的结果
        if search_result.validation_status == 'rejected':
            print(f"[AIEnricher] 跳过已拒绝结果: {search_result.company_name}")
            return None

        raw = search_result.raw_data
        platform = search_result.platform

        # 构建完整的公司数据上下文（精简版，避免prompt过长导致JSON截断）
        combined = {
            'platform': platform,
            'raw_data': raw,
            'crawled_data': {
                'title': crawl_data.get('title', ''),
                'description': crawl_data.get('description', '')[:500],
                'about_text': crawl_data.get('about_text', '')[:2000],
                'contact_text': crawl_data.get('contact_text', '')[:800],
                'all_text': crawl_data.get('all_text', '')[:3000],
                'emails': crawl_data.get('emails', []),
                'phones': crawl_data.get('phones', []),
            }
        }

        data_text = json.dumps(combined, ensure_ascii=False, indent=2)[:4000]

        system_prompt = """You are a senior B2B market research analyst. Your task is to analyze a company's website and produce a DETAILED, COMPREHENSIVE company profile in Chinese.

CRITICAL REQUIREMENTS FOR CONTENT LENGTH AND DETAIL:
1. company_profile.overview: MUST be 100-150 Chinese characters. ONLY include: company name, location/headquarters, main business scope, and 1-2 key products or services. Do NOT include company philosophy, mission, values, slogans, or vague marketing language. Be factual and informative but concise. Example: "USA Solar Energy总部位于美国加州尔湾，专注于住宅和商用太阳能系统的设计、销售与安装，同时提供EV充电桩解决方案，服务覆盖加州全境。"
2. company_profile.product_lines: List SPECIFIC product categories the company actually sells. Be concrete (e.g., "单晶硅太阳能板 400W-600W系列", "微型逆变器", "储能电池系统"), not vague generics like "solar products".
3. company_profile.business_scope: Describe what markets they serve and what value they provide (50-100 Chinese characters).
4. core_products: Top 3-5 specific products with brief descriptions (e.g., "400W单晶半片组件", "Enphase微型逆变器IQ8系列").
5. ai_summary: 3-5 sentences in Chinese explaining what the company does, why it's relevant to solar B2B partnerships, and what makes it a potential lead. NOT a one-liner.
6. solar_relevance.solar_product_types: SPECIFIC solar product types they carry (e.g., "单晶硅PERC组件", "TOPCon双面组件", "混合逆变器", "磷酸铁锂储能柜").
7. solar_relevance.competitive_advantages: 2-3 specific advantages based on website content.

Output ONLY valid JSON, no markdown, no explanation.

JSON structure:
{
  "company_name": "",
  "website": "",
  "country": "",
  "address": "",
  "phone": "",
  "email": "",
  "industry_type": "distributor|manufacturer|brand_owner|installer|energy_storage|other",
  "business_model": "distributor|manufacturer|brand_owner|installer|unknown",
  "has_solar_products": true,
  "target_markets": ["美国住宅市场", "欧洲工商业市场"],
  "core_products": ["具体产品1", "具体产品2", "具体产品3"],
  "confidence_score": 0.0,
  "ai_summary": "3-5句中文分析，说明公司做什么、太阳能业务相关度、为什么值得开发",
  "company_profile": {
    "overview": "100-150字中文公司简介，包含公司名称、所在地、主营业务和核心产品/服务，不包含公司理念/使命",
    "business_scope": "50-100字业务范围描述",
    "product_lines": ["具体产品线1", "具体产品线2"],
    "brands_distributed": ["代理品牌1", "代理品牌2"],
    "services": ["安装服务", "售后维护"],
    "years_in_business": "成立年限或unknown",
    "company_size": "Small/Medium/Large/Unknown"
  },
  "solar_relevance": {
    "sells_solar_panels": true,
    "solar_product_types": ["单晶硅PERC组件400W+", "微型逆变器", "储能系统"],
    "target_solar_segments": ["residential", "commercial", "industrial", "off-grid"],
    "oem_odm_capability": true,
    "competitive_advantages": ["优势1", "优势2"]
  },
  "contact_intelligence": {
    "decision_maker_hints": "采购决策线索",
    "best_contact_method": "email/phone/form",
    "partnership_potential": "合作潜力评估"
  }
}

Rules:
- Output valid JSON only. Use empty strings/arrays for unknown fields.
- ALL Chinese text fields must be detailed and professional, NOT one-sentence summaries.
- If website data is sparse, state what is known and mark unknowns as empty string."""

        user_prompt = f"""Analyze the following company website data and generate a DETAILED company profile in Chinese.

Company Data:
{data_text}

Remember: overview must be 200-400 Chinese characters. Product lines must be specific. Output JSON only."""

        content, error = self.llm._call(
            system_prompt, user_prompt,
            max_tokens=4000, temperature=0.3,
            label=f'lead_deep_enrich:{raw.get("name", "unknown")[:30]}',
            response_format={"type": "json_object"}
        )

        if error or not content:
            print(f"[AIEnricher] Deep enrich API call failed: {error}")
            return None

        # 尝试多种方式解析JSON
        result = self._parse_json_safely(content)
        if result:
            result['confidence_score'] = max(0.0, min(1.0, float(result.get('confidence_score', 0.5))))
            return result

        # Fallback: try basic enrich
        print(f"[AIEnricher] Deep enrich failed, fallback to basic enrich")
        return self.enrich_result(search_result)

    def _parse_json_safely(self, content: str) -> Optional[dict]:
        """安全解析JSON，处理截断、markdown包裹等问题"""
        if not content:
            return None

        # 去除markdown代码块
        for pattern in ['```json', '```']:
            if pattern in content:
                parts = content.split(pattern)
                if len(parts) >= 2:
                    content = parts[1].split('```')[0] if pattern == '```json' else parts[1]

        content = content.strip()
        if not content:
            return None

        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试修复截断的JSON：补全缺失的括号
        try:
            fixed = self._fix_truncated_json(content)
            if fixed:
                return json.loads(fixed)
        except (json.JSONDecodeError, ValueError):
            pass

        # 尝试提取JSON对象（从第一个{到最后一个}）
        try:
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1 and end > start:
                return json.loads(content[start:end+1])
        except json.JSONDecodeError:
            pass

        return None

    def _fix_truncated_json(self, content: str) -> Optional[str]:
        """尝试修复截断的JSON字符串"""
        # 统计括号
        open_braces = content.count('{')
        close_braces = content.count('}')
        open_brackets = content.count('[')
        close_brackets = content.count(']')

        fixed = content
        # 补全缺失的括号
        for _ in range(open_braces - close_braces):
            fixed += '}'
        for _ in range(open_brackets - close_brackets):
            fixed += ']'

        # 如果最后一个是逗号，去掉它
        if fixed.rstrip().endswith(','):
            fixed = fixed.rstrip()[:-1]

        # 如果字符串在引号中截断，尝试关闭它
        quote_count = fixed.count('"') - fixed.count('\\"')
        if quote_count % 2 == 1:
            fixed += '"'

        return fixed
