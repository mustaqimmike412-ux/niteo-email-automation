import random
import hashlib
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class SubjectVariant:
    index: int
    subject_line: str
    subject_type: str
    strategy: str

class SubjectGenerator:
    """为客户生成5条独特的主题行"""

    # 中文国家名 -> 英文国家名映射（确保英文标题中使用英文国家名）
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
        '瑞典，法国': 'Sweden',
        '西班牙，主要项目在欧洲和中东': 'Spain',
        '波斯尼亚和黑塞哥维那.': 'Bosnia and Herzegovina',
    }

    # 主题模板池
    TEMPLATES = {
        "industry_resonance": [
            "Solar Solutions for {customer_name}'s {industry} Products",
            "Powering {customer_name}'s Innovation with Advanced Solar",
            "How {customer_name} Can Enhance Product Performance with Solar",
            "A Solar Partnership Opportunity for {customer_name}",
            "{customer_name} + Solar: A Natural Fit for Your Product Line",
            "Renewable Energy Solutions for {customer_name}'s Portfolio"
        ],
        
        "tech_highlight": [
            "BC Cell Technology - Pure Black & High Efficiency for {customer_name}",
            "The Solar Tech Behind Amazon & Ring's Products",
            "Higher Efficiency, Sleeker Design: BC Cells for {customer_name}",
            "Why Leading Brands Choose Our Back-Contact Solar Technology",
            "Pure Black Solar Panels: More Power, Better Aesthetics",
            "Next-Gen Solar: Unobstructed Surface, Maximum Output"
        ],
        
        "durability_focus": [
            "Durability That Matches {customer_name}'s Quality Standards",
            "Weather-Resistant Solar for Harsh Outdoor Conditions",
            "Long-Lasting Solar Power: Less Maintenance, More Reliability",
            "Tempered Glass Solar Panels: Built for the Real World",
            "How {customer_name} Can Reduce Product Returns with Better Solar",
            "Engineered for Extreme: Solar That Outlasts Standard Panels"
        ],
        
        "logistics_value": [
            "Streamlined Delivery to {country}: DDP Shipping Available",
            "Hassle-Free Solar Supply from Our Global Facilities",
            "DDP to {country}: We Handle Customs, You Focus on Growth",
            "Multi-Country Production = Reliable Supply for {customer_name}",
            "Simplify Your Procurement with Our DDP Delivery Service",
            "Global Manufacturing, Local Delivery for {customer_name}"
        ],
        
        "social_proof_cta": [
            "Quick Question About {customer_name}'s Solar Needs",
            "15-Min Call: How Ring & Arlo Use Our Solar Solutions",
            "Free Sample Offer for {customer_name}'s Engineering Team",
            "See Why Amazon Chose Us for Their Solar Partnership",
            "Can We Support {customer_name}'s Next Product Launch?",
            "Explore Solar Integration: 10-Minute Discovery Call"
        ]
    }
    
    # 禁用词列表（避免垃圾邮件触发）
    SPAM_TRIGGERS = {
        'free', 'urgent', 'act now', 'limited time', 'click here',
        'winner', 'congratulations', 'cash', 'prize', '!!!', '$$$',
        '100% free', 'no obligation', 'risk free', 'call now',
        'order now', 'buy now', 'special promotion', 'great offer',
        'act immediately', 'exclusive deal', 'limited offer'
    }
    
    def __init__(self, company_info: Dict = None):
        self.company_info = company_info or {}
    
    def generate_subjects_for_customer(
        self, 
        customer_data: Dict,
        website_data: Optional[Dict] = None
    ) -> List[SubjectVariant]:
        """
        为单个客户生成5条主题行
        
        Args:
            customer_data: 包含 customer_name, country, industry 等
            website_data: 网站分析结果
        
        Returns:
            List[SubjectVariant]: 5条主题变体
        """
        customer_name = customer_data.get('customer_name', 'Valued Partner')
        country = customer_data.get('country', 'Your Location')
        industry = self._detect_industry(customer_data, website_data)
        
        subjects = []
        
        # 策略：从5个不同维度各选1条
        strategies = [
            ("industry_resonance", "行业共鸣"),
            ("tech_highlight", "技术亮点"), 
            ("durability_focus", "耐用性痛点"),
            ("logistics_value", "供应链价值"),
            ("social_proof_cta", "社交证明/CTA")
        ]
        
        for idx, (template_key, strategy_name) in enumerate(strategies, 1):
            templates = self.TEMPLATES[template_key]
            
            # 使用客户名哈希确保同一客户每次生成结果一致
            seed = self._generate_seed(customer_name, template_key)
            random.seed(seed)
            
            # 选择模板并填充变量
            template = random.choice(templates)
            subject = self._fill_template(template, customer_name, country, industry)
            
            # 验证主题行质量
            subject = self._validate_and_clean(subject)
            
            subjects.append(SubjectVariant(
                index=idx,
                subject_line=subject,
                subject_type=template_key,
                strategy=strategy_name
            ))
        
        return subjects
    
    def _generate_seed(self, customer_name: str, template_key: str) -> int:
        """生成确定性种子，确保同一客户结果一致"""
        hash_input = f"{customer_name}:{template_key}:{self.company_info.get('company_name', '')}"
        return int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
    
    def _fill_template(self, template: str, customer_name: str, country: str, industry: str) -> str:
        """填充模板变量"""
        # 清理客户名（移除特殊字符）
        clean_name = ''.join(c for c in customer_name if c.isalnum() or c in (' ', '-', '_')).strip()
        # 国家名：中文转英文映射
        clean_country = self.COUNTRY_MAP.get(country, country) if country else 'Your Location'

        return template.format(
            customer_name=clean_name,
            country=clean_country,
            industry=industry.title() if industry else 'Product'
        )
    
    def _detect_industry(self, customer_data: Dict, website_data: Optional[Dict]) -> str:
        """检测客户行业"""
        if website_data and website_data.get('industry'):
            return website_data['industry']
        
        # 从 company_info 推断
        company_info = str(customer_data.get('company_info', '')).lower()
        industry_keywords = {
            'security': ['security', 'surveillance', 'camera', 'monitoring', 'cctv'],
            'outdoor': ['outdoor', 'camping', 'hunting', 'wildlife', 'trail'],
            'agriculture': ['agriculture', 'farm', 'livestock', 'pasture'],
            'electronics': ['electronics', 'consumer', 'device', 'gadget'],
            'energy': ['energy', 'power', 'battery', 'storage', 'solar'],
            'distributor': ['distributor', 'wholesale', 'dealer', 'reseller']
        }
        
        scores = {ind: sum(1 for kw in kws if kw in company_info) 
                  for ind, kws in industry_keywords.items()}
        
        if scores and max(scores.values()) > 0:
            return max(scores, key=scores.get)
        
        return 'Product'
    
    def _validate_and_clean(self, subject: str) -> str:
        """验证并清理主题行"""
        # 检查长度
        if len(subject) > 80:
            subject = subject[:77] + '...'
        
        # 检查禁用词
        subject_lower = subject.lower()
        for trigger in self.SPAM_TRIGGERS:
            if trigger in subject_lower:
                # 替换为安全替代词
                subject = subject_lower.replace(trigger, '').strip()
        
        # 确保不以特殊字符开头
        subject = subject.lstrip('!@#$%^&*')
        
        # 首字母大写
        subject = subject[0].upper() + subject[1:] if subject else subject
        
        return subject
    
    def regenerate_for_customer(self, customer_id: int, customer_data: Dict, website_data: Optional[Dict] = None) -> List[SubjectVariant]:
        """重新生成指定客户的主题"""
        return self.generate_subjects_for_customer(customer_data, website_data)

if __name__ == '__main__':
    # 测试
    generator = SubjectGenerator({'company_name': 'Niteo Solar'})
    
    test_customer = {
        'customer_name': 'Reconyx',
        'country': 'USA',
        'company_info': 'Trail cameras and outdoor monitoring solutions'
    }
    
    subjects = generator.generate_subjects_for_customer(test_customer)
    print(f"为 {test_customer['customer_name']} 生成的主题:")
    for s in subjects:
        print(f"  {s.index}. [{s.subject_type}] {s.subject_line}")
