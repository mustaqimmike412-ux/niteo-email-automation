"""种子数据 - 已清空所有公司底层数据

所有素材数据改为用户自行导入，通过数据库 materials 表按 user_id 隔离。
新用户未导入数据时，邮件内容由 AI 生成，不使用任何预设公司信息。
"""

# 空的素材库结构（仅作为数据结构参考，不包含任何实际数据）
MATERIAL_LIBRARY = {
    "company_intro": {},
    "solar_panel_brochure": {},
    "energy_storage_brochure": {},
    "case_ring": {},
    "case_arlo": {},
    "case_eufy": {},
    "material_rules": {"by_track": {}, "by_region": {}},
}


def get_advantages_by_power_type(power_type: str) -> list:
    """已废弃 - 优势数据应由用户通过资料管理库导入"""
    return []


def get_cases_by_track(track: str) -> list:
    """已废弃 - 案例数据应由用户通过资料管理库导入"""
    return []


def get_brochure_by_power_type(power_type: str) -> dict:
    """已废弃 - 宣传册数据应由用户通过资料管理库导入"""
    return {}


def get_storage_brochure() -> dict:
    """已废弃 - 储能宣传册数据应由用户通过资料管理库导入"""
    return {}


def get_case_workflow_rules(track: str, region: str = "") -> dict:
    """已废弃 - 规则数据应由用户通过资料管理库导入"""
    return {"case_priority": [], "tech_priority": [], "delivery": ""}


def get_ring_case_for_email(customer_type: str) -> str:
    """已废弃 - 案例话术应由用户通过资料管理库导入"""
    return ""


def get_arlo_case_for_email(customer_type: str) -> str:
    """已废弃 - 案例话术应由用户通过资料管理库导入"""
    return ""


def get_eufy_case_for_email(customer_type: str) -> str:
    """已废弃 - 案例话术应由用户通过资料管理库导入"""
    return ""
