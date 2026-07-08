import json
from database.connection import get_connection


def get_user_setting(user_id, setting_type):
    """获取单个用户设置，返回解析后的 dict/list，不存在返回 None"""
    if not user_id:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT setting_json FROM user_settings WHERE user_id = ? AND setting_type = ?',
        (user_id, setting_type)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return {}
    return None


def save_user_setting(user_id, setting_type, setting_json):
    """保存/更新用户设置（UPSERT），setting_json 可以是 dict/list 或已序列化的字符串"""
    if not user_id:
        raise ValueError('user_id is required')
    conn = get_connection()
    cursor = conn.cursor()
    if isinstance(setting_json, (dict, list)):
        setting_json_str = json.dumps(setting_json, ensure_ascii=False)
    else:
        setting_json_str = str(setting_json)
    cursor.execute(
        '''INSERT INTO user_settings (user_id, setting_type, setting_json, updated_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(user_id, setting_type) DO UPDATE SET
           setting_json = excluded.setting_json,
           updated_at = CURRENT_TIMESTAMP''',
        (user_id, setting_type, setting_json_str)
    )
    conn.commit()
    conn.close()


def get_all_user_settings(user_id):
    """获取用户所有设置，返回 {setting_type: parsed_json, ...}"""
    if not user_id:
        return {}
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT setting_type, setting_json FROM user_settings WHERE user_id = ?',
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    result = {}
    for row in rows:
        try:
            result[row[0]] = json.loads(row[1])
        except (json.JSONDecodeError, TypeError):
            result[row[0]] = {}
    return result
