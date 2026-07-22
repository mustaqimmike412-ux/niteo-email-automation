"""
跟进邮件模块 - 数据库 CRUD 操作
包含跟进序列和跟进步骤的创建、查询、更新、删除等操作。
"""

import json
from datetime import datetime, timedelta
from database.connection import get_connection


# ==================== 策略模板 ====================
# 每种策略定义后续跟进步骤（不包含第一封，第一封由用户手动发送）
STRATEGY_TEMPLATES = {
    'standard': [
        {
            'step_number': 2,
            'purpose': 'reminder',
            'subject_mode': 'reply',
            'interval_days': 3,
            'strategy': '换角度重申核心价值，不重复第一封原句，控制在100词以内',
        },
        {
            'step_number': 3,
            'purpose': 'case_study',
            'subject_mode': 'new',
            'interval_days': 4,
            'strategy': '分享同行业成功案例，包含具体数据',
        },
        {
            'step_number': 4,
            'purpose': 'question',
            'subject_mode': 'new',
            'interval_days': 5,
            'strategy': '基于客户痛点提出1-2个诊断性问题',
        },
        {
            'step_number': 5,
            'purpose': 'breakup',
            'subject_mode': 'new',
            'interval_days': 6,
            'strategy': '简短分手邮件，yes/no CTA',
        },
    ],
    'aggressive': [
        {
            'step_number': 2,
            'purpose': 'reminder',
            'subject_mode': 'reply',
            'interval_days': 2,
            'strategy': '简短重申核心价值',
        },
        {
            'step_number': 3,
            'purpose': 'case_study',
            'subject_mode': 'new',
            'interval_days': 3,
            'strategy': '同行业案例+数据',
        },
        {
            'step_number': 4,
            'purpose': 'question',
            'subject_mode': 'new',
            'interval_days': 4,
            'strategy': '诊断型问题',
        },
        {
            'step_number': 5,
            'purpose': 'resource',
            'subject_mode': 'new',
            'interval_days': 5,
            'strategy': '分享行业报告/指南',
        },
        {
            'step_number': 6,
            'purpose': 'loss_aversion',
            'subject_mode': 'new',
            'interval_days': 7,
            'strategy': '损失厌恶框架',
        },
        {
            'step_number': 7,
            'purpose': 'breakup',
            'subject_mode': 'new',
            'interval_days': 7,
            'strategy': 'yes/no 分手邮件',
        },
    ],
    'conservative': [
        {
            'step_number': 2,
            'purpose': 'reminder',
            'subject_mode': 'reply',
            'interval_days': 4,
            'strategy': '换角度提醒',
        },
        {
            'step_number': 3,
            'purpose': 'breakup',
            'subject_mode': 'new',
            'interval_days': 5,
            'strategy': '简短分手邮件',
        },
    ],
}


# ==================== 辅助函数 ====================

def _row_to_sequence(row):
    """将数据库行转换为序列字典"""
    if not row:
        return None
    return {
        'id': row[0],
        'customer_id': row[1],
        'user_id': row[2],
        'strategy_type': row[3],
        'total_steps': row[4],
        'current_step': row[5],
        'status': row[6],
        'first_email_log_id': row[7],
        'generation_context': json.loads(row[8]) if row[8] else None,
        'config_json': json.loads(row[9]) if row[9] else None,
        'started_at': row[10],
        'completed_at': row[11],
        'created_at': row[12],
        'updated_at': row[13],
    }


def _row_to_step(row):
    """将数据库行转换为步骤字典"""
    if not row:
        return None
    return {
        'id': row[0],
        'sequence_id': row[1],
        'step_number': row[2],
        'purpose': row[3],
        'strategy': row[4],
        'subject_mode': row[5],
        'interval_days': row[6],
        'subject': row[7],
        'body': row[8],
        'greeting': row[9],
        'signature': row[10],
        'status': row[11],
        'scheduled_at': row[12],
        'sent_at': row[13],
        'email_log_id': row[14],
        'error_message': row[15],
        'material_ids': json.loads(row[16]) if row[16] else None,
        'word_count': row[17],
        'created_at': row[18],
        'updated_at': row[19],
    }


def _build_user_where(user_id):
    """构建 user_id 隔离的 WHERE 子句片段，返回 (clause, params)"""
    if user_id:
        return 'user_id = ?', [user_id]
    return '', []


# ==================== 序列 CRUD ====================

def create_sequence(customer_id, user_id, strategy_type='standard', total_steps=5,
                   first_email_log_id=None, generation_context=None, config_json=None):
    """创建跟进序列

    Args:
        customer_id: 客户ID
        user_id: 用户ID
        strategy_type: 策略类型 (standard/aggressive/conservative)
        total_steps: 总步骤数
        first_email_log_id: 第一封邮件的发送记录ID
        generation_context: 生成上下文（dict），将被序列化为 JSON 存储
        config_json: 配置信息（dict），将被序列化为 JSON 存储

    Returns:
        新创建的序列ID
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO follow_up_sequences
            (customer_id, user_id, strategy_type, total_steps, first_email_log_id,
             generation_context, config_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        customer_id,
        user_id,
        strategy_type,
        total_steps,
        first_email_log_id,
        json.dumps(generation_context, ensure_ascii=False) if generation_context else None,
        json.dumps(config_json, ensure_ascii=False) if config_json else None,
    ))
    sequence_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return sequence_id


def get_sequence(sequence_id, user_id=None):
    """获取跟进序列详情（含所有步骤）

    Args:
        sequence_id: 序列ID
        user_id: 用户ID（用于数据隔离）

    Returns:
        包含 steps 列表的序列字典，或 None
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 查询序列基本信息
    user_clause, user_params = _build_user_where(user_id)
    if user_clause:
        where_sql = f'WHERE id = ? AND {user_clause}'
        params = [sequence_id] + user_params
    else:
        where_sql = 'WHERE id = ?'
        params = [sequence_id]

    cursor.execute(f'''
        SELECT id, customer_id, user_id, strategy_type, total_steps, current_step,
               status, first_email_log_id, generation_context, config_json,
               started_at, completed_at, created_at, updated_at
        FROM follow_up_sequences {where_sql}
    ''', params)
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    sequence = _row_to_sequence(row)

    # 查询该序列下的所有步骤
    cursor.execute('''
        SELECT id, sequence_id, step_number, purpose, strategy, subject_mode,
               interval_days, subject, body, greeting, signature, status,
               scheduled_at, sent_at, email_log_id, error_message, material_ids,
               word_count, created_at, updated_at
        FROM follow_up_steps
        WHERE sequence_id = ?
        ORDER BY step_number
    ''', (sequence_id,))

    sequence['steps'] = [_row_to_step(r) for r in cursor.fetchall()]
    conn.close()
    return sequence


def list_sequences(user_id, status=None, customer_id=None, page=1, per_page=20):
    """获取跟进序列列表（分页）

    Args:
        user_id: 用户ID
        status: 按状态筛选
        customer_id: 按客户筛选
        page: 页码
        per_page: 每页数量

    Returns:
        {'items': [...], 'total': int}
    """
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []

    # user_id 隔离
    if user_id:
        where_clauses.append('user_id = ?')
        params.append(user_id)

    if status:
        where_clauses.append('status = ?')
        params.append(status)
    if customer_id:
        where_clauses.append('customer_id = ?')
        params.append(customer_id)

    where_sql = 'WHERE ' + ' AND '.join(where_clauses) if where_clauses else ''

    # 查总数
    cursor.execute(f'SELECT COUNT(*) FROM follow_up_sequences {where_sql}', params)
    total = cursor.fetchone()[0]

    # 分页查询
    offset = (page - 1) * per_page
    cursor.execute(f'''
        SELECT id, customer_id, user_id, strategy_type, total_steps, current_step,
               status, first_email_log_id, generation_context, config_json,
               started_at, completed_at, created_at, updated_at
        FROM follow_up_sequences {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', params + [per_page, offset])

    items = []
    for row in cursor.fetchall():
        items.append(_row_to_sequence(row))

    conn.close()
    return {'items': items, 'total': total}


def update_sequence(sequence_id, user_id, **kwargs):
    """更新跟进序列

    Args:
        sequence_id: 序列ID
        user_id: 用户ID
        **kwargs: 可更新的字段 (config_json, status, generation_context 等)

    Returns:
        是否更新成功
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 先验证序列存在且属于该用户
    user_clause, user_params = _build_user_where(user_id)
    if user_clause:
        check_sql = f'SELECT id FROM follow_up_sequences WHERE id = ? AND {user_clause}'
        check_params = [sequence_id] + user_params
    else:
        check_sql = 'SELECT id FROM follow_up_sequences WHERE id = ?'
        check_params = [sequence_id]

    cursor.execute(check_sql, check_params)
    if not cursor.fetchone():
        conn.close()
        return False

    # 构建更新字段
    fields = []
    params = []
    allowed_fields = {'status', 'generation_context', 'config_json'}

    for key in allowed_fields:
        if key in kwargs:
            value = kwargs[key]
            # JSON 字段序列化
            if key in ('generation_context', 'config_json') and value is not None:
                value = json.dumps(value, ensure_ascii=False)
            fields.append(f'{key} = ?')
            params.append(value)

    if not fields:
        conn.close()
        return True  # 没有需要更新的字段

    fields.append("updated_at = datetime('now')")
    params.append(sequence_id)

    cursor.execute(f'''
        UPDATE follow_up_sequences
        SET {', '.join(fields)}
        WHERE id = ?
    ''', params)
    conn.commit()
    conn.close()
    return True


def delete_sequence(sequence_id, user_id, admin=False):
    """删除跟进序列（仅 draft/cancelled 状态可删）

    Args:
        sequence_id: 序列ID
        user_id: 用户ID
        admin: 是否为管理员

    Returns:
        (success: bool, error: str or None)
    """
    conn = get_connection()
    cursor = conn.cursor()

    user_clause, user_params = _build_user_where(user_id, admin)
    if user_clause:
        check_sql = f'SELECT status FROM follow_up_sequences WHERE id = ? AND {user_clause}'
        check_params = [sequence_id] + user_params
    else:
        check_sql = 'SELECT status FROM follow_up_sequences WHERE id = ?'
        check_params = [sequence_id]

    cursor.execute(check_sql, check_params)
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, '序列不存在或无权操作'

    status = row[0]
    if status not in ('draft', 'cancelled'):
        conn.close()
        return False, f'仅 draft/cancelled 状态可删除，当前状态: {status}'

    # 删除序列（CASCADE 会同时删除关联的 steps）
    cursor.execute('DELETE FROM follow_up_sequences WHERE id = ?', (sequence_id,))
    conn.commit()
    conn.close()
    return True, None


# ==================== 序列状态流转 ====================

def activate_sequence(sequence_id, user_id, admin=False):
    """激活跟进序列：根据策略模板生成 follow_up_steps 记录，计算 scheduled_at

    Args:
        sequence_id: 序列ID
        user_id: 用户ID
        admin: 是否为管理员

    Returns:
        (success: bool, error: str or None)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 验证序列存在且属于该用户
    user_clause, user_params = _build_user_where(user_id, admin)
    if user_clause:
        check_sql = f'''
            SELECT id, status, strategy_type, first_email_log_id
            FROM follow_up_sequences WHERE id = ? AND {user_clause}
        '''
        check_params = [sequence_id] + user_params
    else:
        check_sql = '''
            SELECT id, status, strategy_type, first_email_log_id
            FROM follow_up_sequences WHERE id = ?
        '''
        check_params = [sequence_id]

    cursor.execute(check_sql, check_params)
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, '序列不存在或无权操作'

    seq_id, status, strategy_type, first_email_log_id = row
    if status not in ('draft', 'paused'):
        conn.close()
        return False, f'仅 draft/paused 状态可激活，当前状态: {status}'

    # 获取策略模板
    template = STRATEGY_TEMPLATES.get(strategy_type, STRATEGY_TEMPLATES['standard'])

    # 获取第一封邮件的发送时间，作为计算基准
    base_time = None
    if first_email_log_id:
        cursor.execute('SELECT sent_at FROM email_logs WHERE id = ?', (first_email_log_id,))
        sent_row = cursor.fetchone()
        if sent_row and sent_row[0]:
            base_time = sent_row[0]

    # 如果没有发送时间，使用当前时间
    if not base_time:
        base_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 解析基准时间为 datetime 对象
    try:
        base_dt = datetime.strptime(str(base_time), '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        base_dt = datetime.now()

    # 检查是否已有步骤（resume 场景下可能已有 pending 之后的步骤）
    cursor.execute('SELECT COUNT(*) FROM follow_up_steps WHERE sequence_id = ?', (sequence_id,))
    existing_steps = cursor.fetchone()[0]

    if existing_steps > 0:
        # 已有步骤，只需更新状态为 active
        cursor.execute('''
            UPDATE follow_up_sequences
            SET status = 'active', started_at = CASE WHEN started_at IS NULL THEN datetime('now') ELSE started_at END,
                updated_at = datetime('now')
            WHERE id = ?
        ''', (sequence_id,))
        conn.commit()
        conn.close()
        return True, None

    # 生成步骤记录
    prev_scheduled = base_dt
    for step_template in template:
        scheduled_dt = prev_scheduled + timedelta(days=step_template['interval_days'])
        scheduled_str = scheduled_dt.strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('''
            INSERT INTO follow_up_steps
                (sequence_id, step_number, purpose, strategy, subject_mode, interval_days, status, scheduled_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        ''', (
            sequence_id,
            step_template['step_number'],
            step_template['purpose'],
            step_template.get('strategy', ''),
            step_template.get('subject_mode', 'reply'),
            step_template['interval_days'],
            scheduled_str,
        ))

        prev_scheduled = scheduled_dt

    # 更新序列状态
    cursor.execute('''
        UPDATE follow_up_sequences
        SET status = 'active', started_at = datetime('now'), updated_at = datetime('now')
        WHERE id = ?
    ''', (sequence_id,))
    conn.commit()
    conn.close()
    return True, None


def delete_sequence(sequence_id, user_id):
    """删除跟进序列

    Args:
        sequence_id: 序列ID
        user_id: 用户ID

    Returns:
        (success, error_message)
    """
    conn = get_connection()
    cursor = conn.cursor()

    user_clause, user_params = _build_user_where(user_id)
    if user_clause:
        check_sql = f'SELECT status FROM follow_up_sequences WHERE id = ? AND {user_clause}'
        check_params = [sequence_id] + user_params
    else:
        check_sql = 'SELECT status FROM follow_up_sequences WHERE id = ?'
        check_params = [sequence_id]

    cursor.execute(check_sql, check_params)
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, '序列不存在或无权操作'

    status = row[0]
    if status != 'active':
        conn.close()
        return False, f'仅 active 状态可暂停，当前状态: {status}'

    cursor.execute('''
        UPDATE follow_up_sequences
        SET status = 'paused', updated_at = datetime('now')
        WHERE id = ?
    ''', (sequence_id,))
    conn.commit()
    conn.close()
    return True, None


def resume_sequence(sequence_id, user_id, admin=False):
    """恢复跟进序列：状态恢复为 active，重新计算下一步的 scheduled_at

    Args:
        sequence_id: 序列ID
        user_id: 用户ID
        admin: 是否为管理员

    Returns:
        (success: bool, error: str or None)
    """
    conn = get_connection()
    cursor = conn.cursor()

    user_clause, user_params = _build_user_where(user_id, admin)
    if user_clause:
        check_sql = f'SELECT status FROM follow_up_sequences WHERE id = ? AND {user_clause}'
        check_params = [sequence_id] + user_params
    else:
        check_sql = 'SELECT status FROM follow_up_sequences WHERE id = ?'
        check_params = [sequence_id]

    cursor.execute(check_sql, check_params)
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, '序列不存在或无权操作'

    status = row[0]
    if status != 'paused':
        conn.close()
        return False, f'仅 paused 状态可恢复，当前状态: {status}'

    # 找到下一个 pending 的步骤，重新计算其 scheduled_at（基于当前时间）
    cursor.execute('''
        SELECT id, interval_days
        FROM follow_up_steps
        WHERE sequence_id = ? AND status = 'pending'
        ORDER BY step_number
        LIMIT 1
    ''', (sequence_id,))
    next_step = cursor.fetchone()

    if next_step:
        step_id, interval_days = next_step
        new_scheduled = datetime.now() + timedelta(days=interval_days)
        cursor.execute('''
            UPDATE follow_up_steps
            SET scheduled_at = ?, updated_at = datetime('now')
            WHERE id = ?
        ''', (new_scheduled.strftime('%Y-%m-%d %H:%M:%S'), step_id))

    # 更新序列状态
    cursor.execute('''
        UPDATE follow_up_sequences
        SET status = 'active', updated_at = datetime('now')
        WHERE id = ?
    ''', (sequence_id,))
    conn.commit()
    conn.close()
    return True, None


def cancel_sequence(sequence_id, user_id):
    """取消跟进序列

    Args:
        sequence_id: 序列ID
        user_id: 用户ID

    Returns:
        (success: bool, error: str or None)
    """
    conn = get_connection()
    cursor = conn.cursor()

    user_clause, user_params = _build_user_where(user_id)
    if user_clause:
        check_sql = f'SELECT status FROM follow_up_sequences WHERE id = ? AND {user_clause}'
        check_params = [sequence_id] + user_params
    else:
        check_sql = 'SELECT status FROM follow_up_sequences WHERE id = ?'
        check_params = [sequence_id]

    cursor.execute(check_sql, check_params)
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, '序列不存在或无权操作'

    status = row[0]
    if status in ('completed', 'cancelled'):
        conn.close()
        return False, f'序列已处于 {status} 状态，无法取消'

    # 将未发送的 pending 步骤也标记为 cancelled
    cursor.execute('''
        UPDATE follow_up_steps
        SET status = 'cancelled', updated_at = datetime('now')
        WHERE sequence_id = ? AND status = 'pending'
    ''', (sequence_id,))

    # 更新序列状态
    cursor.execute('''
        UPDATE follow_up_sequences
        SET status = 'cancelled', updated_at = datetime('now')
        WHERE id = ?
    ''', (sequence_id,))
    conn.commit()
    conn.close()
    return True, None


# ==================== 步骤 CRUD ====================

def get_step(step_id, user_id=None, admin=False):
    """获取单个跟进步骤详情

    Args:
        step_id: 步骤ID
        user_id: 用户ID（用于数据隔离）
        admin: 是否为管理员

    Returns:
        步骤字典，或 None
    """
    conn = get_connection()
    cursor = conn.cursor()

    if user_id:
        cursor.execute('''
            SELECT s.id, s.sequence_id, s.step_number, s.purpose, s.strategy, s.subject_mode,
                   s.interval_days, s.subject, s.body, s.greeting, s.signature, s.status,
                   s.scheduled_at, s.sent_at, s.email_log_id, s.error_message, s.material_ids,
                   s.word_count, s.created_at, s.updated_at
            FROM follow_up_steps s
            JOIN follow_up_sequences seq ON s.sequence_id = seq.id
            WHERE s.id = ? AND seq.user_id = ?
        ''', (step_id, user_id))
    else:
        cursor.execute('''
            SELECT id, sequence_id, step_number, purpose, strategy, subject_mode,
                   interval_days, subject, body, greeting, signature, status,
                   scheduled_at, sent_at, email_log_id, error_message, material_ids,
                   word_count, created_at, updated_at
            FROM follow_up_steps
            WHERE id = ?
        ''', (step_id,))

    row = cursor.fetchone()
    conn.close()
    return _row_to_step(row)


def update_step(step_id, user_id, admin=False, **kwargs):
    """编辑跟进步骤（标题/正文/间隔等）

    Args:
        step_id: 步骤ID
        user_id: 用户ID
        admin: 是否为管理员
        **kwargs: 可更新的字段 (subject, body, greeting, signature, interval_days, strategy, material_ids, word_count 等)

    Returns:
        是否更新成功
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 先验证步骤存在且属于该用户
    if user_id:
        cursor.execute('''
            SELECT s.id FROM follow_up_steps s
            JOIN follow_up_sequences seq ON s.sequence_id = seq.id
            WHERE s.id = ? AND seq.user_id = ?
        ''', (step_id, user_id))
    else:
        cursor.execute('SELECT id FROM follow_up_steps WHERE id = ?', (step_id,))

    if not cursor.fetchone():
        conn.close()
        return False

    # 构建更新字段
    fields = []
    params = []
    allowed_fields = {
        'subject', 'body', 'greeting', 'signature', 'interval_days',
        'strategy', 'subject_mode', 'purpose', 'word_count', 'status'
    }

    for key in allowed_fields:
        if key in kwargs:
            fields.append(f'{key} = ?')
            params.append(kwargs[key])

    # material_ids 需要 JSON 序列化
    if 'material_ids' in kwargs:
        fields.append('material_ids = ?')
        params.append(json.dumps(kwargs['material_ids'], ensure_ascii=False) if kwargs['material_ids'] else None)

    if not fields:
        conn.close()
        return True

    fields.append("updated_at = datetime('now')")
    params.append(step_id)

    cursor.execute(f'''
        UPDATE follow_up_steps
        SET {', '.join(fields)}
        WHERE id = ?
    ''', params)
    conn.commit()
    conn.close()
    return True


def approve_step(step_id, user_id, admin=False):
    """审批跟进步骤，状态变为 approved

    Args:
        step_id: 步骤ID
        user_id: 用户ID
        admin: 是否为管理员

    Returns:
        (success: bool, error: str or None)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 验证步骤存在且属于该用户
    if user_id:
        cursor.execute('''
            SELECT s.status, seq.status
            FROM follow_up_steps s
            JOIN follow_up_sequences seq ON s.sequence_id = seq.id
            WHERE s.id = ? AND seq.user_id = ?
        ''', (step_id, user_id))
    else:
        cursor.execute('''
            SELECT s.status, seq.status
            FROM follow_up_steps s
            JOIN follow_up_sequences seq ON s.sequence_id = seq.id
            WHERE s.id = ?
        ''', (step_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, '步骤不存在或无权操作'

    step_status, seq_status = row
    if step_status != 'pending':
        conn.close()
        return False, f'仅 pending 状态可审批，当前状态: {step_status}'
    if seq_status != 'active':
        conn.close()
        return False, f'序列未处于 active 状态，当前状态: {seq_status}'

    cursor.execute('''
        UPDATE follow_up_steps
        SET status = 'approved', updated_at = datetime('now')
        WHERE id = ?
    ''', (step_id,))
    conn.commit()
    conn.close()
    return True, None


def skip_step(step_id, user_id):
    """跳过跟进步骤，状态变为 skipped，并更新序列的 current_step

    Args:
        step_id: 步骤ID
        user_id: 用户ID

    Returns:
        (success: bool, error: str or None)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 验证步骤存在且属于该用户
    if user_id:
        cursor.execute('''
            SELECT s.status, s.sequence_id, s.step_number, seq.current_step
            FROM follow_up_steps s
            JOIN follow_up_sequences seq ON s.sequence_id = seq.id
            WHERE s.id = ? AND seq.user_id = ?
        ''', (step_id, user_id))
    else:
        cursor.execute('''
            SELECT s.status, s.sequence_id, s.step_number, seq.current_step
            FROM follow_up_steps s
            JOIN follow_up_sequences seq ON s.sequence_id = seq.id
            WHERE s.id = ?
        ''', (step_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, '步骤不存在或无权操作'

    step_status, sequence_id, step_number, current_step = row
    if step_status not in ('pending', 'approved'):
        conn.close()
        return False, f'仅 pending/approved 状态可跳过，当前状态: {step_status}'

    # 标记步骤为 skipped
    cursor.execute('''
        UPDATE follow_up_steps
        SET status = 'skipped', updated_at = datetime('now')
        WHERE id = ?
    ''', (step_id,))

    # 更新序列的 current_step
    if step_number >= current_step:
        cursor.execute('''
            UPDATE follow_up_sequences
            SET current_step = ?, updated_at = datetime('now')
            WHERE id = ?
        ''', (step_number, sequence_id))

    conn.commit()
    conn.close()
    return True, None


def get_due_steps(user_id=None):
    """获取到期待发送的跟进步骤

    返回 status='approved' AND scheduled_at <= now 的步骤列表，
    并附加序列信息和客户信息。

    Args:
        user_id: 用户ID

    Returns:
        步骤字典列表
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if user_id:
        cursor.execute('''
            SELECT s.id, s.sequence_id, s.step_number, s.purpose, s.strategy, s.subject_mode,
                   s.interval_days, s.subject, s.body, s.greeting, s.signature, s.status,
                   s.scheduled_at, s.sent_at, s.email_log_id, s.error_message, s.material_ids,
                   s.word_count, s.created_at, s.updated_at,
                   seq.status as seq_status, seq.strategy_type,
                   c.customer_name, c.country, c.industry_type,
                   e.email_address
            FROM follow_up_steps s
            JOIN follow_up_sequences seq ON s.sequence_id = seq.id
            LEFT JOIN customers c ON seq.customer_id = c.id
            LEFT JOIN emails e ON e.customer_id = c.id AND e.is_active = 1
            WHERE s.status = 'approved'
              AND s.scheduled_at <= ?
              AND seq.status = 'active'
              AND seq.user_id = ?
            ORDER BY s.scheduled_at
        ''', (now, user_id))
    else:
        cursor.execute('''
            SELECT s.id, s.sequence_id, s.step_number, s.purpose, s.strategy, s.subject_mode,
                   s.interval_days, s.subject, s.body, s.greeting, s.signature, s.status,
                   s.scheduled_at, s.sent_at, s.email_log_id, s.error_message, s.material_ids,
                   s.word_count, s.created_at, s.updated_at,
                   seq.status as seq_status, seq.strategy_type,
                   c.customer_name, c.country, c.industry_type,
                   e.email_address
            FROM follow_up_steps s
            JOIN follow_up_sequences seq ON s.sequence_id = seq.id
            LEFT JOIN customers c ON seq.customer_id = c.id
            LEFT JOIN emails e ON e.customer_id = c.id AND e.is_active = 1
            WHERE s.status = 'approved'
              AND s.scheduled_at <= ?
              AND seq.status = 'active'
            ORDER BY s.scheduled_at
        ''', (now,))

    results = []
    for row in cursor.fetchall():
        step = _row_to_step(row[:20])
        # 附加序列和客户信息
        step['sequence_status'] = row[20]
        step['sequence_strategy_type'] = row[21]
        step['customer_name'] = row[22]
        step['customer_country'] = row[23]
        step['customer_industry'] = row[24]
        step['email_address'] = row[25]
        results.append(step)

    conn.close()
    return results


def mark_step_sent(step_id, email_log_id):
    """标记步骤已发送，同时更新 email_logs 的跟进字段

    Args:
        step_id: 步骤ID
        email_log_id: 对应的邮件发送记录ID

    Returns:
        是否更新成功
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 获取步骤信息
    cursor.execute('''
        SELECT sequence_id, step_number
        FROM follow_up_steps
        WHERE id = ?
    ''', (step_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    sequence_id, step_number = row

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 更新步骤状态
    cursor.execute('''
        UPDATE follow_up_steps
        SET status = 'sent', sent_at = ?, email_log_id = ?, updated_at = datetime('now')
        WHERE id = ?
    ''', (now, email_log_id, step_id))

    # 更新序列的 current_step
    cursor.execute('''
        UPDATE follow_up_sequences
        SET current_step = ?, updated_at = datetime('now')
        WHERE id = ?
    ''', (step_number, sequence_id))

    # 更新 email_logs 的跟进字段
    cursor.execute('''
        UPDATE email_logs
        SET follow_up_sequence_id = ?, follow_up_step_number = ?, is_follow_up = 1
        WHERE id = ?
    ''', (sequence_id, step_number, email_log_id))

    # 检查序列是否全部完成（所有步骤都是 sent/skipped/cancelled）
    cursor.execute('''
        SELECT COUNT(*) FROM follow_up_steps
        WHERE sequence_id = ? AND status NOT IN ('sent', 'skipped', 'cancelled')
    ''', (sequence_id,))
    remaining = cursor.fetchone()[0]

    if remaining == 0:
        cursor.execute('''
            UPDATE follow_up_sequences
            SET status = 'completed', completed_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
        ''', (sequence_id,))

    conn.commit()
    conn.close()
    return True


def mark_step_failed(step_id, error_message):
    """标记步骤发送失败

    Args:
        step_id: 步骤ID
        error_message: 错误信息

    Returns:
        是否更新成功
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE follow_up_steps
        SET status = 'failed', error_message = ?, updated_at = datetime('now')
        WHERE id = ?
    ''', (error_message, step_id))
    conn.commit()
    conn.close()
    return True


# ==================== 统计与查询 ====================

def get_follow_up_dashboard(user_id):
    """获取跟进邮件仪表盘统计

    Args:
        user_id: 用户ID

    Returns:
        dict: {
            'active_count': 活跃序列数,
            'today_due_count': 今日到期步骤数,
            'completed_count': 已完成序列数,
            'total_sent_count': 已发送步骤总数
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    user_clause, user_params = _build_user_where(user_id)
    user_where = f'AND {user_clause}' if user_clause else ''

    # 活跃序列数
    cursor.execute(f'''
        SELECT COUNT(*) FROM follow_up_sequences
        WHERE status = 'active' {user_where}
    ''', user_params)
    active_count = cursor.fetchone()[0]

    # 今日到期步骤数（approved 且 scheduled_at <= 明天 0:00）
    today_end = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d') + ' 00:00:00'
    cursor.execute(f'''
        SELECT COUNT(*) FROM follow_up_steps s
        JOIN follow_up_sequences seq ON s.sequence_id = seq.id
        WHERE s.status = 'approved'
          AND s.scheduled_at <= ?
          AND seq.status = 'active'
          {user_where.replace('user_id = ?', 'seq.user_id = ?')}
    ''', [today_end] + user_params)
    today_due_count = cursor.fetchone()[0]

    # 已完成序列数
    cursor.execute(f'''
        SELECT COUNT(*) FROM follow_up_sequences
        WHERE status = 'completed' {user_where}
    ''', user_params)
    completed_count = cursor.fetchone()[0]

    # 已发送步骤总数
    cursor.execute(f'''
        SELECT COUNT(*) FROM follow_up_steps s
        JOIN follow_up_sequences seq ON s.sequence_id = seq.id
        WHERE s.status = 'sent'
          {user_where.replace('user_id = ?', 'seq.user_id = ?')}
    ''', user_params)
    total_sent_count = cursor.fetchone()[0]

    conn.close()
    return {
        'active_count': active_count,
        'today_due_count': today_due_count,
        'completed_count': completed_count,
        'total_sent_count': total_sent_count,
    }


def get_customer_follow_status(customer_id, user_id):
    """获取客户的跟进状态

    Args:
        customer_id: 客户ID
        user_id: 用户ID

    Returns:
        dict: {
            'status': 'none' | 'following' | 'completed',
            'sequence_id': 序列ID 或 None,
            'current_step': 当前步骤,
            'total_steps': 总步骤数,
            'strategy_type': 策略类型
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    user_clause, user_params = _build_user_where(user_id)
    user_where = f'AND {user_clause}' if user_clause else ''

    cursor.execute(f'''
        SELECT id, current_step, total_steps, status, strategy_type
        FROM follow_up_sequences
        WHERE customer_id = ? {user_where}
        ORDER BY created_at DESC
        LIMIT 1
    ''', [customer_id] + user_params)
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            'status': 'none',
            'sequence_id': None,
            'current_step': 0,
            'total_steps': 0,
            'strategy_type': None,
        }

    seq_id, current_step, total_steps, seq_status, strategy_type = row
    follow_status = 'none'
    if seq_status == 'active':
        follow_status = 'following'
    elif seq_status == 'completed':
        follow_status = 'completed'

    return {
        'status': follow_status,
        'sequence_id': seq_id,
        'current_step': current_step,
        'total_steps': total_steps,
        'strategy_type': strategy_type,
    }


def batch_create_sequences(customer_ids, user_id, strategy_type='standard', config_json=None):
    """批量创建跟进序列

    Args:
        customer_ids: 客户ID列表
        user_id: 用户ID
        strategy_type: 策略类型
        config_json: 配置信息（dict）

    Returns:
        list: 成功创建的序列ID列表
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 获取策略对应的步数
    template = STRATEGY_TEMPLATES.get(strategy_type, STRATEGY_TEMPLATES['standard'])
    total_steps = len(template) + 1  # +1 是第一封邮件

    config_str = json.dumps(config_json, ensure_ascii=False) if config_json else None

    created_ids = []
    for customer_id in customer_ids:
        try:
            cursor.execute('''
                INSERT INTO follow_up_sequences
                    (customer_id, user_id, strategy_type, total_steps, config_json)
                VALUES (?, ?, ?, ?, ?)
            ''', (customer_id, user_id, strategy_type, total_steps, config_str))
            created_ids.append(cursor.lastrowid)
        except Exception as e:
            print(f'批量创建序列失败 customer_id={customer_id}: {e}')
            continue

    conn.commit()
    conn.close()
    return created_ids
