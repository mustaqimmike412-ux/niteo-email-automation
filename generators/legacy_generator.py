import json
import os
import re
from services.website_analyzer import WebsiteAnalyzer


class LegacyEmailGenerator:
    """合并旧版 SmartEmailGenerator 和 AdvancedEmailGenerator 的兼容类"""

    def __init__(self):
        self.analyzer = WebsiteAnalyzer()
        self.company_info = self._load_company_info()
        self.advantages = self._load_advantages()

    def _load_company_info(self):
        """加载公司信息"""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'company_info.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _load_advantages(self):
        """优势库已迁移到数据库，此方法不再返回硬编码数据"""
        return []

    # ========== SmartEmailGenerator 核心方法 ==========

    def analyze_customer_type(self, customer_data):
        """判断客户类型：大功率(300W-700W) vs 小功率(1W-200W)"""
        website_data = customer_data.get('website_data', {})
        company_info = customer_data.get('company_info', '')

        large_power_indicators = [
            'utility', 'commercial', 'industrial', 'power plant', 'solar farm',
            'ground mount', 'roof mount', 'MW', 'megawatt', 'large scale',
            '工商业', '光伏电站', '地面电站', '大型', '储能系统'
        ]
        small_power_indicators = [
            'consumer', 'portable', 'camping', 'RV', 'marine', 'IoT', 'sensor',
            'camera', 'doorbell', 'wearable', 'gadget', 'electronics',
            '便携', '露营', '房车', '游艇', '摄像头', '门铃', '可穿戴'
        ]

        text_to_analyze = (website_data.get('title', '') + ' ' +
                          website_data.get('description', '') + ' ' +
                          str(company_info)).lower()

        large_score = sum(1 for indicator in large_power_indicators if indicator in text_to_analyze)
        small_score = sum(1 for indicator in small_power_indicators if indicator in text_to_analyze)

        if large_score > small_score:
            return "large_power"
        elif small_score > large_score:
            return "small_power"
        else:
            business_model = website_data.get('business_model', '')
            if business_model in ['manufacturer', 'distributor']:
                return "large_power"
            else:
                return "small_power"

    def select_relevant_advantages(self, customer_type, industry):
        """根据客户类型选择最相关的优势"""
        selected = []
        if customer_type == "small_power":
            priority = ["core_tech", "case_studies", "oem_odm", "ddp_service", "global_supply"]
        else:
            priority = ["one_stop_solution", "global_supply", "oem_odm", "ddp_service", "case_studies"]

        for adv_key in priority:
            if adv_key in self.advantages:
                selected.append(self.advantages[adv_key])
        return selected

    def generate_fabe_content(self, advantage, customer_data):
        """根据FABE法则生成内容"""
        return {
            "feature": advantage["feature"],
            "advantage": advantage["advantage"],
            "benefit": advantage["benefit"],
            "evidence": advantage["evidence"]
        }

    def generate_email_sequence(self, customer_data):
        """生成5封邮件序列"""
        customer_type = self.analyze_customer_type(customer_data)
        industry = customer_data.get('website_data', {}).get('industry', 'general')
        advantages = self.select_relevant_advantages(customer_type, industry)

        emails = []
        emails.append(self._generate_email_1(customer_data, advantages[0] if advantages else None))
        emails.append(self._generate_email_2(customer_data, advantages[1] if len(advantages) > 1 else None))
        emails.append(self._generate_email_3(customer_data, advantages[2] if len(advantages) > 2 else None))
        emails.append(self._generate_email_4(customer_data, advantages[3] if len(advantages) > 3 else None))
        emails.append(self._generate_email_5(customer_data))

        return {
            "customer_type": customer_type,
            "emails": emails
        }

    def _generate_email_1(self, customer_data, advantage):
        """Email 1: 破冰与行业共鸣"""
        customer_name = customer_data.get('customer_name', '')
        industry = customer_data.get('website_data', {}).get('industry', '')
        subject = f"Solar Solutions for {customer_name}'s {industry.title()} Products"
        body = f"""Hi {customer_name} Team,

We noticed {customer_name}'s focus on innovative {industry} solutions. Many leading brands in this space face challenges with reliable outdoor power supply and product durability.

{advantage['evidence'] if advantage else 'We have extensive experience solving these challenges for global brands.'}

Would you be open to a brief chat about how we can support your product development?

Best regards,
{self.company_info.get('sender_name', '')}
{self.company_info.get('company_name', '')}"""
        return {"subject": subject, "body": body, "type": "ice_breaker"}

    def _generate_email_2(self, customer_data, advantage):
        """Email 2: 核心技术与视觉突围"""
        customer_name = customer_data.get('customer_name', '')
        subject = f"Advanced Cell Technology - Pure Black & High Efficiency"
        body = f"""Hi {customer_name} Team,

Following up on my last email - I'd like to share a technology that could differentiate your products.

{advantage['feature'] if advantage else 'Our advanced cell technology features a pure black surface with all conductive grids on the back.'}

{advantage['advantage'] if advantage else 'This means more sunlight absorption, higher conversion efficiency, and a premium aesthetic that integrates seamlessly with high-end product designs.'}

{advantage['benefit'] if advantage else 'For your customers, this translates to better performance in low-light conditions and a sleeker product appearance.'}

Interested in seeing sample data?

Best regards,
{self.company_info.get('sender_name', '')}
{self.company_info.get('company_name', '')}"""
        return {"subject": subject, "body": body, "type": "tech_highlight"}

    def _generate_email_3(self, customer_data, advantage):
        """Email 3: 场景痛点与极端耐候性"""
        customer_name = customer_data.get('customer_name', '')
        subject = f"Durability That Matches Your Quality Standards"
        body = f"""Hi {customer_name} Team,

Outdoor devices face harsh conditions - UV exposure, physical impact, and extreme temperatures. Standard solar panels often degrade quickly.

{advantage['feature'] if advantage else 'We use high-transparency tempered glass protection instead of conventional ETFE film.'}

{advantage['advantage'] if advantage else 'This provides superior abrasion resistance and anti-aging properties, maintaining stable charging efficiency even in harsh outdoor environments.'}

{advantage['benefit'] if advantage else 'Your customers will experience longer product lifespan and reduced maintenance costs, enhancing their overall satisfaction with your brand.'}

{advantage['evidence'] if advantage else 'Our panels have proven durability in field tests with major brands.'}

Best regards,
{self.company_info.get('sender_name', '')}
{self.company_info.get('company_name', '')}"""
        return {"subject": subject, "body": body, "type": "durability"}

    def _generate_email_4(self, customer_data, advantage):
        """Email 4: 供应链与地域适配"""
        customer_name = customer_data.get('customer_name', '')
        country = customer_data.get('country', '')
        subject = f"Streamlined Delivery to {country if country else 'Your Location'}"
        body = f"""Hi {customer_name} Team,

Managing international logistics and customs can be complex and time-consuming.

{advantage['feature'] if advantage else 'We offer DDP (Delivered Duty Paid) service with direct delivery to major ports.'}

{advantage['advantage'] if advantage else 'We handle all transportation risks, freight costs, and customs clearance procedures.'}

{advantage['benefit'] if advantage else 'You simply wait for delivery without dealing with complex cross-border logistics or hidden fees. Your total cost is transparent from the start.'}

{advantage['evidence'] if advantage else 'Our established delivery network ensures reliable and timely shipments.'}

Best regards,
{self.company_info.get('sender_name', '')}
{self.company_info.get('company_name', '')}"""
        return {"subject": subject, "body": body, "type": "logistics"}

    def _generate_email_5(self, customer_data):
        """Email 5: 最终邀约"""
        customer_name = customer_data.get('customer_name', '')
        subject = f"Quick 10-Minute Call?"
        body = f"""Hi {customer_name} Team,

To summarize what we can offer:

- Premium advanced cell technology for superior efficiency and aesthetics
- Proven OEM/ODM experience with top global brands
- Durable glass-protected panels for harsh outdoor conditions
- Hassle-free DDP delivery to your location

Would you be available for a quick 10-minute call this week to discuss how we can support your specific needs?

Or if you prefer, I can send free samples for your evaluation first.

Best regards,
{self.company_info.get('sender_name', '')}
{self.company_info.get('company_name', '')}
{self.company_info.get('email', '')}
{self.company_info.get('phone', '')}"""
        return {"subject": subject, "body": body, "type": "cta"}

    def format_email(self, email_content):
        """格式化邮件，确保排版整洁专业"""
        body = email_content['body']
        paragraphs = [p.strip() for p in body.split('\n\n') if p.strip()]
        formatted_body = '\n\n'.join(paragraphs)
        lines = formatted_body.split('\n')
        formatted_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('Hi ') or stripped.startswith('Dear '):
                formatted_lines.append(stripped)
            elif stripped.startswith('Best regards') or stripped.startswith('Regards'):
                formatted_lines.append('')
                formatted_lines.append(stripped)
            else:
                formatted_lines.append(stripped)
        formatted_body = '\n'.join(formatted_lines)
        return {
            "subject": email_content['subject'],
            "body": formatted_body
        }

    # ========== AdvancedEmailGenerator 核心方法 ==========

    def deep_analyze_customer(self, customer_data):
        """深度客户分析"""
        website = customer_data.get('website', '')
        company_info = customer_data.get('company_info', '')
        print("\n" + "="*60)
        print("深度客户背调分析")
        print("="*60)
        print(f"\n1. 分析网站: {website}")
        website_data = self.analyzer.analyze_website(website)
        business_profile = self._extract_business_profile(website_data, company_info)
        print(f"\n2. 业务特征分析:")
        print(f"   行业类型: {business_profile['industry']}")
        print(f"   产品类别: {', '.join(business_profile['product_categories'])}")
        print(f"   应用场景: {', '.join(business_profile['use_cases'])}")
        print(f"   目标市场: {', '.join(business_profile['target_markets'])}")
        print(f"   业务痛点: {', '.join(business_profile['pain_points'])}")
        return business_profile

    def _extract_business_profile(self, website_data, company_info):
        """提取业务特征档案"""
        text = (website_data.get('title', '') + ' ' +
                website_data.get('description', '') + ' ' +
                str(company_info)).lower()

        industry_keywords = {
            'security': ['security', 'surveillance', 'camera', 'monitoring', 'cctv', 'trail camera', 'wildlife camera', 'game camera'],
            'solar': ['solar', 'photovoltaic', 'renewable', 'energy', 'power'],
            'consumer_electronics': ['consumer', 'electronics', 'gadget', 'device', 'smart home'],
            'outdoor': ['outdoor', 'camping', 'hunting', 'wildlife', 'trail', 'adventure'],
            'agriculture': ['agriculture', 'farm', 'livestock', 'pasture', 'ranch']
        }

        detected_industry = 'general'
        max_score = 0
        for industry, keywords in industry_keywords.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > max_score:
                max_score = score
                detected_industry = industry

        product_categories = []
        if 'camera' in text or 'surveillance' in text or 'imaging' in text:
            product_categories.append('camera_systems')
        if 'solar' in text or 'panel' in text or 'photovoltaic' in text:
            product_categories.append('solar_products')
        if 'battery' in text or 'power' in text or 'energy' in text:
            product_categories.append('power_solutions')
        if 'tracker' in text or 'gps' in text:
            product_categories.append('tracking_devices')

        use_cases = []
        if any(word in text for word in ['outdoor', 'wildlife', 'trail', 'hunting', 'game']):
            use_cases.append('outdoor_monitoring')
        if any(word in text for word in ['security', 'surveillance', 'monitoring', 'protection']):
            use_cases.append('security_surveillance')
        if any(word in text for word in ['farm', 'agriculture', 'livestock', 'pasture', 'ranch']):
            use_cases.append('agriculture_monitoring')
        if any(word in text for word in ['home', 'residential', 'consumer']):
            use_cases.append('consumer_home')

        target_markets = []
        if 'usa' in text or 'united states' in text or 'america' in text:
            target_markets.append('north_america')
        if 'europe' in text or 'eu' in text:
            target_markets.append('europe')
        if 'asia' in text or 'china' in text:
            target_markets.append('asia_pacific')

        pain_points = []
        if detected_industry == 'security' or 'camera' in product_categories:
            pain_points.extend([
                'outdoor_power_reliability', 'weather_resistance',
                'long_term_durability', 'continuous_power_supply', 'battery_replacement_cost'
            ])
        elif detected_industry == 'outdoor':
            pain_points.extend([
                'outdoor_power_reliability', 'weather_resistance', 'portability'
            ])
        elif detected_industry == 'agriculture':
            pain_points.extend([
                'continuous_power_supply', 'maintenance_free', 'weather_resistance'
            ])
        else:
            pain_points.extend([
                'power_reliability', 'cost_efficiency', 'product_durability'
            ])

        return {
            'industry': detected_industry,
            'product_categories': product_categories,
            'use_cases': use_cases,
            'target_markets': target_markets,
            'pain_points': pain_points,
            'raw_text': text
        }

    def match_advantages(self, business_profile):
        """智能匹配最相关的优势"""
        print(f"\n3. 优势智能匹配:")
        matched_advantages = []
        text = business_profile['raw_text']

        for adv_key, advantage in self.advantages.items():
            score = 0
            matched_keywords = []
            for keyword in advantage.get('keywords', []):
                if keyword.lower() in text:
                    score += 2
                    matched_keywords.append(keyword)

            if adv_key == 'case_studies':
                if business_profile['industry'] == 'security':
                    score += 10
                if 'camera' in business_profile['product_categories']:
                    score += 5
            if adv_key == 'core_tech':
                if any(word in text for word in ['design', 'aesthetic', 'premium', 'high-end']):
                    score += 5
            if adv_key == 'oem_odm':
                if any(word in text for word in ['custom', 'unique', 'specialized']):
                    score += 5

            if score > 0:
                matched_advantages.append({
                    'key': adv_key,
                    'advantage': advantage,
                    'score': score,
                    'matched_keywords': matched_keywords
                })

        matched_advantages.sort(key=lambda x: x['score'], reverse=True)
        top_advantages = matched_advantages[:3]

        for i, matched in enumerate(top_advantages, 1):
            print(f"   匹配{i}: {matched['advantage']['name']} (分数: {matched['score']})")
            print(f"      匹配关键词: {', '.join(matched['matched_keywords'])}")

        return top_advantages

    def generate_personalized_email(self, customer_data, business_profile, matched_advantages):
        """生成个性化邮件"""
        customer_name = customer_data.get('customer_name', 'Valued Partner')
        contact_name = customer_data.get('contact_name', '')
        website = customer_data.get('website', '')
        has_website = bool(website and website.strip() and website.strip().startswith('http'))

        if contact_name and contact_name.strip():
            greeting = f"Hi {contact_name}"
        else:
            greeting = f"Hi {customer_name} Team"

        subject = self._generate_subject(customer_name, business_profile)
        body = self._generate_body(greeting, customer_name, business_profile, matched_advantages, has_website)

        return {
            'subject': subject,
            'body': body
        }

    def _generate_subject(self, customer_name, business_profile):
        """生成邮件主题"""
        industry = business_profile['industry']
        if industry == 'security':
            return f"Solar Power Solutions for {customer_name}'s Outdoor Cameras"
        elif industry == 'outdoor':
            return f"Reliable Outdoor Power for {customer_name}'s Products"
        elif industry == 'agriculture':
            return f"Solar Solutions for {customer_name}'s Farm Monitoring"
        else:
            return f"Partnership Opportunity - {customer_name} & Our Company"

    def _generate_body(self, greeting, customer_name, business_profile, matched_advantages, has_website=True):
        """生成邮件正文"""
        opening = self._generate_opening(customer_name, business_profile, has_website)
        pain_point_section = self._generate_pain_point_section(business_profile)
        solution_sections = []
        for matched in matched_advantages:
            solution_sections.append(self._generate_solution_section(matched['advantage'], business_profile))
        case_study_section = self._generate_case_study_section(business_profile, matched_advantages, customer_name)
        cta = self._generate_cta(customer_name)

        body = f"""{greeting},

{opening}

{pain_point_section}

{chr(10).join(solution_sections)}

{case_study_section}

{cta}

Best regards,
{self.company_info.get('sender_name', '')}
{self.company_info.get('job_title', '')}
{self.company_info.get('company_name', '')}
{self.company_info.get('email', '')}
{self.company_info.get('website', '')}"""
        return body

    def _generate_opening(self, customer_name, business_profile, has_website=True):
        """生成开场白"""
        industry = business_profile['industry']
        use_cases = business_profile['use_cases']

        if industry == 'security' and 'outdoor_monitoring' in use_cases:
            if has_website:
                return f"I recently explored {customer_name}'s website and was impressed by your trail cameras and outdoor monitoring solutions. Your products are clearly designed for harsh outdoor environments where reliable power is critical."
            else:
                return f"I recently came across {customer_name} and was impressed by your trail cameras and outdoor monitoring solutions. Your products are clearly designed for harsh outdoor environments where reliable power is critical."
        elif industry == 'outdoor':
            return f"I've been following {customer_name}'s innovative outdoor products, and I can see you understand the challenges of powering devices in remote locations."
        elif industry == 'agriculture':
            return f"Your work in agricultural monitoring at {customer_name} is impressive. Managing livestock and pasture conditions requires reliable, maintenance-free power solutions."
        else:
            if has_website:
                return f"I hope this email finds you well. I've been researching {customer_name} and am impressed by your product lineup and market presence."
            else:
                return f"I hope this email finds you well. I came across {customer_name} and am impressed by your product lineup and market presence."

    def _generate_pain_point_section(self, business_profile):
        """生成痛点共鸣部分"""
        pain_points = business_profile['pain_points']
        if 'outdoor_power_reliability' in pain_points and 'battery_replacement_cost' in pain_points:
            return """Many of our clients in the outdoor camera and monitoring space face similar challenges:

- Frequent battery replacements in remote locations
- Inconsistent power supply affecting device reliability
- High maintenance costs for deployed equipment
- Weather damage to standard solar panels over time

These issues not only increase operational costs but can also compromise the reliability your customers depend on."""
        else:
            return "We understand that maintaining reliable power for outdoor devices can be challenging, especially in harsh environmental conditions."

    def _generate_solution_section(self, advantage, business_profile):
        """生成解决方案部分"""
        adv_name = advantage['name']
        if 'Technology' in adv_name or 'Core' in adv_name:
            return """**Our Advanced Cell Technology Solves This:**

Our advanced solar cells feature a pure black surface with all conductive grids integrated on the back. This means:

- **More Power**: Unobstructed surface absorbs more sunlight
- **Better Low-Light Performance**: Critical for dawn/dusk wildlife monitoring
- **Premium Aesthetics**: Seamlessly integrates with high-end camera designs
- **Longer Lifespan**: Superior durability in outdoor conditions"""
        elif 'OEM/ODM' in adv_name:
            return """**Customized Solutions for Your Specific Needs:**

We don't believe in one-size-fits-all. Our OEM/ODM capabilities include:

- **Shape Customization**: Irregular forms to fit your camera housings
- **Lightweight Options**: Reduced load for mounting applications
- **Flexible Panels**: For curved or unconventional surfaces
- **Waterproof Integration**: IP67-rated solutions for outdoor use"""
        elif 'Case Studies' in adv_name or 'Success' in adv_name:
            return """**Proven Results with Similar Products:**

We've successfully partnered with leading brands in your space, delivering reliable, aesthetically pleasing solar solutions for consumer security products.

These partnerships demonstrate our ability to deliver reliable, aesthetically pleasing solar solutions for consumer security products."""
        elif 'Global' in adv_name:
            return """**Reliable Supply Chain:**

With manufacturing facilities across multiple countries, we ensure:

- **Consistent Supply**: No single point of failure
- **Flexible Production**: Scale up or down based on demand
- **Trade Risk Mitigation**: Navigate geopolitical challenges smoothly"""
        else:
            return f"**{advantage['name']}:**\n\n{advantage['feature']}\n\n{advantage['advantage']}\n\n{advantage['benefit']}"

    def _generate_case_study_section(self, business_profile, matched_advantages, customer_name='your company'):
        """生成案例匹配部分"""
        industry = business_profile['industry']
        if industry == 'security':
            return f"""**Why This Matters for {customer_name}:**

Your trail cameras and outdoor monitoring solutions operate in the same challenging environments as our existing partners. Whether it's a wildlife camera in a remote forest or a security camera in a harsh climate, the power solution needs to be:

- **Reliable**: No missed footage due to power issues
- **Durable**: Withstand years of outdoor exposure
- **Aesthetically Pleasing**: Match the quality of your product design
- **Low Maintenance**: Reduce customer support burden

We've solved these exact challenges for leading brands - and we can do the same for {customer_name}."""
        else:
            return "Our solutions have been proven across multiple industries and applications, ensuring we can meet your specific requirements."

    def _generate_cta(self, customer_name):
        """生成行动号召"""
        return f"""I'd love to explore how we can support {customer_name}'s product roadmap. Would you be available for a brief 15-minute call this week to discuss:

- Your current power solution challenges
- Potential integration points for solar technology
- How our experience with similar products can accelerate your development

Alternatively, I can send sample units for your engineering team to evaluate firsthand.

Looking forward to hearing from you."""

    def generate_email_for_customer(self, customer_data):
        """为指定客户生成完整邮件（Advanced 模式入口）"""
        business_profile = self.deep_analyze_customer(customer_data)
        matched_advantages = self.match_advantages(business_profile)
        email = self.generate_personalized_email(customer_data, business_profile, matched_advantages)
        return {
            'business_profile': business_profile,
            'matched_advantages': matched_advantages,
            'email': email
        }
