#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开发信生成工作流程 v2.0
基于用户提供的8节点工作流程实现
节点1-4: 背调 -> 分类 -> 优势提炼 -> FABE转化
节点5-8: 素材匹配 -> 开发信生成 -> 精修 -> HTML渲染
"""

import json
import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from duckduckgo_search import DDGS
from services.llm_client import LLMEmailClient
from materials.unified_interface import (
    get_advantages_by_power_type, get_cases_by_track,
    get_brochure_by_power_type, get_storage_brochure, get_case_workflow_rules,
    get_ring_case_for_email, get_arlo_case_for_email, get_eufy_case_for_email
)


class CompanyResearcher:
    """节点1: 公司背调 - 基于官网完成精准调研"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def research(self, customer_name: str, website: str) -> Dict:
        """
        执行公司背调，输出4模块结构化信息
        """
        print(f"\n[节点1] 正在背调: {customer_name}")
        print(f"  访问网站: {website}")
        
        # 抓取网站内容
        website_data = self._fetch_website(website)
        
        # 搜索补充信息
        search_data = self._search_company(customer_name)
        
        # 整合分析输出4模块
        research_result = self._analyze_and_structure(
            customer_name, website_data, search_data
        )
        
        print(f"  ✓ 背调完成")
        return research_result
    
    def _fetch_website(self, url: str) -> Dict:
        """抓取网站内容"""
        if not url or not url.startswith('http'):
            return {'error': '无效URL'}
        
        try:
            import time
            time.sleep(1)
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            title = soup.title.string if soup.title else ''
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            description = meta_desc.get('content', '') if meta_desc else ''
            page_text = soup.get_text(separator=' ', strip=True)[:5000]
            
            # 提取产品关键词
            products = self._extract_products(page_text)
            
            # 检测行业
            industry = self._detect_industry(page_text)
            
            # 检测业务模式
            business_model = self._detect_business_model(page_text)
            
            # 检测服务地区
            regions = self._detect_regions(page_text)
            
            return {
                'title': title,
                'description': description,
                'page_text': page_text,
                'products': products,
                'industry': industry,
                'business_model': business_model,
                'regions': regions
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _search_company(self, customer_name: str) -> Dict:
        """搜索公司补充信息"""
        try:
            with DDGS() as ddgs:
                results = ddgs.text(f"{customer_name} solar panel products", max_results=5)
                news = [{'title': r['title'], 'body': r['body']} for r in results]
                return {'company_news': news}
        except:
            return {'company_news': []}
    
    def _extract_products(self, text: str) -> List[str]:
        """提取产品关键词"""
        solar_products = [
            'solar panel', 'solar module', 'photovoltaic', 'pv panel',
            'solar charger', 'solar battery', 'solar light', 'solar lamp',
            'solar camera', 'solar gate', 'solar fence', 'solar tracker',
            'flexible solar', 'portable solar', 'solar kit', 'solar system'
        ]
        found = []
        text_lower = text.lower()
        for product in solar_products:
            if product in text_lower:
                found.append(product)
        return list(set(found))[:5]
    
    def _detect_industry(self, text: str) -> str:
        """检测行业类型"""
        keywords = {
            'security': ['security', 'surveillance', 'camera', 'cctv', 'monitoring'],
            'outdoor': ['outdoor', 'camping', 'hunting', 'trail', 'wildlife'],
            'automation': ['gate opener', 'automation', 'automatic gate', 'smart home'],
            'agriculture': ['agriculture', 'farm', 'livestock', 'pasture', 'irrigation'],
            'energy_storage': ['energy storage', 'power station', 'battery', 'inverter'],
            'consumer_electronics': ['consumer', 'electronics', 'gadget', 'device'],
            'distributor': ['distributor', 'wholesale', 'dealer', 'reseller', 'importer']
        }
        scores = {k: sum(1 for w in v if w in text.lower()) for k, v in keywords.items()}
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return 'general'
    
    def _detect_business_model(self, text: str) -> str:
        """检测业务模式"""
        text_lower = text.lower()
        if any(w in text_lower for w in ['distributor', 'wholesale', 'dealer', 'reseller']):
            return 'distributor'
        elif any(w in text_lower for w in ['manufacturer', 'factory', 'oem', 'odm']):
            return 'manufacturer'
        elif any(w in text_lower for w in ['brand', 'original', 'designer']):
            return 'brand_owner'
        elif any(w in text_lower for w in ['installer', 'contractor', 'epc']):
            return 'installer'
        return 'unknown'
    
    def _detect_regions(self, text: str) -> List[str]:
        """检测服务地区"""
        regions = []
        region_keywords = {
            'USA': ['usa', 'united states', 'america', 'us market'],
            'Europe': ['europe', 'eu', 'germany', 'uk', 'france', 'italy'],
            'Australia': ['australia', 'au', 'oceania'],
            'Asia': ['asia', 'china', 'japan', 'korea', 'southeast asia'],
            'Middle East': ['middle east', 'saudi', 'uae', 'dubai']
        }
        text_lower = text.lower()
        for region, keywords in region_keywords.items():
            if any(kw in text_lower for kw in keywords):
                regions.append(region)
        return regions
    
    def _analyze_and_structure(self, customer_name: str, website_data: Dict, search_data: Dict) -> Dict:
        """分析并输出4模块结构化信息"""
        
        # 模块1: 客户基础画像
        profile = {
            'company_name': customer_name,
            'main_business': website_data.get('title', ''),
            'target_markets': website_data.get('regions', []),
            'business_model': website_data.get('business_model', 'unknown'),
            'core_products': website_data.get('products', []),
            'has_own_brand': 'brand' in str(website_data.get('page_text', '')).lower()
        }
        
        # 模块2: 太阳能相关产品线盘点
        solar_products = website_data.get('products', [])
        has_solar = len(solar_products) > 0
        
        product_analysis = {
            'has_solar_products': has_solar,
            'solar_products': solar_products,
            'power_range_estimate': self._estimate_power_range(website_data),
            'panel_type': self._estimate_panel_type(website_data),
            'procurement_mode': 'OEM Customization' if 'oem' in str(website_data.get('page_text', '')).lower() else 'Finished Product Procurement',
            'volume_estimate': 'unknown'
        }
        
        # 模块3: 业务痛点与切入机会
        pain_points = self._identify_pain_points(website_data)
        opportunities = self._identify_opportunities(website_data, pain_points)
        
        # 模块4: 初步分类标签
        power_tendency = self._classify_power_tendency(website_data)
        track = self._classify_track(website_data)
        
        return {
            'module1_profile': profile,
            'module2_products': product_analysis,
            'module3_pain_points': pain_points,
            'module4_tags': {
                'power_tendency': power_tendency,
                'track': track,
                'case_match': 'security' if track == 'Security & Smart Home Hardware' else 'none'
            }
        }
    
    def _estimate_power_range(self, website_data: Dict) -> str:
        """估算功率范围"""
        text = str(website_data.get('page_text', '')).lower()
        if any(w in text for w in ['300w', '400w', '500w', '600w', '700w', 'kw', 'kilowatt']):
            return 'high_power'
        elif any(w in text for w in ['1w', '5w', '10w', '20w', '50w', '100w', '200w']):
            return 'low_power'
        return 'unknown'
    
    def _estimate_panel_type(self, website_data: Dict) -> str:
        """估算面板类型"""
        text = str(website_data.get('page_text', '')).lower()
        if 'flexible' in text:
            return 'flexible'
        elif 'rigid' in text or 'glass' in text:
            return 'rigid'
        elif 'integrated' in text or 'bipv' in text:
            return 'integrated'
        return 'unknown'
    
    def _identify_pain_points(self, website_data: Dict) -> List[Dict]:
        """识别业务痛点"""
        pain_points = []
        text = str(website_data.get('page_text', '')).lower()
        industry = website_data.get('industry', '')
        
        # 根据行业识别痛点（全部英文）
        if industry == 'security':
            pain_points.extend([
                {'type': 'aesthetics', 'desc': 'Solar panel appearance does not match the overall design language of security devices'},
                {'type': 'battery_life', 'desc': 'Insufficient charging efficiency in low-light conditions, affecting continuous device power supply'},
                {'type': 'weatherability', 'desc': 'Long-term outdoor exposure causes panel degradation and performance loss'}
            ])
        elif industry == 'outdoor':
            pain_points.extend([
                {'type': 'portability', 'desc': 'Existing solar panels are too heavy and bulky for outdoor carry experience'},
                {'type': 'efficiency', 'desc': 'Charging efficiency drops significantly under cloudy skies or tree shade'},
                {'type': 'durability', 'desc': 'Panels are easily damaged in harsh outdoor environments'}
            ])
        elif industry == 'automation':
            pain_points.extend([
                {'type': 'compatibility', 'desc': 'Voltage and power mismatch between solar panels and automation equipment'},
                {'type': 'installation', 'desc': 'Complex installation increases labor and integration costs'},
                {'type': 'reliability', 'desc': 'High failure rate and maintenance costs during long-term outdoor operation'}
            ])
        else:
            pain_points.extend([
                {'type': 'supply_chain', 'desc': 'Unstable supplier lead times disrupt production schedules'},
                {'type': 'cost', 'desc': 'High procurement costs compress profit margins'},
                {'type': 'quality', 'desc': 'Inconsistent product quality leads to high after-sales issues'}
            ])
        
        return pain_points
    
    def _identify_opportunities(self, website_data: Dict, pain_points: List[Dict]) -> List[Dict]:
        """识别切入机会"""
        opportunities = []
        industry = website_data.get('industry', '')
        
        if industry == 'security':
            opportunities = [
                {'priority': 1, 'desc': 'Provide pure black BC cells that blend seamlessly with security device aesthetics'},
                {'priority': 2, 'desc': 'High-efficiency power generation in low-light conditions for 24/7 device operation'},
                {'priority': 3, 'desc': 'Proven track record with leading brands in the same product category'}
            ]
        elif industry == 'automation':
            opportunities = [
                {'priority': 1, 'desc': 'Custom dimensions and power output to perfectly match gate openers and similar devices'},
                {'priority': 2, 'desc': 'Simplified installation solutions that reduce customer integration costs'},
                {'priority': 3, 'desc': 'Global multi-country production ensuring stable supply'}
            ]
        else:
            opportunities = [
                {'priority': 1, 'desc': 'BC cell technology boosts generation efficiency by 15-20%'},
                {'priority': 2, 'desc': 'Full customization OEM/ODM services'},
                {'priority': 3, 'desc': 'Global supply chain guaranteeing reliable delivery'}
            ]
        
        return opportunities
    
    def _classify_power_tendency(self, website_data: Dict) -> str:
        """分类功率倾向"""
        text = str(website_data.get('page_text', '')).lower()
        has_high = any(w in text for w in ['300w', '400w', '500w', '600w', '700w'])
        has_low = any(w in text for w in ['1w', '5w', '10w', '20w', '50w', '100w', '200w'])
        
        if has_high and has_low:
            return 'mixed'
        elif has_high:
            return 'high_power'
        elif has_low:
            return 'low_power'
        return 'unknown'
    
    def _classify_track(self, website_data: Dict) -> str:
        """分类赛道属性"""
        industry = website_data.get('industry', '')
        track_map = {
            'security': 'Security & Smart Home Hardware',
            'outdoor': 'Outdoor & Portable Power',
            'automation': 'Security & Smart Home Hardware',
            'agriculture': 'Commercial & Industrial PV',
            'energy_storage': 'Residential Energy Storage',
            'consumer_electronics': 'Outdoor & Portable Power',
            'distributor': 'General'
        }
        return track_map.get(industry, 'General')


class CustomerClassifier:
    """节点2: 判断客户类型 - 标准化分类标签输出"""
    
    def classify(self, research_result: Dict) -> Dict:
        """
        基于背调结果输出标准化分类标签
        """
        print(f"\n[节点2] 判断客户类型")
        
        tags = research_result.get('module4_tags', {})
        power = tags.get('power_tendency', 'unknown')
        track = tags.get('track', 'General')
        
        # 功率类型判定
        if power == 'high_power':
            power_type = 'High Power'
        elif power == 'low_power':
            power_type = 'Low Power'
        elif power == 'mixed':
            power_type = 'High Power'
        else:
            if track in ['Security & Smart Home Hardware', 'Outdoor & Portable Power']:
                power_type = 'Low Power'
            else:
                power_type = 'High Power'
        
        # 案例匹配标签
        if track == 'Security & Smart Home Hardware':
            case_tag = 'Security / Smart Home'
        else:
            case_tag = 'No Matched Case'
        
        # 匹配优先级
        pain_points = research_result.get('module3_pain_points', [])
        priorities = [p['type'] for p in pain_points[:3]]
        
        classification = {
            'power_type': power_type,
            'track': track,
            'case_tag': case_tag,
            'priorities': priorities
        }
        
        print(f"  客户主类型: {power_type}")
        print(f"  核心赛道: {track}")
        print(f"  案例匹配: {case_tag}")
        print(f"  匹配优先级: {', '.join(priorities)}")
        print(f"  ✓ 分类完成")
        
        return classification


class AdvantageSelector:
    """节点3: 优势点提炼 - 从完整素材库筛选匹配优势"""

    def __init__(self, user_id: int = None, is_admin: bool = False):
        self.user_id = user_id
        self.is_admin = is_admin

    def select(self, classification: Dict, research_result: Dict) -> List[Dict]:
        """
        从素材库筛选与客户最匹配的优势点
        """
        print(f"\n[节点3] 优势点提炼（调用完整素材库）")

        power_type = classification['power_type']
        track = classification['track']
        pain_points = research_result.get('module3_pain_points', [])
        pain_types = [p['type'] for p in pain_points]

        # 从素材库获取对应功率类型的优势
        advantages = get_advantages_by_power_type(power_type, user_id=self.user_id, admin=self.is_admin)
        
        # 计算每个优势的匹配度
        scored = []
        for adv in advantages:
            score = 0
            # 痛点匹配
            for pain in pain_types:
                pain_lower = pain.lower()
                name_lower = adv['name'].lower()
                if any(kw in name_lower for kw in [pain_lower, pain]):
                    score += 2
            # 赛道匹配
            if 'all' in adv.get('scope', '') or track in adv.get('scope', ''):
                score += 1
            scored.append((score, adv))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [adv for score, adv in scored[:4]]
        
        for i, adv in enumerate(selected, 1):
            print(f"  优势{i}: {adv['name']}")
        print(f"  ✓ 优势提炼完成（素材库调用）")
        
        return selected


class FABETransformer:
    """节点4: FABE法则实践 - 将优势转化为客户利益话术（基于素材库）"""

    def __init__(self, user_id: int = None, is_admin: bool = False):
        self.user_id = user_id
        self.is_admin = is_admin
    
    def transform(self, advantages: List[Dict], classification: Dict, research_result: Dict) -> List[Dict]:
        """
        将优势点转化为FABE话术
        """
        print(f"\n[节点4] FABE法则转化（基于素材库）")
        
        fabe_points = []
        track = classification['track']
        
        for adv in advantages:
            # 提取F（特征）- 直接从素材库获取
            feature = adv.get('tech_features', adv.get('feature', ''))
            
            # 推导A（优势）
            advantage = self._derive_advantage(adv)
            
            # 翻译为B（利益）- 结合客户赛道
            benefit = self._translate_benefit(adv, track, research_result)
            
            # 匹配E（证据）- 从素材库案例获取
            evidence = self._match_evidence(adv, classification, research_result)
            
            fabe_points.append({
                'advantage_name': adv['name'],
                'F': feature,
                'A': advantage,
                'B': benefit,
                'E': evidence
            })
        
        for i, point in enumerate(fabe_points, 1):
            print(f"  FABE{i}: {point['advantage_name']}")
        print(f"  ✓ FABE转化完成（素材库调用）")
        
        return fabe_points
    
    def _derive_advantage(self, adv: Dict) -> str:
        """从特征推导优势"""
        name = adv['name']
        if 'BC' in name or '纯黑' in name:
            return 'Unobstructed surface absorbs more sunlight, superior low-light performance, premium pure-black appearance'
        elif '定制' in name or 'custom' in name.lower():
            return 'Industry-leading quality control backed by top-tier partnerships, highly matched mold and production solutions'
        elif '全球' in name or 'global' in name.lower():
            return 'Flexible multi-country production allocation, mitigating geopolitical trade risks'
        elif 'DDP' in name:
            return 'Door-to-door delivery, customer handles zero customs complexity'
        elif '弱光' in name or 'low light' in name.lower():
            return 'Maintains high conversion efficiency even in suboptimal lighting conditions'
        else:
            return 'Industry-leading technology and quality standards'
    
    def _translate_benefit(self, adv: Dict, track: str, research_result: Dict) -> str:
        """将优势翻译为客户利益"""
        name = adv['name']
        pain_points = research_result.get('module3_pain_points', [])
        
        if track == 'Security & Smart Home Hardware':
            if 'BC' in name or '纯黑' in name:
                return 'Solar panels blend seamlessly with security devices, elevating overall product aesthetics and end-user willingness to pay'
            elif '弱光' in name or 'low light' in name.lower() or 'efficiency' in name.lower():
                return 'Maintains efficient charging on rainy days and at night, extending device runtime by 30-50% and reducing customer complaints'
            elif '定制' in name or 'custom' in name.lower():
                return 'Integrate solar solutions without modifying device structure, shortening time-to-market by 2-3 months'
        elif track == 'Outdoor & Portable Power':
            if 'BC' in name or '纯黑' in name:
                return 'Lighter and thinner solar panels reduce backpack/camping gear weight by 20%, enhancing user experience'
            elif '弱光' in name or 'low light' in name.lower():
                return 'Charges quickly even under tree shade and cloudy skies, eliminating weather constraints on outdoor power'
        elif track == 'automation' or 'automation' in track.lower():
            if '定制' in name or 'custom' in name.lower():
                return 'Custom sizes and power outputs perfectly match gate openers and automation equipment, reducing integration costs'
            elif 'BC' in name or '纯黑' in name:
                return 'Sleek pure-black panels complement modern gate designs, enhancing curb appeal for end customers'
        
        # 通用利益
        if '全球' in name or 'global' in name.lower():
            return 'Supply chain resilience ensures uninterrupted delivery regardless of regional disruptions'
        elif 'DDP' in name:
            return 'Zero customs hassle, goods delivered straight to your warehouse, saving 20%+ on logistics management costs'
        elif '认证' in name or 'cert' in name.lower():
            return 'Full global certifications eliminate compliance barriers, accelerating market entry in any region'
        else:
            return 'Enhanced product competitiveness drives higher customer satisfaction and repeat purchase rates'
    
    def _match_evidence(self, adv: Dict, classification: Dict, research_result: Dict) -> str:
        """从素材库匹配证据"""
        name = adv['name'].lower()
        track = classification['track']

        # 根据赛道匹配案例
        if 'security' in track.lower() or 'smart home' in track.lower():
            if 'bc' in name or 'cell' in name or '纯黑' in name:
                # 安防赛道 + BC技术 -> 使用Ring/Arlo案例
                ring_case = get_ring_case_for_email('smart_home', user_id=self.user_id, admin=self.is_admin)
                return ring_case[:200] + '...' if ring_case else ''
            elif 'oem' in name or 'odm' in name or 'custom' in name:
                ring_case = get_ring_case_for_email('smart_home', user_id=self.user_id, admin=self.is_admin)
                return ring_case[:200] + '...' if ring_case else ''
            elif 'ddp' in name or 'logistics' in name:
                arlo_case = get_arlo_case_for_email('north_america_buyer', user_id=self.user_id, admin=self.is_admin)
                return arlo_case[:200] + '...' if arlo_case else ''
            elif 'global' in name or 'production' in name or 'supply' in name:
                return ''

        # 通用证据
        if 'bc' in name or 'cell' in name:
            return ''
        elif 'oem' in name or 'custom' in name:
            return ''
        elif 'ddp' in name:
            return ''
        elif 'cert' in name or 'solution' in name:
            return ''

        return ''


class MaterialMatcher:
    """节点5: 素材库智能匹配 - 按规则调用完整素材库"""
    
    def match(self, classification: Dict, research_result: Dict,
              selected_material_ids: list = None, user_id: int = None,
              admin: bool = False) -> Dict:
        """
        按规则匹配素材，支持用户手动选择素材注入
        """
        print(f"\n[节点5] 素材库智能匹配（调用完整素材库）")

        power_type = classification['power_type']
        track = classification['track']
        regions = research_result.get('module1_profile', {}).get('target_markets', [])

        matched = {
            'company_intro': {},
            'advantages': get_advantages_by_power_type(power_type, user_id=user_id, admin=admin),
            'brochure': get_brochure_by_power_type(power_type, user_id=user_id, admin=admin),
            'cases': get_cases_by_track(track, user_id=user_id, admin=admin),
            'rules': get_case_workflow_rules(track, regions[0] if regions else '', user_id=user_id, admin=admin),
            'custom_selected': [],
        }
        
        # 大功率客户额外获取储能素材
        if '大功率' in power_type:
            matched['storage'] = get_storage_brochure(user_id=user_id, admin=admin)
        
        # 用户手动选择的素材（最高优先级）
        if selected_material_ids:
            from database.material_models import get_material_by_id
            for mid in selected_material_ids:
                try:
                    m = get_material_by_id(mid, user_id=user_id)
                    if m and m.get('content_json'):
                        matched['custom_selected'].append(m['content_json'])
                except Exception as e:
                    print(f"  ⚠ 加载选中素材 {mid} 失败: {e}")
            if matched['custom_selected']:
                print(f"  用户选中素材: {len(matched['custom_selected'])} 项")
        
        # 获取案例调用规则
        rules = matched['rules']
        
        print(f"  公司简介: 已加载")
        print(f"  优势素材: {len(matched['advantages'])} 项")
        print(f"  宣传册素材: {len(matched['brochure'])} 项")
        print(f"  案例素材: {len(matched['cases'])} 项")
        if 'storage' in matched:
            print(f"  储能素材: {len(matched['storage'])} 项")
        if rules.get('case_priority'):
            print(f"  案例优先级: {rules['case_priority']}")
        if rules.get('delivery'):
            print(f"  推荐交付方式: {rules['delivery']}")
        print(f"  ✓ 素材匹配完成（完整素材库调用）")
        
        return matched


class EmailComposer:
    """节点6: 开发信生成 - 整合信息生成高精准度英文开发信"""
    
    def __init__(self, user_id: int = None, sender_material_id: int = None):
        """初始化邮件撰写器，支持 per-user 发信人信息和指定发信人模板"""
        if sender_material_id:
            from materials.sender_info_service import get_sender_info_by_id
            sender = get_sender_info_by_id(sender_material_id, user_id=user_id)
            if sender:
                self.sender_info = sender
            else:
                from materials.sender_info_service import get_sender_info
                self.sender_info = get_sender_info(user_id=user_id)
        else:
            from materials.sender_info_service import get_sender_info
            self.sender_info = get_sender_info(user_id=user_id)

    def _load_sender_info(self) -> Dict:
        """加载发件人信息（兼容旧版）"""
        from materials.sender_info_service import get_sender_info
        return get_sender_info(user_id=self.user_id)
    
    def compose(self, research_result: Dict, classification: Dict,
                fabe_points: List[Dict], materials: Dict,
                contact_name: str = None, email_type: str = 'public',
                has_website: bool = True, target_word_count=None) -> Dict:
        """
        生成完整开发信

        Args:
            contact_name: 联系人姓名（如果有）
            email_type: 'personal'（个人邮箱，有名字）或 'public'（公共邮箱，无名字）
            has_website: 客户是否有网站信息，影响开篇措辞
            target_word_count: 目标字数范围 {'min': int, 'max': int}
        """
        if target_word_count is None:
            target_word_count = {'min': 150, 'max': 250}
        max_words = target_word_count.get('max', 250)

        print(f"\n[节点6] 开发信生成")

        profile = research_result.get('module1_profile', {})
        customer_name = profile.get('company_name', 'Valued Partner')

        # 生成主题
        subject = self._generate_subject(classification, fabe_points)

        # 生成称呼（根据是否有名字）
        greeting = self._generate_greeting(contact_name, customer_name, email_type)

        # 生成正文
        body = self._generate_body(research_result, classification, fabe_points, materials, has_website)

        # 根据目标字数调整正文长度
        body_words = len(body.split())
        if body_words > max_words:
            body = self._compress_body(body, max_words)
            print(f"  正文已压缩: {body_words} → {len(body.split())} 词")

        # 生成签名
        signature = self._generate_signature()

        email = {
            'subject': subject,
            'greeting': greeting,
            'body': body,
            'signature': signature,
            'full_text': f"{greeting}\n\n{body}\n\n{signature}"
        }

        print(f"  主题: {subject}")
        print(f"  称呼: {greeting}")
        print(f"  字数: {len(body.split())} 词")
        print(f"  ✓ 开发信生成完成")

        return email

    def _compress_body(self, body: str, max_words: int) -> str:
        """压缩正文到目标词数，保留开头和结尾"""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', body)
        if len(sentences) <= 2:
            return body

        head = sentences[0]
        tail = ' '.join(sentences[-2:])
        mid_budget = max(0, max_words - len(head.split()) - len(tail.split()))

        mid_result = []
        mid_words = 0
        for s in sentences[1:-2]:
            w = len(s.split())
            if mid_words + w <= mid_budget:
                mid_result.append(s)
                mid_words += w
            else:
                break

        parts = [head] + mid_result + sentences[-2:]
        return ' '.join(parts)
    
    def _generate_subject(self, classification: Dict, fabe_points: List[Dict]) -> str:
        """生成邮件主题"""
        track = classification['track']
        
        if track == 'Security & Smart Home Hardware':
            subjects = [
                "Solar Solutions for Your Security Devices",
                "Custom Solar Panels for Security Hardware",
                "Reliable Solar Power for Smart Home Products"
            ]
        elif track == 'Outdoor & Portable Power':
            subjects = [
                "Lighter Solar Panels for Outdoor Gear",
                "High-Efficiency Solar Solutions for Portable Power",
                "Custom Solar Solutions for Outdoor Brands"
            ]
        else:
            subjects = [
                "Solar Partnership Opportunity",
                "Custom PV Solutions for Your Product Line",
                "Reliable Solar Solutions for Your Products"
            ]
        
        import random
        return random.choice(subjects)
    
    def _generate_greeting(self, contact_name: str = None, customer_name: str = 'Team', email_type: str = 'public') -> str:
        """
        生成称呼（严格规则）
        1. 公共邮箱 / 无具体联系人: Hi [对方公司名称] Team,
        2. 有具体联系人姓名: Hi [First Name],
        统一使用 Hi，不使用 Dear。
        """
        import re
        
        # 清理并验证 contact_name
        invalid_names = {'n/a', 'na', '-', '', 'team', 'unknown', 'none'}
        has_valid_name = (
            contact_name and 
            contact_name.strip() and 
            contact_name.strip().lower() not in invalid_names
        )
        
        # 只有个人邮箱且有有效名字时才使用名字称呼
        if email_type == 'personal' and has_valid_name:
            # 有具体联系人 - 只取 First Name
            first_name = contact_name.strip().split()[0].strip().title()
            return f"Hi {first_name},"
        else:
            # 公共邮箱或无有效名字 - 使用公司名 + Team
            clean_name = customer_name
            suffix_patterns = [
                r'\s+INC\.?$', r'\s+LLC\.?$', r'\s+LTD\.?$', r'\s+PTY\.?$',
                r'\s+GMBH\.?$', r'\s+SA\.?$', r'\s+CORP\.?$', r'\s+CORPORATION\.?$',
                r'\s+LIMITED\.?$', r'\s+CO\.?$'
            ]
            for pattern in suffix_patterns:
                clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)
            clean_name = clean_name.strip()
            clean_name = clean_name.title() if clean_name else 'Valued'
            return f"Hi {clean_name} Team,"
    
    def _generate_body(self, research_result: Dict, classification: Dict,
                       fabe_points: List[Dict], materials: Dict,
                       has_website: bool = True) -> str:
        """生成邮件正文"""
        profile = research_result.get('module1_profile', {})
        products = profile.get('core_products', [])
        product_mention = products[0] if products else 'your products'

        # 第一段：破冰
        opening = self._generate_opening(profile, research_result, has_website)

        # 第二段：核心价值点（FABE）
        value_section = self._generate_value_section(fabe_points)

        # 第三段：案例背书 / 痛点解决方案
        case_section = self._generate_case_section(classification, materials, research_result)

        # 第四段：CTA
        cta = self._generate_cta(classification)

        body = f"{opening}\n\n{value_section}\n\n{case_section}\n\n{cta}"

        return body
    
    def _generate_opening(self, profile: Dict, research_result: Dict, has_website: bool = True) -> str:
        """生成开篇破冰（直接切入，禁止 How are you 等空泛客套）"""
        company_name = profile.get('company_name', '')
        products = profile.get('core_products', [])
        industry = research_result.get('module4_tags', {}).get('track', '')
        
        if 'security' in industry.lower() or 'smart home' in industry.lower() or 'security' in str(products).lower():
            return f"I came across {company_name} while researching solar-powered security solutions. Your approach to integrating renewable energy into surveillance hardware caught my attention."
        elif 'outdoor' in str(products).lower() or 'portable' in str(products).lower():
            return f"I noticed {company_name} focuses on outdoor and portable power products. With the growing demand for off-grid energy solutions, I thought there might be a fit here."
        else:
            if has_website:
                return f"I visited {company_name}'s website and was impressed by your product lineup — particularly your focus on {products[0] if products else 'your core products'}. I believe our solar solutions could add real value to what you're building."
            else:
                return f"I came across {company_name} and was impressed by your product lineup. I believe our solar solutions could add real value to what you're building."
    
    def _generate_value_section(self, fabe_points: List[Dict]) -> str:
        """生成价值点部分"""
        lines = ["Here's what we bring to the table:"]
        
        for point in fabe_points[:3]:
            # 使用FABE句式
            f = point['F']
            b = point['B']
            line = f"• {b}"
            lines.append(line)
        
        return '\n'.join(lines)
    
    def _generate_case_section(self, classification: Dict, materials: Dict, research_result: Dict) -> str:
        """
        生成案例/解决方案部分
        有案例匹配时直接使用案例
        无案例匹配时分析痛点并提供定制化解决方案
        """
        track = classification['track']
        cases = materials.get('cases', [])
        pain_points = research_result.get('module3_pain_points', [])
        
        # 有案例匹配时：直接使用案例素材
        if cases and ('security' in track.lower() or 'smart home' in track.lower()):
            case_names = [c.get('name', str(c)) for c in cases]
            case_text = ', '.join(str(n) for n in case_names[:3]) if case_names else ''
            
            rules = materials.get('rules', {})
            tech_priority = rules.get('tech_priority', [])
            
            if cases and len(cases) > 0:
                # 直接使用用户导入的案例内容
                case_content = cases[0].get('content', cases[0]) if isinstance(cases[0], dict) else str(cases[0])
                if isinstance(case_content, dict):
                    case_text = case_content.get('email_copy', '') or case_content.get('summary', '') or str(case_content)[:500]
                elif isinstance(case_content, str):
                    case_text = case_content[:500]
                else:
                    case_text = str(case_content)[:500]
                return case_text
            else:
                return ''
        
        # 无案例匹配时：分析痛点 + 提供定制化解决方案
        elif pain_points:
            # 提取前3个痛点
            top_pains = pain_points[:3]
            pain_descriptions = [p['desc'] for p in top_pains]
            
            # 根据痛点类型生成对应的解决方案
            solutions = self._generate_solutions_from_pains(top_pains, classification)
            
            # 构建痛点+解决方案段落
            pain_text = "Based on our analysis of your product category, we understand common challenges include: "
            pain_text += "; ".join(pain_descriptions[:2]) + "."
            
            solution_text = "Here's how we can help: "
            solution_lines = []
            for sol in solutions[:3]:
                solution_lines.append(f"• {sol}")
            
            return pain_text + "\n\n" + solution_text + "\n" + "\n".join(solution_lines)
        
        # 无痛点也无案例时的兜底方案
        else:
            return (
                "We specialize in custom solar solutions tailored to your specific product requirements. "
                "Whether you need custom dimensions, specific power outputs, unique connectors, or aesthetic matching, "
                "our R&D team can turn your requirements into production-ready solutions."
            )
    
    def _generate_solutions_from_pains(self, pain_points: List[Dict], classification: Dict) -> List[str]:
        """根据痛点生成对应的解决方案"""
        solutions = []
        power_type = classification['power_type']
        
        for pain in pain_points:
            pain_type = pain.get('type', '')
            pain_desc = pain.get('desc', '')
            
            if pain_type == 'supply_chain' or 'supply' in pain_desc.lower():
                solutions.append(
                    "Supply chain resilience through our multi-country production network "
                    "ensures uninterrupted delivery regardless of regional disruptions."
                )
            elif pain_type == 'cost' or 'cost' in pain_desc.lower():
                solutions.append(
                    "Our DDP (Delivered Duty Paid) service provides transparent, all-inclusive pricing "
                    "with no hidden customs or logistics fees, giving you full cost control from day one."
                )
            elif pain_type == 'quality' or 'quality' in pain_desc.lower():
                solutions.append(
                    "Our products meet international quality standards with comprehensive certifications, "
                    "ensuring every panel meets the highest global standards."
                )
            elif pain_type == 'compatibility' or 'compatibility' in pain_desc.lower():
                solutions.append(
                    "Full OEM/ODM customization: we tailor voltage, dimensions, connectors, and mounting "
                    "to integrate seamlessly with your existing product design—no structural modifications needed."
                )
            elif pain_type == 'aesthetics' or 'aesthetics' in pain_desc.lower():
                solutions.append(
                    "Our premium cell technology delivers a clean, premium appearance "
                    "that blends perfectly with high-end product designs."
                )
            elif pain_type == 'efficiency' or 'efficiency' in pain_desc.lower():
                solutions.append(
                    "Advanced cell technology achieves higher conversion efficiency than conventional panels, "
                    "with superior low-light performance."
                )
            elif pain_type == 'battery_life' or 'battery' in pain_desc.lower():
                solutions.append(
                    "Optimized cell technology and power management extend device runtime by 30-50%, "
                    "reducing end-user charging frequency and support tickets."
                )
            elif pain_type in ['weatherability', 'durability'] or 'durability' in pain_desc.lower():
                solutions.append(
                    "Tempered glass protective layers (not fragile ETFE) withstand extreme temperatures, "
                    "sandstorms, and physical impact—proven in harsh outdoor environments worldwide."
                )
            elif pain_type == 'installation' or 'installation' in pain_desc.lower():
                solutions.append(
                    "Plug-and-play integration with custom mounting brackets and connectors. "
                    "We design for your assembly line, not the other way around."
                )
            elif pain_type == 'reliability' or 'reliability' in pain_desc.lower():
                solutions.append(
                    "Rigorous quality control with comprehensive certifications. "
                    "Proven track record of reliable on-time delivery and high customer satisfaction."
                )
            elif pain_type == 'portability' or 'portability' in pain_desc.lower():
                solutions.append(
                    "Lightweight flexible and folding panel options reduce weight by 20-40% "
                    "without sacrificing power output—ideal for on-the-go applications."
                )
            else:
                # 通用解决方案
                solutions.append(
                    "Our experienced R&D team specializes in solving unique integration challenges. "
                    "From concept to production sample, with full technical support throughout."
                )
        
        return solutions
    
    def _generate_cta(self, classification: Dict) -> str:
        """生成行动号召"""
        ctas = [
            "Worth a brief conversation? I can share a tailored spec sheet for your product category.",
            "Would you be open to a 10-minute call next week to explore how this could work for your lineup?",
            "Happy to send over some sample specs and pricing - no commitment needed."
        ]
        import random
        return random.choice(ctas)
    
    def _generate_signature(self) -> str:
        """生成签名（固定格式，分行左对齐，不添加多余符号）"""
        name = self.sender_info.get('sender_name', '')
        title = self.sender_info.get('job_title', '')
        company = self.sender_info.get('company_name', '')

        signature_lines = ["Best regards,"]
        if name:
            signature_lines.append(name)
        if title:
            signature_lines.append(title)
        if company:
            signature_lines.append(company)
        return "\n".join(signature_lines)


class EmailRefiner:
    """节点7: 邮件内容精修 - 优化表达、精简篇幅"""
    
    def refine(self, email: Dict, target_word_count=None) -> Dict:
        """
        精修邮件内容
        """
        if target_word_count is None:
            target_word_count = {'min': 150, 'max': 250}
        max_words = target_word_count.get('max', 250)
        
        print(f"\n[节点7] 邮件内容精修")
        
        original_body = email['body']
        
        # 精简冗余
        refined_body = self._trim_redundancy(original_body)
        
        # 优化语气
        refined_body = self._optimize_tone(refined_body)
        
        # 检查词数（上限）
        word_count = len(refined_body.split())
        if word_count > max_words:
            refined_body = self._compress_to_target(refined_body, max_words)
        
        email['body'] = refined_body
        email['full_text'] = f"{email['greeting']}\n\n{refined_body}\n\n{email['signature']}"
        email['word_count'] = len(refined_body.split())
        
        print(f"  原文字数: {len(original_body.split())} 词")
        print(f"  优化后: {email['word_count']} 词")
        print(f"  ✓ 精修完成")
        
        return email
    
    def _trim_redundancy(self, text: str) -> str:
        """删除冗余内容"""
        # 删除重复的空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 删除客套话
        filler_phrases = [
            r'I would like to',
            r'It is my pleasure to',
            r'We are honored to',
            r'Please allow me to',
        ]
        for phrase in filler_phrases:
            text = re.sub(phrase, '', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    def _optimize_tone(self, text: str) -> str:
        """优化语气为美式商务风格"""
        replacements = {
            'would be able to': 'can',
            'in the event that': 'if',
            'at this point in time': 'now',
            'due to the fact that': 'because',
            'in order to': 'to',
            'we are writing to': '',
            'we would like to introduce': 'here is',
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
            text = text.replace(old.capitalize(), new.capitalize() if new else '')
        
        return text
    
    def _compress_to_target(self, text: str, target: int) -> str:
        """压缩到目标词数，保留开头和结尾（CTA）"""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= 2:
            return text

        words_list = text.split()
        total_words = len(words_list)

        if total_words <= target:
            return text

        # 保留第一句（开头）和最后两句（CTA/结尾）
        head = sentences[0]
        tail_sentences = sentences[-2:]
        tail = ' '.join(tail_sentences)
        tail_words = len(tail.split())

        # 中间部分允许的词数
        mid_budget = max(0, target - len(head.split()) - tail_words)

        # 从中间句子中选取
        mid_sentences = sentences[1:-2]
        mid_result = []
        mid_words = 0
        for s in mid_sentences:
            w = len(s.split())
            if mid_words + w <= mid_budget:
                mid_result.append(s)
                mid_words += w
            else:
                break

        parts = [head] + mid_result + tail_sentences
        return ' '.join(parts)


class HTMLRenderer:
    """节点8: HTML格式渲染输出"""
    
    def render(self, email: Dict) -> str:
        """
        将邮件渲染为HTML格式
        """
        print(f"\n[节点8] HTML格式渲染")
        
        subject = email['subject']
        greeting = email['greeting']
        body = email['body']
        signature = email['signature']
        
        # 将正文转换为HTML
        body_html = self._body_to_html(body)
        signature_html = self._signature_to_html(signature)
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <p style="margin: 0 0 16px 0;">{greeting}</p>
    
    {body_html}
    
    <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e0e0e0;">
        {signature_html}
    </div>
</body>
</html>"""
        
        print(f"  ✓ HTML渲染完成")
        
        return html
    
    def _body_to_html(self, body: str) -> str:
        """将正文转为HTML"""
        lines = body.split('\n')
        html_parts = []
        
        in_list = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('•'):
                if not in_list:
                    html_parts.append('<ul style="margin: 8px 0; padding-left: 20px;">')
                    in_list = True
                html_parts.append(f'<li style="margin-bottom: 6px;">{line[1:].strip()}</li>')
            else:
                if in_list:
                    html_parts.append('</ul>')
                    in_list = False
                html_parts.append(f'<p style="margin: 0 0 12px 0;">{line}</p>')
        
        if in_list:
            html_parts.append('</ul>')
        
        return '\n'.join(html_parts)
    
    def _signature_to_html(self, signature: str) -> str:
        """将签名转为HTML"""
        lines = signature.split('\n')
        html_lines = []
        
        for i, line in enumerate(lines):
            if i == 0 and line.lower() in ['best,', 'regards,', 'sincerely,']:
                html_lines.append(f'<p style="margin: 0 0 4px 0; color: #666;">{line}</p>')
            elif i == 1:  # 姓名
                html_lines.append(f'<p style="margin: 0; font-weight: bold;">{line}</p>')
            else:
                html_lines.append(f'<p style="margin: 0; color: #666; font-size: 13px;">{line}</p>')
        
        return '\n'.join(html_lines)


class EmailWorkflow:
    """
    开发信生成工作流主控制器
    整合8个节点，提供一键生成开发信的功能
    """
    
    def __init__(self, user_id: int = None, sender_material_id: int = None, is_admin: bool = False):
        self.user_id = user_id
        self.sender_material_id = sender_material_id
        self.is_admin = is_admin
        self.researcher = CompanyResearcher()
        self.classifier = CustomerClassifier()
        self.advantage_selector = AdvantageSelector(user_id=user_id, is_admin=is_admin)
        self.fabe_transformer = FABETransformer(user_id=user_id, is_admin=is_admin)
        self.material_matcher = MaterialMatcher()
        self.composer = EmailComposer(user_id=user_id, sender_material_id=sender_material_id)
        self.refiner = EmailRefiner()
        self.renderer = HTMLRenderer()
        self.llm = LLMEmailClient()
    
    def _should_use_llm(self):
        """判断是否使用 LLM 模式生成邮件"""
        if not self.llm.is_available():
            return False
        # 读取调度配置中的 generation 设置
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'scheduler_config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config.get('generation', 'template') == 'ai'
        return False

    def _strip_greeting_and_signature(self, body: str, greeting: str, signature: str) -> str:
        """
        从 LLM 生成的 body 中剥离 greeting 和 signature，只保留纯正文。
        LLM 的 compose_email 和 refine_email 都会在输出中包含 greeting 和 signature，
        但我们的架构要求 body 字段只包含纯正文，greeting 和 signature 由编排层单独管理。
        """
        lines = body.split('\n')
        stripped_lines = []
        skip_mode = 'none'  # 'none' | 'greeting' | 'signature'

        # 签名关键词检测
        sig_keywords = ['Best regards', 'best regards', 'Regards,', 'regards,',
                        'Sincerely', 'sincerely']

        for line in lines:
            stripped = line.strip()

            # 检测 greeting 行（以 "Hi " 开头且匹配 greeting 内容）
            if skip_mode == 'none' and stripped.startswith('Hi ') and (
                greeting.split()[-1].rstrip(',') in stripped or
                stripped.rstrip(',').endswith('Team')
            ):
                skip_mode = 'greeting'
                continue

            # 检测签名开始（包含签名关键词）
            if skip_mode in ('none', 'greeting') and any(kw in stripped for kw in sig_keywords):
                # 如果这行就是 greeting 本身（如 "Hi XXX Team,"），跳过
                if stripped.startswith('Hi '):
                    continue
                skip_mode = 'signature'
                continue

            # 签名后的所有行都跳过
            if skip_mode == 'signature':
                continue

            stripped_lines.append(line)

        result = '\n'.join(stripped_lines).strip()
        # 清理开头和结尾的多余空行
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result

    def _generate_with_llm(self, customer_name, website, progress_callback=None, target_word_count=None):
        """使用 DeepSeek V4 Pro 生成邮件（LLM 增强模式）

        Args:
            customer_name: 客户公司名称
            website: 客户官网URL
            progress_callback: 进度回调函数，接收(step_id, status)参数
            target_word_count: 目标字数范围 {'min': int, 'max': int}
        """
        has_website = bool(website and website.strip() and website.strip().startswith('http'))

        def _notify(step_id, status='running'):
            if progress_callback:
                try:
                    progress_callback(step_id, status)
                except Exception:
                    pass

        print(f"\n[LLM模式] DeepSeek V4 Pro 邮件生成工作流")
        print(f"目标客户: {customer_name}")
        print(f"网站: {website if has_website else '(无)'}")

        # ===== 节点1: 公司背调（LLM 增强）=====
        print(f"\n[节点1] 公司背调 (LLM)")
        _notify('research', 'running')
        page_text = ''
        search_summary = ''

        if has_website:
            try:
                page_data = self.researcher._fetch_website(website)
                page_text = page_data.get('page_text', '') if page_data else ''
                print(f"  网页抓取成功: {len(page_text)} 字符")
            except Exception as e:
                print(f"  网页抓取失败: {e}")

            try:
                search_results = self.researcher._search_company(customer_name)
                search_summary = '\n'.join([r.get('title', '') + ': ' + r.get('body', '') for r in search_results[:5]]) if search_results else ''
                print(f"  搜索结果: {len(search_summary)} 字符")
            except Exception as e:
                print(f"  搜索失败: {e}")

        # 调用 LLM 分析
        llm_analysis = self.llm.analyze_company(page_text, search_summary, customer_name)
        if llm_analysis:
            print(f"  ✓ LLM 分析成功")
            # 将 LLM 分析结果转换为管线兼容格式
            research_result = {
                'module1_profile': {
                    'company_name': customer_name,
                    'main_business': llm_analysis.get('main_business', ''),
                    'target_markets': llm_analysis.get('target_markets', []),
                    'business_model': llm_analysis.get('business_model', 'unknown'),
                    'core_products': llm_analysis.get('core_products', []),
                    'has_own_brand': llm_analysis.get('business_model') in ('brand_owner', 'manufacturer')
                },
                'module2_products': {
                    'has_solar_products': llm_analysis.get('has_solar_products', False),
                    'solar_products': llm_analysis.get('solar_products', []),
                    'power_range_estimate': llm_analysis.get('power_tendency', 'unknown'),
                    'panel_type': 'unknown',
                    'procurement_mode': 'unknown',
                    'volume_estimate': 'unknown'
                },
                'module3_pain_points': llm_analysis.get('pain_points', []),
                'module4_tags': {
                    'power_tendency': llm_analysis.get('power_tendency', 'unknown'),
                    'track': llm_analysis.get('track', 'General'),
                    'case_match': 'security' if 'security' in llm_analysis.get('track', '').lower() else 'none'
                }
            }
        else:
            print(f"  ⚠ LLM 分析失败，回退到规则引擎")
            if has_website:
                research_result = self.researcher.research(customer_name, website)
            else:
                research_result = {
                    'module1_profile': {'company_name': customer_name, 'main_business': '', 'target_markets': [], 'business_model': 'unknown', 'core_products': [], 'has_own_brand': False},
                    'module2_products': {'has_solar_products': False, 'solar_products': [], 'power_range_estimate': 'unknown', 'panel_type': 'unknown', 'procurement_mode': 'unknown', 'volume_estimate': 'unknown'},
                    'module3_pain_points': [],
                    'module4_tags': {'power_tendency': 'unknown', 'track': 'General', 'case_match': 'none'}
                }
        _notify('research', 'completed')

        # ===== 节点2: 客户分类（LLM）=====
        print(f"\n[节点2] 客户分类 (LLM)")
        _notify('classify', 'running')
        classification = self.llm.classify_customer(research_result)
        if classification:
            print(f"  ✓ LLM 分类成功: {classification}")
        else:
            print(f"  ⚠ LLM 分类失败，回退到规则引擎")
            classification = self.classifier.classify(research_result)
        _notify('classify', 'completed')

        # ===== 节点3: 优势提炼（LLM）=====
        print(f"\n[节点3] 优势提炼 (LLM)")
        _notify('advantage', 'running')
        # 构建素材库文本摘要
        from materials.unified_interface import get_advantages_by_power_type
        power_type = classification.get('power_type', 'High Power')
        raw_advantages = get_advantages_by_power_type(power_type, user_id=self.user_id, admin=self.is_admin)
        material_summary = '\n'.join([
            f"- {a.get('name', '')}: {a.get('tech_features', '')} (Scope: {a.get('scope', '')})"
            for a in raw_advantages
        ])
        advantages = self.llm.select_advantages(classification, research_result, material_summary)
        if advantages:
            print(f"  ✓ LLM 优势提炼成功: {len(advantages)} 个")
        else:
            print(f"  ⚠ LLM 优势提炼失败，回退到规则引擎")
            advantages = self.advantage_selector.select(classification, research_result)
        _notify('advantage', 'completed')

        # ===== 节点4: FABE 话术（LLM）=====
        print(f"\n[节点4] FABE 话术 (LLM)")
        _notify('fabe', 'running')
        fabe_points = self.llm.generate_fabe(advantages, classification, research_result)
        if fabe_points:
            print(f"  ✓ LLM FABE 生成成功: {len(fabe_points)} 个")
        else:
            print(f"  ⚠ LLM FABE 失败，回退到规则引擎")
            fabe_points = self.fabe_transformer.transform(advantages, classification, research_result)
        _notify('fabe', 'completed')

        # ===== 节点5: 素材匹配（LLM）=====
        print(f"\n[节点5] 素材匹配 (LLM)")
        _notify('material', 'running')
        company_info = {}
        company_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'company_info.json')
        if os.path.exists(company_path):
            with open(company_path, 'r', encoding='utf-8') as f:
                company_info = json.load(f)
        materials = self.llm.match_materials(classification, research_result, company_info)
        if materials:
            print(f"  ✓ LLM 素材匹配成功")
        else:
            print(f"  ⚠ LLM 素材匹配失败，回退到规则引擎")
            materials = self.material_matcher.match(
                classification, research_result,
                selected_material_ids=selected_material_ids,
                user_id=self.user_id, admin=self.is_admin
            )
        _notify('material', 'completed')

        # ===== 节点6: 邮件生成（LLM）=====
        print(f"\n[节点6] 邮件生成 (LLM)")
        _notify('compose', 'running')
        llm_email = self.llm.compose_email(
            research_result, classification, fabe_points, materials,
            has_website=has_website, company_info=company_info,
            target_word_count=target_word_count
        )

        if llm_email.get('error'):
            print(f"  ⚠ LLM 邮件生成失败: {llm_email['error']}，回退到规则引擎")
            email = self.composer.compose(research_result, classification, fabe_points, materials, has_website=has_website, target_word_count=target_word_count)
        else:
            print(f"  ✓ LLM 邮件生成成功")
            greeting = self.composer._generate_greeting(None, customer_name, 'public')
            signature = self.composer._generate_signature()
            # LLM 返回的 body 包含 greeting 和 signature，需要剥离，只保留纯正文
            llm_body = llm_email['body']
            llm_body = self._strip_greeting_and_signature(llm_body, greeting, signature)
            email = {
                'subject': llm_email['subject'],
                'greeting': greeting,
                'body': llm_body,
                'signature': signature,
                'full_text': f"{greeting}\n\n{llm_body}\n\n{signature}"
            }
        _notify('compose', 'completed')

        # ===== 节点7: 邮件润色（LLM）=====
        print(f"\n[节点7] 邮件润色 (LLM)")
        _notify('refine', 'running')
        # 传入纯正文给润色（不含 greeting/signature）
        refined = self.llm.refine_email(email['subject'], email['body'], target_word_count=target_word_count)
        if not refined.get('error'):
            email['subject'] = refined['subject']
            # LLM 润色返回的 body 也可能包含 greeting/signature，需要剥离
            refined_body = self._strip_greeting_and_signature(refined['body'], email['greeting'], email['signature'])
            email['body'] = refined_body
            email['full_text'] = f"{email['greeting']}\n\n{refined_body}\n\n{email['signature']}"
            print(f"  ✓ LLM 润色完成")
        else:
            print(f"  ⚠ LLM 润色失败，使用原始内容")
            email = self.refiner.refine(email, target_word_count=target_word_count)
        _notify('refine', 'completed')

        # ===== 节点8: HTML 渲染（LLM）=====
        print(f"\n[节点8] HTML 渲染 (LLM)")
        html = self.llm.render_html(email)
        if html:
            print(f"  ✓ LLM HTML 渲染完成")
        else:
            print(f"  ⚠ LLM HTML 渲染失败，回退到规则引擎")
            html = self.renderer.render(email)

        print(f"\n{'=' * 60}")
        print(f"LLM 邮件生成完成!")
        print(f"{'=' * 60}")

        return {
            'customer_name': customer_name,
            'subject': email['subject'],
            'greeting': email['greeting'],
            'body': email['body'],
            'signature': email['signature'],
            'full_text': email['full_text'],
            'html': html,
            'word_count': email.get('word_count', len(email['body'].split())),
            'classification': classification,
            'fabe_points': fabe_points
        }

    def generate_email(self, customer_name: str, website: str,
                        progress_callback=None, target_word_count=None,
                        selected_material_ids: list = None) -> Dict:
        """
        一键生成开发信

        Args:
            customer_name: 客户公司名称
            website: 客户官网URL（可为空字符串）
            progress_callback: 进度回调函数，接收(step_id, status)参数
            target_word_count: 目标字数范围 {'min': int, 'max': int}
            selected_material_ids: 用户手动选中的素材ID列表

        Returns:
            包含主题、正文、HTML的完整邮件字典
        """
        has_website = bool(website and website.strip() and website.strip().startswith('http'))

        # 判断是否使用 LLM 模式
        if self._should_use_llm():
            return self._generate_with_llm(customer_name, website, progress_callback, target_word_count)

        print("=" * 60)
        print("开发信生成工作流 v2.0")
        print("=" * 60)
        print(f"目标客户: {customer_name}")
        print(f"网站: {website if has_website else '(无)'}")

        # 节点1: 公司背调（无网站时跳过网站抓取，仅做搜索）
        if has_website:
            research_result = self.researcher.research(customer_name, website)
        else:
            # 无网站时，构建最小化的 research_result
            print("\n[节点1] 客户无网站信息，跳过网站背调")
            research_result = {
                'module1_profile': {
                    'company_name': customer_name,
                    'main_business': '',
                    'target_markets': [],
                    'business_model': 'unknown',
                    'core_products': [],
                    'has_own_brand': False
                },
                'module2_products': {
                    'has_solar_products': False,
                    'solar_products': [],
                    'power_range_estimate': 'unknown',
                    'panel_type': 'unknown',
                    'procurement_mode': 'unknown',
                    'volume_estimate': 'unknown'
                },
                'module3_pain_points': [],
                'module4_tags': {
                    'power_tendency': 'unknown',
                    'track': 'General',
                    'case_match': 'none'
                }
            }

        # 节点2: 判断客户类型
        classification = self.classifier.classify(research_result)

        # 节点3: 优势点提炼
        advantages = self.advantage_selector.select(classification, research_result)

        # 节点4: FABE法则实践
        fabe_points = self.fabe_transformer.transform(advantages, classification, research_result)

        # 节点5: 素材库智能匹配
        materials = self.material_matcher.match(
            classification, research_result,
            selected_material_ids=selected_material_ids,
            user_id=self.user_id, admin=self.is_admin
        )

        # 节点6: 开发信生成（传入 has_website 控制措辞）
        email = self.composer.compose(research_result, classification, fabe_points, materials, has_website=has_website)

        # 节点7: 邮件内容精修
        email = self.refiner.refine(email)

        # 节点8: HTML格式渲染
        html = self.renderer.render(email)

        print("\n" + "=" * 60)
        print("开发信生成完成!")
        print("=" * 60)

        return {
            'customer_name': customer_name,
            'subject': email['subject'],
            'greeting': email['greeting'],
            'body': email['body'],
            'signature': email['signature'],
            'full_text': email['full_text'],
            'html': html,
            'word_count': email.get('word_count', 0),
            'classification': classification,
            'fabe_points': fabe_points
        }


if __name__ == '__main__':
    # 测试
    workflow = EmailWorkflow()
    result = workflow.generate_email(
        customer_name="TOPEN INTERNATIONAL INC",
        website="https://topens.com"
    )
    print("\n" + "=" * 60)
    print("最终邮件内容:")
    print("=" * 60)
    print(f"\n主题: {result['subject']}")
    print(f"\n{result['full_text']}")
