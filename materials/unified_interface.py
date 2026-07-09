"""统一素材访问接口 - 所有数据从数据库按 user_id 隔离加载，不再回退到种子数据"""
import json
from database.connection import get_connection
from database.material_models import (
    get_materials_by_type,
    get_advantages_by_power_type_db,
    get_cases_by_track_db,
    get_brochure_by_power_type_db,
    get_storage_brochure_db,
    get_case_workflow_rules_db,
)

# 空素材库（不再包含任何公司数据）
MATERIAL_LIBRARY = {
    "company_intro": {},
    "solar_panel_brochure": {},
    "energy_storage_brochure": {},
    "case_ring": {},
    "case_arlo": {},
    "case_eufy": {},
    "material_rules": {"by_track": {}, "by_region": {}},
}


def get_material(material_key, user_id=None, admin=False):
    """从数据库查询素材（支持 user_id 隔离）"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if user_id and not admin:
            cursor.execute(
                'SELECT content_json FROM materials WHERE material_key = ? AND is_active = 1 AND (user_id IS NULL OR user_id = ?)',
                (material_key, user_id),
            )
        else:
            cursor.execute(
                'SELECT content_json FROM materials WHERE material_key = ? AND is_active = 1',
                (material_key,),
            )
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception:
        pass
    return MATERIAL_LIBRARY.get(material_key, {})


def get_material_library(user_id=None, admin=False):
    """获取完整素材库（支持 user_id 隔离）"""
    try:
        from database.material_models import get_material_library_db
        result = get_material_library_db(user_id=user_id, admin=admin)
        if result:
            return result
    except Exception:
        pass
    return MATERIAL_LIBRARY


def get_advantages_by_power_type(power_type, user_id=None, admin=False):
    """根据功率类型获取优势列表（按 user_id 隔离）"""
    try:
        result = get_advantages_by_power_type_db(power_type, user_id=user_id, admin=admin)
        if result:
            return result
    except Exception:
        pass
    return []


def get_cases_by_track(track, user_id=None, admin=False):
    """根据赛道获取案例列表（按 user_id 隔离）"""
    try:
        result = get_cases_by_track_db(track, user_id=user_id, admin=admin)
        if result:
            return result
    except Exception:
        pass
    return []


def get_brochure_by_power_type(power_type, user_id=None, admin=False):
    """根据功率类型获取宣传册素材（按 user_id 隔离）"""
    try:
        result = get_brochure_by_power_type_db(power_type, user_id=user_id, admin=admin)
        if result:
            return result
    except Exception:
        pass
    return {}


def get_storage_brochure(user_id=None, admin=False):
    """获取储能宣传册素材（按 user_id 隔离）"""
    try:
        result = get_storage_brochure_db(user_id=user_id, admin=admin)
        if result:
            return result
    except Exception:
        pass
    return {}


def get_case_workflow_rules(track, region="", user_id=None, admin=False):
    """根据赛道和地区获取案例调用规则（按 user_id 隔离）"""
    try:
        result = get_case_workflow_rules_db(track, region, user_id=user_id, admin=admin)
        if result:
            return result
    except Exception:
        pass
    return {"case_priority": [], "tech_priority": [], "delivery": ""}


def get_ring_case_for_email(customer_type, user_id=None, admin=False):
    """从数据库获取 Ring 案例话术（按 user_id 隔离）"""
    try:
        materials = get_materials_by_type('case_study', user_id=user_id, admin=admin)
        for mat in materials:
            content = mat.get('content', {})
            name = mat.get('name', '').lower()
            if 'ring' in name:
                return content.get('email_copy', '') or content.get('summary', '') or str(content)[:500]
    except Exception:
        pass
    return ""


def get_arlo_case_for_email(customer_type, user_id=None, admin=False):
    """从数据库获取 Arlo 案例话术（按 user_id 隔离）"""
    try:
        materials = get_materials_by_type('case_study', user_id=user_id, admin=admin)
        for mat in materials:
            content = mat.get('content', {})
            name = mat.get('name', '').lower()
            if 'arlo' in name:
                return content.get('email_copy', '') or content.get('summary', '') or str(content)[:500]
    except Exception:
        pass
    return ""


def get_eufy_case_for_email(customer_type, user_id=None, admin=False):
    """从数据库获取 Eufy 案例话术（按 user_id 隔离）"""
    try:
        materials = get_materials_by_type('case_study', user_id=user_id, admin=admin)
        for mat in materials:
            content = mat.get('content', {})
            name = mat.get('name', '').lower()
            if 'eufy' in name:
                return content.get('email_copy', '') or content.get('summary', '') or str(content)[:500]
    except Exception:
        pass
    return ""


__all__ = [
    'MATERIAL_LIBRARY',
    'get_material',
    'get_material_library',
    'get_advantages_by_power_type',
    'get_cases_by_track',
    'get_brochure_by_power_type',
    'get_storage_brochure',
    'get_case_workflow_rules',
    'get_ring_case_for_email',
    'get_arlo_case_for_email',
    'get_eufy_case_for_email',
]
