"""统一发送日志服务 - 所有发送记录必须通过此服务写入 email_logs"""
from datetime import datetime
from database.connection import get_connection


def log_email_send(customer_id, email_id, task_id, source, subject, content,
                   status, error_message=None, conn=None):
    """
    统一写入 email_logs 表
    source 字段规范: 'manual' | 'scheduled' | 'batch' | 'cli'
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO email_logs
            (customer_id, email_id, task_id, source, email_subject, email_content,
             send_status, error_message, sent_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (customer_id, email_id, task_id, source, subject, content,
              status, error_message,
              datetime.now().isoformat() if status == 'sent' else None))
        conn.commit()
        log_id = cursor.lastrowid
    finally:
        if should_close:
            conn.close()
    return log_id
