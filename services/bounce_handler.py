"""
退信处理模块：处理硬退信、软退信，自动禁用邮箱、升级策略
"""
import sqlite3
from datetime import datetime
from database.connection import get_connection

# 硬退信关键词（收件人不存在、域名无效、永久拒绝等）
HARD_BOUNCE_KEYWORDS = [
    'does not exist', 'invalid', 'no such user', 'unknown user',
    'recipient rejected', 'user unknown', 'mailbox unavailable',
    'address rejected', 'permanent failure', '550 5.1.1',
    '550 5.1.3', '551', '552', '553', '5.1.1', '5.1.2',
    '550 requested action not taken', 'permanent error',
    'recipient address rejected', 'mailbox not found',
    'email address could not be found', 'address does not exist',
    'account disabled', 'account suspended', 'account closed',
    'domain not found', 'mx record not found', 'dns error'
]

# 软退信关键词（邮箱满、临时故障、灰名单等）
SOFT_BOUNCE_KEYWORDS = [
    'mailbox full', 'quota exceeded', 'over quota', '452',
    '421', '450', '451', '4.4.1', '4.4.2', '4.4.7',
    '4.7.1', 'temporary failure', 'try again', 'defer',
    'greylist', 'graylist', 'temporarily deferred',
    'too many connections', 'rate limit', 'throttle',
    'message delayed', 'delivery temporarily suspended'
]

# 软退信升级为硬退信的阈值
SOFT_BOUNCE_THRESHOLD = 3


def classify_bounce(reason: str) -> str:
    """根据退信原因分类为 hard/soft/unknown"""
    reason_lower = (reason or '').lower()
    for kw in HARD_BOUNCE_KEYWORDS:
        if kw.lower() in reason_lower:
            return 'hard'
    for kw in SOFT_BOUNCE_KEYWORDS:
        if kw.lower() in reason_lower:
            return 'soft'
    return 'unknown'


def handle_bounce(email_address: str, bounce_reason: str = '', bounce_type: str = None,
                  source: str = 'imap', message_id: str = None) -> dict:
    """
    处理退信事件

    Args:
        email_address: 退信的邮箱地址
        bounce_reason: 退信原因描述
        bounce_type: 已知类型 'hard'|'soft'，None则自动分类
        source: 来源 'imap'|'smtp'
        message_id: 关联的邮件ID

    Returns:
        {'action': 'disabled'|'incremented'|'none', 'email_id': int, 'bounce_type': str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 查找邮箱对应的记录
    cursor.execute(
        "SELECT id, customer_id, bounce_status, bounce_count, is_active FROM emails WHERE email_address = ?",
        (email_address,)
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {'action': 'none', 'email_id': None, 'bounce_type': bounce_type or 'unknown',
                'reason': '邮箱不在系统中'}

    email_id, customer_id, current_status, current_count, is_active = row
    current_count = current_count or 0

    # 分类
    bt = bounce_type or classify_bounce(bounce_reason)
    now_ts = int(datetime.now().timestamp())

    if bt == 'hard':
        # 硬退信：立即禁用邮箱
        cursor.execute("""
            UPDATE emails SET
                bounce_status = 'hard',
                bounce_count = bounce_count + 1,
                last_bounce_at = ?,
                bounce_reason = ?,
                is_active = 0
            WHERE id = ?
        """, (now_ts, bounce_reason[:500], email_id))

        # 记录到 bounce_logs
        _log_bounce(cursor, email_address, customer_id, 'hard', bounce_reason, source, message_id)

        conn.commit()
        conn.close()
        return {'action': 'disabled', 'email_id': email_id, 'bounce_type': 'hard',
                'reason': bounce_reason}

    elif bt == 'soft':
        new_count = current_count + 1
        if new_count >= SOFT_BOUNCE_THRESHOLD:
            # 达到阈值，升级为硬退信处理
            cursor.execute("""
                UPDATE emails SET
                    bounce_status = 'hard',
                    bounce_count = ?,
                    last_bounce_at = ?,
                    bounce_reason = ?,
                    is_active = 0
                WHERE id = ?
            """, (new_count, now_ts,
                  f"{bounce_reason[:400]} (累计{new_count}次软退信，已升级为硬退信)",
                  email_id))
            _log_bounce(cursor, email_address, customer_id, 'hard',
                       f"{bounce_reason} (soft->hard threshold)", source, message_id)
            conn.commit()
            conn.close()
            return {'action': 'disabled', 'email_id': email_id, 'bounce_type': 'hard',
                    'reason': f"累计{new_count}次软退信，已禁用"}
        else:
            # 软退信，计数但不禁用
            cursor.execute("""
                UPDATE emails SET
                    bounce_status = 'soft',
                    bounce_count = ?,
                    last_bounce_at = ?,
                    bounce_reason = ?
                WHERE id = ?
            """, (new_count, now_ts, bounce_reason[:500], email_id))
            _log_bounce(cursor, email_address, customer_id, 'soft', bounce_reason, source, message_id)
            conn.commit()
            conn.close()
            return {'action': 'incremented', 'email_id': email_id, 'bounce_type': 'soft',
                    'reason': f"第{new_count}次软退信（阈值{SOFT_BOUNCE_THRESHOLD}次后禁用）"}

    else:
        # 未知类型，记为 soft 但不立即处理
        cursor.execute("""
            UPDATE emails SET
                bounce_status = 'soft',
                bounce_count = bounce_count + 1,
                last_bounce_at = ?,
                bounce_reason = ?
            WHERE id = ?
        """, (now_ts, f"[未知类型] {bounce_reason[:450]}", email_id))
        _log_bounce(cursor, email_address, customer_id, 'soft', f"[unknown] {bounce_reason}",
                   source, message_id)
        conn.commit()
        conn.close()
        return {'action': 'incremented', 'email_id': email_id, 'bounce_type': 'unknown',
                'reason': '退信类型未知，暂记为软退信'}


def _log_bounce(cursor, email_address, customer_id, bounce_type, reason, source, message_id):
    """记录退信日志"""
    try:
        cursor.execute("""
            INSERT INTO bounce_logs
            (message_id, recipient_email, customer_id, bounce_type, bounce_reason, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (message_id, email_address, customer_id, bounce_type, reason[:500], source))
    except Exception:
        pass  # 忽略重复插入


def handle_smtp_failure(email_address: str, error_message: str) -> dict:
    """
    SMTP发送失败时调用，自动分类并处理
    """
    bt = classify_bounce(error_message)
    return handle_bounce(email_address, error_message, bt, source='smtp')


def get_bounce_stats(user_id: int = None) -> dict:
    """获取退信统计"""
    conn = get_connection()
    cursor = conn.cursor()

    where = "WHERE user_id = ?" if user_id else ""
    params = (user_id,) if user_id else ()

    cursor.execute(f"""
        SELECT
            COUNT(CASE WHEN bounce_status = 'hard' THEN 1 END) as hard_count,
            COUNT(CASE WHEN bounce_status = 'soft' THEN 1 END) as soft_count,
            COUNT(*) as total_emails
        FROM emails
        {where}
    """, params)
    hard_count, soft_count, total = cursor.fetchone()

    cursor.execute(f"""
        SELECT COUNT(*) FROM bounce_logs
        {where.replace('user_id', 'bounce_logs.user_id') if where else ''}
    """, params)
    bounce_total = cursor.fetchone()[0]

    conn.close()
    return {
        'hard_bounce_count': hard_count or 0,
        'soft_bounce_count': soft_count or 0,
        'total_emails': total or 0,
        'bounce_rate': round(((hard_count or 0) + (soft_count or 0)) / max(total, 1) * 100, 2),
        'total_bounce_events': bounce_total or 0
    }
