import json
import sqlite3
from typing import Dict, List, Optional
from database.connection import get_connection

# 内存缓存
_materials_cache = {}
_cache_loaded = False


def _load_cache():
    """将数据库素材加载到内存缓存"""
    global _cache_loaded
    if _cache_loaded:
        return
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT material_key, material_type, category, scope, track,
                   region, content_json, content_summary, priority, is_active, id, user_id
            FROM materials WHERE is_active = 1
        """)
        _materials_cache.clear()
        for row in cursor.fetchall():
            _materials_cache[row[0]] = {
                'id': row[10],
                'material_key': row[0],
                'material_type': row[1],
                'category': row[2],
                'scope': row[3],
                'track': row[4],
                'region': row[5],
                'content': json.loads(row[6]) if row[6] else {},
                'summary': row[7],
                'priority': row[8] or 0,
                'is_active': row[9],
                'user_id': row[11]
            }
        conn.close()
        _cache_loaded = True
    except Exception as e:
        print(f"  ⚠ 加载素材缓存失败: {e}")
        _cache_loaded = False


def invalidate_cache():
    """使缓存失效（数据变更后调用）"""
    global _cache_loaded, _materials_cache
    _materials_cache = {}
    _cache_loaded = False


def get_material(material_key: str, user_id: int = None, admin: bool = False) -> Optional[Dict]:
    """获取单个素材"""
    _load_cache()
    mat = _materials_cache.get(material_key)
    if mat and not admin and user_id:
        if mat.get('user_id') is not None and mat.get('user_id') != user_id:
            return None
    return mat


def get_materials_by_type(material_type: str, user_id: int = None, admin: bool = False, **filters) -> List[Dict]:
    """按类型和条件筛选素材（支持 user_id 隔离）"""
    _load_cache()
    results = []
    for key, mat in _materials_cache.items():
        if mat['material_type'] != material_type:
            continue
        # user_id 隔离：用户只能看到私有素材 + 系统公共素材(user_id IS NULL)
        if not admin and user_id is not None:
            mat_user_id = mat.get('user_id')
            if mat_user_id is not None and mat_user_id != user_id:
                continue
        match = True
        for k, v in filters.items():
            if v and mat.get(k) != v:
                match = False
                break
        if match:
            results.append(mat)
    return sorted(results, key=lambda x: x.get('priority', 0), reverse=True)


def get_advantages_by_power_type_db(power_type: str, user_id=None, admin=False) -> List[Dict]:
    """根据功率类型获取优势列表（数据库版，支持 user_id 隔离）"""
    scope = 'small_power' if power_type == 'Low Power' else 'large_power'
    materials = get_materials_by_type('advantage', user_id=user_id, admin=admin)
    result = []
    for mat in materials:
        content = mat['content']
        mat_scope = mat.get('scope', 'all')
        if mat_scope == 'all' or mat_scope == scope:
            result.append(content)
    return result[:4]


def get_cases_by_track_db(track: str, user_id=None, admin=False) -> List[Dict]:
    """根据赛道获取案例列表（数据库版，支持 user_id 隔离）"""
    materials = get_materials_by_type('case_study', user_id=user_id, admin=admin)
    result = []
    for mat in materials:
        if mat.get('track') and mat['track'].lower() in track.lower():
            result.append(mat['content'])
    return result


def get_brochure_by_power_type_db(power_type: str, user_id=None, admin=False) -> Dict:
    """根据功率类型获取宣传册素材（数据库版，支持 user_id 隔离）"""
    scope = 'small_power' if power_type == 'Low Power' else 'large_power'
    materials = get_materials_by_type('brochure', user_id=user_id, admin=admin)
    result = {}
    for mat in materials:
        content = mat['content']
        mat_scope = mat.get('scope', 'all')
        if mat_scope == 'all' or mat_scope == scope:
            result[mat['material_key']] = content
    return result


def get_storage_brochure_db(user_id=None, admin=False) -> Dict:
    """获取储能宣传册素材（数据库版，支持 user_id 隔离）"""
    materials = get_materials_by_type('storage', user_id=user_id, admin=admin)
    result = {}
    for mat in materials:
        result[mat['material_key']] = mat['content']
    return result


def get_case_workflow_rules_db(track: str, region: str = "", user_id=None, admin=False) -> Dict:
    """获取案例调用规则（数据库版，支持 user_id 隔离）"""
    materials = get_materials_by_type('rule', user_id=user_id, admin=admin)
    track_rules = {}
    for mat in materials:
        if mat.get('track') == track:
            track_rules = mat['content']
            break

    result = {
        'case_priority': track_rules.get('case_priority', []),
        'tech_priority': track_rules.get('tech_priority', []),
        'delivery': track_rules.get('delivery', '')
    }

    if region:
        for mat in materials:
            if mat.get('region') == region:
                region_content = mat['content']
                result['mandatory_add'] = region_content.get('mandatory_add', [])
                result['case_endorsement'] = region_content.get('case_endorsement', '')
                result['emphasis'] = region_content.get('emphasis', '')
                break

    return result


def get_material_library_db(user_id: int = None, admin: bool = False) -> Dict:
    """获取完整素材库（数据库版，支持 user_id 隔离）"""
    _load_cache()
    result = {}
    for key, mat in _materials_cache.items():
        # user_id 隔离：用户只能看到私有素材 + 系统公共素材(user_id IS NULL)
        if not admin and user_id is not None:
            mat_user_id = mat.get('user_id')
            if mat_user_id is not None and mat_user_id != user_id:
                continue
        result[key] = mat['content']
    return result


def get_sender_info_material(user_id: int = None, admin: bool = False) -> Optional[Dict]:
    """获取发信人信息素材（按优先级：用户私有 > 系统公共）"""
    materials = get_materials_by_type('sender_info', user_id=user_id, admin=admin)
    if not materials:
        return None
    # 优先返回用户私有的（user_id 匹配）
    if user_id and not admin:
        personal = [m for m in materials if m.get('user_id') == user_id]
        if personal:
            return personal[0]
    # 否则返回系统公共的（user_id IS NULL）
    public = [m for m in materials if m.get('user_id') is None]
    if public:
        return public[0]
    # 最后回退到第一个
    return materials[0]


def log_material_usage(material_id: int, customer_id: int = None,
                       email_log_id: int = None, context: str = "",
                       user_id: int = None):
    """记录素材使用日志"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO material_usage_log (material_id, customer_id, email_log_id, usage_context, user_id)
            VALUES (?, ?, ?, ?, ?)
        """, (material_id, customer_id, email_log_id, context, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  ⚠ 记录素材使用日志失败: {e}")


def get_material_usage_logs(page=1, per_page=20, user_id=None, admin=False) -> Dict:
    """获取素材使用日志列表（分页）"""
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []
    if not admin and user_id:
        where_clauses.append("user_id = ?")
        params.append(user_id)

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    cursor.execute(f"SELECT COUNT(*) FROM material_usage_log {where_sql}", params)
    total = cursor.fetchone()[0]

    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT id, material_id, customer_id, email_log_id, usage_context, created_at, user_id
        FROM material_usage_log {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])

    logs = []
    for row in cursor.fetchall():
        logs.append({
            'id': row[0], 'material_id': row[1], 'customer_id': row[2],
            'email_log_id': row[3], 'usage_context': row[4],
            'created_at': row[5], 'user_id': row[6]
        })

    conn.close()
    return {
        'logs': logs,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    }


# ========== CRUD 操作（供 API 使用）==========

def get_materials_list(material_type=None, category=None, scope=None, track=None,
                       region=None, search=None, active_only=True,
                       page=1, per_page=20, user_id=None, admin=False) -> Dict:
    """获取资料列表（支持筛选、分页、搜索）"""
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if material_type:
        where_clauses.append("material_type = ?")
        params.append(material_type)
    if category:
        where_clauses.append("category = ?")
        params.append(category)
    if scope:
        where_clauses.append("scope = ?")
        params.append(scope)
    if track:
        where_clauses.append("track = ?")
        params.append(track)
    if region:
        where_clauses.append("region = ?")
        params.append(region)
    if active_only:
        where_clauses.append("is_active = 1")
    if search:
        where_clauses.append("(name LIKE ? OR content_summary LIKE ? OR tags LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    if not admin and user_id:
        where_clauses.append("user_id = ?")
        params.append(user_id)

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # 总数
    cursor.execute(f"SELECT COUNT(*) FROM materials {where_sql}", params)
    total = cursor.fetchone()[0]

    # 分页数据
    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT id, material_key, name, material_type, category, scope, track,
               region, content_summary, priority, is_active, has_attachment,
               tags, created_at, updated_at
        FROM materials {where_sql}
        ORDER BY priority DESC, updated_at DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])

    materials = []
    for row in cursor.fetchall():
        materials.append({
            'id': row[0], 'material_key': row[1], 'name': row[2],
            'material_type': row[3], 'category': row[4], 'scope': row[5],
            'track': row[6], 'region': row[7], 'content_summary': row[8],
            'priority': row[9], 'is_active': row[10], 'has_attachment': row[11],
            'tags': row[12], 'created_at': row[13], 'updated_at': row[14]
        })

    conn.close()

    return {
        'materials': materials,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    }


def get_material_by_id(material_id: int, user_id: int = None, admin: bool = False) -> Optional[Dict]:
    """根据 ID 获取素材详情"""
    conn = get_connection()
    cursor = conn.cursor()
    if not admin and user_id:
        cursor.execute("""
            SELECT id, material_key, name, material_type, category, scope, track,
                   region, content_json, content_summary, priority, is_active,
                   has_attachment, attachment_path, attachment_type, attachment_name,
                   tags, source, created_at, updated_at
            FROM materials WHERE id = ? AND user_id = ?
        """, (material_id, user_id))
    else:
        cursor.execute("""
            SELECT id, material_key, name, material_type, category, scope, track,
                   region, content_json, content_summary, priority, is_active,
                   has_attachment, attachment_path, attachment_type, attachment_name,
                   tags, source, created_at, updated_at
            FROM materials WHERE id = ?
        """, (material_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        'id': row[0], 'material_key': row[1], 'name': row[2],
        'material_type': row[3], 'category': row[4], 'scope': row[5],
        'track': row[6], 'region': row[7],
        'content_json': json.loads(row[8]) if row[8] else {},
        'content_summary': row[9], 'priority': row[10], 'is_active': row[11],
        'has_attachment': row[12], 'attachment_path': row[13],
        'attachment_type': row[14], 'attachment_name': row[15],
        'tags': row[16], 'source': row[17],
        'created_at': row[18], 'updated_at': row[19]
    }


def create_material(data: Dict, user_id: int = None) -> int:
    """创建新素材"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO materials (material_key, name, material_type, category, scope, track,
                               region, content_json, content_summary, priority, is_active,
                               tags, source, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('material_key', ''), data.get('name', ''),
        data.get('material_type', ''), data.get('category', ''),
        data.get('scope', ''), data.get('track', ''),
        data.get('region', ''),
        json.dumps(data.get('content_json', {}), ensure_ascii=False),
        data.get('content_summary', ''),
        data.get('priority', 0), data.get('is_active', 1),
        data.get('tags', ''), data.get('source', 'manual'),
        user_id
    ))
    material_id = cursor.lastrowid
    conn.commit()
    conn.close()
    invalidate_cache()
    return material_id


def update_material(material_id: int, data: Dict, user_id: int = None, admin: bool = False) -> bool:
    """更新素材"""
    conn = get_connection()
    cursor = conn.cursor()

    fields = []
    params = []
    for key in ['material_key', 'name', 'material_type', 'category', 'scope',
                'track', 'region', 'content_summary', 'priority', 'is_active',
                'tags']:
        if key in data:
            fields.append(f"{key} = ?")
            params.append(data[key])

    if 'content_json' in data:
        fields.append("content_json = ?")
        params.append(json.dumps(data['content_json'], ensure_ascii=False))

    if fields:
        fields.append("updated_at = datetime('now')")
        if not admin and user_id:
            params.extend([material_id, user_id])
            cursor.execute(f"UPDATE materials SET {', '.join(fields)} WHERE id = ? AND user_id = ?", params)
        else:
            params.append(material_id)
            cursor.execute(f"UPDATE materials SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()

    conn.close()
    invalidate_cache()
    return True


def delete_material(material_id: int, user_id: int = None, admin: bool = False) -> bool:
    """删除素材"""
    conn = get_connection()
    cursor = conn.cursor()
    if not admin and user_id:
        cursor.execute("DELETE FROM materials WHERE id = ? AND user_id = ?", (material_id, user_id))
    else:
        cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()
    invalidate_cache()
    return True


def get_material_types(user_id: int = None, admin: bool = False) -> List[str]:
    """获取所有素材类型"""
    conn = get_connection()
    cursor = conn.cursor()
    if not admin and user_id:
        cursor.execute("SELECT DISTINCT material_type FROM materials WHERE user_id = ? ORDER BY material_type", (user_id,))
    else:
        cursor.execute("SELECT DISTINCT material_type FROM materials ORDER BY material_type")
    types = [row[0] for row in cursor.fetchall()]
    conn.close()
    return types


def get_material_categories() -> List[str]:
    """获取所有分类"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category FROM materials WHERE category IS NOT NULL ORDER BY category")
    categories = [row[0] for row in cursor.fetchall()]
    conn.close()
    return categories


def get_material_tracks() -> List[str]:
    """获取所有赛道"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT track FROM materials WHERE track IS NOT NULL ORDER BY track")
    tracks = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tracks


def get_material_stats(user_id: int = None, admin: bool = False) -> Dict:
    """获取素材库统计"""
    conn = get_connection()
    cursor = conn.cursor()

    user_where = " WHERE user_id = ?" if (not admin and user_id) else ""
    user_params = [user_id] if (not admin and user_id) else []

    cursor.execute(f"SELECT COUNT(*) FROM materials{user_where}", user_params)
    total = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM materials WHERE is_active = 1{' AND user_id = ?' if (not admin and user_id) else ''}", user_params)
    active = cursor.fetchone()[0]

    cursor.execute(f"SELECT material_type, COUNT(*) FROM materials{' WHERE user_id = ?' if (not admin and user_id) else ''} GROUP BY material_type", user_params)
    type_counts = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute(f"SELECT COUNT(*) FROM material_usage_log{user_where}", user_params)
    usage_count = cursor.fetchone()[0]

    conn.close()
    return {
        'total': total,
        'active': active,
        'inactive': total - active,
        'type_counts': type_counts,
        'usage_count': usage_count
    }


def update_attachment(material_id: int, attachment_path: str, attachment_type: str, attachment_name: str):
    """更新附件信息"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE materials
        SET has_attachment = 1, attachment_path = ?, attachment_type = ?, attachment_name = ?,
            updated_at = datetime('now')
        WHERE id = ?
    """, (attachment_path, attachment_type, attachment_name, material_id))
    conn.commit()
    conn.close()
    invalidate_cache()


def remove_attachment(material_id: int):
    """移除附件信息"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE materials
        SET has_attachment = 0, attachment_path = NULL, attachment_type = NULL, attachment_name = NULL,
            updated_at = datetime('now')
        WHERE id = ?
    """, (material_id,))
    conn.commit()
    conn.close()
    invalidate_cache()
