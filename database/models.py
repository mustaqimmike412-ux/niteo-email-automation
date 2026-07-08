import sqlite3
from datetime import datetime
import os
import json

DB_PATH = os.path.join(os.path.dirname(__file__), 'email_automation.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    conn.execute('PRAGMA foreign_keys=ON')  # 启用外键约束，确保级联删除生效
    return conn

def init_database():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 客户信息主表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            country TEXT,
            address TEXT,
            website TEXT,
            company_info TEXT,
            supplier TEXT,
            supplier_info TEXT,
            customs_data TEXT,
            logistics_info TEXT,
            industry_type TEXT,
            website_title TEXT,
            website_description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 联系人表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            contact_name TEXT,
            job_title TEXT,
            source TEXT CHECK(source IN ('customer_email', 'linkedin', 'manual')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    ''')
    
    # 邮箱表（支持多个邮箱）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            contact_id INTEGER,
            email_address TEXT NOT NULL,
            email_type TEXT CHECK(email_type IN ('public', 'personal', 'linkedin')),
            contact_name TEXT,
            job_title TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
        )
    ''')
    
    # 邮件发送记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            email_id INTEGER,
            contact_id INTEGER,
            task_id TEXT,
            source TEXT DEFAULT 'manual',
            email_subject TEXT,
            email_content TEXT,
            send_status TEXT CHECK(send_status IN ('pending', 'sent', 'failed')),
            error_message TEXT,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE SET NULL,
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
        )
    ''')

    # 迁移：为已有表添加 task_id 和 source 字段
    try:
        cursor.execute('ALTER TABLE email_logs ADD COLUMN task_id TEXT')
    except:
        pass
    try:
        cursor.execute('ALTER TABLE email_logs ADD COLUMN source TEXT DEFAULT \'manual\'')
    except:
        pass

    # 调度器邮件发送记录表（独立存储调度器发送的邮件）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_logs_scheduled (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            email_id INTEGER,
            contact_id INTEGER,
            task_id TEXT,
            schedule_job_id TEXT,
            email_subject TEXT,
            email_content TEXT,
            send_status TEXT CHECK(send_status IN ('pending', 'sent', 'failed')),
            error_message TEXT,
            scheduled_at TIMESTAMP,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE SET NULL,
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
        )
    ''')

    # 邮件模板表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_name TEXT NOT NULL,
            subject_template TEXT NOT NULL,
            body_template TEXT NOT NULL,
            email_type TEXT CHECK(email_type IN ('public', 'personal')),
            industry_type TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 客户主题池表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customer_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            subject_line TEXT NOT NULL,
            subject_index INTEGER NOT NULL,
            subject_type TEXT NOT NULL,
            generation_strategy TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            UNIQUE(customer_id, subject_index)
        )
    ''')
    
    # 主题使用记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subject_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            email_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            subject_line TEXT NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE,
            FOREIGN KEY (subject_id) REFERENCES customer_subjects(id) ON DELETE CASCADE
        )
    ''')
    
    # 发送调度表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS send_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            scheduled_at TIMESTAMP NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'failed', 'cancelled')),
            subject_id INTEGER,
            email_log_id INTEGER,
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (subject_id) REFERENCES customer_subjects(id) ON DELETE SET NULL,
            FOREIGN KEY (email_log_id) REFERENCES email_logs(id) ON DELETE SET NULL
        )
    ''')
    
    # 创建索引优化查询
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(customer_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_emails_address ON emails(email_address)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_emails_customer ON emails(customer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_customer ON contacts(customer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_logs_sent ON email_logs(sent_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_logs_status ON email_logs(send_status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_logs_scheduled_sent ON email_logs_scheduled(sent_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_logs_scheduled_status ON email_logs_scheduled(send_status)')

    # 冷却期手动解除记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cooldown_override (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            released_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cooldown_override_customer ON cooldown_override(customer_id)')

    # 新表索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_customer_subjects_customer ON customer_subjects(customer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_subject_usage_customer ON subject_usage_log(customer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_subject_usage_email ON subject_usage_log(email_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_send_schedule_status ON send_schedule(status, scheduled_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_send_schedule_time ON send_schedule(scheduled_at)')

    # 资料管理表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            material_type TEXT NOT NULL,
            category TEXT,
            scope TEXT,
            track TEXT,
            region TEXT,
            content_json TEXT NOT NULL,
            content_summary TEXT,
            priority INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            has_attachment INTEGER DEFAULT 0,
            attachment_path TEXT,
            attachment_type TEXT,
            attachment_name TEXT,
            tags TEXT,
            source TEXT DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS material_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            customer_id INTEGER,
            email_log_id INTEGER,
            usage_context TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
            FOREIGN KEY (email_log_id) REFERENCES email_logs(id) ON DELETE SET NULL
        )
    ''')

    # 资料表索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_type ON materials(material_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_category ON materials(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_scope ON materials(scope)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_track ON materials(track)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_active ON materials(is_active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_priority ON materials(priority DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_type_scope ON materials(material_type, scope, is_active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_type_track ON materials(material_type, track, is_active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_material ON material_usage_log(material_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_customer ON material_usage_log(customer_id)')

    # 发送任务项表（单封邮件粒度追踪）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS send_task_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            email_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            email_address TEXT NOT NULL,
            contact_name TEXT,
            email_type TEXT,
            subject TEXT,
            greeting TEXT,
            item_status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 2,
            error_message TEXT,
            scheduled_send_at TIMESTAMP,
            actual_send_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_items_task ON send_task_items(task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_items_status ON send_task_items(task_id, item_status)')

    # 发送任务元数据表（用于刷新页面后恢复进度）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS send_tasks_meta (
            task_id TEXT PRIMARY KEY,
            task_type TEXT NOT NULL DEFAULT 'manual',
            status TEXT DEFAULT 'pending',
            customer_id INTEGER,
            customer_name TEXT,
            total_emails INTEGER DEFAULT 0,
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            current_index INTEGER DEFAULT 0,
            progress INTEGER DEFAULT 0,
            current_step TEXT DEFAULT '',
            step_status TEXT DEFAULT '{}',
            email_preview_subject TEXT,
            email_preview_body TEXT,
            email_preview_word_count INTEGER,
            send_config TEXT DEFAULT '{}',
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_send_tasks_meta_status ON send_tasks_meta(status, created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_send_tasks_meta_created ON send_tasks_meta(created_at DESC)')

    # 迁移：为 send_tasks_meta 添加 user_id 字段
    try:
        cursor.execute('ALTER TABLE send_tasks_meta ADD COLUMN user_id INTEGER')
    except:
        pass

    conn.commit()
    conn.close()
    print("数据库初始化完成")


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


def get_statistics():
    """获取数据库统计信息"""
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    
    # 客户总数
    cursor.execute("SELECT COUNT(*) FROM customers")
    stats['customer_count'] = cursor.fetchone()[0]
    
    # 联系人总数
    cursor.execute("SELECT COUNT(*) FROM contacts")
    stats['contact_count'] = cursor.fetchone()[0]
    
    # 邮箱总数
    cursor.execute("SELECT COUNT(*) FROM emails")
    stats['email_count'] = cursor.fetchone()[0]
    
    # 邮箱类型分布
    cursor.execute("SELECT email_type, COUNT(*) FROM emails GROUP BY email_type")
    stats['email_types'] = cursor.fetchall()
    
    # 联系人来源分布
    cursor.execute("SELECT source, COUNT(*) FROM contacts GROUP BY source")
    stats['contact_sources'] = cursor.fetchall()
    
    # 邮件发送统计
    cursor.execute("SELECT COUNT(*) FROM email_logs WHERE send_status = 'sent'")
    stats['sent_count'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM email_logs WHERE send_status = 'failed'")
    stats['failed_count'] = cursor.fetchone()[0]
    
    conn.close()
    return stats

if __name__ == '__main__':
    init_database()
    stats = get_statistics()
    print("\n数据库统计:")
    print(f"客户总数: {stats['customer_count']}")
    print(f"联系人总数: {stats['contact_count']}")
    print(f"邮箱总数: {stats['email_count']}")
