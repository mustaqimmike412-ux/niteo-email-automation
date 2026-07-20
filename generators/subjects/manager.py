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
        根据邮箱数量计算需要生成的标题数量

        Args:
            email_count: 邮箱数量
            user_override: 用户指定的标题数量（0 = 自动决定）

        Returns:
            int: 需要生成的标题数量
        """
        if user_override > 0:
            return min(max(1, user_override), min(email_count, 20))
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
        为客户生成指定数量的备选标题

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

        # 从模板池随机选择指定数量的模板（不重复）
        selected_templates = random.sample(self.TEMPLATES,
                                           min(subject_count, len(self.TEMPLATES)))

        subjects = []
        for template in selected_templates:
            subject = template.format(
                customer=clean_name,
                country=clean_country,
                industry=clean_industry
            )
            subject = self._validate_and_clean(subject)
            if subject and subject not in subjects:  # 去重
                subjects.append(subject)

        # 如果有邮件正文，基于内容生成额外标题（从正文提取关键信息）
        if email_body and len(email_body) > 20:
            content_subjects = self._generate_subjects_from_body(email_body, clean_name)
            for cs in content_subjects:
                if len(subjects) < subject_count and cs not in subjects:
                    subjects.append(cs)

        # 如果生成的数量不够，补充通用标题
        while len(subjects) < subject_count:
            generic = self._generate_generic_subject(clean_name, clean_industry)
            if generic not in subjects:
                subjects.append(generic)

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
        # 算法：多次随机尝试，若某次洗牌无相邻重复则采用；超过上限则用贪心修正
        assignment_plan = self._shuffle_no_adjacent(pool, subjects)

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
                            num_subjects: int = 0) -> Tuple[List[str], List[Dict]]:
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

        Returns:
            Tuple[List[str], List[Dict]]: (生成的标题列表, 分配后的邮箱列表)
        """
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
        2. 若100次都没成功，用贪心算法逐位随机选择与上一个不同的标题
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

        # 阶段2：贪心构建
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
            chosen = random.choice(candidates)
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
        """从邮件正文提取关键信息，生成基于内容的标题（最多3条）"""
        sentences = re.split(r'(?<=[.!?])\s+', email_body)
        subjects = []

        # 提取包含关键信息的句子
        keywords = ['solar', 'panel', 'efficiency', 'power', 'energy', 'battery',
                     'storage', 'BC cell', 'black', 'tempered glass', 'DDP',
                     'warranty', 'cost', 'savings', 'partner', 'integrate',
                     'solution', 'performance', 'capacity', 'output']

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 120:
                continue
            # 检查是否包含关键词
            words = sentence.lower().split()
            if any(kw in words for kw in keywords):
                # 取前8-12个单词作为标题
                title_words = words[:min(10, len(words))]
                title = ' '.join(w.capitalize() if i == 0 else w for i, w in enumerate(title_words))
                title = self._validate_and_clean(title)
                if title and title not in subjects:
                    subjects.append(title)
                if len(subjects) >= 3:
                    break

        return subjects

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
