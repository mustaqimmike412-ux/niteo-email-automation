"""
DeepSeek V4 Pro API 客户端
用于邮件生成工作流的多个节点：公司背调、FABE话术、邮件生成、邮件润色
使用 openai SDK（DeepSeek 兼容 OpenAI 接口）
"""
import json
import os
import time
import random
from openai import OpenAI
from openai import APITimeoutError, APIConnectionError, RateLimitError, InternalServerError


class LLMEmailClient:
    """DeepSeek 大模型邮件生成客户端"""

    def __init__(self, api_key=None, base_url=None, model=None, user_id=None):
        self.user_id = user_id
        # 优先从数据库读取配置
        db_config = self._load_db_config()
        # 回退到 JSON 文件
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'llm_config.json')
        file_config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = json.load(f)

        self.api_key = api_key or db_config.get('api_key') or file_config.get('api_key', '')
        self.base_url = base_url or db_config.get('base_url') or file_config.get('base_url', 'https://api.deepseek.com')
        self.model = model or db_config.get('model') or file_config.get('model', 'deepseek-v4-pro')
        self.client = None

    def _load_db_config(self):
        """从数据库加载 DeepSeek 配置"""
        try:
            from database.api_config_models import get_api_config
            cfg = get_api_config('DeepSeek')
            if cfg:
                return {
                    'api_key': cfg.get('api_key', ''),
                    'base_url': cfg.get('base_url', ''),
                    'model': cfg.get('model', '')
                }
        except Exception:
            pass
        return {}

    def _get_client(self):
        if not self.client and self.api_key:
            try:
                from httpx import Timeout
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=Timeout(connect=30.0, read=120.0, write=30.0, pool=10.0)
                )
            except ImportError:
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=120
                )
        return self.client

    def is_available(self):
        return bool(self.api_key)

    def _call(self, system_prompt, user_prompt, max_tokens=1000, temperature=0.7, label='unknown', response_format=None):
        """统一的 API 调用方法，带重试机制和用量记录"""
        client = self._get_client()
        if not client:
            return None, 'API Key 未配置'

        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                kwargs = {
                    'model': self.model,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt}
                    ],
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                }
                if response_format:
                    kwargs['response_format'] = response_format

                response = client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content.strip()
                self._log_usage(label, response.usage)
                return content, None

            except (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError) as e:
                if attempt < max_retries:
                    delay = min((2 ** attempt) + random.uniform(0, 1), 30)
                    print(f"[LLMClient] {label} API错误（{type(e).__name__}），{delay:.1f}秒后重试({attempt+1}/{max_retries})...")
                    time.sleep(delay)
                else:
                    print(f"[LLMClient] {label} 重试耗尽，最终错误: {e}")
                    return None, str(e)
            except Exception as e:
                # 客户端错误（400/401/403等）不重试
                return None, str(e)

    # ==================== 节点1: 公司背调分析 ====================

    def analyze_company(self, page_text, search_summary, customer_name):
        """
        分析公司网页文本和搜索结果，输出结构化的背调报告。

        Args:
            page_text: 网页全文（最多5000字符）
            search_summary: 搜索引擎结果摘要
            customer_name: 客户公司名称

        Returns:
            dict or None: 结构化分析结果，失败返回 None
        """
        system_prompt = """You are a professional B2B market research analyst. Analyze the following company information and output a JSON object.

Output ONLY valid JSON, no markdown, no explanation. JSON structure:
{
  "main_business": "brief description of what the company does",
  "target_markets": ["market1", "market2"],
  "business_model": "distributor" | "manufacturer" | "brand_owner" | "installer" | "unknown",
  "core_products": ["product1", "product2"],
  "industry": "security" | "outdoor" | "automation" | "agriculture" | "energy_storage" | "consumer_electronics" | "distributor" | "other",
  "has_solar_products": true/false,
  "solar_products": ["solar product1"],
  "power_tendency": "high_power" | "low_power" | "mixed" | "unknown",
  "track": "Security & Smart Home Hardware" | "Outdoor & Portable Power" | "Automation & Gate Systems" | "Agriculture & Livestock" | "Energy Storage" | "Consumer Electronics" | "General",
  "pain_points": [{"type": "keyword", "desc": "description"}],
  "opportunities": [{"type": "keyword", "desc": "description"}]
}

Rules:
- If the company sells security cameras, trail cameras, smart home devices → industry=security
- If outdoor equipment, camping gear, portable power → industry=outdoor
- If gate openers, access control → industry=automation
- If livestock, pasture monitoring → industry=agriculture
- business_model: if they mention "distributing", "wholesale" → distributor; if "manufacturing", "factory" → manufacturer; if own brand name → brand_owner
- has_solar_products: true only if they explicitly sell solar panels, solar chargers, or solar-powered devices
- Limit target_markets to top 3
- Limit core_products to top 5
- Limit pain_points and opportunities to top 3 each"""

        user_prompt = f"""Company Name: {customer_name}

--- Website Content ---
{page_text[:5000]}

--- Search Results ---
{search_summary[:2000]}

Analyze this company and output the JSON."""

        content, error = self._call(system_prompt, user_prompt, max_tokens=1200, temperature=0.3, label=f'research:{customer_name}')
        if error or not content:
            return None

        try:
            # 尝试提取 JSON（可能被 ```json 包裹）
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            result = json.loads(content.strip())
            return result
        except json.JSONDecodeError:
            return None

    # ==================== 节点4: FABE 话术生成 ====================

    def generate_fabe(self, advantages, classification, research_result):
        """
        基于素材库优势和客户信息，生成 FABE 话术。

        Args:
            advantages: 素材库优势列表 [{name, tech_features, scope, customer_value}, ...]
            classification: 客户分类 {power_type, track, case_tag, priorities}
            research_result: 背调结果

        Returns:
            list or None: FABE 列表 [{advantage_name, F, A, B, E}, ...]
        """
        company_name = research_result.get('module1_profile', {}).get('company_name', 'the customer')
        track = classification.get('track', 'General')
        pain_points = research_result.get('module3_pain_points', [])
        pain_desc = '; '.join([p.get('desc', '') for p in pain_points[:3]]) if pain_points else 'Unknown'

        advantages_text = '\n'.join([
            f"- {a.get('name', '')}: Features={a.get('tech_features', '')}, Scope={a.get('scope', '')}, Value={a.get('customer_value', '')}"
            for a in advantages[:4]
        ])

        system_prompt = """You are a B2B sales copywriting expert for a solar energy company.
Generate FABE (Feature-Advantage-Benefit-Evidence) selling points for each advantage.

Output ONLY valid JSON array, no markdown. Each item:
{"advantage_name": "name", "F": "feature description", "A": "what this means for the customer", "B": "how it solves their specific pain point", "E": "brief evidence or credibility point"}

Rules:
- F: Describe the technical feature clearly in 1-2 sentences
- A: Translate the feature into a customer-facing advantage
- B: Connect the advantage to the customer's specific pain points or industry needs
- E: Include a brief credibility point (certification, customer count, years of experience, or case study reference)
- Keep each field concise (1-2 sentences max)
- Write in professional business English"""

        user_prompt = f"""Customer: {company_name}
Industry Track: {track}
Customer Pain Points: {pain_desc}

Our Advantages to translate into FABE:
{advantages_text}

Generate FABE for each advantage."""

        content, error = self._call(system_prompt, user_prompt, max_tokens=1500, temperature=0.5, label=f'fabe:{company_name}')
        if error or not content:
            return None

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            result = json.loads(content.strip())
            if isinstance(result, list):
                return result
            return None
        except json.JSONDecodeError:
            return None

    # ==================== 节点6: 邮件正文生成 ====================

    def compose_email(self, research_result, classification, fabe_points, materials,
                       contact_name=None, email_type='public', has_website=True, company_info=None,
                       target_word_count=None):
        """
        基于全部管线上下文生成完整开发信。

        Args:
            research_result: 背调结果
            classification: 客户分类
            fabe_points: FABE 话术列表
            materials: 素材库匹配结果
            contact_name: 联系人姓名
            email_type: 邮箱类型
            has_website: 客户是否有网站
            company_info: 我方公司信息
            target_word_count: 目标字数范围 {'min': int, 'max': int}

        Returns:
            dict: {'subject': str, 'body': str, 'error': str or None}
        """
        # 默认字数范围（容差±10）
        if target_word_count is None:
            target_word_count = 150
        if isinstance(target_word_count, int):
            target_word_count = {'min': max(10, target_word_count - 10), 'max': target_word_count + 10}
        min_words = target_word_count.get('min', 140)
        max_words = target_word_count.get('max', 160)
        _exact_target = (min_words + max_words) // 2
        profile = research_result.get('module1_profile', {})
        customer_name = profile.get('company_name', 'Valued Partner')
        pain_points = research_result.get('module3_pain_points', [])
        company_info = company_info or {}

        greeting_target = contact_name if contact_name and email_type == 'personal' else f'{customer_name} Team'

        # 构建 FABE 摘要（传入完整 F/A/B/E 字段）
        fabe_summary = '\n'.join([
            f"- {fp.get('advantage_name', '')}:\n  Feature: {fp.get('F', '')}\n  Advantage: {fp.get('A', '')}\n  Benefit: {fp.get('B', '')}\n  Evidence: {fp.get('E', '')}"
            for fp in (fabe_points or [])[:3]
        ])

        # 构建痛点摘要（兼容字符串列表和字典列表）
        if pain_points and isinstance(pain_points[0], str):
            pain_summary = '\n'.join([f"- {p}" for p in pain_points[:3]])
        else:
            pain_summary = '\n'.join([f"- {p.get('desc', '')}" for p in (pain_points or [])[:3]])

        # 构建素材摘要
        cases = materials.get('cases', []) if materials else []
        case_summary = '\n'.join([f"- {c.get('title', c.get('name', 'Case'))}" for c in cases[:2]])

        # 根据发信人信息是否完整，构建不同的 prompt
        has_sender = bool(company_info.get('sender_name'))
        has_company = bool(company_info.get('company_name'))
        sender_name = company_info.get('sender_name', '')
        job_title = company_info.get('job_title', '')
        company_name = company_info.get('company_name', '')

        if has_sender and has_company:
            # 发信人信息完整 — 使用真实姓名/公司名
            company_block = f"""Our company info:
- Company Name: {company_name}
- Products: {', '.join(company_info.get('main_products', [])) if company_info.get('main_products') else 'Solar panels, solar power systems, off-grid solutions'}
- Years in business: {company_info.get('years_in_business') or '10+'}
- Sender Name: {sender_name}
- Sender Title: {job_title or 'Sales Representative'}
- Key strengths:
  * {company_info.get('strength1') or 'OEM/ODM capability'}
  * {company_info.get('strength2') or 'Multi-region manufacturing'}
  * {company_info.get('strength3') or 'International certifications'}
  * {company_info.get('strength4') or 'R&D customization'}

SENDER IDENTITY (use in EVERY email — this is FIXED, never change):
- Your name: {sender_name}
- Your company: {company_name}
- Your title: {job_title or 'Sales Representative'}"""
            signature_block = f"""Best regards,
{sender_name}
{job_title or 'Sales Representative'}
{company_name}"""
        else:
            # 发信人/公司信息不完整，使用匿名版 prompt
            company_block = """About our company:
- We are a solar energy company providing solar panels, solar power systems, and off-grid solutions.
- We offer OEM/ODM capability, multi-region manufacturing, international certifications, and R&D customization.
- We have 10+ years of industry experience."""
            signature_block = """Best regards,
[Your Name]
[Your Title]
[Your Company]"""

        system_prompt = f"""You are a professional B2B sales representative. Write a personalized cold email to a potential customer.

YOUR SENDER IDENTITY (MANDATORY — use EXACTLY these details, NEVER invent or change):
- Your name: {sender_name or 'Sales Representative'}
- Your company: {company_name or 'our solar energy company'}
- Your title: {job_title or 'Sales Representative'}

STRICT FORMAT RULES:
1. DO NOT write a greeting line (no "Hi xxx,"). The system will add the greeting automatically. Start your output directly with the self-introduction sentence.

   Write ONE self-introduction sentence as the first line. Vary the phrasing each time — here are examples:
   - "I'm {sender_name or '[Your Name]'} from {company_name or '[Company]'}." (if sender info available)
   - "My name is {sender_name or '[Your Name]'}, reaching out from {company_name or '[Company]'}."
   - "This is {sender_name or '[Your Name]'} from {company_name or '[Company]'}."
   - "{company_name or '[Company]'} and I have been helping businesses like yours with..."
   Pick ONE and never repeat the same opener across emails. Do NOT use placeholders — always use the real name.

2. Body Structure — The email MUST contain ALL 4 sections below. NO section may be skipped, regardless of word count:

   Section 1 — OPENING (1-2 sentences):
   Show you understand THEIR business. Mention their company name AND at least one of their core products.
   Vary your opener — do NOT always start with "I noticed". Use diverse phrasing such as:
   - "Having followed [Company]'s expansion into..."
   - "It's great to see how [Company] has been..."
   - "With [Company]'s focus on..."
   - "I came across [Company]'s work in..."
   - "[Company]'s commitment to [specific area] caught my attention."
   NEVER repeat the same opening pattern. Make each email feel unique.

   Section 2 — PAIN POINT (1-3 sentences, scale with word budget):
   State ONE specific pain point from the "Customer Pain Points" below.
   Explain WHY this hurts their business. Use their product names and market terms.
   Be specific and concrete — NOT vague.
   If word budget allows (180+ words), you MAY add a second pain point in the same section.

   Section 3 — SOLUTION & EVIDENCE (2-4 sentences, scale with word budget):
   THIS SECTION IS MANDATORY. NEVER skip it. NEVER replace it with another pain point.
   Present our solar solution using the FABE points below.
   Explain HOW our product solves the pain point(s) above.
   MUST include at least ONE specific number, statistic, or metric from the evidence.
   If word budget is tight, keep this to 2 sentences but it MUST exist.

   Section 4 — CLOSING / CALL TO ACTION (1-2 sentences):
   A clear, specific next step. Vary your CTA phrasing:
   - "Would you be open to a quick call next Tuesday?"
   - "I'd love to share a few case studies — would that be helpful?"
   - "Can I send over a sample spec sheet for your review?"
   Pick ONE natural CTA — never use the exact same wording twice.

3. Signature (FIXED, never change):
   {signature_block}

WORD BUDGET ALLOCATION (CRITICAL — follow these proportions):
- Opening: ~15% of word count
- Pain Point: ~25% of word count
- Solution: ~40% of word count (LARGEST section — this is the core of the email)
- Closing/CTA: ~10% of word count
- Greeting+Intro: ~10%
The Solution section MUST always be the longest or second-longest section. If you find yourself writing more pain points than solution, STOP and rebalance.

CONTENT RULES:
- Length: MUST be between {min_words} and {max_words} words (target: {_exact_target}). This is a HARD constraint. Count every word precisely. If under {min_words}, add more detail to the Solution section. If over {max_words}, trim the Opening or Pain Point section — NEVER cut the Solution.
- The email MUST be structured as: Opening → Pain Point → Solution → CTA. This order is FIXED.
- NEVER end the email with a pain point. The Solution section MUST come before the CTA.
- Focus on how our solar solutions solve THEIR specific pain points
- {"Do NOT mention visiting their website." if not has_website else "Reference their products/business naturally."}
- Write in English
- Use concrete, specific language — avoid vague buzzwords like "innovative", "leading", "cutting-edge", "state-of-the-art"
- Every claim MUST be backed by a specific feature, number, or case study from the FABE points
- Output format: First line must be "SUBJECT: <email subject line>", then a blank line, then the email body
- MUST end with a CTA and do NOT truncate the email
- DIVERSITY IS KEY: vary your sentence structure, vocabulary, and phrasing. No two emails should read the same way.

{company_block}"""

        # 加载邮件规范（按用户ID隔离）
        from database.email_guidelines_models import get_active_guidelines_text
        guidelines_text = get_active_guidelines_text(user_id=self.user_id)

        system_prompt += f"""

---
EMAIL GUIDELINES (MUST FOLLOW — these override any conflicting instructions above):
{guidelines_text}"""

        # 补充更多客户背调信息
        products_info = research_result.get('module2_products', {})
        business_model = profile.get('business_model', 'unknown')
        has_solar = products_info.get('has_solar_products', False)
        solar_products = products_info.get('solar_products', [])

        customer_profile_extra = ''
        if business_model and business_model != 'unknown':
            customer_profile_extra += f'\nBusiness Model: {business_model}'
        if has_solar:
            customer_profile_extra += f'\nAlready has solar products: {", ".join(solar_products[:3])}'
        else:
            customer_profile_extra += '\nDoes not currently offer solar products (potential new market)'

        user_prompt = f"""Recipient: {greeting_target}
Recipient type: {"Personal email (has contact name)" if contact_name and email_type == 'personal' else "Public email (no specific contact)"}
Customer Company: {customer_name}
Industry: {profile.get('main_business', 'Unknown')}
Core Products: {', '.join(profile.get('core_products', [])[:5])}
Target Markets: {', '.join(profile.get('target_markets', [])[:3])}{customer_profile_extra}

Customer Pain Points:
{pain_summary if pain_summary else 'Not specifically identified'}

Our FABE Selling Points:
{fabe_summary if fabe_summary else 'Standard solar solutions'}

Relevant Cases:
{case_summary if case_summary else 'Various solar projects worldwide'}

INSTRUCTIONS:
1. DO NOT write a greeting line (no "Hi xxx,"). Start directly with the self-introduction sentence. The system will add the greeting automatically.
2. The email MUST contain ALL 4 sections: Opening → Pain Point → Solution → CTA. No section may be skipped.
3. Use the FABE Selling Points to explain HOW our solution solves the pain point(s).
4. Mention {customer_name} and at least one of their core products naturally in the email.
5. The Solution section is the most important part — it MUST be present and substantial. NEVER end with just a pain point.
6. If word count is low (under 150 words): write 1 pain point + 1 solution. If high (180+ words): you may add a second pain point.
7. End with a clear, specific CTA.
8. Follow the STRICT FORMAT RULES for greeting and signature exactly as specified."""

        content, error = self._call(system_prompt, user_prompt, max_tokens=1500, temperature=0.7, label=f'compose:{customer_name}')
        if error:
            return {'subject': '', 'body': '', 'error': error}
        if not content:
            return {'subject': '', 'body': '', 'error': 'LLM returned empty content'}

        # 解析 subject 和 body
        subject = ''
        body = content.strip()

        # 尝试多种格式提取 subject
        if content.startswith('SUBJECT:'):
            parts = content.split('\n', 1)
            subject = parts[0].replace('SUBJECT:', '').strip()
            body = parts[1].strip() if len(parts) > 1 else ''
        elif 'Subject:' in content:
            # 尝试找到 Subject: 行
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.strip().startswith('Subject:'):
                    subject = line.replace('Subject:', '').strip()
                    body = '\n'.join(lines[i+1:]).strip()
                    break
        elif '\n\n' in content:
            # 第一行是 subject，空行后是 body
            parts = content.split('\n\n', 1)
            potential_subject = parts[0].strip()
            # 如果第一行很短（<100字符），认为是 subject
            if len(potential_subject) < 100 and potential_subject:
                subject = potential_subject
                body = parts[1].strip() if len(parts) > 1 else ''

        # 如果 subject 为空，生成一个默认主题
        if not subject:
            subject = f"Solar Solutions for {customer_name}"

        return {'subject': subject, 'body': body, 'error': None}

    # ==================== 节点7: 邮件润色 ====================

    def refine_email(self, subject, body, target_word_count=None, customer_name=None):
        """
        润色精修邮件内容。

        Args:
            subject: 邮件主题
            body: 邮件正文
            target_word_count: 目标字数范围 {'min': int, 'max': int}
            customer_name: 客户公司名称（用于保持 greeting 一致性）

        Returns:
            dict: {'subject': str, 'body': str, 'error': str or None}
        """
        if target_word_count is None:
            target_word_count = 150
        if isinstance(target_word_count, int):
            target_word_count = {'min': max(10, target_word_count - 10), 'max': target_word_count + 10}
        min_words = target_word_count.get('min', 140)
        max_words = target_word_count.get('max', 160)
        _exact_target = (min_words + max_words) // 2

        greeting_instruction = ''
        if customer_name:
            greeting_instruction = f'\n11. If the greeting uses the company name, it MUST be "Hi {customer_name} Team," — do NOT change it to "[First Name]" or any placeholder.'

        system_prompt = f"""You are an expert B2B email editor. Refine the following cold email while preserving its structure and core message.

Rules:
1. Keep the professional business American English tone
2. Remove redundant phrases or filler words, BUT keep all pain point analysis and specific claims intact
3. Ensure the email length is between {min_words} and {max_words} words (target: {_exact_target}). This is a HARD constraint — if under {min_words}, expand relevant points; if over {max_words}, trim filler words.
4. Preserve the structure: Greeting + Self-intro → Opening → Pain Point 1 → Pain Point 2 → Solution & Evidence → CTA → Signature
5. Keep the core message, all pain points, FABE points, specific numbers, and CTA intact — do NOT remove or weaken them
6. Improve sentence flow and clarity
7. Output format: First line "SUBJECT: <refined subject>", blank line, then refined body
8. Do NOT add new information that wasn't in the original
9. MUST NOT introduce generic openers like "How are you", "Hope you're doing well", "I hope this email finds you well"
10. MUST keep the greeting format: "Hi [First Name]," or "Hi [Company] Team," — do NOT change to "Dear"
11. MUST keep the signature block EXACTLY as it appears in the original — do NOT replace real names with placeholders like [Your Name]
12. MUST keep the self-introduction sentence (e.g., "I'm [Sender Name] from [Company].") right after the greeting — do NOT remove or change it{greeting_instruction}"""

        user_prompt = f"""SUBJECT: {subject}

{body}

Refine this email now."""

        content, error = self._call(system_prompt, user_prompt, max_tokens=1200, temperature=0.3, label='refine')
        if error or not content:
            return {'subject': subject, 'body': body, 'error': error}

        if content.startswith('SUBJECT:'):
            parts = content.split('\n', 1)
            new_subject = parts[0].replace('SUBJECT:', '').strip()
            new_body = parts[1].strip() if len(parts) > 1 else ''
        else:
            new_subject = subject
            new_body = content.strip()

        return {'subject': new_subject, 'body': new_body, 'error': None}

    # ==================== 节点2: 客户分类 ====================

    def classify_customer(self, research_result):
        """
        基于背调结果进行客户分类。

        Args:
            research_result: 背调结果字典

        Returns:
            dict or None: {power_type, track, case_tag, priorities}
        """
        profile = research_result.get('module1_profile', {})
        products = research_result.get('module2_products', {})
        pain_points = research_result.get('module3_pain_points', [])
        tags = research_result.get('module4_tags', {})

        company_name = profile.get('company_name', 'Customer')
        power_tendency = tags.get('power_tendency', 'unknown')
        track = tags.get('track', 'General')
        industry = profile.get('industry', '')
        core_products = profile.get('core_products', [])

        system_prompt = """You are a B2B sales strategist. Classify the customer based on their profile.

Output ONLY valid JSON, no markdown. Structure:
{
  "power_type": "High Power" | "Low Power",
  "track": "Security & Smart Home Hardware" | "Outdoor & Portable Power" | "Automation & Gate Systems" | "Agriculture & Livestock" | "Energy Storage" | "Consumer Electronics" | "General",
  "case_tag": "Ring / Arlo / Eufy" | "No Matched Case",
  "priorities": ["priority1", "priority2", "priority3"]
}

Rules:
- power_type: High Power if they deal with large solar installations, commercial energy storage, or high-wattage products. Low Power for portable, consumer, or small-scale products.
- track: Based on their primary industry and products.
- case_tag: Only "Ring / Arlo / Eufy" if they are in security/smart home and explicitly sell or distribute Ring, Arlo, or Eufy products. Otherwise "No Matched Case".
- priorities: Extract top 3 pain point types or business priorities from the analysis."""

        user_prompt = f"""Customer: {company_name}
Industry: {industry}
Core Products: {', '.join(core_products[:5])}
Power Tendency: {power_tendency}
Current Track: {track}
Has Solar Products: {products.get('has_solar_products', False)}
Pain Points: {'; '.join([p.get('desc', '') for p in pain_points[:3]]) if pain_points else 'None identified'}

Classify this customer."""

        content, error = self._call(system_prompt, user_prompt, max_tokens=400, temperature=0.3, label=f'classify:{company_name}')
        if error or not content:
            return None
        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            return json.loads(content.strip())
        except json.JSONDecodeError:
            return None

    # ==================== 节点3: 优势提炼 ====================

    def select_advantages(self, classification, research_result, material_library):
        """
        基于客户分类和背调结果，从素材库中提炼最相关的优势。

        Args:
            classification: 客户分类结果
            research_result: 背调结果
            material_library: 素材库内容文本

        Returns:
            list or None: 优势列表
        """
        company_name = research_result.get('module1_profile', {}).get('company_name', 'Customer')
        pain_points = research_result.get('module3_pain_points', [])
        track = classification.get('track', 'General')
        power_type = classification.get('power_type', 'High Power')

        pain_summary = '; '.join([p.get('desc', '') for p in pain_points[:3]]) if pain_points else 'None'

        system_prompt = """You are a B2B sales strategist. From the provided advantage library, select the TOP 4 most relevant advantages for this specific customer.

Output ONLY valid JSON array, no markdown. Each item:
{"name": "advantage name", "tech_features": "technical description", "scope": "applicable scope", "customer_value": "why it matters to this customer", "relevance_score": 1-10}

Rules:
- Select advantages that directly address the customer's pain points and industry
- Explain WHY each advantage is relevant to THIS specific customer
- relevance_score: 10 = perfectly matched, 1 = barely relevant
- Prioritize advantages that solve their specific pain points"""

        user_prompt = f"""Customer: {company_name}
Industry Track: {track}
Power Type: {power_type}
Pain Points: {pain_summary}

Advantage Library:
{material_library[:3000]}

Select the top 4 most relevant advantages and explain why."""

        content, error = self._call(system_prompt, user_prompt, max_tokens=800, temperature=0.4, label=f'advantages:{company_name}')
        if error or not content:
            return None
        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            result = json.loads(content.strip())
            return result if isinstance(result, list) else None
        except json.JSONDecodeError:
            return None

    # ==================== 节点5: 素材匹配 ====================

    def match_materials(self, classification, research_result, company_info):
        """
        基于客户分类和背调结果，智能匹配素材库内容。

        Args:
            classification: 客户分类
            research_result: 背调结果
            company_info: 我方公司信息

        Returns:
            dict or None: 匹配到的素材
        """
        company_name = research_result.get('module1_profile', {}).get('company_name', 'Customer')
        track = classification.get('track', 'General')
        power_type = classification.get('power_type', 'High Power')
        pain_points = research_result.get('module3_pain_points', [])
        pain_summary = '; '.join([p.get('desc', '') for p in pain_points[:3]]) if pain_points else 'None'

        system_prompt = """You are a B2B marketing content strategist. Based on the customer profile, assemble the most relevant sales materials.

Output ONLY valid JSON, no markdown. Structure:
{
  "company_intro": "brief company introduction tailored to this customer",
  "advantages": ["advantage1", "advantage2", "advantage3", "advantage4"],
  "brochure": "relevant brochure content summary",
  "cases": [{"title": "case title", "summary": "case summary relevant to customer"}],
  "rules": "case workflow rules for this customer type",
  "storage": "energy storage content if applicable"
}

Rules:
- company_intro: Tailor the intro to highlight aspects most relevant to this customer's industry
- advantages: List 4 key advantages that match their needs
- cases: Provide 2-3 relevant case studies
- storage: Only include if power_type is High Power or they deal with energy storage
- All content should be in English"""

        user_prompt = f"""Customer: {company_name}
Track: {track}
Power Type: {power_type}
Pain Points: {pain_summary}

Our Company: {company_info.get('company_name', 'Our Company')}
Our Strengths: {company_info.get('strength1', '')}, {company_info.get('strength2', '')}, {company_info.get('strength3', '')}

Assemble the most relevant sales materials."""

        content, error = self._call(system_prompt, user_prompt, max_tokens=1000, temperature=0.4, label=f'materials:{company_name}')
        if error or not content:
            return None
        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            return json.loads(content.strip())
        except json.JSONDecodeError:
            return None

    # ==================== 节点7.5: 邮件排版（LLM）====================

    def format_email(self, body: str, target_words: int = None) -> Dict:
        """
        使用 LLM 对邮件正文进行排版美化：仅调整段落结构和空行，不删改任何文字。

        Args:
            body: 邮件正文（纯文本）
            target_words: 目标字数（用于校验，排版不应大幅改变字数）

        Returns:
            dict: {'body': str, 'word_count': int} 或 {'error': str}
        """
        original_word_count = len(body.split())

        system_prompt = f"""You are a text formatting assistant. Your task is ONLY to add proper paragraph breaks to the given email text.

ABSOLUTE RULES (VIOLATION = FAILURE):
1. DO NOT delete, add, rewrite, or reorder ANY words
2. DO NOT remove greetings (Hi, Hello, etc.), sign-offs (Best regards, etc.), or names
3. DO NOT change any sentence or word
4. Your ONLY action: insert blank lines between paragraphs to improve readability
5. Keep each paragraph to 2-4 sentences
6. Preserve the exact original text character-for-character, only adding \\n\\n between paragraphs

Output ONLY the text with paragraph breaks added. Nothing else."""

        user_prompt = f"Add paragraph breaks to this email text. DO NOT change any words:\n\n{body}"

        content, error = self._call(system_prompt, user_prompt, max_tokens=1200, temperature=0.0, label='format_email')
        if error or not content:
            return {'error': error or '排版失败', 'body': body, 'word_count': original_word_count}

        formatted = content.strip()

        # 安全校验：排版后字数不能比原文少太多（允许标点符号微调）
        formatted_words = len(formatted.split())
        if original_word_count > 20 and formatted_words < original_word_count * 0.7:
            # 排版导致内容丢失超过30%，回退到原文
            print(f"  ⚠ 排版安全校验：字数从 {original_word_count} 降到 {formatted_words}，内容丢失过多，回退到原文")
            return {'body': body, 'word_count': original_word_count}

        # 如果排版后变长太多（LLM可能添加了内容），也回退
        if formatted_words > original_word_count * 1.3:
            print(f"  ⚠ 排版安全校验：字数从 {original_word_count} 涨到 {formatted_words}，可能添加了内容，回退到原文")
            return {'body': body, 'word_count': original_word_count}

        return {
            'body': formatted,
            'word_count': formatted_words
        }

    # ==================== 节点8: HTML 渲染 ====================

    def render_html(self, email):
        """
        将邮件内容渲染为 HTML 格式。

        Args:
            email: 邮件字典 {subject, greeting, body, signature}

        Returns:
            str or None: HTML 字符串
        """
        system_prompt = """You are an HTML email developer. Convert the following email into a professional HTML email template.

Requirements:
1. Use inline CSS (no external stylesheets)
2. Max-width: 600px, centered
3. Professional business style with subtle branding
4. Mobile-friendly
5. Include proper HTML structure (DOCTYPE, html, head, body)
6. The email should look polished and trustworthy
7. Use a clean color scheme (blues/grays)
8. Output ONLY the raw HTML code, no markdown, no explanation"""

        user_prompt = f"""Subject: {email.get('subject', '')}

Greeting: {email.get('greeting', '')}

Body:
{email.get('body', '')}

Signature:
{email.get('signature', '')}

Generate the HTML email template."""

        content, error = self._call(system_prompt, user_prompt, max_tokens=1200, temperature=0.3, label='render_html')
        if error or not content:
            return None
        # 清理可能的 markdown 包裹
        if content.startswith('```html'):
            content = content.split('```html')[1].split('```')[0]
        elif content.startswith('```'):
            content = content.split('```')[1].split('```')[0]
        return content.strip()

    # ==================== 原有端到端生成方法（保留兼容） ====================

    def generate_email(self, customer_name, website, contact_name=None,
                       email_type='public', company_info=None, product_info=None):
        """端到端生成邮件（简单模式，不经过管线）"""
        client = self._get_client()
        if not client:
            return {'subject': '', 'body': '', 'error': 'API Key 未配置'}

        company_info = company_info or {}
        greeting_target = contact_name if contact_name and email_type == 'personal' else f'{customer_name} Team'

        system_prompt = """You are a professional B2B sales representative for a solar energy company.
Your task is to write a personalized cold email to a potential customer.

STRICT FORMAT RULES:
1. Greeting (choose ONE based on recipient type):
   - Public email / no specific contact: "Hi [Company Name] Team,"
   - Has contact person name: "Hi [First Name],"
   - NEVER use "Dear", always use "Hi"
2. Body: Free-form, professional business American English.
   - MUST NOT use generic openers like "How are you", "I hope this email finds you well"
   - Be direct, concise, and specific to the recipient's business
3. Closing & Signature (FIXED order, NEVER change):
   - Closing line: "Best regards,"
   - Then left-aligned, each on its own line, no extra symbols:
     [Full Name]
     [Job Title]
     [Company Full Name]

CONTENT RULES:
- Keep the email concise (150-250 words)
- Must include a clear call-to-action (CTA)
- Focus on how solar solutions can benefit THEIR specific business
- Do NOT mention visiting their website if no website is provided
- Write in English
- Output format: First line is "SUBJECT: <subject>", then a blank line, then the body"""

        # 加载邮件规范（按用户ID隔离）
        from database.email_guidelines_models import get_active_guidelines_text
        guidelines_text = get_active_guidelines_text(user_id=self.user_id)

        system_prompt += f"""

---
EMAIL GUIDELINES (MUST FOLLOW — these override any conflicting instructions above):
{guidelines_text}"""

        user_prompt = f"""Recipient: {greeting_target}
Company: {customer_name}
{'Website: ' + website if website else 'No website available'}

Our company: {company_info.get('company_name', 'Niteo Solar')}
Our products: Solar panels, solar power systems, off-grid solutions

Please generate the email now."""

        content, error = self._call(system_prompt, user_prompt, max_tokens=800, temperature=0.7, label=f'quick:{customer_name}')
        if error or not content:
            return {'subject': '', 'body': '', 'error': error}

        if content.startswith('SUBJECT:'):
            parts = content.split('\n', 1)
            subject = parts[0].replace('SUBJECT:', '').strip()
            body = parts[1].strip() if len(parts) > 1 else ''
        else:
            lines = content.split('\n')
            subject = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()

        return {'subject': subject, 'body': body, 'error': None}

    # ==================== 用量记录 ====================

    def _log_usage(self, label, usage):
        """记录 API 调用用量到数据库"""
        try:
            from database.connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS llm_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                model TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute('''
                INSERT INTO llm_usage_log (label, prompt_tokens, completion_tokens, total_tokens, model)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                label,
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
                usage.total_tokens if usage else 0,
                self.model
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass
