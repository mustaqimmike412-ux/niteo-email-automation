#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发信人信息服务
将发信人信息从硬编码 JSON 迁移到数据库 materials 表，支持 per-user 配置。
"""

import json
import os
from typing import Dict, Optional

from database.material_models import get_sender_info_material


# 默认发信人信息（最后的回退）
DEFAULT_SENDER_INFO = {
    "sender_name": "Travis",
    "job_title": "Business Development Manager",
    "company_name": "Niteo Solar",
    "company_website": "https://www.niteosolar.com",
    "sender_email": "travisturner89@gmail.com",
    "signature": "Travis\nBusiness Development Manager\nNiteo Solar"
}


def _load_sender_info_from_json() -> Dict:
    """从 JSON 配置文件读取发信人信息（兼容旧版）"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'company_info.json'
    )
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保返回结构一致
                return {
                    'sender_name': data.get('sender_name', DEFAULT_SENDER_INFO['sender_name']),
                    'job_title': data.get('job_title', DEFAULT_SENDER_INFO['job_title']),
                    'company_name': data.get('company_name', DEFAULT_SENDER_INFO['company_name']),
                    'company_website': data.get('company_website', DEFAULT_SENDER_INFO['company_website']),
                    'sender_email': data.get('sender_email', DEFAULT_SENDER_INFO['sender_email']),
                    'signature': data.get('signature', DEFAULT_SENDER_INFO['signature'])
                }
        except Exception as e:
            print(f"[sender_info_service] 读取 JSON 配置失败: {e}")
    return DEFAULT_SENDER_INFO.copy()


def get_sender_info(user_id: int = None, admin: bool = False) -> Dict:
    """
    获取发信人信息。
    
    优先级：
    1. 用户私有的 sender_info 素材（user_id 匹配）
    2. 系统公共的 sender_info 素材（user_id IS NULL）
    3. config/company_info.json 配置文件
    4. 硬编码默认值
    
    返回结构保持与现有 JSON 完全一致，避免邮件生成格式变化。
    """
    # 1. 尝试从数据库读取
    material = get_sender_info_material(user_id=user_id, admin=admin)
    if material and material.get('content_json'):
        content = material['content_json']
        # 确保返回结构一致
        return {
            'sender_name': content.get('sender_name', DEFAULT_SENDER_INFO['sender_name']),
            'job_title': content.get('job_title', DEFAULT_SENDER_INFO['job_title']),
            'company_name': content.get('company_name', DEFAULT_SENDER_INFO['company_name']),
            'company_website': content.get('company_website', DEFAULT_SENDER_INFO['company_website']),
            'sender_email': content.get('sender_email', DEFAULT_SENDER_INFO['sender_email']),
            'signature': content.get('signature', DEFAULT_SENDER_INFO['signature'])
        }
    
    # 2. 回退到 JSON 配置文件
    return _load_sender_info_from_json()


def save_sender_info(data: Dict, user_id: int = None) -> int:
    """
    保存发信人信息到 materials 表。
    
    Args:
        data: 发信人信息字典，需包含 sender_name, job_title, company_name 等字段
        user_id: 用户 ID（None 表示系统公共）
    
    Returns:
        素材 ID
    """
    from database.material_models import create_material, get_materials_by_type, update_material
    
    # 检查是否已存在
    existing = get_sender_info_material(user_id=user_id, admin=True)
    
    material_data = {
        'material_key': f'sender_info_{user_id or "system"}',
        'name': f"{data.get('sender_name', 'Sender')} - 发信人资料",
        'material_type': 'sender_info',
        'category': 'sender_profile',
        'scope': 'all',
        'content_json': data,
        'content_summary': f"{data.get('sender_name')} at {data.get('company_name')}, {data.get('job_title')}",
        'priority': 10,
        'is_active': 1,
        'tags': 'sender,profile',
        'source': 'user' if user_id else 'system'
    }
    
    if existing:
        update_material(existing['id'], material_data, user_id=user_id, admin=True)
        return existing['id']
    else:
        return create_material(material_data, user_id=user_id)
