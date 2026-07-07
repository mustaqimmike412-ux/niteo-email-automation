import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse, urljoin
import time
import random
from duckduckgo_search import DDGS

class WebsiteAnalyzer:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def analyze_website(self, url):
        """分析网站内容，提取关键信息"""
        if not url or not url.startswith('http'):
            return {
                'title': '',
                'description': '',
                'products': [],
                'services': [],
                'industry': '',
                'regions': [],
                'business_model': '',
                'about_us': '',
                'error': '无效的URL'
            }
        
        try:
            # 添加随机延迟，避免请求过快
            time.sleep(random.uniform(1, 3))
            
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 提取标题
            title = soup.title.string if soup.title else ''
            
            # 提取meta description
            description = ''
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                description = meta_desc.get('content', '')
            
            # 提取页面文本内容
            page_text = soup.get_text(separator=' ', strip=True)
            
            # 分析行业类型
            industry = self._detect_industry(page_text, title)
            
            # 提取产品关键词
            products = self._extract_products(page_text)
            
            # 提取服务地区
            regions = self._extract_regions(page_text)
            
            # 提取业务模式
            business_model = self._detect_business_model(page_text)
            
            # 尝试获取About Us页面内容
            about_us = self._get_about_us(url, soup)
            
            return {
                'title': title,
                'description': description,
                'products': products,
                'services': self._extract_services(page_text),
                'industry': industry,
                'regions': regions,
                'business_model': business_model,
                'about_us': about_us,
                'error': None
            }
            
        except requests.RequestException as e:
            return {
                'title': '',
                'description': '',
                'products': [],
                'services': [],
                'industry': '',
                'regions': [],
                'business_model': '',
                'about_us': '',
                'error': f'请求错误: {str(e)}'
            }
        except Exception as e:
            return {
                'title': '',
                'description': '',
                'products': [],
                'services': [],
                'industry': '',
                'regions': [],
                'business_model': '',
                'about_us': '',
                'error': f'分析错误: {str(e)}'
            }
    
    def search_company_info(self, company_name, website=''):
        """使用搜索引擎搜索公司信息"""
        search_results = {
            'company_news': [],
            'products_found': [],
            'market_info': '',
            'competitors': []
        }
        
        try:
            with DDGS() as ddgs:
                # 搜索公司新闻和动态
                query = f"{company_name} company news products"
                results = ddgs.text(query, max_results=5)
                for r in results:
                    search_results['company_news'].append({
                        'title': r['title'],
                        'snippet': r['body'],
                        'url': r['href']
                    })
                
                # 搜索产品信息
                query = f"{company_name} products services"
                results = ddgs.text(query, max_results=3)
                for r in results:
                    search_results['products_found'].append(r['body'])
                
        except Exception as e:
            print(f"搜索出错: {e}")
        
        return search_results
    
    def _detect_industry(self, text, title):
        """检测行业类型"""
        text_lower = (text + ' ' + title).lower()
        
        industry_keywords = {
            'solar': ['solar', 'photovoltaic', 'pv', 'panel', 'renewable energy', '太阳能', '光伏'],
            'electronics': ['electronics', 'electronic', 'semiconductor', 'chip', 'circuit', '电子'],
            'security': ['security', 'surveillance', 'camera', 'monitoring', '安防', '监控'],
            'agriculture': ['agriculture', 'farm', 'livestock', 'cattle', '畜牧', '农业'],
            'automation': ['automation', 'control', 'gate', 'automatic', '自动化', '控制'],
            'energy': ['energy', 'power', 'battery', '储能', '能源'],
            'telecom': ['telecom', 'communication', 'network', 'wireless', '通信', '网络'],
            'manufacturing': ['manufacturing', 'factory', 'production', '制造', '生产'],
            'software': ['software', 'saas', 'platform', 'app', '软件'],
            'hardware': ['hardware', 'device', 'equipment', '硬件']
        }
        
        industry_scores = {}
        for industry, keywords in industry_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            if score > 0:
                industry_scores[industry] = score
        
        if industry_scores:
            return max(industry_scores, key=industry_scores.get)
        return 'general'
    
    def _extract_products(self, text):
        """提取产品关键词"""
        product_keywords = [
            'solar panel', 'inverter', 'battery', 'controller', 'sensor',
            'camera', 'monitor', 'gate opener', 'tracker', 'collar',
            'module', 'system', 'device', 'equipment', 'solution',
            'charger', 'adapter', 'connector', 'cable', 'mounting'
        ]
        
        found_products = []
        text_lower = text.lower()
        
        for keyword in product_keywords:
            if keyword in text_lower:
                found_products.append(keyword)
        
        return list(set(found_products))[:8]
    
    def _extract_services(self, text):
        """提取服务关键词"""
        service_keywords = [
            'installation', 'maintenance', 'consulting', 'design',
            'support', 'training', 'customization', 'oem', 'odm'
        ]
        
        found_services = []
        text_lower = text.lower()
        
        for keyword in service_keywords:
            if keyword in text_lower:
                found_services.append(keyword)
        
        return found_services
    
    def _extract_regions(self, text):
        """提取服务地区"""
        region_keywords = [
            'north america', 'europe', 'asia', 'pacific', 'middle east',
            'africa', 'south america', 'global', 'worldwide',
            'usa', 'uk', 'germany', 'france', 'australia', 'japan'
        ]
        
        found_regions = []
        text_lower = text.lower()
        
        for keyword in region_keywords:
            if keyword in text_lower:
                found_regions.append(keyword)
        
        return found_regions
    
    def _detect_business_model(self, text):
        """检测业务模式"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['manufacturer', 'factory', '生产']):
            return 'manufacturer'
        elif any(word in text_lower for word in ['distributor', 'dealer', '分销']):
            return 'distributor'
        elif any(word in text_lower for word in ['retailer', 'store', '零售']):
            return 'retailer'
        elif any(word in text_lower for word in ['wholesale', '批发']):
            return 'wholesaler'
        elif any(word in text_lower for word in ['solution provider', '系统集成']):
            return 'solution_provider'
        else:
            return 'unknown'
    
    def _get_about_us(self, base_url, soup):
        """尝试获取About Us页面内容"""
        try:
            # 查找About Us链接
            about_link = None
            for link in soup.find_all('a', href=True):
                if 'about' in link.text.lower() or 'about' in link['href'].lower():
                    about_link = urljoin(base_url, link['href'])
                    break
            
            if about_link:
                response = requests.get(about_link, headers=self.headers, timeout=10)
                about_soup = BeautifulSoup(response.content, 'html.parser')
                about_text = about_soup.get_text(separator=' ', strip=True)
                # 返回前500字符
                return about_text[:500]
            
        except:
            pass
        
        return ''

class EmailGenerator:
    def __init__(self):
        self.company_info = None  # 将在设置业务信息后更新
        
    def set_company_info(self, info):
        """设置我方公司信息"""
        self.company_info = info
    
    def generate_email(self, customer_data, email_type='personal'):
        """生成个性化开发信"""
        company_name = customer_data.get('customer_name', 'Valued Partner')
        contact_name = customer_data.get('contact_name', '')
        website_data = customer_data.get('website_data', {})
        
        # 如果联系人为空，使用通用称呼
        if not contact_name or contact_name == 'Sir/Madam':
            if email_type == 'public':
                contact_name = 'Sales Team'
            else:
                contact_name = 'Sir/Madam'
        
        # 生成邮件内容
        if email_type == 'public':
            return self._generate_public_email(company_name, website_data)
        else:
            return self._generate_personalized_email(company_name, contact_name, website_data)
    
    def _generate_personalized_email(self, company_name, contact_name, website_data):
        """生成个性化开发信"""
        
        # 提取客户信息
        industry = website_data.get('industry', '')
        products = website_data.get('products', [])
        services = website_data.get('services', [])
        regions = website_data.get('regions', [])
        business_model = website_data.get('business_model', '')
        about_us = website_data.get('about_us', '')
        
        # 构建个性化内容
        personalization = self._build_personalization(company_name, industry, products, regions, business_model)
        
        # 构建我方公司介绍
        company_intro = self._build_company_intro()
        
        # 构建合作建议
        cooperation = self._build_cooperation_suggestion(industry, products, business_model)
        
        subject = f"Partnership Opportunity - {company_name} & {self.company_info.get('company_name', 'Our Company')}"
        
        body = f"""Dear {contact_name},

I hope this email finds you well. My name is {self.company_info.get('sender_name', '[Your Name]')} from {self.company_info.get('company_name', '[Your Company]')}.

{personalization}

{company_intro}

{cooperation}

I would love to schedule a brief call to discuss how we can support {company_name}'s growth and explore potential collaboration opportunities. Would you be available for a 15-minute call next week?

Best regards,
{self.company_info.get('sender_name', '[Your Name]')}
{self.company_info.get('job_title', '[Your Position]')}
{self.company_info.get('company_name', '[Your Company]')}
{self.company_info.get('email', '[Email]')}
{self.company_info.get('phone', '[Phone]')}
{self.company_info.get('website', '[Website]')}
"""
        
        return {
            'subject': subject,
            'body': body
        }
    
    def _generate_public_email(self, company_name, website_data):
        """生成公共邮箱的开发信"""
        
        industry = website_data.get('industry', '')
        products = website_data.get('products', [])
        
        subject = f"Business Cooperation Inquiry - {company_name}"
        
        body = f"""Dear Sales Team,

I hope this email finds you well. My name is {self.company_info.get('sender_name', '[Your Name]')} from {self.company_info.get('company_name', '[Your Company]')}.

I visited {company_name}'s website and was impressed by your company's products and market presence in the {industry} industry.

{self.company_info.get('company_name', 'Our company')} is a professional manufacturer specializing in {', '.join(self.company_info.get('main_products', ['high-quality products']))}. We have been serving customers worldwide for {self.company_info.get('years_in_business', 'many')} years.

Our key advantages:
{self._format_products_list()}

Could you please direct this email to the appropriate person who handles procurement or business development? We would appreciate the opportunity to discuss how we can support {company_name}'s business growth.

Thank you for your time and consideration.

Best regards,
{self.company_info.get('sender_name', '[Your Name]')}
{self.company_info.get('job_title', '[Your Position]')}
{self.company_info.get('company_name', '[Your Company]')}
{self.company_info.get('email', '[Email]')}
{self.company_info.get('phone', '[Phone]')}
"""
        
        return {
            'subject': subject,
            'body': body
        }
    
    def _build_personalization(self, company_name, industry, products, regions, business_model):
        """构建个性化段落"""
        parts = []
        
        parts.append(f"I recently visited {company_name}'s website and was impressed by your company's focus on the {industry} industry.")
        
        if products:
            parts.append(f"I noticed that you offer products such as {', '.join(products[:3])}, which aligns well with our expertise.")
        
        if regions:
            parts.append(f"It's great to see that you serve customers in {', '.join(regions[:3])}.")
        
        if business_model:
            model_desc = {
                'manufacturer': 'manufacturing capabilities',
                'distributor': 'distribution network',
                'retailer': 'retail presence',
                'wholesaler': 'wholesale operations',
                'solution_provider': 'integrated solutions'
            }
            if business_model in model_desc:
                parts.append(f"Your {model_desc[business_model]} are particularly impressive.")
        
        return '\n\n'.join(parts)
    
    def _build_company_intro(self):
        """构建公司介绍"""
        if not self.company_info:
            return "We are a professional manufacturer with extensive experience in the industry."
        
        intro = f"""At {self.company_info.get('company_name', 'our company')}, we specialize in:
{self._format_products_list()}

Our key strengths include:
- {self.company_info.get('strength1', 'High-quality manufacturing')}
- {self.company_info.get('strength2', 'Competitive pricing')}
- {self.company_info.get('strength3', 'Reliable delivery')}
- {self.company_info.get('strength4', 'Professional technical support')}"""
        
        return intro
    
    def _build_cooperation_suggestion(self, industry, products, business_model):
        """构建合作建议"""
        if not self.company_info:
            return "I believe there could be great synergy between our companies."
        
        our_products = self.company_info.get('main_products', [])
        
        suggestion = f"""Given {self.company_info.get('company_name', 'our')}'s expertise in {', '.join(our_products[:3]) if our_products else 'relevant products'}, I believe we could provide significant value to {self.company_info.get('company_name', 'your company')} through:

- Supplying high-quality {our_products[0] if our_products else 'products'} that complement your current offerings
- Offering competitive OEM/ODM services to expand your product line
- Providing reliable supply chain support for your {industry} business
- Collaborating on custom solutions for your specific market needs"""
        
        return suggestion
    
    def _format_products_list(self):
        """格式化产品列表"""
        if not self.company_info:
            return "- High-quality products\n- OEM/ODM services"
        
        products = self.company_info.get('main_products', [])
        if products:
            return '\n'.join([f"- {p}" for p in products])
        return "- High-quality products\n- OEM/ODM services"

if __name__ == '__main__':
    # 测试
    analyzer = WebsiteAnalyzer()
    result = analyzer.analyze_website('https://www.halterhq.com/')
    print("网站分析结果:")
    print(result)
