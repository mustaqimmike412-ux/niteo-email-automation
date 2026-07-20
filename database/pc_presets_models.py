"""邮件限定预设 CRUD 模型"""
import json
from database.connection import get_connection


def get_pc_presets(user_id):
    """获取用户的所有邮件限定预设"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, description, preset_json, is_default, created_at, updated_at '
        'FROM pc_presets WHERE user_id = ? ORDER BY is_default DESC, updated_at DESC',
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    presets = []
    for r in rows:
        try:
            preset_data = json.loads(r[3])
        except:
            preset_data = {}
        presets.append({
            'id': r[0],
            'name': r[1],
            'description': r[2],
            'preset': preset_data,
            'is_default': r[4],
            'created_at': r[5],
            'updated_at': r[6]
        })
    return presets


def get_pc_preset(preset_id, user_id=None):
    """获取单个预设"""
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute(
            'SELECT id, name, description, preset_json, is_default FROM pc_presets WHERE id = ? AND user_id = ?',
            (preset_id, user_id)
        )
    else:
        cursor.execute(
            'SELECT id, name, description, preset_json, is_default FROM pc_presets WHERE id = ?',
            (preset_id,)
        )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    try:
        preset_data = json.loads(row[3])
    except:
        preset_data = {}
    return {
        'id': row[0],
        'name': row[1],
        'description': row[2],
        'preset': preset_data,
        'is_default': row[4]
    }


def save_pc_preset(user_id, name, description, preset_json, preset_id=None, is_default=False):
    """创建或更新预设"""
    conn = get_connection()
    cursor = conn.cursor()

    if is_default:
        # 先清除其他默认
        cursor.execute('UPDATE pc_presets SET is_default = 0 WHERE user_id = ?', (user_id,))

    if preset_id:
        cursor.execute(
            '''UPDATE pc_presets SET name = ?, description = ?, preset_json = ?,
               is_default = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND user_id = ?''',
            (name, description, preset_json, 1 if is_default else 0, preset_id, user_id)
        )
    else:
        cursor.execute(
            '''INSERT INTO pc_presets (user_id, name, description, preset_json, is_default)
               VALUES (?, ?, ?, ?, ?)''',
            (user_id, name, description, preset_json, 1 if is_default else 0)
        )
        preset_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return preset_id


def delete_pc_preset(preset_id, user_id):
    """删除预设"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM pc_presets WHERE id = ? AND user_id = ?', (preset_id, user_id))
    conn.commit()
    conn.close()


def set_default_preset(preset_id, user_id):
    """设置默认预设"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE pc_presets SET is_default = 0 WHERE user_id = ?', (user_id,))
    cursor.execute('UPDATE pc_presets SET is_default = 1 WHERE id = ? AND user_id = ?', (preset_id, user_id))
    conn.commit()
    conn.close()
