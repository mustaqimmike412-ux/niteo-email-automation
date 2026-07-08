import json
from database.connection import get_connection


def persist_send_task_meta(task_id, task_type='manual', status='pending', customer_id=None,
                           customer_name=None, total_emails=0, sent_count=0, failed_count=0,
                           current_index=0, progress=0, current_step='', step_status=None,
                           email_preview=None, send_config=None, error=None, user_id=None):
    """持久化发送任务元数据到数据库（upsert 语义）"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO send_tasks_meta
            (task_id, task_type, status, customer_id, customer_name, total_emails,
             sent_count, failed_count, current_index, progress, current_step,
             step_status, email_preview_subject, email_preview_body,
             email_preview_word_count, send_config, error, user_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(task_id) DO UPDATE SET
                status=excluded.status,
                total_emails=excluded.total_emails,
                sent_count=excluded.sent_count,
                failed_count=excluded.failed_count,
                current_index=excluded.current_index,
                progress=excluded.progress,
                current_step=excluded.current_step,
                step_status=excluded.step_status,
                email_preview_subject=excluded.email_preview_subject,
                email_preview_body=excluded.email_preview_body,
                email_preview_word_count=excluded.email_preview_word_count,
                send_config=excluded.send_config,
                error=excluded.error,
                updated_at=CURRENT_TIMESTAMP
        ''', (
            task_id, task_type, status, customer_id, customer_name, total_emails,
            sent_count, failed_count, current_index, progress, current_step,
            json.dumps(step_status or {}, ensure_ascii=False),
            email_preview.get('subject') if email_preview else None,
            email_preview.get('body') if email_preview else None,
            email_preview.get('word_count') if email_preview else None,
            json.dumps(send_config or {}, ensure_ascii=False),
            error,
            user_id
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  ⚠ 持久化任务元数据失败: {e}")


def get_active_send_tasks(user_id=None, admin=False):
    """获取所有活跃任务（running/paused）和最近24小时完成的任务"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        params = []
        user_where = ""
        if not admin and user_id:
            user_where = " AND user_id = ?"
            params = [user_id]
        cursor.execute(f'''
            SELECT task_id, task_type, status, customer_id, customer_name,
                   total_emails, sent_count, failed_count, current_index,
                   progress, current_step, step_status, email_preview_subject,
                   email_preview_body, email_preview_word_count, send_config,
                   error, created_at, started_at, completed_at
            FROM send_tasks_meta
            WHERE (status IN ('running', 'paused')
               OR (status IN ('completed', 'failed', 'cancelled')
                   AND created_at > datetime('now', '-24 hours'))){user_where}
            ORDER BY
                CASE WHEN status IN ('running', 'paused') THEN 0 ELSE 1 END,
                created_at DESC
        ''', params)
        rows = cursor.fetchall()
        conn.close()

        tasks = []
        for row in rows:
            tasks.append({
                'task_id': row[0], 'task_type': row[1], 'status': row[2],
                'customer_id': row[3], 'customer_name': row[4],
                'total_emails': row[5], 'sent_count': row[6], 'failed_count': row[7],
                'current_index': row[8], 'progress': row[9], 'current_step': row[10],
                'step_status': json.loads(row[11]) if row[11] else {},
                'email_preview': {
                    'subject': row[12], 'body': row[13], 'word_count': row[14]
                } if row[12] else None,
                'send_config': json.loads(row[15]) if row[15] else {},
                'error': row[16], 'created_at': row[17],
                'started_at': row[18], 'completed_at': row[19],
            })
        return tasks
    except Exception as e:
        print(f"  ⚠ 获取活跃任务失败: {e}")
        return []


def get_send_task_items(task_id, user_id=None, admin=False):
    """获取指定任务的所有邮件项"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if not admin and user_id:
            cursor.execute('''
                SELECT email_id, customer_id, email_address, contact_name, email_type,
                       subject, greeting, item_status, retry_count, max_retries,
                       error_message, scheduled_send_at, actual_send_at
                FROM send_task_items
                WHERE task_id = ? AND user_id = ?
                ORDER BY id
            ''', (task_id, user_id))
        else:
            cursor.execute('''
                SELECT email_id, customer_id, email_address, contact_name, email_type,
                       subject, greeting, item_status, retry_count, max_retries,
                       error_message, scheduled_send_at, actual_send_at
                FROM send_task_items
                WHERE task_id = ?
                ORDER BY id
            ''', (task_id,))
        rows = cursor.fetchall()
        conn.close()

        items = []
        for row in rows:
            items.append({
                'email_id': row[0], 'customer_id': row[1], 'email_address': row[2],
                'contact_name': row[3], 'email_type': row[4], 'subject': row[5],
                'greeting': row[6], 'status': row[7], 'retry_count': row[8],
                'max_retries': row[9], 'error_message': row[10],
                'scheduled_send_at': row[11], 'actual_send_at': row[12],
            })
        return items
    except Exception as e:
        print(f"  ⚠ 获取任务项失败: {e}")
        return []


def get_statistics(user_id=None, admin=False):
    """获取数据库统计信息"""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    user_where = ""
    user_params = []
    if not admin and user_id:
        user_where = " WHERE user_id = ?"
        user_params = [user_id]

    # 客户总数
    cursor.execute(f"SELECT COUNT(*) FROM customers{user_where}", user_params)
    stats['customer_count'] = cursor.fetchone()[0]

    # 联系人总数
    cursor.execute(f"SELECT COUNT(*) FROM contacts{user_where}", user_params)
    stats['contact_count'] = cursor.fetchone()[0]

    # 邮箱总数
    cursor.execute(f"SELECT COUNT(*) FROM emails{user_where}", user_params)
    stats['email_count'] = cursor.fetchone()[0]

    # 邮箱类型分布
    cursor.execute(f"SELECT email_type, COUNT(*) FROM emails{user_where} GROUP BY email_type", user_params)
    stats['email_types'] = cursor.fetchall()

    # 联系人来源分布
    cursor.execute(f"SELECT source, COUNT(*) FROM contacts{user_where} GROUP BY source", user_params)
    stats['contact_sources'] = cursor.fetchall()

    # 邮件发送统计
    cursor.execute(f"SELECT COUNT(*) FROM email_logs WHERE send_status = 'sent'{(' AND user_id = ?' if not admin and user_id else '')}", user_params if not admin and user_id else [])
    stats['sent_count'] = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM email_logs WHERE send_status = 'failed'{(' AND user_id = ?' if not admin and user_id else '')}", user_params if not admin and user_id else [])
    stats['failed_count'] = cursor.fetchone()[0]

    conn.close()
    return stats
