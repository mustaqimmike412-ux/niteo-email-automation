"""
API 配置管理模块
支持 DeepSeek、Google Places 等 API 的增删改查
"""
import json
from database.connection import get_connection


def get_all_api_configs(user_id: int = None, admin: bool = False):
    """获取所有 API 配置"""
    conn = get_connection()
    cursor = conn.cursor()
    if not admin and user_id:
        cursor.execute('''
            SELECT id, api_name, api_key, base_url, model, extra_config, is_active, created_at, updated_at
            FROM api_configs WHERE (user_id = ? OR user_id IS NULL) ORDER BY id DESC
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT id, api_name, api_key, base_url, model, extra_config, is_active, created_at, updated_at
            FROM api_configs ORDER BY id DESC
        ''')
    rows = cursor.fetchall()
    conn.close()
    return [{
        'id': r[0],
        'api_name': r[1],
        'api_key': r[2],
        'base_url': r[3],
        'model': r[4],
        'extra_config': json.loads(r[5]) if r[5] else {},
        'is_active': bool(r[6]),
        'created_at': r[7],
        'updated_at': r[8]
    } for r in rows]


def get_api_config(api_name: str, user_id: int = None, admin: bool = False):
    """根据名称获取 API 配置"""
    conn = get_connection()
    cursor = conn.cursor()
    if not admin and user_id:
        cursor.execute('''
            SELECT id, api_name, api_key, base_url, model, extra_config, is_active
            FROM api_configs WHERE api_name = ? AND is_active = 1 AND (user_id = ? OR user_id IS NULL)
        ''', (api_name, user_id))
    else:
        cursor.execute('''
            SELECT id, api_name, api_key, base_url, model, extra_config, is_active
            FROM api_configs WHERE api_name = ? AND is_active = 1
        ''', (api_name,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        'id': row[0],
        'api_name': row[1],
        'api_key': row[2],
        'base_url': row[3],
        'model': row[4],
        'extra_config': json.loads(row[5]) if row[5] else {},
        'is_active': bool(row[6])
    }


def get_api_key(api_name: str) -> str:
    """快速获取 API Key（仅返回 key 字符串）"""
    cfg = get_api_config(api_name)
    return cfg['api_key'] if cfg else ''


def create_api_config(api_name: str, api_key: str, base_url: str = '',
                      model: str = '', extra_config: dict = None, user_id: int = None) -> bool:
    """创建 API 配置"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO api_configs (api_name, api_key, base_url, model, extra_config, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (api_name, api_key, base_url, model,
              json.dumps(extra_config) if extra_config else None, user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[APIConfig] 创建失败: {e}")
        return False
    finally:
        conn.close()


def update_api_config(api_name: str, api_key: str = None, base_url: str = None,
                      model: str = None, extra_config: dict = None,
                      is_active: bool = None, user_id: int = None, admin: bool = False) -> bool:
    """更新 API 配置"""
    conn = get_connection()
    cursor = conn.cursor()
    sets = ['updated_at = CURRENT_TIMESTAMP']
    params = []
    if api_key is not None:
        sets.append('api_key = ?')
        params.append(api_key)
    if base_url is not None:
        sets.append('base_url = ?')
        params.append(base_url)
    if model is not None:
        sets.append('model = ?')
        params.append(model)
    if extra_config is not None:
        sets.append('extra_config = ?')
        params.append(json.dumps(extra_config))
    if is_active is not None:
        sets.append('is_active = ?')
        params.append(1 if is_active else 0)
    if not sets:
        conn.close()
        return False
    params.append(api_name)
    where_extra = ""
    if not admin and user_id:
        where_extra = " AND (user_id = ? OR user_id IS NULL)"
        params.append(user_id)
    cursor.execute(f"UPDATE api_configs SET {', '.join(sets)} WHERE api_name = ?{where_extra}", params)
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def delete_api_config(api_name: str, user_id: int = None, admin: bool = False) -> bool:
    """删除 API 配置"""
    conn = get_connection()
    cursor = conn.cursor()
    if not admin and user_id:
        cursor.execute('DELETE FROM api_configs WHERE api_name = ? AND (user_id = ? OR user_id IS NULL)', (api_name, user_id))
    else:
        cursor.execute('DELETE FROM api_configs WHERE api_name = ?', (api_name,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def init_default_configs():
    """初始化默认配置（从现有 JSON 文件迁移）"""
    import os

    # 尝试从 llm_config.json 读取 DeepSeek 配置
    try:
        llm_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'config', 'llm_config.json')
        if os.path.exists(llm_path):
            with open(llm_path, 'r', encoding='utf-8') as f:
                llm_cfg = json.load(f)
            if llm_cfg.get('api_key') and not get_api_config('DeepSeek'):
                create_api_config(
                    api_name='DeepSeek',
                    api_key=llm_cfg.get('api_key', ''),
                    base_url=llm_cfg.get('base_url', 'https://api.deepseek.com'),
                    model=llm_cfg.get('model', 'deepseek-v4-pro')
                )
                print("[APIConfig] 已迁移 DeepSeek 配置到数据库")
    except Exception as e:
        print(f"[APIConfig] DeepSeek 迁移失败: {e}")

    # 尝试从 search_config.json 读取 Google Places 配置
    try:
        search_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   'config', 'search_config.json')
        if os.path.exists(search_path):
            with open(search_path, 'r', encoding='utf-8') as f:
                search_cfg = json.load(f)
            if search_cfg.get('google_places_api_key') and not get_api_config('Google Places'):
                create_api_config(
                    api_name='Google Places',
                    api_key=search_cfg.get('google_places_api_key', ''),
                    base_url='https://maps.googleapis.com/maps/api',
                    extra_config={'engine': search_cfg.get('web_search_engine', 'duckduckgo')}
                )
                print("[APIConfig] 已迁移 Google Places 配置到数据库")
    except Exception as e:
        print(f"[APIConfig] Google Places 迁移失败: {e}")
