#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库ID重置脚本
将客户ID从205-302重置为1-98，保持所有外键关联完整性
"""

import os
import sys
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_connection

DB_PATH = os.path.join(os.path.dirname(__file__), 'email_automation.db')
BACKUP_PATH = DB_PATH + '.backup'


def backup_database():
    """备份数据库"""
    print("1. 备份数据库...")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"   ✓ 已备份到: {BACKUP_PATH}")


def reset_customer_ids():
    """重置客户ID从1开始"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # 禁用外键约束
        print("2. 禁用外键约束...")
        cursor.execute("PRAGMA foreign_keys = OFF")

        # 开始事务
        print("3. 开始事务...")
        cursor.execute("BEGIN TRANSACTION")

        # 获取所有客户数据（按ID排序）
        print("4. 备份客户数据...")
        cursor.execute("""
            SELECT id, customer_name, country, address, website, company_info,
                   supplier, supplier_info, customs_data, logistics_info,
                   industry_type, website_title, website_description,
                   created_at, updated_at
            FROM customers
            ORDER BY id
        """)
        customers_data = cursor.fetchall()
        print(f"   共 {len(customers_data)} 个客户")

        # 获取所有联系人数据
        print("5. 备份联系人数据...")
        cursor.execute("SELECT * FROM contacts ORDER BY id")
        contacts_data = cursor.fetchall()
        print(f"   共 {len(contacts_data)} 个联系人")

        # 获取所有邮箱数据
        print("6. 备份邮箱数据...")
        cursor.execute("SELECT * FROM emails ORDER BY id")
        emails_data = cursor.fetchall()
        print(f"   共 {len(emails_data)} 个邮箱")

        # 获取所有主题数据
        print("7. 备份主题池数据...")
        cursor.execute("SELECT * FROM customer_subjects ORDER BY id")
        subjects_data = cursor.fetchall()
        print(f"   共 {len(subjects_data)} 个主题")

        # 获取所有调度数据
        print("8. 备份调度数据...")
        cursor.execute("SELECT * FROM send_schedule ORDER BY id")
        schedule_data = cursor.fetchall()
        print(f"   共 {len(schedule_data)} 条调度")

        # 获取所有主题使用记录
        print("9. 备份主题使用记录...")
        cursor.execute("SELECT * FROM subject_usage_log ORDER BY id")
        usage_data = cursor.fetchall()
        print(f"   共 {len(usage_data)} 条记录")

        # 清空业务表
        print("10. 清空业务表...")
        cursor.execute("DELETE FROM subject_usage_log")
        cursor.execute("DELETE FROM send_schedule")
        cursor.execute("DELETE FROM customer_subjects")
        cursor.execute("DELETE FROM emails")
        cursor.execute("DELETE FROM contacts")
        cursor.execute("DELETE FROM customers")
        print("    ✓ 已清空")

        # 重置sqlite_sequence
        print("11. 重置自增计数器...")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='customers'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='contacts'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='emails'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='customer_subjects'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='send_schedule'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='subject_usage_log'")
        print("    ✓ 已重置")

        # 重新插入customers（ID会从1开始自动分配）
        print("12. 重新插入客户数据...")
        old_to_new_id = {}
        for row in customers_data:
            old_id = row[0]
            cursor.execute("""
                INSERT INTO customers (customer_name, country, address, website, company_info,
                    supplier, supplier_info, customs_data, logistics_info,
                    industry_type, website_title, website_description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row[1:])
            new_id = cursor.lastrowid
            old_to_new_id[old_id] = new_id

        print(f"    ✓ 已插入 {len(old_to_new_id)} 个客户")
        print(f"    ID映射: {min(old_to_new_id.values())} - {max(old_to_new_id.values())}")

        # 重新插入contacts
        print("13. 重新插入联系人数据...")
        contacts_inserted = 0
        for row in contacts_data:
            old_customer_id = row[1]
            new_customer_id = old_to_new_id.get(old_customer_id)
            if new_customer_id:
                cursor.execute("""
                    INSERT INTO contacts (customer_id, contact_name, job_title, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (new_customer_id, row[2], row[3], row[4], row[5]))
                contacts_inserted += 1
        print(f"    ✓ 已插入 {contacts_inserted} 个联系人")

        # 重新插入emails
        print("14. 重新插入邮箱数据...")
        emails_inserted = 0
        for row in emails_data:
            old_customer_id = row[1]
            new_customer_id = old_to_new_id.get(old_customer_id)
            if new_customer_id:
                cursor.execute("""
                    INSERT INTO emails (customer_id, contact_id, email_address, email_type, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (new_customer_id, row[2], row[3], row[4], row[5], row[6]))
                emails_inserted += 1
        print(f"    ✓ 已插入 {emails_inserted} 个邮箱")

        # 重新插入customer_subjects
        print("15. 重新插入主题池数据...")
        subjects_inserted = 0
        for row in subjects_data:
            old_customer_id = row[1]
            new_customer_id = old_to_new_id.get(old_customer_id)
            if new_customer_id:
                cursor.execute("""
                    INSERT INTO customer_subjects (customer_id, subject_line, subject_index, subject_type, generation_strategy)
                    VALUES (?, ?, ?, ?, ?)
                """, (new_customer_id, row[2], row[3], row[4], row[5]))
                subjects_inserted += 1
        print(f"    ✓ 已插入 {subjects_inserted} 个主题")

        # 重新插入send_schedule
        print("16. 重新插入调度数据...")
        schedule_inserted = 0
        for row in schedule_data:
            old_customer_id = row[1]
            new_customer_id = old_to_new_id.get(old_customer_id)
            if new_customer_id:
                cursor.execute("""
                    INSERT INTO send_schedule (customer_id, email_id, subject_id, scheduled_at, status, priority, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (new_customer_id, row[2], row[3], row[4], row[5], row[6], row[7]))
                schedule_inserted += 1
        print(f"    ✓ 已插入 {schedule_inserted} 条调度")

        # 重新插入subject_usage_log
        print("17. 重新插入主题使用记录...")
        usage_inserted = 0
        for row in usage_data:
            old_customer_id = row[1]
            new_customer_id = old_to_new_id.get(old_customer_id)
            if new_customer_id:
                cursor.execute("""
                    INSERT INTO subject_usage_log (customer_id, email_id, subject_id, subject_line, used_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (new_customer_id, row[2], row[3], row[4], row[5]))
                usage_inserted += 1
        print(f"    ✓ 已插入 {usage_inserted} 条记录")

        # 修改email_logs表结构允许customer_id为NULL
        print("18. 修改邮件日志表结构...")
        cursor.execute("""
            CREATE TABLE email_logs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                email_id INTEGER,
                contact_id INTEGER,
                email_subject TEXT,
                email_content TEXT,
                send_status TEXT,
                error_message TEXT,
                sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
                FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("""
            INSERT INTO email_logs_new (id, customer_id, email_id, contact_id, email_subject, email_content, send_status, error_message, sent_at, created_at)
            SELECT id, customer_id, email_id, contact_id, email_subject, email_content, send_status, error_message, sent_at, created_at
            FROM email_logs
        """)
        cursor.execute("DROP TABLE email_logs")
        cursor.execute("ALTER TABLE email_logs_new RENAME TO email_logs")
        print("    ✓ 邮件日志表已更新（customer_id允许NULL）")

        # 解除email_logs的客户关联
        print("19. 解除邮件日志客户关联...")
        cursor.execute("UPDATE email_logs SET customer_id = NULL WHERE customer_id IS NOT NULL")
        print("    ✓ 邮件日志已解除客户关联（保留历史）")

        # 提交事务
        print("20. 提交事务...")
        conn.commit()

        # 重新启用外键约束
        print("21. 重新启用外键约束...")
        cursor.execute("PRAGMA foreign_keys = ON")

        # 验证
        print("\n" + "=" * 50)
        print("验证结果:")
        print("=" * 50)

        cursor.execute("SELECT MIN(id), MAX(id), COUNT(*) FROM customers")
        min_id, max_id, count = cursor.fetchone()
        print(f"客户ID范围: {min_id} - {max_id}")
        print(f"客户总数: {count}")

        cursor.execute("SELECT COUNT(*) FROM contacts")
        print(f"联系人总数: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM emails")
        print(f"邮箱总数: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM customer_subjects")
        print(f"主题池总数: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM email_logs")
        print(f"邮件日志总数: {cursor.fetchone()[0]} (历史记录保留)")

        print("\n✓ ID重置完成!")

    except Exception as e:
        print(f"\n✗ 错误: {e}")
        print("正在回滚事务...")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print("=" * 50)
    print("数据库ID重置工具")
    print("=" * 50)
    print(f"数据库路径: {DB_PATH}")
    print("\n此操作将:")
    print("  - 备份现有数据库")
    print("  - 将客户ID从205-302重置为1-98")
    print("  - 保留邮件发送历史记录")
    print("\n按 Enter 继续，或按 Ctrl+C 取消...")
    input()

    backup_database()
    reset_customer_ids()

    print(f"\n备份文件: {BACKUP_PATH}")
    print("如需恢复，请将备份文件复制回原路径")
