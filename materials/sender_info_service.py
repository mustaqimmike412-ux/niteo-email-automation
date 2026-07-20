#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发信人信息服务
将发信人信息从硬编码 JSON 迁移到数据库 materials 表，支持 per-user 配置。
"""

import json
import os
from typing import Dict, List, Optional

from database.material_models import get_sender_info_material


# 默认发信人信息（已清空，所有信息由用户自行配置）
DEFAULT_SENDER_INFO = {
    "sender_name": "",
    "job_title": "",
    "company_name": "",
    "company_website": "",
    "sender_email": "",
    "signature": ""
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


def _normalize_sender_content(content: Dict) -> Dict:
    """统一发信人内容格式"""
    return {
        'sender_name': content.get('sender_name', DEFAULT_SENDER_INFO['sender_name']),
        'job_title': content.get('job_title', DEFAULT_SENDER_INFO['job_title']),
        'company_name': content.get('company_name', DEFAULT_SENDER_INFO['company_name']),
        'company_website': content.get('company_website', DEFAULT_SENDER_INFO['company_website']),
        'sender_email': content.get('sender_email', DEFAULT_SENDER_INFO['sender_email']),
        'signature': content.get('signature', DEFAULT_SENDER_INFO['signature'])
    }


def get_sender_info(user_id: int = None, admin: bool = False) -> Dict:
    """
    获取发信人信息（默认第一条）。
    优先级：
    1. 用户私有的 sender_info 素材（user_id 匹配）
    2. 系统公共的 sender_info 素材（user_id IS NULL）
    3. config/company_info.json 配置文件
    4. 硬编码默认值
    """
    material = get_sender_info_material(user_id=user_id, admin=admin)
    if material:
        content = material.get('content') or material.get('content_json') or {}
        if content:
            return _normalize_sender_content(content)
    return _load_sender_info_from_json()


def get_sender_info_by_id(material_id: int, user_id: int = None, admin: bool = False) -> Optional[Dict]:
    """
    按 ID 获取特定发信人信息。
    """
    from database.material_models import get_material_by_id
    material = get_material_by_id(material_id, user_id=user_id, admin=admin)
    if material and material.get('content_json'):
        result = _normalize_sender_content(material['content_json'])
        result['material_id'] = material_id
        return result
    return None


def get_sender_info_list(user_id: int = None, admin: bool = False) -> List[Dict]:
    """
    获取所有发信人模板列表。
    返回每个模板的 id, name, content_json 摘要。
    """
    from database.material_models import get_materials_by_type
    materials = get_materials_by_type('sender_info', user_id=user_id, admin=admin)
    result = []
    for m in materials:
        content = m.get('content') or m.get('content_json') or {}
        result.append({
            'id': m.get('id'),
            'name': m.get('name') or content.get('sender_name', 'Unknown'),
            'sender_name': content.get('sender_name', ''),
            'job_title': content.get('job_title', ''),
            'company_name': content.get('company_name', ''),
            'sender_email': content.get('sender_email', ''),
            'signature': content.get('signature', ''),
            'is_public': m.get('is_public', 0),
            'user_id': m.get('user_id'),
        })
    return result


def save_sender_info(data: Dict, user_id: int = None, material_id: int = None) -> int:
    """
    保存发信人信息到 materials 表。
    
    Args:
        data: 发信人信息字典，需包含 sender_name, job_title, company_name 等字段
        user_id: 用户 ID（None 表示系统公共）
        material_id: 指定素材 ID（编辑模式），None 表示新建
    
    Returns:
        素材 ID
    """
    from database.material_models import create_material, get_material_by_id, update_material
    
    # 生成唯一 material_key
    import time
    ts = str(int(time.time()))
    material_key = f"sender_info_{user_id or 'system'}_{ts}"
    if material_id:
        existing = get_material_by_id(material_id, user_id=user_id, admin=False)
        if existing:
            material_key = existing.get('material_key', material_key)

    material_data = {
        'material_key': material_key,
        'name': f"{data.get('sender_name', 'Sender')}",
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

    if material_id:
        existing = get_material_by_id(material_id, user_id=user_id, admin=False)
        if existing:
            update_material(material_id, material_data, user_id=user_id, admin=False)
            return material_id

    return create_material(material_data, user_id=user_id)
