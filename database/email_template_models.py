"""
用户邮件模板池数据模型
支持开场白(opening)和问候语(greeting)模板的管理
按 user_id 隔离数据
"""
import random
from database.connection import get_connection


def init_email_templates_table():
    """初始化用户邮件模板表（由 schema.py 调用）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_email_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            template_type TEXT NOT NULL CHECK(template_type IN ('greeting', 'opening')),
            template_text TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_templates_user ON user_email_templates(user_id, template_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_templates_active ON user_email_templates(user_id, template_type, is_active)')
    conn.commit()
    conn.close()


def get_templates(user_id, template_type, active_only=True):
    """获取某用户的指定类型模板列表

    Args:
        user_id: 用户ID
        template_type: 'greeting' 或 'opening'
        active_only: 是否只返回启用的模板

    Returns:
        list[dict]: 模板列表，每个元素包含 id, template_text, is_active, created_at
    """
    conn = get_connection()
    cursor = conn.cursor()
    if active_only:
        cursor.execute('''
            SELECT id, template_text, is_active, created_at
            FROM user_email_templates
            WHERE user_id = ? AND template_type = ? AND is_active = 1
            ORDER BY created_at
        ''', (user_id, template_type))
    else:
        cursor.execute('''
            SELECT id, template_text, is_active, created_at
            FROM user_email_templates
            WHERE user_id = ? AND template_type = ?
            ORDER BY created_at
        ''', (user_id, template_type))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            'id': r[0],
            'template_text': r[1],
            'is_active': bool(r[2]),
            'created_at': r[3]
        }
        for r in rows
    ]


def add_template(user_id, template_type, template_text):
    """新增模板

    Returns:
        int: 新模板ID
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_email_templates (user_id, template_type, template_text, is_active)
        VALUES (?, ?, ?, 1)
    ''', (user_id, template_type, template_text))
    conn.commit()
    tpl_id = cursor.lastrowid
    conn.close()
    return tpl_id


def update_template(template_id, template_text=None, is_active=None, user_id=None):
    """更新模板

    Args:
        template_id: 模板ID
        template_text: 新文本（为None时不更新）
        is_active: 新状态（为None时不更新）
        user_id: 如果传入，则校验模板属于该用户
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 校验权限
    if user_id is not None:
        cursor.execute('SELECT user_id FROM user_email_templates WHERE id = ?', (template_id,))
        row = cursor.fetchone()
        if not row or row[0] != user_id:
            conn.close()
            raise PermissionError('无权操作此模板')

    fields = []
    params = []
    if template_text is not None:
        fields.append('template_text = ?')
        params.append(template_text)
    if is_active is not None:
        fields.append('is_active = ?')
        params.append(1 if is_active else 0)
    if fields:
        fields.append('updated_at = CURRENT_TIMESTAMP')
        sql = f"UPDATE user_email_templates SET {', '.join(fields)} WHERE id = ?"
        params.append(template_id)
        cursor.execute(sql, params)
        conn.commit()
    conn.close()


def delete_template(template_id, user_id=None):
    """删除模板

    Args:
        template_id: 模板ID
        user_id: 如果传入，则校验模板属于该用户
    """
    conn = get_connection()
    cursor = conn.cursor()

    if user_id is not None:
        cursor.execute('SELECT user_id FROM user_email_templates WHERE id = ?', (template_id,))
        row = cursor.fetchone()
        if not row or row[0] != user_id:
            conn.close()
            raise PermissionError('无权删除此模板')

    cursor.execute('DELETE FROM user_email_templates WHERE id = ?', (template_id,))
    conn.commit()
    conn.close()


def get_random_template(user_id, template_type):
    """随机选取一个活跃模板

    Args:
        user_id: 用户ID
        template_type: 'greeting' 或 'opening'

    Returns:
        dict or None: 模板字典（含 id, template_text），无配置时返回 None
    """
    templates = get_templates(user_id, template_type, active_only=True)
    if not templates:
        return None
    return random.choice(templates)
