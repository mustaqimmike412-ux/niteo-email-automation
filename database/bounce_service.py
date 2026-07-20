"""
退信数据服务层
提供 bounce_logs 的 CRUD 操作和统计查询
"""
from database.connection import get_connection


def save_bounce_log(data: dict) -> int:
    """保存一条退信记录，返回 bounce_id"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO bounce_logs
            (message_id, email_log_id, email_id, customer_id, bounce_type,
             recipient_email, original_subject, diagnostic_code, status_code,
             action, bounce_subject, bounce_from, raw_bounce_snippet, matched_log)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('message_id'),
            data.get('email_log_id'),
            data.get('email_id'),
            data.get('customer_id'),
            data.get('bounce_type'),
            data.get('recipient_email'),
            data.get('original_subject'),
            data.get('diagnostic_code'),
            data.get('status_code'),
            data.get('action'),
            data.get('bounce_subject'),
            data.get('bounce_from'),
            data.get('raw_snippet'),
            data.get('matched_log', 0)
        ))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"[BounceService] save error: {e}")
        return 0
    finally:
        conn.close()


def update_email_log_bounce(recipient_email: str, bounce_type: str,
                           original_subject: str = None, user_id: int = None) -> int:
    """根据退信邮箱匹配原始发送记录并更新 bounce_status，返回匹配的 log_id。
    当提供 user_id 时，通过 emails->customers 链过滤，防止跨用户操作。"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        log_id = None

        # 构建 user_id 过滤条件
        user_join = ''
        user_where = ''
        user_params_extra = []
        if user_id is not None:
            user_join = ' JOIN customers c ON e.customer_id = c.id '
            user_where = ' AND c.user_id = ? '
            user_params_extra = [user_id]

        # 方法1：收件人 + 主题匹配
        if original_subject:
            cursor.execute(f'''
                SELECT el.id, el.email_id, el.customer_id
                FROM email_logs el
                JOIN emails e ON el.email_id = e.id
                {user_join}
                WHERE e.email_address = ?
                  AND el.send_status = 'sent'
                  AND (el.bounce_status IS NULL OR el.bounce_status = '')
                  {user_where}
                ORDER BY el.sent_at DESC LIMIT 1
            ''', (recipient_email,) + tuple(user_params_extra))
            row = cursor.fetchone()
            if row:
                log_id, email_id, customer_id = row
            else:
                cursor.execute(f'''
                    SELECT el.id, el.email_id, el.customer_id
                    FROM email_logs el
                    JOIN emails e ON el.email_id = e.id
                    {user_join}
                    WHERE e.email_address = ?
                      AND el.email_subject LIKE ?
                      AND el.send_status = 'sent'
                      AND (el.bounce_status IS NULL OR el.bounce_status = '')
                      {user_where}
                    ORDER BY el.sent_at DESC LIMIT 1
                ''', (recipient_email, f'%{original_subject}%') + tuple(user_params_extra))
                row = cursor.fetchone()

        if not log_id:
            cursor.execute(f'''
                SELECT el.id, el.email_id, el.customer_id
                FROM email_logs el
                JOIN emails e ON el.email_id = e.id
                {user_join}
                WHERE e.email_address = ?
                  AND el.send_status = 'sent'
                  AND (el.bounce_status IS NULL OR el.bounce_status = '')
                  {user_where}
                ORDER BY el.sent_at DESC LIMIT 1
            ''', (recipient_email,) + tuple(user_params_extra))
            row = cursor.fetchone()

        if row:
            log_id, email_id, customer_id = row
            cursor.execute('UPDATE email_logs SET bounce_status = ? WHERE id = ?',
                          (bounce_type, log_id))
            conn.commit()
            return log_id
        return 0
    except Exception as e:
        print(f"[BounceService] match error: {e}")
        return 0
    finally:
        conn.close()


def get_bounce_stats(user_id: int = None, admin: bool = False) -> dict:
    """获取退信统计"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        user_where = ""
        user_params = []
        if not admin and user_id:
            user_where = " AND user_id = ?"
            user_params = [user_id]

        # 总退信
        cursor.execute(f"SELECT COUNT(*) FROM bounce_logs WHERE 1=1{user_where}", user_params)
        total = cursor.fetchone()[0]

        # 硬退信
        cursor.execute(f"SELECT COUNT(*) FROM bounce_logs WHERE bounce_type = 'hard'{user_where}", user_params)
        hard = cursor.fetchone()[0]

        # 软退信
        cursor.execute(f"SELECT COUNT(*) FROM bounce_logs WHERE bounce_type = 'soft'{user_where}", user_params)
        soft = cursor.fetchone()[0]

        # 今日退信
        cursor.execute(f"SELECT COUNT(*) FROM bounce_logs WHERE date(created_at) = date('now'){user_where}", user_params)
        today = cursor.fetchone()[0]

        # 退信率
        sent_where = ""
        sent_params = []
        if not admin and user_id:
            sent_where = " AND user_id = ?"
            sent_params = [user_id]
        cursor.execute(f"SELECT COUNT(*) FROM email_logs WHERE send_status = 'sent'{sent_where}", sent_params)
        total_sent = cursor.fetchone()[0]
        rate = round(total / total_sent * 100, 1) if total_sent > 0 else 0

        # TOP 5 退信原因
        cursor.execute(f'''
            SELECT diagnostic_code, COUNT(*) as cnt
            FROM bounce_logs
            WHERE diagnostic_code IS NOT NULL AND diagnostic_code != ''{user_where}
            GROUP BY diagnostic_code
            ORDER BY cnt DESC LIMIT 5
        ''', user_params)
        top_reasons = [{'code': r[0], 'count': r[1]} for r in cursor.fetchall()]

        # TOP 5 退信域名
        cursor.execute(f'''
            SELECT substr(recipient_email, instr(recipient_email, '@') + 1) as domain, COUNT(*) as cnt
            FROM bounce_logs
            WHERE 1=1{user_where}
            GROUP BY domain
            ORDER BY cnt DESC LIMIT 5
        ''', user_params)
        top_domains = [{'domain': r[0], 'count': r[1]} for r in cursor.fetchall()]

        conn.close()
        return {
            'total': total,
            'hard': hard,
            'soft': soft,
            'unknown': total - hard - soft,
            'today': today,
            'rate': rate,
            'top_reasons': top_reasons,
            'top_domains': top_domains
        }
    except Exception as e:
        print(f"[BounceService] stats error: {e}")
        conn.close()
        return {'total': 0, 'hard': 0, 'soft': 0, 'unknown': 0, 'today': 0, 'rate': 0,
                'top_reasons': [], 'top_domains': []}


def get_bounce_list(page: int = 1, per_page: int = 20, bounce_type: str = '', user_id: int = None, admin: bool = False) -> dict:
    """获取退信列表"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        where_clauses = []
        params = []
        if bounce_type:
            where_clauses.append('bounce_type = ?')
            params.append(bounce_type)
        if not admin and user_id:
            where_clauses.append('(b.user_id = ? OR b.user_id IS NULL)')
            params.append(user_id)

        where = 'WHERE ' + ' AND '.join(where_clauses) if where_clauses else ''

        cursor.execute(f'SELECT COUNT(*) FROM bounce_logs b {where}', params)
        total = cursor.fetchone()[0]

        offset = (page - 1) * per_page
        cursor.execute(f'''
            SELECT b.id, b.recipient_email, b.bounce_type, b.status_code,
                   b.diagnostic_code, b.bounce_subject, b.original_subject,
                   b.created_at, b.matched_log, b.processed,
                   c.customer_name, b.customer_id
            FROM bounce_logs b
            LEFT JOIN customers c ON b.customer_id = c.id
            {where}
            ORDER BY b.created_at DESC
            LIMIT ? OFFSET ?
        ''', params + [per_page, offset])
        rows = cursor.fetchall()
        conn.close()

        return {
            'items': [{
                'id': r[0],
                'recipient': r[1],
                'bounce_type': r[2],
                'status_code': r[3],
                'diagnostic_code': r[4],
                'bounce_subject': r[5],
                'original_subject': r[6],
                'created_at': r[7],
                'matched': bool(r[8]),
                'processed': bool(r[9]),
                'customer_name': r[10],
                'customer_id': r[11]
            } for r in rows],
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }
    except Exception as e:
        print(f"[BounceService] list error: {e}")
        conn.close()
        return {'items': [], 'total': 0, 'page': 1, 'per_page': per_page, 'total_pages': 0}


def get_processed_message_ids() -> set:
    """获取已处理的 Message-ID 集合"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT message_id FROM bounce_logs WHERE message_id IS NOT NULL')
    rows = cursor.fetchall()
    conn.close()
    return {r[0] for r in rows}
