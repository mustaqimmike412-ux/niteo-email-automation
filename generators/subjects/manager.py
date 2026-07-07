"""
智能邮件标题管理器
根据邮件内容实时生成多个备选标题，并按邮箱数量智能分配轮换
"""
import random
import re
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

    def calculate_subject_count(self, email_count: int) -> int:
        """
        根据邮箱数量计算需要生成的标题数量

        规则：
        - 1-4 个邮箱：生成 2 个标题
        - 5-10 个邮箱：生成 3 个标题
        - 11-20 个邮箱：生成 5 个标题
        - 21+ 个邮箱：生成 ceil(email_count / 4) 个标题（每4个邮箱1个标题）

        Returns:
            int: 需要生成的标题数量
        """
        if email_count <= 4:
            return 2
        elif email_count <= 10:
            return 3
        elif email_count <= 20:
            return 5
        else:
            return min(15, (email_count + 3) // 4)  # 最多15个标题

    def generate_subjects(self, customer_name: str, country: str,
                          industry: str, email_count: int) -> List[str]:
        """
        为客户生成指定数量的备选标题

        Args:
            customer_name: 客户名称
            country: 国家
            industry: 行业
            email_count: 邮箱数量（用于计算需要多少标题）

        Returns:
            List[str]: 生成的标题列表
        """
        subject_count = self.calculate_subject_count(email_count)

        # 清理客户名
        clean_name = self._clean_customer_name(customer_name)
        clean_industry = industry.title() if industry else 'Product'
        # 国家名：中文转英文映射，确保英文标题中使用英文国家名
        clean_country = self.COUNTRY_MAP.get(country, country) if country else 'Your Region'

        # 使用客户名作为种子，确保同一客户每次生成结果一致
        random.seed(hash(clean_name) % 10000)

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
        将标题分配给各个邮箱，随机打乱避免顺序规律

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

        # 计算每个标题应该分配多少个邮箱
        email_count = len(email_items)
        subject_count = len(subjects)
        base_count = email_count // subject_count
        extra = email_count % subject_count

        # 构建分配计划：每个标题分配多少个邮箱
        assignment_plan = []
        for i in range(subject_count):
            count = base_count + (1 if i < extra else 0)
            assignment_plan.extend([i] * count)

        # 随机打乱分配计划（关键：避免顺序规律）
        random.shuffle(assignment_plan)

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
                            email_items: List[Dict]) -> Tuple[List[str], List[Dict]]:
        """
        一站式生成标题并分配给邮箱

        Args:
            customer_id: 客户ID
            customer_name: 客户名称
            country: 国家
            industry: 行业
            email_items: 邮箱列表

        Returns:
            Tuple[List[str], List[Dict]]: (生成的标题列表, 分配后的邮箱列表)
        """
        subjects = self.generate_subjects(customer_name, country, industry,
                                          len(email_items))
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
