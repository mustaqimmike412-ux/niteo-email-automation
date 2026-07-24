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


# ==================== 字数强制修正工具函数 ====================

def _enforce_word_count(body: str, target: int, min_wc: int, max_wc: int) -> str:
    """
    强制将邮件正文修正到 [min_wc, max_wc] 范围内。
    - 超长：按句子裁剪，保留开头和结尾
    - 过短：按句子重复扩展最后一段论述
    """
    words = body.split()
    count = len(words)

    if min_wc <= count <= max_wc:
        return body  # 已在范围内

    if count > max_wc:
        # 超长：裁剪。保留开头和结尾，压缩中间
        sentences = re.split(r'(?<=[.!?])\s+', body)
        if len(sentences) <= 2:
            # 只有1-2句，直接截断
            return ' '.join(words[:max_wc])
        head = sentences[0]
        tail = ' '.join(sentences[-2:])  # 保留最后两句
        head_words = len(head.split())
        tail_words = len(tail.split())
        mid_budget = max(0, max_wc - head_words - tail_words)
        mid_sentences = sentences[1:-2]
        mid_text = ' '.join(mid_sentences)
        mid_words = mid_text.split()
        if len(mid_words) > mid_budget:
            mid_text = ' '.join(mid_words[:mid_budget])
        result = head + ' ' + mid_text + ' ' + tail
        # 最终兜底
        result_words = result.split()
        if len(result_words) > max_wc:
            result = ' '.join(result_words[:max_wc])
        return result

    else:
        # 过短：扩展。从已有句子中选择最有价值的重复/扩展
        sentences = re.split(r'(?<=[.!?])\s+', body)
        if len(sentences) <= 1:
            # 只有1句，无法智能扩展，填充通用但相关的补充
            padding_sentences = [
                "Our solutions are designed to meet the highest industry standards.",
                "We would welcome the opportunity to discuss how we can support your goals.",
                "Please feel free to reach out if you have any questions."
            ]
            needed = max_wc - count
            added = []
            for ps in padding_sentences:
                if needed <= 0:
                    break
                added.append(ps)
                needed -= len(ps.split())
            return body + ' ' + ' '.join(added)
        else:
            # 重复最后一句论述性句子（通常是CTA或总结）
            last_substantive = sentences[-2] if len(sentences) >= 2 else sentences[-1]
            result_words = list(words)
            while len(result_words) < min_wc:
                expand_words = last_substantive.split()
                # 稍微改写避免完全重复
                result_words.extend(expand_words)
            result_words = result_words[:max_wc]
            return ' '.join(result_words)


# ==================== 字数强制修正工具函数 END ====================


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
        advantages = get_advantages_by_power_type(power_type, user_id=self.user_id)
        
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
                ring_case = get_ring_case_for_email('smart_home', user_id=self.user_id)
                return ring_case[:200] + '...' if ring_case else ''
            elif 'oem' in name or 'odm' in name or 'custom' in name:
                ring_case = get_ring_case_for_email('smart_home', user_id=self.user_id)
                return ring_case[:200] + '...' if ring_case else ''
            elif 'ddp' in name or 'logistics' in name:
                arlo_case = get_arlo_case_for_email('north_america_buyer', user_id=self.user_id)
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
            'advantages': get_advantages_by_power_type(power_type, user_id=user_id),
            'brochure': get_brochure_by_power_type(power_type, user_id=user_id),
            'cases': get_cases_by_track(track, user_id=user_id),
            'rules': get_case_workflow_rules(track, regions[0] if regions else '', user_id=user_id),
            'custom_selected': [],
        }
        
        # 大功率客户额外获取储能素材
        if '大功率' in power_type:
            matched['storage'] = get_storage_brochure(user_id=user_id)
        
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
            target_word_count = {'min': 140, 'max': 160}
        elif isinstance(target_word_count, int):
            target_word_count = {'min': max(10, target_word_count - 10), 'max': target_word_count + 10}
        max_words = target_word_count.get('max', 160)
        min_words = target_word_count.get('min', 140)

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

        # 字数强制修正（规则引擎回退模式）
        body_words = len(body.split())
        if body_words < min_words or body_words > max_words:
            body = _enforce_word_count(body, (min_words + max_words) // 2, min_words, max_words)
            email['body'] = body
            email['full_text'] = f"{greeting}\n\n{body}\n\n{signature}"

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
    
    def _is_valid_name(self, name: str) -> bool:
        """检查名字是否有效（至少包含一个字母字符，不只是标点/数字/空白）"""
        if not name or not name.strip():
            return False
        stripped = name.strip()
        if stripped.lower() in {'n/a', 'na', '-', '', 'team', 'unknown', 'none'}:
            return False
        if not any(c.isalpha() for c in stripped):
            return False
        return True

    def _extract_first_name(self, contact_name: str) -> str:
        """从 contact_name 提取 first_name，带有效性校验"""
        if not self._is_valid_name(contact_name):
            return ''
        first = contact_name.strip().split()[0].strip()
        return first if any(c.isalpha() for c in first) else ''

    def _generate_greeting(self, contact_name: str = None, customer_name: str = 'Team', email_type: str = 'public') -> str:
        """
        生成称呼（多样化规则，避免模式化特征）
        1. 优先使用用户自定义问候语模板（如有配置）
        2. 公共邮箱 / 无具体联系人: 随机选择 "Hi/Hello/Greetings" + [对方公司名称] Team,
        3. 有具体联系人姓名: 随机选择 "Hi/Hello/Good day" + [First Name],
        """
        import re
        import random

        # 防御：customer_name 为 None 时兜底（避免默认 Team 导致后面加 Team 重复）
        safe_customer_name = (customer_name or 'Valued').strip()

        # 提取有效的 first_name（若无效则回退到公司名）
        first_name = self._extract_first_name(contact_name)
        has_valid_name = bool(first_name)

        # 优先查询用户自定义问候语模板
        if getattr(self, 'user_id', None):
            try:
                from database.email_template_models import get_random_template
                tpl = get_random_template(self.user_id, 'greeting')
                if tpl:
                    text = tpl['template_text']
                    # 清理公司名
                    clean_name = safe_customer_name
                    suffix_patterns = [
                        r'\s+INC\.?$', r'\s+LLC\.?$', r'\s+LTD\.?$', r'\s+PTY\.?$',
                        r'\s+GMBH\.?$', r'\s+SA\.?$', r'\s+CORP\.?$', r'\s+CORPORATION\.?$',
                        r'\s+LIMITED\.?$', r'\s+CO\.?$'
                    ]
                    for pattern in suffix_patterns:
                        clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)
                    clean_name = clean_name.strip().title() if clean_name.strip() else 'Valued'
                    # 替换占位符
                    text = text.replace('{first_name}', first_name)
                    text = text.replace('{company_name}', clean_name)
                    text = text.replace('{team}', 'Team' if email_type != 'personal' or not has_valid_name else '')
                    # 防御：模板替换后不能为空或只剩问候词
                    text_stripped = text.strip().rstrip(',').strip()
                    if text_stripped and text_stripped.lower() not in ('hi', 'hello', 'dear', 'good day'):
                        return text
            except Exception:
                pass  # 模板查询失败时回退到默认逻辑

        personal_greetings = ['Hi', 'Hello', 'Good day']
        company_greetings = ['Hi', 'Hello', 'Greetings']

        # 只有个人邮箱且有有效名字时才使用名字称呼
        if email_type == 'personal' and has_valid_name:
            greeting = random.choice(personal_greetings)
            return f"{greeting} {first_name},"
        else:
            clean_name = safe_customer_name
            suffix_patterns = [
                r'\s+INC\.?$', r'\s+LLC\.?$', r'\s+LTD\.?$', r'\s+PTY\.?$',
                r'\s+GMBH\.?$', r'\s+SA\.?$', r'\s+CORP\.?$', r'\s+CORPORATION\.?$',
                r'\s+LIMITED\.?$', r'\s+CO\.?$'
            ]
            for pattern in suffix_patterns:
                clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)
            clean_name = clean_name.strip()
            clean_name = clean_name.title() if clean_name else 'Valued'
            greeting = random.choice(company_greetings)
            return f"{greeting} {clean_name} Team,"
    
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
        """生成签名（使用默认格式：姓名 + 职位 + 公司）"""
        # 使用发件人信息中的姓名、职位、公司拼接签名
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
            target_word_count = {'min': 140, 'max': 160}
        elif isinstance(target_word_count, int):
            target_word_count = {'min': max(10, target_word_count - 10), 'max': target_word_count + 10}
        max_words = target_word_count.get('max', 160)
        min_words = target_word_count.get('min', 140)

        print(f"\n[节点7] 邮件内容精修")

        original_body = email['body']

        # 精简冗余
        refined_body = self._trim_redundancy(original_body)

        # 优化语气
        refined_body = self._optimize_tone(refined_body)

        # 字数强制修正（上下限都检查）
        word_count = len(refined_body.split())
        if word_count < min_words or word_count > max_words:
            refined_body = _enforce_word_count(refined_body, (min_words + max_words) // 2, min_words, max_words)
        
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
        self.llm = LLMEmailClient(user_id=user_id)
    
    def _should_use_llm(self):
        """判断是否使用 LLM 模式生成邮件"""
        if not self.llm.is_available():
            return False
        # 读取调度配置中的 generation 设置
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'scheduler_config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            mode = config.get('generation', 'ai')  # 默认 LLM 模式
            return mode == 'ai'
        return True  # 无配置文件时默认使用 LLM 模式

    def _compress_body_to_target(self, body: str, max_words: int) -> str:
        """将正文裁剪到目标字数，保留开头和结尾句，从中间删减"""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', body)
        if len(sentences) <= 2:
            return body

        # 保留首句和末两句
        head = sentences[0]
        tail_sentences = sentences[-2:]
        tail = ' '.join(tail_sentences)
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

        parts = [head] + mid_result + tail_sentences
        result = ' '.join(parts)
        # 确保不超过目标
        words = result.split()
        if len(words) > max_words:
            result = ' '.join(words[:max_words])
        return result

    def _format_email_body(self, body: str) -> str:
        """对正文进行排版美化：确保段落间距合理，格式整洁

        - 如果已有段落分隔（连续空行），规范化间距
        - 如果没有段落，按句子自动分组为 4-5 段
        - 每段 2-4 个句子
        """
        import re
        body = body.strip()

        # 检查是否已有段落分隔（连续2个以上换行）
        if re.search(r'\n\n\n*', body):
            # 已有段落，规范化：每个段落之间空一行，首尾去空行
            paragraphs = re.split(r'\n{2,}', body)
            paragraphs = [p.strip() for p in paragraphs if p.strip()]
            return '\n\n'.join(paragraphs)

        # 没有段落分隔，按句子自动分组
        sentences = re.split(r'(?<=[.!?])\s+', body)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= 3:
            # 句子太少，不分段，只规范化间距
            return ' '.join(sentences)

        # 根据句子数量决定段落数（4-5段）
        num_paragraphs = min(5, max(4, len(sentences) // 2))
        base_size = len(sentences) // num_paragraphs
        extra = len(sentences) % num_paragraphs

        paragraphs = []
        idx = 0
        for i in range(num_paragraphs):
            size = base_size + (1 if i < extra else 0)
            if idx < len(sentences):
                para = ' '.join(sentences[idx:idx + size])
                paragraphs.append(para)
                idx += size

        return '\n\n'.join(paragraphs)

    def _strip_greeting_and_signature(self, body: str, greeting: str, signature: str) -> str:
        """
        从 LLM 生成的 body 中剥离 greeting 和 signature，只保留纯正文。
        策略：
        - 签名：从末尾向前搜索，找到签名关键词行后，跳过后续所有行（含名字/职位/公司名）
        - greeting：从开头向后搜索，跳过 Hi/Dear/Hello 开头的行及其后空行
        - 额外兜底：body 结尾如果包含签名中的名字行（来自 LLM 自行添加），也一并移除
        """
        lines = body.split('\n')
        if not lines:
            return ''

        # 找签名的起始行（从末尾向前搜索）
        sig_keywords = ['Best regards', 'best regards', 'Regards,', 'regards,',
                        'Sincerely', 'sincerely', 'Warm regards', 'Best,']

        sig_start = len(lines)  # 签名开始的行号
        for i in range(len(lines) - 1, -1, -1):
            stripped = lines[i].strip()
            if not stripped:
                continue  # 跳过空行
            if any(kw in stripped for kw in sig_keywords):
                sig_start = i
                break  # 只通过关键词匹配定位签名起始行，不再猜测短行

        # 兜底：如果没找到签名关键词，但 body 末尾的行看起来像签名（短行+非句尾），
        # 尝试移除最后 1-3 行签名块
        if sig_start == len(lines):
            # 检查最后几行是否像签名：短行、不以句号结尾、连续出现
            tail_start = len(lines)
            for i in range(len(lines) - 1, max(len(lines) - 6, -1), -1):
                stripped = lines[i].strip()
                if not stripped:
                    continue
                # 如果这行是签名关键词，也标记
                if any(kw in stripped for kw in sig_keywords):
                    tail_start = i
                    break
                # 短行（< 60字符）且不以句号结尾，可能是签名中的名字/职位/公司行
                if len(stripped) < 60 and not stripped.endswith('.') and not stripped.endswith('?') and not stripped.endswith('!'):
                    tail_start = i
                else:
                    break  # 遇到正常的正文行，停止
            # 只在连续3行以上看起来像签名时才移除
            sig_lines = [l for l in lines[tail_start:] if l.strip()]
            if len(sig_lines) >= 2:
                sig_start = tail_start

        # 找 greeting 的结束行（从开头向后搜索）
        greeting_end = 0
        for i, line in enumerate(lines[:min(5, len(lines))]):  # 只检查前5行
            stripped = line.strip()
            if not stripped:
                if greeting_end > 0:
                    break  # greeting 后的空行表示 greeting 结束
                continue
            if greeting_end == 0 and (stripped.startswith('Hi ') or stripped.startswith('Dear ') or stripped.startswith('Hello ')):
                greeting_end = i + 1
            elif greeting_end > 0:
                # greeting 后的第一个非空非签名行是正文开始
                if any(kw in stripped for kw in sig_keywords):
                    break  # 这行是签名关键词，不是正文
                greeting_end = i + 1
                break

        # 提取正文
        body_lines = lines[greeting_end:sig_start]
        result = '\n'.join(body_lines).strip()
        # 清理开头和结尾的多余空行
        result = re.sub(r'\n{3,}', '\n\n', result)

        # 清理正文开头可能出现的孤立短词（LLM 有时会生成 "Solar." 之类的垃圾开头）
        # 如果正文开头是一个极短的词（<15字符）+ 句号，且后面跟着空行和正常段落，则移除它
        while True:
            first_line = result.split('\n')[0].strip() if result else ''
            if len(first_line) < 20 and first_line.endswith('.') and len(result.split('\n')) > 2:
                # 检查这是否是一个完整的句子（有主语和谓语）
                words = first_line.split()
                if len(words) <= 3:
                    # 孤立短词，移除第一行及其后的空行
                    parts = result.split('\n', 1)
                    if len(parts) > 1:
                        result = parts[1].lstrip('\n')
                    else:
                        break
                else:
                    break
            else:
                break

        return result

    def _generate_with_llm(self, customer_name, website, progress_callback=None, target_word_count=None, selected_material_ids=None, skip_refine=False, skip_format=False, language='en', opening_template=None):
        """使用 DeepSeek V4 Pro 生成邮件（LLM 增强模式）

        Args:
            customer_name: 客户公司名称
            website: 客户官网URL
            progress_callback: 进度回调函数，接收(step_id, status)参数
            target_word_count: 目标字数 - 支持两种格式：
              - int: 目标字数（自动转范围：min=target-30, max=target+30）
              - dict: {'min': int, 'max': int}（兼容旧前端）
            selected_material_ids: 用户手动选中的素材ID列表
            language: 邮件语言 (en/fr/de)
        """
        # 统一格式：int → 范围自动计算（容差±10）；dict → 直接使用；None → 默认150
        if target_word_count is None:
            target_word_count = 150  # 默认目标字数 150
        if isinstance(target_word_count, int):
            target_word_count = {'min': max(10, target_word_count - 10), 'max': target_word_count + 10}
        # 已经是 dict → 直接保留（兼容旧前端）

        # 保存原始目标字数（int），用于最终字数校验
        _original_target = target_word_count
        if isinstance(_original_target, dict):
            _original_target = (_original_target.get('min', 140) + _original_target.get('max', 160)) // 2

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
        llm_analysis = self.llm.analyze_company(page_text, search_summary, customer_name, language=language)
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
        _notify('pain_points', 'running')
        classification = self.llm.classify_customer(research_result, language=language)
        if classification:
            print(f"  ✓ LLM 分类成功: {classification}")
        else:
            print(f"  ⚠ LLM 分类失败，回退到规则引擎")
            classification = self.classifier.classify(research_result)
        _notify('pain_points', 'completed')

        # ===== 节点3: 优势提炼（LLM）=====
        print(f"\n[节点3] 优势提炼 (LLM)")
        _notify('advantages', 'running')
        # 构建素材库文本摘要
        from materials.unified_interface import get_advantages_by_power_type
        power_type = classification.get('power_type', 'High Power')
        raw_advantages = get_advantages_by_power_type(power_type, user_id=self.user_id)
        material_summary = '\n'.join([
            f"- {a.get('name', '')}: {a.get('tech_features', '')} (Scope: {a.get('scope', '')})"
            for a in raw_advantages
        ])
        advantages = self.llm.select_advantages(classification, research_result, material_summary, language=language)
        if advantages:
            print(f"  ✓ LLM 优势提炼成功: {len(advantages)} 个")
        else:
            print(f"  ⚠ LLM 优势提炼失败，回退到规则引擎")
            advantages = self.advantage_selector.select(classification, research_result)
        _notify('advantages', 'completed')

        # ===== 节点4: FABE 话术（LLM）=====
        print(f"\n[节点4] FABE 话术 (LLM)")
        _notify('fabe', 'running')
        fabe_points = self.llm.generate_fabe(advantages, classification, research_result, language=language)
        if fabe_points:
            print(f"  ✓ LLM FABE 生成成功: {len(fabe_points)} 个")
        else:
            print(f"  ⚠ LLM FABE 失败，回退到规则引擎")
            fabe_points = self.fabe_transformer.transform(advantages, classification, research_result)
        _notify('fabe', 'completed')

        # ===== 节点5: 素材匹配（LLM）=====
        print(f"\n[节点5] 素材匹配 (LLM)")
        _notify('material', 'running')
        # 获取公司信息：先从发信人信息合并，再从 company_info.json 补充
        company_info = {}
        # 优先从发信人信息中获取
        sender_info = self.composer.sender_info if hasattr(self.composer, 'sender_info') else {}
        if sender_info:
            company_info['sender_name'] = sender_info.get('sender_name', '')
            company_info['job_title'] = sender_info.get('job_title', '')
            company_info['company_name'] = sender_info.get('company_name', '')
            company_info['company_website'] = sender_info.get('company_website', '')
        # 从 company_info.json 补充缺失字段
        company_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'company_info.json')
        if os.path.exists(company_path):
            with open(company_path, 'r', encoding='utf-8') as f:
                json_info = json.load(f)
                for key, val in json_info.items():
                    if not company_info.get(key):
                        company_info[key] = val
        materials = self.llm.match_materials(classification, research_result, company_info, language=language)
        if materials:
            print(f"  ✓ LLM 素材匹配成功")
        else:
            print(f"  ⚠ LLM 素材匹配失败，回退到规则引擎")
            materials = self.material_matcher.match(
                classification, research_result,
                selected_material_ids=selected_material_ids,
                user_id=self.user_id
            )
        _notify('material', 'completed')

        # ===== 邮箱类型自动识别 =====
        email_type = 'public'
        contact_name_for_email = None
        try:
            from database.connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            # 通过customer_name关联customers表获取emails
            cursor.execute(
                'SELECT e.email_address, e.email_type, e.contact_name '
                'FROM emails e JOIN customers c ON e.customer_id = c.id '
                'WHERE c.customer_name = ? AND e.is_active = 1 '
                'AND (c.user_id = ? OR ? = 1)',
                (customer_name, self.user_id, 1 if self.is_admin else 0)
            )
            rows = cursor.fetchall()
            conn.close()
            if rows:
                # 优先选择个人邮箱（有contact_name的）
                personal_row = None
                public_row = None
                for row in rows:
                    addr, etype, cname = row
                    if etype == 'personal' and cname and cname.strip():
                        personal_row = (addr, etype, cname)
                    elif etype == 'public' or not personal_row:
                        public_row = (addr, etype, cname)
                chosen = personal_row or public_row
                if chosen:
                    email_addr, email_type, contact_name_for_email = chosen
                    # 如果数据库没有contact_name，用classify_email推断
                    if not contact_name_for_email or not contact_name_for_email.strip():
                        from utils.email_classifier import classify_email
                        email_type, contact_name_for_email = classify_email(email_addr)
                    print(f"  邮箱识别: {email_addr} → 类型={email_type}, 姓名={contact_name_for_email}")
            else:
                print(f"  未找到客户邮箱，默认使用公共邮箱类型")
        except Exception as e:
            print(f"  ⚠ 邮箱类型识别失败，默认公共邮箱: {e}")

        # ===== 节点6: 邮件生成（LLM）=====
        print(f"\n[节点6] 邮件生成 (LLM)")
        _notify('compose', 'running')

        # 处理开场白模板：优先使用外部传入的，否则随机获取
        if opening_template:
            # 外部已传入（已替换变量），直接使用
            print(f"  [模板] 使用指定开场白模板: {opening_template[:60]}...")
        elif getattr(self, 'user_id', None):
            try:
                from database.email_template_models import get_random_template
                tpl = get_random_template(self.user_id, 'opening')
                if tpl:
                    text = tpl['template_text']
                    # 替换占位符
                    text = text.replace('{sender_name}', company_info.get('sender_name', 'Travis'))
                    text = text.replace('{job_title}', company_info.get('job_title', 'Business Development Manager'))
                    text = text.replace('{company_name}', company_info.get('company_name', 'Niteo Solar'))
                    text = text.replace('{customer_name}', customer_name)
                    profile = research_result.get('module1_profile', {})
                    products = profile.get('core_products', [])
                    product = products[0] if products else 'your products'
                    text = text.replace('{product}', product)
                    opening_template = text
                    print(f"  [模板] 使用随机开场白模板: {opening_template[:60]}...")
            except Exception as e:
                print(f"  [模板] 开场白模板查询失败: {e}")

        llm_email = self.llm.compose_email(
            research_result, classification, fabe_points, materials,
            contact_name=contact_name_for_email, email_type=email_type,
            has_website=has_website, company_info=company_info,
            target_word_count=target_word_count,
            language=language,
            opening_template=opening_template
        )

        if llm_email.get('error'):
            print(f"  ⚠ LLM 邮件生成失败: {llm_email['error']}，回退到规则引擎")
            email = self.composer.compose(research_result, classification, fabe_points, materials,
                                          contact_name=contact_name_for_email, email_type=email_type,
                                          has_website=has_website, target_word_count=target_word_count)
        else:
            print(f"  ✓ LLM 邮件生成成功")
            greeting = self.composer._generate_greeting(contact_name_for_email, customer_name, email_type)
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
        if not skip_refine:
            print(f"\n[节点7] 邮件润色 (LLM)")
            _notify('refine', 'running')
            # 传入纯正文给润色（不含 greeting/signature）
            refined = self.llm.refine_email(email['subject'], email['body'], target_word_count=target_word_count, customer_name=customer_name, language=language)
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
        else:
            print(f"\n[节点7] 邮件润色 — 跳过（调度器模式）")

        # ===== 节点7.5: 邮件排版（LLM）=====
        if not skip_format:
            print(f"\n[节点7.5] 邮件排版 (LLM)")
            _notify('format', 'running')
            format_result = self.llm.format_email(email['body'], target_words=_original_target, language=language)
            if not format_result.get('error'):
                email['body'] = format_result['body']
                email['full_text'] = f"{email['greeting']}\n\n{email['body']}\n\n{email['signature']}"
                print(f"  ✓ LLM 排版完成: {format_result['word_count']} 词, {len(email['body'].split(chr(10)*2))} 段")
            else:
                print(f"  ⚠ LLM 排版失败，使用原始内容: {format_result.get('error')}")
            _notify('format', 'completed')
        else:
            print(f"\n[节点7.5] 邮件排版 — 跳过（手动模式，用户可自行排版）")

        # ===== 节点8: HTML 渲染（LLM）=====
        print(f"\n[节点8] HTML 渲染 (LLM)")
        html = self.llm.render_html(email, language=language)
        if html:
            print(f"  ✓ LLM HTML 渲染完成")
        else:
            print(f"  ⚠ LLM HTML 渲染失败，回退到规则引擎")
            html = self.renderer.render(email)

        # 后处理：清理 LLM 可能编造的自我介绍（即使有 sender_name，如果公司名不匹配也清理）
        sender_name = self.composer.sender_info.get('sender_name', '') if hasattr(self.composer, 'sender_info') else ''
        sender_company = self.composer.sender_info.get('company_name', '') if hasattr(self.composer, 'sender_info') else ''
        import re
        common_names = r'(?:Travis|Tom|John|Mike|David|James|Alex|Chris|Daniel|Kevin|Ryan|Steve|Mark|Paul|Jason|Brian|Eric|Sarah|Emily|Lisa|Anna)'
        titles = r'(?:Business Development Manager|Sales Manager|Account Manager|Sales Director|Regional Director|VP of Sales|Marketing Manager|Product Manager)'
        # 匹配完整的自我介绍句子（"My name is [Name], [Title] at [Company]"），整体移除
        intro_patterns = [
            rf"My name is\s+{common_names}\s*,\s*and\s+I\s+am\s+(?:the\s+|a\s+)?{titles}\s+at\s+[^.]+[.!]\s*",
            rf"(?:My name is|I'm|I am)\s+{common_names}\s*,\s*{titles}\s+at\s+[^.!]+[.!]\s*",
            rf"I'm\s+{common_names}\s*,\s*{titles}\s+at\s+[^.]+[.!]\s*",
        ]
        for pattern in intro_patterns:
            email['body'] = re.sub(pattern, "", email['body'], count=1)
            email['full_text'] = re.sub(pattern, "", email['full_text'], count=1)

        # 清理 LLM 可能编造的公司名（如果用户未配置公司名）
        if not sender_company:
            for fake_name in ['Niteo Solar', 'Niteo Energy', 'Niteo Power', 'Niteo Tech']:
                email['body'] = email['body'].replace(fake_name, 'our company')
                email['full_text'] = email['full_text'].replace(fake_name, 'our company')
                email['subject'] = email['subject'].replace(fake_name, 'Solar Solutions')

        print(f"\n{'=' * 60}")
        print(f"LLM 邮件生成完成!")
        print(f"{'=' * 60}")

        body_words = len(email['body'].split())
        print(f"最终字数: {body_words} 词 (目标: {_original_target})")

        # ==================== 强制字数校验和自动修正 ====================
        min_wc = max(10, _original_target - 10)
        max_wc = _original_target + 10
        if body_words < min_wc or body_words > max_wc:
            print(f"[字数修正] {body_words} 词超出范围 [{min_wc}, {max_wc}]，正在自动修正...")
            email['body'] = _enforce_word_count(email['body'], _original_target, min_wc, max_wc)
            email['full_text'] = email.get('greeting', '') + '\n\n' + email['body'] + '\n\n' + email.get('signature', '')
            body_words = len(email['body'].split())
            print(f"[字数修正] 修正后字数: {body_words} 词")

        return {
            'customer_name': customer_name,
            'subject': email['subject'],
            'greeting': email['greeting'],
            'body': email['body'],
            'signature': email['signature'],
            'full_text': email['full_text'],
            'html': html,
            'word_count': body_words,
            'language': language,
            'classification': classification,
            'fabe_points': fabe_points
        }

    def generate_follow_up_email(self, sequence_id, step_id, user_id=None):
        """
        生成跟进邮件内容（跳过背调/分类/优势/FABE，只做素材匹配→生成→排版）

        参数:
            sequence_id: 跟进序列 ID
            step_id: 跟进步骤 ID
            user_id: 当前用户 ID

        返回:
            dict: {subject, body, greeting, signature, full_text} 或 None（失败时）
        """
        from database.follow_up_models import get_sequence, get_step, update_step
        from database.connection import get_connection
        from generators.follow_up_prompts import build_follow_up_prompt

        print(f"\n[跟进邮件] 开始生成 sequence_id={sequence_id}, step_id={step_id}")

        # ===== 1. 读取序列和步骤信息 =====
        admin = self.is_admin
        sequence = get_sequence(sequence_id, user_id=user_id)
        if not sequence:
            print(f"  ✗ 序列不存在: sequence_id={sequence_id}")
            update_step(step_id, user_id=user_id,
                        error_message=f'序列不存在: sequence_id={sequence_id}')
            return None

        step = get_step(step_id, user_id=user_id)
        if not step:
            print(f"  ✗ 步骤不存在: step_id={step_id}")
            update_step(step_id, user_id=user_id,
                        error_message=f'步骤不存在: step_id={step_id}')
            return None

        # ===== 2. 从 generation_context 解析上下文 =====
        gen_ctx = sequence.get('generation_context') or {}
        first_email_info = gen_ctx.get('first_email', {})
        classification = gen_ctx.get('customer_classification', {})
        sender_info = gen_ctx.get('sender_info', {})
        advantages = gen_ctx.get('advantages', [])
        config_json = sequence.get('config_json') or {}

        # 从序列关联的第一封邮件记录中读取邮件内容
        first_email_subject = ''
        first_email_body = ''
        first_email_log_id = sequence.get('first_email_log_id')

        if first_email_log_id:
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT email_subject, email_content FROM email_logs WHERE id = ?',
                    (first_email_log_id,)
                )
                log_row = cursor.fetchone()
                conn.close()
                if log_row:
                    first_email_subject = log_row[0] or ''
                    first_email_body = log_row[1] or ''
                    print(f"  ✓ 读取第一封邮件记录: {len(first_email_body)} 字符")
            except Exception as e:
                print(f"  ⚠ 读取第一封邮件记录失败: {e}")

        # 如果 email_logs 没有数据，尝试从 generation_context 获取
        if not first_email_body and first_email_info:
            first_email_subject = first_email_info.get('subject', '')
            first_email_body = first_email_info.get('body', '') or first_email_info.get('full_text', '')

        # ===== 3. 解析客户分类和发信人信息 =====
        power_type = classification.get('power_type', 'High Power')
        track = classification.get('track', 'General')
        pain_points = classification.get('pain_points', [])

        # 从 generation_context 或发信人信息中提取
        sender_name = sender_info.get('sender_name', config_json.get('sender_name', ''))
        sender_company = sender_info.get('company_name', config_json.get('sender_company', ''))
        sender_position = sender_info.get('job_title', config_json.get('sender_position', ''))

        # 如果 generation_context 中没有发信人信息，尝试从 composer 获取
        if not sender_name and hasattr(self.composer, 'sender_info'):
            si = self.composer.sender_info or {}
            sender_name = si.get('sender_name', '')
            sender_company = si.get('company_name', '')
            sender_position = si.get('job_title', '')

        # 获取客户信息
        customer_name = ''
        customer_country = ''
        customer_industry = ''
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT customer_name, country, industry_type FROM customers WHERE id = ?',
                (sequence.get('customer_id'),)
            )
            c_row = cursor.fetchone()
            conn.close()
            if c_row:
                customer_name = c_row[0] or ''
                customer_country = c_row[1] or ''
                customer_industry = c_row[2] or ''
        except Exception as e:
            print(f"  ⚠ 读取客户信息失败: {e}")

        # 如果 generation_context 中有客户信息，优先使用
        if not customer_name:
            customer_name = gen_ctx.get('customer_name', '')
        if not customer_industry:
            customer_industry = classification.get('industry', '')
        if not customer_country:
            customer_country = classification.get('country', '')

        # ===== 4. 根据步骤 purpose 加载素材 =====
        case_material = None
        brochure_material = None
        purpose = step['purpose']

        if purpose == 'case_study':
            # 按 track 加载案例素材
            try:
                cases = get_cases_by_track(track, user_id=user_id)
                if cases:
                    # 取第一个最相关的案例
                    case_material = cases[0]
                    print(f"  ✓ 加载案例素材: {case_material.get('title', case_material.get('name', 'case'))}")
            except Exception as e:
                print(f"  ⚠ 加载案例素材失败: {e}")

        elif purpose == 'resource':
            # 按 power_type 加载宣传册素材
            try:
                brochure_material = get_brochure_by_power_type(power_type, user_id=user_id)
                if brochure_material:
                    print(f"  ✓ 加载宣传册素材: {list(brochure_material.keys())}")
            except Exception as e:
                print(f"  ⚠ 加载宣传册素材失败: {e}")

        # ===== 5. 构建 context 字典 =====
        # 根据策略确定目标字数
        purpose_word_counts = {
            'reminder': 80,
            'case_study': 120,
            'question': 80,
            'resource': 100,
            'loss_aversion': 100,
            'breakup': 50,
        }
        word_count = config_json.get('word_count', purpose_word_counts.get(purpose, 100))

        context = {
            'first_email_subject': first_email_subject,
            'first_email_body': first_email_body,
            'customer_name': customer_name or 'Valued Partner',
            'customer_country': customer_country,
            'customer_industry': customer_industry,
            'sender_name': sender_name,
            'sender_company': sender_company,
            'sender_position': sender_position,
            'power_type': power_type,
            'track': track,
            'advantages': advantages,
            'pain_points': pain_points,
            'case_material': case_material,
            'brochure_material': brochure_material,
            'word_count': word_count,
            'language': config_json.get('language', 'en'),
        }

        # ===== 6. 构建 Prompt 并调用 LLM =====
        step_number = step['step_number']
        total_steps = sequence.get('total_steps', step_number)

        try:
            system_prompt, user_prompt = build_follow_up_prompt(
                purpose, step_number, total_steps, context
            )
        except Exception as e:
            print(f"  ✗ 构建 Prompt 失败: {e}")
            update_step(step_id, user_id=user_id,
                        error_message=f'构建 Prompt 失败: {e}')
            return None

        print(f"  调用 LLM 生成跟进邮件 (purpose={purpose}, step={step_number}/{total_steps})")

        # breakup 邮件字数极少，max_tokens 也相应调低
        max_tokens = 300 if purpose == 'breakup' else 800

        content, error = self.llm._call(
            system_prompt, user_prompt,
            max_tokens=max_tokens,
            temperature=0.7,
            label=f'follow_up:{customer_name}:step{step_number}'
        )

        if error or not content:
            error_msg = error or 'LLM 返回空内容'
            print(f"  ✗ LLM 调用失败: {error_msg}")
            update_step(step_id, user_id=user_id,
                        error_message=f'LLM 调用失败: {error_msg}')
            return None

        # ===== 7. 解析 JSON 结果 =====
        try:
            # 清理可能的 markdown 包裹
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            result = json.loads(content.strip())
            subject = result.get('subject', '')
            body = result.get('body', '')
            greeting = result.get('greeting', f'Hi {customer_name} Team,')
            signature = result.get('signature', f'Best regards,\n{sender_name}')

            if not body:
                print(f"  ✗ LLM 返回的 body 为空")
                update_step(step_id, user_id=user_id,
                            error_message='LLM 返回的 body 为空')
                return None

            print(f"  ✓ LLM 生成成功: {len(body.split())} 词")
        except json.JSONDecodeError as e:
            error_msg = f'JSON 解析失败: {e}'
            print(f"  ✗ {error_msg}")
            print(f"  原始内容: {content[:500]}")
            update_step(step_id, user_id=user_id,
                        error_message=error_msg)
            return None

        # ===== 8. 处理 subject_mode: reply 模式 =====
        if step.get('subject_mode') == 'reply' and first_email_subject:
            subject = f"Re: {first_email_subject}"
            print(f"  reply 模式: 标题 = Re: {first_email_subject}")

        # ===== 9. 签名规范化 =====
        # 如果 LLM 返回的签名使用了占位符，替换为真实信息
        if sender_name:
            signature = signature.replace('[Sender Name]', sender_name).replace('[Your Name]', sender_name)
        if sender_position:
            signature = signature.replace('[Sender Title]', sender_position).replace('[Your Title]', sender_position)
        if sender_company:
            signature = signature.replace('[Sender Company]', sender_company).replace('[Your Company]', sender_company)

        # ===== 10. 排版 =====
        try:
            formatted_body = self._format_email_body(body)
            # 排版安全校验：字数不能偏差太大
            original_wc = len(body.split())
            formatted_wc = len(formatted_body.split())
            if original_wc > 10 and (formatted_wc < original_wc * 0.7 or formatted_wc > original_wc * 1.3):
                print(f"  ⚠ 排版安全校验：字数从 {original_wc} 到 {formatted_wc}，回退到原文")
            else:
                body = formatted_body
        except Exception as e:
            print(f"  ⚠ 排版失败，使用原始内容: {e}")

        # ===== 11. 字数校验 =====
        final_word_count = len(body.split())
        if purpose != 'breakup' and final_word_count > word_count * 1.5:
            # 超出目标太多，裁剪
            print(f"  ⚠ 字数 {final_word_count} 超出目标 {word_count} 的 1.5 倍，正在裁剪...")
            body = self._compress_body_to_target(body, int(word_count * 1.2))
            final_word_count = len(body.split())

        # ===== 12. 组装完整邮件 =====
        full_text = f"{greeting}\n\n{body}\n\n{signature}"

        # ===== 13. 保存结果到 follow_up_steps =====
        try:
            update_step(step_id, user_id=user_id,
                        subject=subject, body=body, greeting=greeting,
                        signature=signature, word_count=final_word_count,
                        status='pending')
            print(f"  ✓ 步骤结果已保存到数据库")
        except Exception as e:
            print(f"  ⚠ 保存步骤结果失败: {e}")

        print(f"\n[跟进邮件] 生成完成!")
        print(f"  主题: {subject}")
        print(f"  字数: {final_word_count} 词 (目标: {word_count})")

        return {
            'subject': subject,
            'body': body,
            'greeting': greeting,
            'signature': signature,
            'full_text': full_text,
            'word_count': final_word_count,
        }

    def generate_email(self, customer_name: str, website: str,
                        progress_callback=None, target_word_count=None,
                        selected_material_ids: list = None,
                        skip_refine=False, skip_format=False,
                        language: str = 'en',
                        opening_template: str = None) -> Dict:
        """
        一键生成开发信

        Args:
            customer_name: 客户公司名称
            website: 客户官网URL（可为空字符串）
            progress_callback: 进度回调函数，接收(step_id, status)参数
            target_word_count: 目标字数范围 {'min': int, 'max': int}
            selected_material_ids: 用户手动选中的素材ID列表
            language: 邮件语言 (en/fr/de)，默认英语
            opening_template: 用户指定的开场白模板（已替换变量后的文本），传入时优先使用

        Returns:
            包含主题、正文、HTML的完整邮件字典
        """
        has_website = bool(website and website.strip() and website.strip().startswith('http'))

        # 所有模式都使用 LLM 生成（不再区分模板/LLM 模式）
        return self._generate_with_llm(customer_name, website, progress_callback, target_word_count, selected_material_ids, skip_refine=skip_refine, skip_format=skip_format, language=language, opening_template=opening_template)


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
