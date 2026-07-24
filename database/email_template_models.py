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


def get_templates_by_ids(user_id, template_type, template_ids):
    """按ID列表获取指定类型的模板（仅返回属于该用户且启用的模板）

    Args:
        user_id: 用户ID
        template_type: 'greeting' 或 'opening'
        template_ids: 模板ID列表

    Returns:
        list[dict]: 模板列表
    """
    if not template_ids:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(template_ids))
    cursor.execute(f'''
        SELECT id, template_text, is_active, created_at
        FROM user_email_templates
        WHERE user_id = ? AND template_type = ? AND is_active = 1 AND id IN ({placeholders})
        ORDER BY id
    ''', (user_id, template_type) + tuple(template_ids))
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


def interleave_templates(templates, count):
    """将模板列表穿插分配到指定数量，确保相邻元素不重复

    Args:
        templates: 模板列表（每个元素至少含 id, template_text）
        count: 需要分配的总数

    Returns:
        list[dict]: 分配后的模板列表，长度等于 count
    """
    if not templates or count <= 0:
        return []

    n = len(templates)
    if n == 1:
        return [templates[0]] * count

    # 构建分配池：每个模板尽量均匀分布
    base = count // n
    extra = count % n
    pool = []
    for i in range(n):
        times = base + (1 if i < extra else 0)
        pool.extend([i] * times)

    # 随机打乱并确保相邻不重复（类似标题分配算法）
    for _ in range(100):
        candidate = pool[:]
        random.shuffle(candidate)
        if all(candidate[i] != candidate[i + 1] for i in range(len(candidate) - 1)):
            return [templates[idx] for idx in candidate]

    # 贪心构建：优先选剩余最多的候选，避免死锁
    remaining = {}
    for idx in set(pool):
        remaining[idx] = pool.count(idx)

    result = []
    last_idx = -1
    for _ in range(len(pool)):
        candidates = [idx for idx, cnt in remaining.items()
                      if cnt > 0 and idx != last_idx]
        if not candidates:
            candidates = [idx for idx, cnt in remaining.items() if cnt > 0]
        candidates.sort(key=lambda x: remaining[x], reverse=True)
        chosen = candidates[0]
        result.append(chosen)
        remaining[chosen] -= 1
        last_idx = chosen

    return [templates[idx] for idx in result]


# ==================== 默认模板数据 ====================

DEFAULT_GREETING_TEMPLATES = [
    "Hi {first_name},",
    "Hello {first_name},",
    "Good day {first_name},",
    "Dear {first_name},",
    "Hi {company_name} Team,",
    "Hello {company_name} Team,",
]

DEFAULT_OPENING_TEMPLATES = [
    "My name is {sender_name}, and I am the {job_title} at {company_name}. I came across {customer_name} while researching innovative companies in the solar space, and I was impressed by what you are building.",
    "I hope this message finds you well. My name is {sender_name}, and I represent {company_name} as the {job_title}. I have been following {customer_name}'s growth and wanted to introduce how our solar solutions might align with your goals.",
    "Having followed {customer_name}'s expansion into the renewable energy sector, I wanted to reach out. I am {sender_name}, {job_title} at {company_name}, and I believe there may be a valuable opportunity for us to collaborate.",
    "I am writing to introduce {company_name} and explore a potential partnership with {customer_name}. My name is {sender_name}, and as the {job_title}, I have worked with several companies facing similar challenges to yours.",
    "My name is {sender_name}, {job_title} at {company_name}. I recently learned about {customer_name} and was intrigued by your approach to {product}. I would love to share how we have helped similar businesses scale with our solar technology.",
    "I hope you are having a great week. I am {sender_name} from {company_name}, serving as the {job_title}. I came across {customer_name} and thought our solar solutions could be a strong fit for your current product line.",
]


def init_default_templates(user_id):
    """为指定用户初始化默认模板（仅当该用户没有任何模板时）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM user_email_templates WHERE user_id = ?', (user_id,))
    count = cursor.fetchone()[0]
    conn.close()

    if count > 0:
        return  # 用户已有模板，跳过

    for text in DEFAULT_GREETING_TEMPLATES:
        add_template(user_id, 'greeting', text)

    for text in DEFAULT_OPENING_TEMPLATES:
        add_template(user_id, 'opening', text)
