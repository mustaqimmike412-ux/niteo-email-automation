"""统一素材访问接口 - 优先查数据库，缺失时回退到种子数据"""
import json
from database.connection import get_connection
from materials.seed_data import (
    MATERIAL_LIBRARY,
    get_advantages_by_power_type as _fallback_get_advantages_by_power_type,
    get_cases_by_track,
    get_brochure_by_power_type,
    get_storage_brochure,
    get_case_workflow_rules,
    get_ring_case_for_email,
    get_arlo_case_for_email,
    get_eufy_case_for_email,
)


def get_material(material_key):
    """优先从数据库查询，缺失时回退到种子数据"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
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
    return MATERIAL_LIBRARY.get(material_key)


def get_material_library(user_id: int = None, admin: bool = False):
    """获取完整素材库（支持 user_id 隔离）"""
    try:
        from database.material_models import get_material_library_db
        result = get_material_library_db(user_id=user_id, admin=admin)
        if result:
            return result
    except Exception:
        pass
    return MATERIAL_LIBRARY


def get_advantages_by_power_type(power_type: str) -> list:
    """根据功率类型获取优势列表（优先数据库）"""
    try:
        from database.material_models import get_advantages_by_power_type_db
        result = get_advantages_by_power_type_db(power_type)
        if result:
            return result
    except Exception:
        pass
    return _fallback_get_advantages_by_power_type(power_type)


# 导出兼容接口
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
