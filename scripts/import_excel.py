import pandas as pd
import sqlite3
import re
import os
import sys

# 确保能导入项目根目录模块
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from database.connection import get_connection
from database.schema import init_database
from utils.file_parser import parse_emails, _detect_email_type

def parse_email_text(email_text, source='customer_email'):
    """
    从文本中解析联系人和邮箱信息
    统一使用 file_parser.parse_emails() 的解析逻辑
    返回: [{'contact_name': ..., 'job_title': ..., 'email_address': ..., 'email_type': ..., 'source': ...}, ...]
    """
    if pd.isna(email_text) or not str(email_text).strip():
        return []

    results = []
    parsed = parse_emails(email_text)

    for email, email_type, contact_name, job_title in parsed:
        results.append({
            'contact_name': contact_name if contact_name and contact_name != '-' else None,
            'job_title': job_title if job_title and job_title != '-' else None,
            'email_address': email,
            'email_type': email_type,
            'source': source
        })

    return results

def classify_email_type(email_address, contact_name=None):
    """分类邮箱类型 — 委托给 file_parser._detect_email_type"""
    return _detect_email_type(email_address)

def import_excel_to_db(excel_path):
    """导入Excel数据到数据库"""
    print(f"正在读取Excel文件: {excel_path}")
    df = pd.read_excel(excel_path)

    print(f"读取到 {len(df)} 行数据")

    conn = get_connection()
    cursor = conn.cursor()

    success_count = 0
    error_count = 0
    total_contacts = 0
    total_emails = 0

    for idx, row in df.iterrows():
        try:
            # 插入客户信息
            cursor.execute('''
                INSERT INTO customers
                (customer_name, country, address, website, company_info,
                 supplier, supplier_info, customs_data, logistics_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(row.get('客户', '')).strip(),
                str(row.get('国家', '')).strip() if pd.notna(row.get('国家')) else None,
                str(row.get('地址', '')).strip() if pd.notna(row.get('地址')) else None,
                str(row.get('官网', '')).strip() if pd.notna(row.get('官网')) else None,
                str(row.get('公司信息和客户主要产品', '')).strip() if pd.notna(row.get('公司信息和客户主要产品')) else None,
                str(row.get('供应商', '')).strip() if pd.notna(row.get('供应商')) else None,
                str(row.get('供应商信息', '')).strip() if pd.notna(row.get('供应商信息')) else None,
                str(row.get('海关数据购买产品名', '')).strip() if pd.notna(row.get('海关数据购买产品名')) else None,
                str(row.get('物流信息', '')).strip() if pd.notna(row.get('物流信息')) else None
            ))

            customer_id = cursor.lastrowid

            # 解析客户邮箱
            customer_emails = parse_email_text(str(row.get('客户邮箱', '')), 'customer_email')
            for email_info in customer_emails:
                # 插入联系人
                contact_id = None
                if email_info['contact_name']:
                    cursor.execute('''
                        INSERT INTO contacts
                        (customer_id, contact_name, job_title, source)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        customer_id,
                        email_info['contact_name'],
                        email_info['job_title'],
                        email_info['source']
                    ))
                    contact_id = cursor.lastrowid
                    total_contacts += 1

                # 插入邮箱（同时保存 contact_name 和 job_title）
                cursor.execute('''
                    INSERT INTO emails
                    (customer_id, contact_id, email_address, email_type,
                     contact_name, job_title)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    customer_id,
                    contact_id,
                    email_info['email_address'],
                    email_info['email_type'],
                    email_info['contact_name'],
                    email_info['job_title']
                ))
                total_emails += 1

            # 解析领英邮箱
            linkedin_emails = parse_email_text(str(row.get('领英邮箱', '')), 'linkedin')
            for email_info in linkedin_emails:
                # 插入联系人
                contact_id = None
                if email_info['contact_name']:
                    cursor.execute('''
                        INSERT INTO contacts
                        (customer_id, contact_name, job_title, source)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        customer_id,
                        email_info['contact_name'],
                        email_info['job_title'],
                        email_info['source']
                    ))
                    contact_id = cursor.lastrowid
                    total_contacts += 1

                # 插入邮箱（标记为linkedin类型，同时保存 contact_name 和 job_title）
                cursor.execute('''
                    INSERT INTO emails
                    (customer_id, contact_id, email_address, email_type,
                     contact_name, job_title)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    customer_id,
                    contact_id,
                    email_info['email_address'],
                    'linkedin',
                    email_info['contact_name'],
                    email_info['job_title']
                ))
                total_emails += 1

            success_count += 1

        except Exception as e:
            error_count += 1
            print(f"导入第 {idx + 1} 行时出错: {str(e)}")

    conn.commit()
    conn.close()

    print(f"\n导入完成!")
    print(f"成功导入客户: {success_count} 条")
    print(f"失败: {error_count} 条")
    print(f"联系人总数: {total_contacts}")
    print(f"邮箱总数: {total_emails}")

    return success_count, error_count

def show_statistics():
    """显示数据库统计信息"""
    conn = get_connection()
    cursor = conn.cursor()

    # 客户统计
    cursor.execute("SELECT COUNT(*) FROM customers")
    customer_count = cursor.fetchone()[0]

    # 联系人统计
    cursor.execute("SELECT COUNT(*) FROM contacts")
    contact_count = cursor.fetchone()[0]

    # 邮箱统计
    cursor.execute("SELECT COUNT(*) FROM emails")
    email_count = cursor.fetchone()[0]

    # 邮箱类型分布
    cursor.execute("SELECT email_type, COUNT(*) FROM emails GROUP BY email_type")
    type_stats = cursor.fetchall()

    # 联系人来源分布
    cursor.execute("SELECT source, COUNT(*) FROM contacts GROUP BY source")
    source_stats = cursor.fetchall()

    # 有联系人的邮箱 vs 无联系人的邮箱
    cursor.execute("SELECT COUNT(*) FROM emails WHERE contact_id IS NOT NULL")
    emails_with_contact = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM emails WHERE contact_id IS NULL")
    emails_without_contact = cursor.fetchone()[0]

    # 有 contact_name 的邮箱
    cursor.execute("SELECT COUNT(*) FROM emails WHERE contact_name IS NOT NULL AND contact_name != ''")
    emails_with_name = cursor.fetchone()[0]

    # 显示一些示例数据
    cursor.execute('''
        SELECT c.customer_name, e.contact_name, e.job_title, e.email_address, e.email_type
        FROM customers c
        JOIN emails e ON c.id = e.customer_id
        WHERE e.contact_name IS NOT NULL
        LIMIT 5
    ''')
    examples = cursor.fetchall()

    conn.close()

    print("\n" + "=" * 50)
    print("数据库统计报告")
    print("=" * 50)
    print(f"客户总数: {customer_count}")
    print(f"联系人总数: {contact_count}")
    print(f"邮箱总数: {email_count}")
    print(f"\n邮箱类型分布:")
    for email_type, count in type_stats:
        print(f"  {email_type}: {count}")
    print(f"\n联系人来源分布:")
    for source, count in source_stats:
        print(f"  {source}: {count}")
    print(f"\n邮箱关联情况:")
    print(f"  有关联联系人: {emails_with_contact}")
    print(f"  无关联联系人: {emails_without_contact}")
    print(f"  有联系人姓名: {emails_with_name}")

    if examples:
        print(f"\n联系人示例:")
        for ex in examples:
            print(f"  {ex[0]}: {ex[1]} ({ex[2]}) - {ex[3]} [{ex[4]}]")

if __name__ == '__main__':
    # 初始化数据库
    init_database()

    # 导入Excel数据
    excel_path = r'c:\Users\fjy\.trae-cn\attachments\6a2fffcfb8fffc68440d4dd7\30a4f47b-274e-41d7-b2d0-4d9d7f7e825d_8bae562b-71f1-4366-b423-95d10068db05_开发表格20260405updated.xlsx'

    if os.path.exists(excel_path):
        import_excel_to_db(excel_path)
        show_statistics()
    else:
        print(f"文件不存在: {excel_path}")
