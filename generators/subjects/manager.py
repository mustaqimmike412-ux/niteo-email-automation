"""
智能邮件标题管理器
根据邮件内容实时生成多个备选标题，并按邮箱数量智能分配轮换
"""
import random
import re
import time
import hashlib
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class SubjectAssignment:
    """标题分配结果"""
    email_id: int
    email_address: str
    subject_line: str
    subject_index: int


@dataclass
class SubjectPool:
    """客户的标题池"""
    customer_id: int
    customer_name: str
    subjects: List[str] = field(default_factory=list)
    assignments: List[SubjectAssignment] = field(default_factory=list)


class SmartSubjectManager:
    """
    智能邮件标题管理器

    核心功能：
    1. 根据邮件内容实时生成多个备选标题
    2. 按邮箱数量智能计算需要生成的标题数量
    3. 随机打乱分配，避免顺序规律被识别
    """

    # 中文国家名 -> 英文国家名映射
    COUNTRY_MAP = {
        '肯尼亚': 'Kenya',
        '乌干达': 'Uganda',
        '坦桑尼亚': 'Tanzania',
        '美国': 'the USA',
        '波兰': 'Poland',
        '巴基斯坦': 'Pakistan',
        '澳大利亚': 'Australia',
        '加拿大': 'Canada',
        '德国': 'Germany',
        '英国': 'the UK',
        '荷兰': 'the Netherlands',
        '新西兰': 'New Zealand',
        '斯里兰卡': 'Sri Lanka',
        '尼日利亚': 'Nigeria',
        '迪拜': 'Dubai',
        '阿根廷': 'Argentina',
        '秘鲁': 'Peru',
        '法国': 'France',
        '哥伦比亚': 'Colombia',
        '多米尼加': 'the Dominican Republic',
        # 带额外描述的国家，提取主要部分映射
        '瑞典，法国': 'Sweden',
        '西班牙，主要项目在欧洲和中东': 'Spain',
        '波斯尼亚和黑塞哥维那.': 'Bosnia and Herzegovina',
    }

    # 标题生成策略模板
    TEMPLATES = [
        # 行业共鸣型
        "Solar Solutions for {customer}'s {industry} Innovation",
        "Powering {customer}'s Next-Gen Products with Advanced Solar",
        "How {customer} Can Enhance Performance with Solar Integration",
        "A Solar Partnership Opportunity for {customer}",
        "{customer} + Solar: A Natural Fit for Your Product Line",
        "Renewable Energy Solutions Tailored for {customer}",

        # 技术亮点型
        "BC Cell Technology - Pure Black & High Efficiency for {customer}",
        "The Solar Tech Behind Leading Brands' Products",
        "Higher Efficiency, Sleeker Design: BC Cells for {customer}",
        "Why Top Brands Choose Our Back-Contact Solar Technology",
        "Pure Black Solar Panels: More Power, Better Aesthetics",
        "Next-Gen Solar: Unobstructed Surface, Maximum Output",

        # 耐用性型
        "Durability That Matches {customer}'s Quality Standards",
        "Weather-Resistant Solar for Harsh Outdoor Conditions",
        "Long-Lasting Solar Power: Less Maintenance, More Reliability",
        "Tempered Glass Solar Panels: Built for the Real World",
        "How {customer} Can Reduce Returns with Better Solar",
        "Engineered for Extreme: Solar That Outlasts Standard Panels",

        # 供应链型
        "Streamlined Delivery to {country}: DDP Shipping Available",
        "Hassle-Free Solar Supply from Our Global Facilities",
        "DDP to {country}: We Handle Customs, You Focus on Growth",
        "Multi-Country Production = Reliable Supply for {customer}",
        "Simplify Your Procurement with Our DDP Delivery Service",
        "Global Manufacturing, Local Delivery for {customer}",

        # 社交证明/CTA型
        "Quick Question About {customer}'s Solar Needs",
        "15-Min Call: How Industry Leaders Use Our Solar Solutions",
        "Free Sample Offer for {customer}'s Engineering Team",
        "See Why Top Brands Chose Us for Solar Partnership",
        "Can We Support {customer}'s Next Product Launch?",
        "Explore Solar Integration: 10-Minute Discovery Call",

        # 价值主张型
        "Cut Energy Costs by 30%: Solar for {customer}'s Operations",
        "Sustainable Growth: Solar Solutions for {customer}",
        "Boost Product Value with Integrated Solar Technology",
        "The Competitive Edge: Solar-Powered Products by {customer}",
        "Future-Proof Your Products with Solar Integration",
        "Reduce Carbon Footprint: Solar Partnership with {customer}",
    ]

    # 禁用词（避免垃圾邮件触发）
    SPAM_TRIGGERS = {
        'free', 'urgent', 'act now', 'limited time', 'click here',
        'winner', 'congratulations', 'cash', 'prize', '!!!', '$$$',
        '100% free', 'no obligation', 'risk free', 'call now',
        'order now', 'buy now', 'special promotion', 'great offer',
        'act immediately', 'exclusive deal', 'limited offer', 'discount'
    }

    def __init__(self):
        self.generated_pools: Dict[int, SubjectPool] = {}

    def calculate_subject_count(self, email_count: int, user_override: int = 0) -> int:
        """
        计算需要生成的标题数量。
        用户指定数量时优先使用用户设置（上限20），不再限制为邮箱数量，
        让用户能在预览区看到所有设定的标题。

        Args:
            email_count: 邮箱数量
            user_override: 用户指定的标题数量（0 = 自动决定）

        Returns:
            int: 需要生成的标题数量
        """
        if user_override > 0:
            return min(max(1, user_override), 20)
        if email_count <= 4:
            return 2
        elif email_count <= 10:
            return 3
        elif email_count <= 20:
            return 5
        else:
            return min(15, (email_count + 3) // 4)  # 最多15个标题

    def generate_subjects(self, customer_name: str, country: str,
                          industry: str, email_count: int,
                          email_body: str = None,
                          user_override: int = 0) -> List[str]:
        """
        为客户生成指定数量的备选标题。
        优先基于邮件正文内容生成，内容不足时用模板补充。

        Args:
            customer_name: 客户名称
            country: 国家
            industry: 行业
            email_count: 邮箱数量（用于计算需要多少标题）
            email_body: 邮件正文（用于生成基于内容的标题）
            user_override: 用户指定的标题数量（0 = 自动决定）

        Returns:
            List[str]: 生成的标题列表
        """
        subject_count = self.calculate_subject_count(email_count, user_override)

        # 清理客户名
        clean_name = self._clean_customer_name(customer_name)
        clean_industry = industry.title() if industry else 'Product'
        # 国家名：中文转英文映射，确保英文标题中使用英文国家名
        clean_country = self.COUNTRY_MAP.get(country, country) if country else 'Your Region'

        # 使用客户名+日期作为种子：同一客户每天标题不同，防止被标记为垃圾
        today_seed = int(hashlib.md5(f"{clean_name}_{time.strftime('%Y%m%d')}".encode()).hexdigest()[:8], 16)
        random.seed(today_seed)

        subjects = []

        # 第一步：优先基于邮件正文生成内容相关标题（优先使用 DeepSeek LLM）
        if email_body and len(email_body) > 20:
            content_subjects = self._generate_subjects_from_body(email_body, clean_name)
            for cs in content_subjects:
                if cs and cs not in subjects:
                    subjects.append(cs)
                if len(subjects) >= subject_count:
                    break

        # 第二步：如果内容标题不够（LLM不可用+正则也提取不够），用模板补充
        if len(subjects) < subject_count:
            templates_needed = min(subject_count - len(subjects), len(self.TEMPLATES))
            selected_templates = random.sample(self.TEMPLATES, templates_needed)
            for template in selected_templates:
                subject = template.format(
                    customer=clean_name,
                    country=clean_country,
                    industry=clean_industry
                )
                subject = self._validate_and_clean(subject)
                if subject and subject not in subjects:
                    subjects.append(subject)
                if len(subjects) >= subject_count:
                    break

        # 第三步：如果还不够，补充通用标题
        while len(subjects) < subject_count:
            generic = self._generate_generic_subject(clean_name, clean_industry)
            if generic not in subjects:
                subjects.append(generic)
            if len(subjects) >= subject_count:
                break

        # 重置随机种子
        random.seed()

        return subjects[:subject_count]

    def assign_subjects_to_emails(self, customer_id: int, customer_name: str,
                                   email_items: List[Dict],
                                   subjects: List[str]) -> List[Dict]:
        """
        将标题分配给各个邮箱，相邻两封邮件标题不重复

        Args:
            customer_id: 客户ID
            customer_name: 客户名称
            email_items: 邮箱列表，每个元素包含 email_id, email_address 等
            subjects: 生成的标题列表

        Returns:
            List[Dict]: 添加了 subject 字段的 email_items
        """
        if not subjects:
            # 如果没有标题，使用默认标题
            default = f"Partnership Opportunity with {self._clean_customer_name(customer_name)}"
            for item in email_items:
                item['subject'] = default
                item['subject_index'] = 0
            return email_items

        email_count = len(email_items)
        subject_count = len(subjects)

        # 计算每个标题应分配的次数
        base_count = email_count // subject_count
        extra = email_count % subject_count

        # 构建标题池：每个标题出现 base_count 或 base_count+1 次
        pool = []
        for i in range(subject_count):
            count = base_count + (1 if i < extra else 0)
            pool.extend([i] * count)

        # 去重洗牌：保证相邻元素不重复
        assignment_plan = self._shuffle_no_adjacent(pool, subjects)

        # 最终兜底：如果洗牌后仍有相邻重复，强制修正
        for i in range(1, len(assignment_plan)):
            if assignment_plan[i] == assignment_plan[i - 1]:
                # 找一个与前后都不重复的索引来交换
                for j in range(len(assignment_plan)):
                    if assignment_plan[j] != assignment_plan[i - 1]:
                        if i + 1 >= len(assignment_plan) or assignment_plan[j] != assignment_plan[i + 1]:
                            assignment_plan[i], assignment_plan[j] = assignment_plan[j], assignment_plan[i]
                            break

        # 分配标题
        result = []
        for i, item in enumerate(email_items):
            subject_idx = assignment_plan[i]
            item_copy = item.copy()
            item_copy['subject'] = subjects[subject_idx]
            item_copy['subject_index'] = subject_idx
            result.append(item_copy)

        return result

    def generate_and_assign(self, customer_id: int, customer_name: str,
                            country: str, industry: str,
                            email_items: List[Dict],
                            email_body: str = None,
                            num_subjects: int = 0,
                            subjects: List[str] = None) -> Tuple[List[str], List[Dict]]:
        """
        一站式生成标题并分配给邮箱

        Args:
            customer_id: 客户ID
            customer_name: 客户名称
            country: 国家
            industry: 行业
            email_items: 邮箱列表
            email_body: 邮件正文（用于生成基于内容的标题）
            num_subjects: 用户指定的标题数量（0 = 自动决定）
            subjects: 预先生成的标题列表（如预览阶段已生成）。传入时直接使用，不再重新生成

        Returns:
            Tuple[List[str], List[Dict]]: (生成的标题列表, 分配后的邮箱列表)
        """
        if subjects is None:
            subjects = self.generate_subjects(customer_name, country, industry,
                                              len(email_items),
                                              email_body=email_body,
                                              user_override=num_subjects)
        assigned_items = self.assign_subjects_to_emails(
            customer_id, customer_name, email_items, subjects
        )

        # 保存到内存池
        self.generated_pools[customer_id] = SubjectPool(
            customer_id=customer_id,
            customer_name=customer_name,
            subjects=subjects
        )

        return subjects, assigned_items

    def _shuffle_no_adjacent(self, pool: List[int], subjects: List[str]) -> List[int]:
        """
        对标题池进行洗牌，保证相邻两封邮件标题不重复。

        策略：
        1. 如果标题数 >= 2，先尝试随机洗牌（最多100次），若无相邻重复则直接采用
        2. 若100次都没成功，用贪心算法（优先选剩余最多的候选，避免死锁）
        3. 如果只有1个标题，无法避免重复，退回简单打乱
        """
        if len(subjects) <= 1:
            random.shuffle(pool)
            return pool

        # 阶段1：随机洗牌尝试（快速路径）
        for _ in range(100):
            candidate = pool[:]
            random.shuffle(candidate)
            if all(candidate[i] != candidate[i + 1] for i in range(len(candidate) - 1)):
                return candidate

        # 阶段2：贪心构建（优先选剩余最多的候选，避免死锁）
        # 统计每个标题的剩余可用次数
        remaining = {}
        for idx in set(pool):
            remaining[idx] = pool.count(idx)

        result = []
        last_idx = -1
        for _ in range(len(pool)):
            # 候选：与上一个不同且还有剩余的标题
            candidates = [idx for idx, cnt in remaining.items()
                          if cnt > 0 and idx != last_idx]
            if not candidates:
                # 极端情况：只剩一种标题了，只能用它
                candidates = [idx for idx, cnt in remaining.items() if cnt > 0]
            # 关键修复：选剩余数量最多的候选，避免低频元素被过早耗尽导致死锁
            candidates.sort(key=lambda x: remaining[x], reverse=True)
            chosen = candidates[0]
            result.append(chosen)
            remaining[chosen] -= 1
            last_idx = chosen

        return result

    def _clean_customer_name(self, name: str) -> str:
        """清理客户名"""
        # 移除常见公司后缀
        suffixes = ['INC.', 'LLC', 'Ltd.', 'Limited', 'Corp.', 'Corporation',
                    'GmbH', 'S.A.', 'B.V.', 'Pty Ltd', 'Co.', 'Company']
        clean = name
        for suffix in suffixes:
            clean = clean.replace(suffix, '').replace(suffix.upper(), '')
        clean = clean.strip()
        # 只保留字母数字和空格
        clean = re.sub(r'[^\w\s-]', '', clean).strip()
        return clean if clean else 'Valued Partner'

    def _validate_and_clean(self, subject: str) -> str:
        """验证并清理标题"""
        # 检查长度
        if len(subject) > 80:
            subject = subject[:77] + '...'

        # 检查禁用词
        subject_lower = subject.lower()
        for trigger in self.SPAM_TRIGGERS:
            if trigger in subject_lower:
                # 移除禁用词
                subject = re.sub(re.escape(trigger), '', subject_lower,
                                 flags=re.IGNORECASE).strip()

        # 清理多余空格和特殊字符
        subject = re.sub(r'\s+', ' ', subject).strip()
        subject = subject.lstrip('!@#$%^&*')

        # 首字母大写
        if subject:
            subject = subject[0].upper() + subject[1:]

        return subject

    def _generate_generic_subject(self, customer_name: str, industry: str) -> str:
        """生成通用标题（当模板不够时补充）"""
        generics = [
            f"Exploring Solar Opportunities with {customer_name}",
            f"Solar Integration Proposal for {customer_name}",
            f"Partnership Discussion: {customer_name} & Solar Innovation",
            f"How Solar Can Benefit {customer_name}'s {industry} Line",
            f"{customer_name}: Let's Discuss Solar Integration",
            f"Solar Solutions Tailored for {customer_name}",
        ]
        return random.choice(generics)

    def _generate_subjects_from_body(self, email_body: str, customer_name: str) -> List[str]:
        """
        从邮件正文提取核心卖点，生成基于内容的多样化标题。
        优先使用 DeepSeek LLM 提取核心卖点，LLM 不可用时回退到正则提取。
        """
        clean_name = self._clean_customer_name(customer_name)

        # 第一步：用 DeepSeek LLM 从邮件正文提取核心卖点并直接生成标题
        llm_subjects = self._extract_themes_with_llm(email_body, clean_name)
        if llm_subjects and len(llm_subjects) >= 3:
            return llm_subjects

        # 第二步：LLM 失败时回退到正则提取
        import re
        subjects = []
        themes = self._extract_themes_fallback(email_body)

        for theme in themes[:5]:
            variations = self._create_subject_variations(theme, clean_name)
            for v in variations:
                if v and v not in subjects and len(subjects) < 15:
                    subjects.append(v)

        # 如果正则提取也太少，从正文中提取关键句
        if len(subjects) < 3:
            keyword_hints = ['efficiency', 'power', 'solar panel', 'panel', 'warranty', 'delivery',
                             'custom', 'oem', 'sample', 'cost', 'save', 'quality', 'durability',
                             'technology', 'solution', 'manufacturing', 'ship', 'export']
            skip_prefixes = ['hi ', 'hello ', 'dear ', 'best regards', 'sincerely', 'thank you',
                             'my name is', 'i am ', 'i noticed', 'i hope', 'we are ', 'our company']
            sentences = re.split(r'(?<=[.!?])\s+', email_body)
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 30 or len(sentence) > 90:
                    continue
                lower = sentence.lower()
                if any(x in lower for x in skip_prefixes):
                    continue
                if not any(h in lower for h in keyword_hints):
                    continue
                title = sentence[0].upper() + sentence[1:]
                title = self._validate_and_clean(title)
                if title and title not in subjects and len(subjects) < 15:
                    subjects.append(title)

        return subjects

    def _extract_themes_with_llm(self, email_body: str, customer_name: str) -> List[str]:
        """使用 DeepSeek LLM 从邮件正文提取核心卖点并直接生成多样化的邮件标题"""
        try:
            from services.llm_client import LLMEmailClient
            llm = LLMEmailClient()
            if not llm.is_available():
                print("[标题生成] DeepSeek API 不可用，回退到正则提取")
                return []

            system_prompt = (
                "You are an expert email marketing copywriter. "
                "Your task is to analyze the given email body and generate diverse, compelling email subject lines.\n\n"
                "RULES:\n"
                "1. Read the email body carefully and identify the core selling points, value propositions, and call-to-action.\n"
                "2. Each subject line must reflect a DIFFERENT aspect or angle from the email content.\n"
                "3. DO NOT use spam trigger words (free, urgent, act now, limited time, etc.).\n"
                "4. Keep each subject line under 70 characters.\n"
                "5. Include the customer name naturally in some subjects but not all.\n"
                "6. Vary sentence styles: some direct statements, some questions, some benefit-driven.\n"
                "7. Make each subject line unique and distinct from the others.\n"
                "8. Output ONLY a valid JSON array of strings, no explanation, no markdown, no code fences.\n"
            )
            # 截取邮件正文核心部分（去掉问候语和签名）
            body_for_analysis = email_body[:2000]
            user_prompt = (
                f"Customer name: {customer_name}\n\n"
                f"Email body:\n{body_for_analysis}\n\n"
                f"Generate exactly 10 unique email subject lines based on the content above. "
                f"Output as JSON array of strings: [\"subject1\", \"subject2\", ...]"
            )

            result, error = llm._call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1000,
                temperature=0.8,
                label='subject_generation'
            )

            if error or not result:
                print(f"[标题生成] LLM 调用失败: {error}")
                return []

            # 解析 JSON 数组
            import json
            result = result.strip()
            # 处理可能的 markdown 代码块包裹
            if result.startswith('```'):
                result = re.sub(r'^```\w*\n?', '', result)
                result = re.sub(r'\n?```$', '', result)

            subjects_list = json.loads(result)
            if not isinstance(subjects_list, list):
                return []

            # 清理和验证每个标题
            valid_subjects = []
            for s in subjects_list:
                if not isinstance(s, str):
                    continue
                s = self._validate_and_clean(s.strip())
                if s and len(s) > 10 and len(s) <= 80 and s not in valid_subjects:
                    valid_subjects.append(s)

            print(f"[标题生成] LLM 生成了 {len(valid_subjects)} 个有效标题")
            return valid_subjects

        except json.JSONDecodeError as e:
            print(f"[标题生成] JSON 解析失败: {e}")
            return []
        except Exception as e:
            print(f"[标题生成] LLM 提取异常: {e}")
            return []

    def _extract_themes_fallback(self, email_body: str) -> List[str]:
        """回退方案：用正则从邮件正文提取核心主题/卖点短语"""
        themes = []
        body_lower = email_body.lower()

        # 产品特性主题
        product_patterns = [
            (r'\b(\d+[%％]?)\s*(?:more efficient|higher efficiency|efficiency)',
             lambda m: f"{m.group(1)} Higher Efficiency"),
            (r'\b(\d+[%％]?)\s*(?:more power|power output)',
             lambda m: f"{m.group(1)} More Power Output"),
            (r'\b(pure black|all black|black surface)\b',
             lambda m: "Pure Black Design"),
            (r'\b(back[- ]?contact|bc cell|bc technology)\b',
             lambda m: "Back-Contact Cell Technology"),
            (r'\b(tempered glass|hardened glass)\b',
             lambda m: "Tempered Glass Construction"),
            (r'\b(ddp|delivered duty paid|door[- ]?to[- ]?door)\b',
             lambda m: "DDP Delivery Service"),
            (r'\b(\d+[+-]?\s*years?)\s*(?:warranty|guarantee)',
             lambda m: f"{m.group(1)} Warranty"),
            (r'\b(oem|odm|custom)\b',
             lambda m: "OEM/ODM Customization"),
        ]

        for pattern, formatter in product_patterns:
            match = re.search(pattern, body_lower)
            if match:
                theme = formatter(match)
                if theme and theme not in themes:
                    themes.append(theme)

        # 价值主张主题
        value_patterns = [
            (r'\b(cost|save|saving|reduce cost)\b', "Cost Reduction Solutions"),
            (r'\b(quality|reliable|durable|robust)\b', "Quality & Reliability"),
            (r'\b(30%|50%|70%|\d+%)\s*(?:cost|save|reduce)',
             lambda m: f"{m.group(1)} Cost Savings"),
            (r'\b(carbon|sustainable|green|eco[- ]?friendly)\b',
             "Sustainability Focus"),
            (r'\b(global|worldwide|international|multi[- ]?country)\b',
             "Global Supply Chain"),
            (r'\b(sample|test|trial|free sample)\b',
             "Free Sample Available"),
        ]

        for pattern, theme in value_patterns:
            if isinstance(theme, str):
                if re.search(pattern, body_lower) and theme not in themes:
                    themes.append(theme)
            else:
                match = re.search(pattern, body_lower)
                if match:
                    t = theme(match)
                    if t and t not in themes:
                        themes.append(t)

        # 行动号召主题
        if re.search(r'\b(call|schedule|meeting|discuss|talk)\b', body_lower):
            themes.append("Schedule a Discussion")
        if re.search(r'\b(quote|pricing|price|proposal)\b', body_lower):
            themes.append("Request a Quote")

        return themes

    def _create_subject_variations(self, theme: str, customer_name: str) -> List[str]:
        """为一个主题创建多种句式的标题变体，确保多样化"""
        variations = []

        # 句式1: 直接陈述
        variations.append(f"{theme} for {customer_name}")

        # 句式2: 提问式
        variations.append(f"Could {theme} Work for {customer_name}?")

        # 句式3: 利益导向
        variations.append(f"How {customer_name} Benefits from {theme}")

        # 句式4: 简短有力
        if len(theme) < 40:
            variations.append(theme)

        # 句式5: 合作视角
        variations.append(f"{theme}: A Partnership with {customer_name}")

        # 句式6: 行动号召
        variations.append(f"Explore {theme} with {customer_name}")

        # 句式7: 价值主张
        variations.append(f"{customer_name} + {theme}: A Perfect Match")

        # 去重和清理
        result = []
        for v in variations:
            v = self._validate_and_clean(v)
            if v and v not in result:
                result.append(v)

        return result[:4]  # 每个主题最多4个变体

    def get_pool_stats(self, customer_id: int) -> Optional[Dict]:
        """获取标题池统计信息"""
        pool = self.generated_pools.get(customer_id)
        if not pool:
            return None
        return {
            'customer_id': pool.customer_id,
            'customer_name': pool.customer_name,
            'subject_count': len(pool.subjects),
            'subjects': pool.subjects
        }


# 全局实例
subject_manager = SmartSubjectManager()
