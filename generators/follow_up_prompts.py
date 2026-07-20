"""
跟进邮件 LLM Prompt 模板
每个 purpose 对应不同的生成策略
"""

import json


# ==================== 通用规则 ====================

# 禁用词列表（垃圾邮件高频词）
BANNED_WORDS = [
    'Follow up', 'Just checking in', 'Just wanted to follow up',
    'Free', 'Discount', 'Special offer', 'Limited time',
    'Act now', 'Don\'t miss out', 'No obligation',
]

# 通用输出格式指令
OUTPUT_FORMAT_INSTRUCTION = """Output ONLY valid JSON, no markdown, no explanation.
JSON structure:
{
  "subject": "email subject line (compelling, not spammy)",
  "body": "email body text (pure content, no greeting or signature lines)",
  "greeting": "Hi [Name], or Hi [Company] Team,",
  "signature": "Best regards,\\n[Sender Name]\\n[Sender Title]\\n[Sender Company]"
}"""

# 通用禁用词规则
BANNED_WORDS_RULE = """BANNED WORDS (NEVER use these in any form):
- "Follow up" / "Just checking in" / "Just wanted to follow up"
- "Free" / "Discount" / "Special offer" / "Limited time"
- "Act now" / "Don't miss out" / "No obligation"
Using ANY of these will result in immediate rejection."""

# 通用语气规则
TONE_RULE = """TONE:
- Professional but friendly, conversational feel
- Direct and confident, not pushy or desperate
- Sound like a human, not a template
- Vary sentence structure and vocabulary"""


# ==================== 各 purpose 的 Prompt 构建函数 ====================

def _build_reminder_prompt(context: dict) -> str:
    """reminder: 用完全不同的措辞重申核心价值主张，简短有力"""
    lang = context.get('language', 'en')

    if lang == 'zh':
        system = f"""你是一位专业的 B2B 销售代表。这是对潜在客户的第{context.get('step_number', 2)}封跟进邮件。

PURPOSE: 用完全不同的措辞重新强调核心价值主张。

{BANNED_WORDS_RULE}

{OUTPUT_FORMAT_INSTRUCTION}

{TONE_RULE}

CONTENT RULES:
1. 绝对不要重复第一封邮件的任何原句
2. 从全新的角度切入同一个核心价值（例如：如果第一封强调"效率"，这次强调"可靠性"或"长期回报"）
3. 简短有力，控制在 {context.get('word_count', 80)} 词以内
4. 不要使用问候语和签名占位符（greeting 和 signature 字段会自动处理）
5. body 中只写纯正文内容，不包含 greeting 和 signature"""

        user = f"""客户公司: {context.get('customer_name', 'the customer')}
客户行业: {context.get('customer_industry', 'Unknown')}
客户所在国家: {context.get('customer_country', 'Unknown')}
发信人: {context.get('sender_name', 'Sales Representative')}
发信人公司: {context.get('sender_company', '')}
发信人职位: {context.get('sender_position', '')}

第一封邮件标题: {context.get('first_email_subject', '')}
第一封邮件正文（绝不可重复其中的原句）:
{context.get('first_email_body', '')[:2000]}

之前使用的产品优势:
{_format_advantages(context.get('advantages', []))}

客户痛点:
{_format_pain_points(context.get('pain_points', []))}

请用全新的角度重申核心价值。"""
    else:
        system = f"""You are a professional B2B sales representative. This is follow-up email #{context.get('step_number', 2)} to a prospect.

PURPOSE: Restate the core value proposition from a completely different angle.

{BANNED_WORDS_RULE}

{OUTPUT_FORMAT_INSTRUCTION}

{TONE_RULE}

CONTENT RULES:
1. NEVER repeat any sentence from the first email — use completely different wording
2. Approach the same core value from a fresh angle (e.g., if the first email emphasized "efficiency", this time emphasize "reliability" or "long-term ROI")
3. Keep it concise and impactful, within {context.get('word_count', 80)} words
4. Do NOT include greeting or signature in the body — these go in their own JSON fields
5. The "body" field should contain ONLY the email body text"""

        user = f"""Customer Company: {context.get('customer_name', 'the customer')}
Customer Industry: {context.get('customer_industry', 'Unknown')}
Customer Country: {context.get('customer_country', 'Unknown')}
Sender: {context.get('sender_name', 'Sales Representative')}
Sender Company: {context.get('sender_company', '')}
Sender Title: {context.get('sender_position', '')}

First email subject: {context.get('first_email_subject', '')}
First email body (DO NOT repeat ANY sentences from this):
{context.get('first_email_body', '')[:2000]}

Product advantages used previously:
{_format_advantages(context.get('advantages', []))}

Customer pain points:
{_format_pain_points(context.get('pain_points', []))}

Restate the core value from a completely fresh angle."""

    return system, user


def _build_case_study_prompt(context: dict) -> str:
    """case_study: 分享同行业成功案例，含具体数据"""
    lang = context.get('language', 'en')

    # 构建案例素材部分
    case_section = ''
    if context.get('case_material'):
        case_section = f"""
CASE STUDY MATERIAL (incorporate this naturally):
{json.dumps(context['case_material'], ensure_ascii=False, indent=2)[:3000]}
"""
    else:
        case_section = "\n(No specific case material provided — create a plausible case study relevant to the customer's industry.)\n"

    if lang == 'zh':
        system = f"""你是一位专业的 B2B 销售代表。这是对潜在客户的第{context.get('step_number', 3)}封跟进邮件。

PURPOSE: 分享一个与该客户同行业/同规模的成功案例。

{BANNED_WORDS_RULE}

{OUTPUT_FORMAT_INSTRUCTION}

{TONE_RULE}

CONTENT RULES:
1. 分享一个与客户同行业或同规模的成功案例
2. 案例中必须包含具体数据（百分比提升、数量、时间缩短等）
3. 从案例自然过渡到我们的产品，不要硬推销
4. 控制在 {context.get('word_count', 120)} 词以内
5. body 中只写纯正文内容
{case_section}
不要使用问候语和签名占位符（greeting 和 signature 字段会自动处理）。"""

        user = f"""客户公司: {context.get('customer_name', 'the customer')}
客户行业: {context.get('customer_industry', 'Unknown')}
客户赛道: {context.get('track', 'General')}
发信人: {context.get('sender_name', 'Sales Representative')}
发信人公司: {context.get('sender_company', '')}

第一封邮件提到的核心价值:
{_summarize_first_email(context)}

客户痛点:
{_format_pain_points(context.get('pain_points', []))}

请分享一个相关的成功案例。"""
    else:
        system = f"""You are a professional B2B sales representative. This is follow-up email #{context.get('step_number', 3)} to a prospect.

PURPOSE: Share a relevant success story from a company in the same industry or similar scale.

{BANNED_WORDS_RULE}

{OUTPUT_FORMAT_INSTRUCTION}

{TONE_RULE}

CONTENT RULES:
1. Share ONE success story relevant to the customer's industry or scale
2. MUST include specific data points (percentage improvements, quantities, time saved, etc.)
3. Transition naturally from the case study to our product — no hard sell
4. Keep within {context.get('word_count', 120)} words
5. The "body" field should contain ONLY the email body text
{case_section}
Do NOT include greeting or signature in the body — these go in their own JSON fields."""

        user = f"""Customer Company: {context.get('customer_name', 'the customer')}
Customer Industry: {context.get('customer_industry', 'Unknown')}
Customer Track: {context.get('track', 'General')}
Sender: {context.get('sender_name', 'Sales Representative')}
Sender Company: {context.get('sender_company', '')}

Core value mentioned in first email:
{_summarize_first_email(context)}

Customer pain points:
{_format_pain_points(context.get('pain_points', []))}

Share a relevant success story."""

    return system, user


def _build_question_prompt(context: dict) -> str:
    """question: 基于客户痛点提出诊断性问题，激发回复欲望"""
    lang = context.get('language', 'en')

    if lang == 'zh':
        system = f"""你是一位专业的 B2B 销售代表。这是对潜在客户的第{context.get('step_number', 4)}封跟进邮件。

PURPOSE: 基于第一封邮件提到的客户痛点或产品优势，提出1-2个诊断性问题。

{BANNED_WORDS_RULE}

{OUTPUT_FORMAT_INSTRUCTION}

{TONE_RULE}

CONTENT RULES:
1. 提出1-2个诊断性问题，让对方觉得"这个问题值得回复"
2. 问题必须基于第一封邮件提到的客户痛点或产品优势
3. 绝对不要在问题中推销产品 — 纯粹以顾问身份提问
4. 问题要有针对性（与客户行业/痛点相关），不要泛泛而谈
5. 控制在 {context.get('word_count', 80)} 词以内
6. body 中只写纯正文内容

不要使用问候语和签名占位符（greeting 和 signature 字段会自动处理）。"""

        user = f"""客户公司: {context.get('customer_name', 'the customer')}
客户行业: {context.get('customer_industry', 'Unknown')}
发信人: {context.get('sender_name', 'Sales Representative')}
发信人公司: {context.get('sender_company', '')}

第一封邮件正文:
{context.get('first_email_body', '')[:2000]}

客户痛点:
{_format_pain_points(context.get('pain_points', []))}

之前使用的产品优势:
{_format_advantages(context.get('advantages', []))}

请提出1-2个诊断性问题。"""
    else:
        system = f"""You are a professional B2B sales representative. This is follow-up email #{context.get('step_number', 4)} to a prospect.

PURPOSE: Ask 1-2 diagnostic questions based on the customer's pain points or product advantages from the first email.

{BANNED_WORDS_RULE}

{OUTPUT_FORMAT_INSTRUCTION}

{TONE_RULE}

CONTENT RULES:
1. Ask 1-2 diagnostic questions that make the recipient think "this is worth answering"
2. Questions MUST be based on pain points or advantages mentioned in the first email
3. Do NOT pitch or sell in the questions — act purely as a consultant
4. Questions must be specific to the customer's industry/pain points, not generic
5. Keep within {context.get('word_count', 80)} words
6. The "body" field should contain ONLY the email body text

Do NOT include greeting or signature in the body — these go in their own JSON fields."""

        user = f"""Customer Company: {context.get('customer_name', 'the customer')}
Customer Industry: {context.get('customer_industry', 'Unknown')}
Sender: {context.get('sender_name', 'Sales Representative')}
Sender Company: {context.get('sender_company', '')}

First email body:
{context.get('first_email_body', '')[:2000]}

Customer pain points:
{_format_pain_points(context.get('pain_points', []))}

Product advantages used previously:
{_format_advantages(context.get('advantages', []))}

Ask 1-2 diagnostic questions."""

    return system, user


def _build_resource_prompt(context: dict) -> str:
    """resource: 分享行业资源，融入宣传册内容"""
    lang = context.get('language', 'en')

    # 构建宣传册素材部分
    brochure_section = ''
    if context.get('brochure_material'):
        brochure_section = f"""
BROCHURE MATERIAL (incorporate key points from this):
{json.dumps(context['brochure_material'], ensure_ascii=False, indent=2)[:3000]}
"""
    else:
        brochure_section = "\n(No specific brochure material provided — share a relevant industry resource or insight.)\n"

    if lang == 'zh':
        system = f"""你是一位专业的 B2B 销售代表。这是对潜在客户的第{context.get('step_number', 5)}封跟进邮件。

PURPOSE: 分享有价值的行业资源（报告、指南、趋势分析等），在签名前加入简短的产品关联。

{BANNED_WORDS_RULE}

{OUTPUT_FORMAT_INSTRUCTION}

{TONE_RULE}

CONTENT RULES:
1. 分享一个有价值的行业资源（如行业报告、选购指南、市场趋势等）
2. 资源内容必须与客户的行业/痛点相关
3. 在签名前用1-2句话自然关联我们的产品（不要硬推销）
4. 控制在 {context.get('word_count', 100)} 词以内
5. body 中只写纯正文内容
{brochure_section}
不要使用问候语和签名占位符（greeting 和 signature 字段会自动处理）。"""

        user = f"""客户公司: {context.get('customer_name', 'the customer')}
客户行业: {context.get('customer_industry', 'Unknown')}
客户赛道: {context.get('track', 'General')}
客户分类: {context.get('power_type', 'Unknown')}
发信人: {context.get('sender_name', 'Sales Representative')}
发信人公司: {context.get('sender_company', '')}

客户痛点:
{_format_pain_points(context.get('pain_points', []))}

请分享一个有价值的行业资源。"""
    else:
        system = f"""You are a professional B2B sales representative. This is follow-up email #{context.get('step_number', 5)} to a prospect.

PURPOSE: Share a valuable industry resource (report, guide, trend analysis), with a brief product tie-in before the signature.

{BANNED_WORDS_RULE}

{OUTPUT_FORMAT_INSTRUCTION}

{TONE_RULE}

CONTENT RULES:
1. Share a valuable industry resource (e.g., industry report, buyer's guide, market trends)
2. The resource MUST be relevant to the customer's industry/pain points
3. Add 1-2 sentences naturally connecting to our product before the signature — no hard sell
4. Keep within {context.get('word_count', 100)} words
5. The "body" field should contain ONLY the email body text
{brochure_section}
Do NOT include greeting or signature in the body — these go in their own JSON fields."""

        user = f"""Customer Company: {context.get('customer_name', 'the customer')}
Customer Industry: {context.get('customer_industry', 'Unknown')}
Customer Track: {context.get('track', 'General')}
Customer Classification: {context.get('power_type', 'Unknown')}
Sender: {context.get('sender_name', 'Sales Representative')}
Sender Company: {context.get('sender_company', '')}

Customer pain points:
{_format_pain_points(context.get('pain_points', []))}

Share a valuable industry resource."""

    return system, user


def _build_loss_aversion_prompt(context: dict) -> str:
    """loss_aversion: 以"不行动的损失"角度唤醒关注"""
    lang = context.get('language', 'en')

    if lang == 'zh':
        system = f"""你是一位专业的 B2B 销售代表。这是对潜在客户的第{context.get('step_number', 6)}封跟进邮件。

PURPOSE: 以"如果不做这件事可能会错过什么"的角度，重新唤醒对方关注。

{BANNED_WORDS_RULE}

{OUTPUT_FORMAT_INSTRUCTION}

{TONE_RULE}

CONTENT RULES:
1. 从"机会成本"或"竞争压力"的角度切入 — 如果不行动会失去什么
2. 提及竞争对手可能已经在采取类似行动（用客观语气，不要危言耸听）
3. 与客户的具体痛点/行业趋势关联，不要泛泛而谈
4. 结尾给出明确的、低压力的下一步行动建议
5. 控制在 {context.get('word_count', 100)} 词以内
6. body 中只写纯正文内容

不要使用问候语和签名占位符（greeting 和 signature 字段会自动处理）。"""

        user = f"""客户公司: {context.get('customer_name', 'the customer')}
客户行业: {context.get('customer_industry', 'Unknown')}
客户所在国家: {context.get('customer_country', 'Unknown')}
发信人: {context.get('sender_name', 'Sales Representative')}
发信人公司: {context.get('sender_company', '')}

第一封邮件提到的核心价值:
{_summarize_first_email(context)}

客户痛点:
{_format_pain_points(context.get('pain_points', []))}

之前使用的产品优势:
{_format_advantages(context.get('advantages', []))}

请以"不行动的损失"角度撰写。"""
    else:
        system = f"""You are a professional B2B sales representative. This is follow-up email #{context.get('step_number', 6)} to a prospect.

PURPOSE: Re-engage the prospect by framing the cost of inaction — what they might miss if they don't act.

{BANNED_WORDS_RULE}

{OUTPUT_FORMAT_INSTRUCTION}

{TONE_RULE}

CONTENT RULES:
1. Frame from the angle of "opportunity cost" or "competitive pressure" — what they lose by not acting
2. Mention that competitors may already be taking similar action (objective tone, no fear-mongering)
3. Connect to the customer's specific pain points/industry trends — be specific, not generic
4. End with a clear, low-pressure next step
5. Keep within {context.get('word_count', 100)} words
6. The "body" field should contain ONLY the email body text

Do NOT include greeting or signature in the body — these go in their own JSON fields."""

        user = f"""Customer Company: {context.get('customer_name', 'the customer')}
Customer Industry: {context.get('customer_industry', 'Unknown')}
Customer Country: {context.get('customer_country', 'Unknown')}
Sender: {context.get('sender_name', 'Sales Representative')}
Sender Company: {context.get('sender_company', '')}

Core value from first email:
{_summarize_first_email(context)}

Customer pain points:
{_format_pain_points(context.get('pain_points', []))}

Product advantages used previously:
{_format_advantages(context.get('advantages', []))}

Frame from the "cost of inaction" angle."""

    return system, user


def _build_breakup_prompt(context: dict) -> str:
    """breakup: 简短分手邮件，yes/no CTA，不超过50词"""
    lang = context.get('language', 'en')

    if lang == 'zh':
        system = """你是一位专业的 B2B 销售代表。这是最后一封跟进邮件。

PURPOSE: 分手邮件 — 尊重对方时间，明确 yes/no CTA。

BANNED WORDS (NEVER use):
- "Follow up" / "Just checking in" / "Free" / "Discount"

Output ONLY valid JSON, no markdown, no explanation.
JSON structure:
{
  "subject": "email subject line",
  "body": "email body (under 50 words!)",
  "greeting": "Hi [Name], or Hi [Company] Team,",
  "signature": "Best regards,\\n[Sender Name]\\n[Sender Title]\\n[Sender Company]"
}

CONTENT RULES:
1. 简短尊重，表明"如果现在不合适也没关系"
2. 明确的 yes/no CTA（例如："Should I close your file, or would you like to reconnect?"）
3. 不超过 50 词
4. 语气：温暖但坚定，不留暧昧空间
5. body 中只写纯正文内容

不要使用问候语和签名占位符（greeting 和 signature 字段会自动处理）。"""

        user = f"""客户公司: {context.get('customer_name', 'the customer')}
发信人: {context.get('sender_name', 'Sales Representative')}
发信人公司: {context.get('sender_company', '')}

请撰写分手邮件。"""
    else:
        system = """You are a professional B2B sales representative. This is the final follow-up email.

PURPOSE: Breakup email — respect their time, clear yes/no CTA.

BANNED WORDS (NEVER use):
- "Follow up" / "Just checking in" / "Free" / "Discount"

Output ONLY valid JSON, no markdown, no explanation.
JSON structure:
{
  "subject": "email subject line",
  "body": "email body (under 50 words!)",
  "greeting": "Hi [Name], or Hi [Company] Team,",
  "signature": "Best regards,\\n[Sender Name]\\n[Sender Title]\\n[Sender Company]"
}

CONTENT RULES:
1. Short and respectful — "If the timing isn't right, no worries"
2. Clear yes/no CTA (e.g., "Should I close your file, or would you like to reconnect?")
3. MAXIMUM 50 words — strict limit
4. Tone: warm but firm, no ambiguity
5. The "body" field should contain ONLY the email body text

Do NOT include greeting or signature in the body — these go in their own JSON fields."""

        user = f"""Customer Company: {context.get('customer_name', 'the customer')}
Sender: {context.get('sender_name', 'Sales Representative')}
Sender Company: {context.get('sender_company', '')}

Write the breakup email."""

    return system, user


# ==================== 路由函数 ====================

PURPOSE_BUILDERS = {
    'reminder': _build_reminder_prompt,
    'case_study': _build_case_study_prompt,
    'question': _build_question_prompt,
    'resource': _build_resource_prompt,
    'loss_aversion': _build_loss_aversion_prompt,
    'breakup': _build_breakup_prompt,
}


def build_follow_up_prompt(purpose, step_number, total_steps, context):
    """
    构建跟进邮件的 LLM Prompt

    参数:
        purpose: reminder/case_study/question/resource/loss_aversion/breakup
        step_number: 当前步骤号（从2开始）
        total_steps: 总步骤数
        context: dict, 包含:
            - first_email_subject: 第一封邮件标题
            - first_email_body: 第一封邮件正文
            - customer_name: 客户公司名
            - customer_country: 国家
            - customer_industry: 行业
            - sender_name: 发信人姓名
            - sender_company: 发信人公司名
            - sender_position: 发信人职位
            - power_type: 客户分类（mono/hybrid/micro 或 High Power/Low Power）
            - track: 赛道（commercial/residential/storage）
            - advantages: 之前使用的优势列表
            - pain_points: 客户痛点
            - case_material: 案例素材（如果有）
            - brochure_material: 宣传册素材（如果有）
            - word_count: 目标字数
            - language: 语言（en/zh）

    返回: str, 完整的 LLM prompt（返回 (system_prompt, user_prompt) 元组）
    """
    # 最后一封一定是 breakup
    if step_number == total_steps:
        purpose = 'breakup'

    # 注入步骤信息到 context
    ctx = dict(context)
    ctx['step_number'] = step_number
    ctx['total_steps'] = total_steps

    # 获取对应的 prompt 构建函数
    builder = PURPOSE_BUILDERS.get(purpose)
    if not builder:
        # 未知 purpose，回退到 reminder
        print(f"  ⚠ 未知的 purpose: {purpose}，回退到 reminder")
        builder = _build_reminder_prompt

    system_prompt, user_prompt = builder(ctx)

    return system_prompt, user_prompt


# ==================== 辅助函数 ====================

def _format_advantages(advantages):
    """格式化优势列表为文本"""
    if not advantages:
        return 'Not specified'
    if isinstance(advantages, list):
        lines = []
        for a in advantages[:4]:
            if isinstance(a, dict):
                name = a.get('name', a.get('advantage_name', ''))
                value = a.get('customer_value', a.get('B', ''))
                lines.append(f"- {name}: {value}" if value else f"- {name}")
            else:
                lines.append(f"- {a}")
        return '\n'.join(lines) if lines else 'Not specified'
    return str(advantages)


def _format_pain_points(pain_points):
    """格式化痛点列表为文本"""
    if not pain_points:
        return 'Not identified'
    if isinstance(pain_points, list):
        lines = []
        for p in pain_points[:3]:
            if isinstance(p, dict):
                desc = p.get('desc', p.get('description', p.get('type', '')))
                lines.append(f"- {desc}")
            else:
                lines.append(f"- {p}")
        return '\n'.join(lines) if lines else 'Not identified'
    return str(pain_points)


def _summarize_first_email(context):
    """从第一封邮件中提取核心价值摘要"""
    subject = context.get('first_email_subject', '')
    body = context.get('first_email_body', '')
    # 取前500字符作为摘要
    summary = ''
    if subject:
        summary += f"Subject: {subject}\n"
    if body:
        # 截取前300词
        words = body.split()[:300]
        summary += ' '.join(words)
    return summary if summary else 'Not available'