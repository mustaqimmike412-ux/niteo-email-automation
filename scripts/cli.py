#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能邮件自动化系统主程序
整合网站分析、客户类型判断、FABE法则邮件生成
"""

import os
import sys
import argparse
from datetime import datetime

# 确保能导入项目根目录模块
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from database.schema import init_database
from database.connection import get_connection
from scripts.import_excel import import_excel_to_db, show_statistics
from core.sender import EmailSender, create_config_template
from generators.legacy_generator import LegacyEmailGenerator

def init_system():
    """初始化系统"""
    print("=" * 50)
    print("智能邮件自动化系统初始化")
    print("=" * 50)
    
    print("\n1. 初始化数据库...")
    init_database()
    
    print("\n2. 创建配置文件模板...")
    create_config_template()
    
    # 创建公司信息模板
    company_info_template = {
        "company_name": "Niteo Solar",
        "sender_name": "Travis",
        "job_title": "Business Development Manager",
        "email": "travis@niteowork.com",
        "phone": "+86 xxx xxxx xxxx",
        "website": "www.niteosolar.com",
        "years_in_business": "10+",
        "main_products": [
            "High-performance solar panels (1W-200W)",
            "Customized OEM/ODM solar solutions",
            "Energy storage systems",
            "BIPV (Building Integrated Photovoltaics)"
        ],
        "strength1": "BC (Back Contact) cell technology with pure black aesthetics",
        "strength2": "Global manufacturing footprint (China, Saudi, Indonesia, Vietnam)",
        "strength3": "Proven partnerships with Amazon, Ring, Arlo, EcoFlow",
        "strength4": "DDP delivery service to Los Angeles and major ports",
        "industry": "Solar Energy / Renewable Energy",
        "target_markets": ["North America", "Europe", "Asia Pacific"],
        "company_description": "Leading solar panel manufacturer specializing in customized OEM/ODM solutions for consumer electronics, security devices, and energy storage systems."
    }
    
    config_dir = os.path.join(os.path.dirname(__file__), 'config')
    os.makedirs(config_dir, exist_ok=True)
    company_info_path = os.path.join(config_dir, 'company_info.json')
    
    if not os.path.exists(company_info_path):
        import json
        with open(company_info_path, 'w', encoding='utf-8') as f:
            json.dump(company_info_template, f, indent=4, ensure_ascii=False)
        print(f"\n3. 创建公司信息模板: {company_info_path}")
    
    print("\n系统初始化完成!")
    print("请完成以下配置：")
    print("  1. 修改 config/smtp_config.json - 配置邮箱")
    print("  2. 修改 config/company_info.json - 配置公司信息")

def import_data(excel_path):
    """导入Excel数据"""
    if not os.path.exists(excel_path):
        print(f"错误: 文件不存在 {excel_path}")
        return
    
    print(f"正在导入数据: {excel_path}")
    success, error = import_excel_to_db(excel_path)
    show_statistics()

def replace_data(excel_path, confirm=False):
    """
    用新Excel数据替换数据库中的老客户数据
    会清空现有客户、联系人、邮箱数据，重新导入
    """
    if not os.path.exists(excel_path):
        print(f"错误: 文件不存在 {excel_path}")
        return
    
    if not confirm:
        print("=" * 60)
        print("警告: 此操作将删除所有现有客户数据并重新导入!")
        print("=" * 60)
        print(f"目标文件: {excel_path}")
        print("\n现有数据将被清空，包括:")
        print("  - 客户信息")
        print("  - 联系人信息")
        print("  - 邮箱地址")
        print("  - 邮件发送记录将保留，但关联会断开")
        print("\n如需继续，请添加 --confirm 参数")
        return
    
    print("=" * 60)
    print("开始替换客户数据")
    print("=" * 60)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. 获取替换前的统计
    cursor.execute("SELECT COUNT(*) FROM customers")
    old_customer_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM contacts")
    old_contact_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM emails")
    old_email_count = cursor.fetchone()[0]
    
    print(f"\n替换前数据:")
    print(f"  客户: {old_customer_count}")
    print(f"  联系人: {old_contact_count}")
    print(f"  邮箱: {old_email_count}")
    
    # 2. 清空相关表（保留 email_logs 作为历史记录）
    print("\n1. 清空现有客户数据...")
    cursor.execute("DELETE FROM send_schedule")
    cursor.execute("DELETE FROM subject_usage_log")
    cursor.execute("DELETE FROM customer_subjects")
    cursor.execute("DELETE FROM emails")
    cursor.execute("DELETE FROM contacts")
    cursor.execute("DELETE FROM customers")
    conn.commit()
    print("   ✓ 已清空")
    
    # 3. 重新导入数据
    print("\n2. 导入新数据...")
    conn.close()
    
    success, error = import_excel_to_db(excel_path)
    
    if success:
        # 显示导入后的统计
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM customers")
        new_customer_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM contacts")
        new_contact_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM emails")
        new_email_count = cursor.fetchone()[0]
        conn.close()
        
        print(f"\n替换完成!")
        print(f"替换后数据:")
        print(f"  客户: {new_customer_count} (+{new_customer_count - old_customer_count})")
        print(f"  联系人: {new_contact_count} (+{new_contact_count - old_contact_count})")
        print(f"  邮箱: {new_email_count} (+{new_email_count - old_email_count})")
        print(f"\n建议下一步: 生成主题池")
        print(f"  python main.py subjects --generate")
    else:
        print(f"\n导入失败: {error}")
        print("数据库已清空，请检查Excel文件后重试")

def analyze_and_generate(customer_id=None, limit=1):
    """分析客户并生成邮件序列"""
    print("=" * 60)
    print("智能客户分析与邮件生成")
    print("=" * 60)
    
    generator = LegacyEmailGenerator()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    if customer_id:
        cursor.execute('''
            SELECT c.id, c.customer_name, c.country, c.website, c.company_info,
                   e.email_address, co.contact_name, e.email_type
            FROM customers c
            JOIN emails e ON c.id = e.customer_id
            LEFT JOIN contacts co ON e.contact_id = co.id
            WHERE c.id = ? AND e.is_active = 1
            LIMIT 1
        ''', (customer_id,))
    else:
        cursor.execute('''
            SELECT c.id, c.customer_name, c.country, c.website, c.company_info,
                   e.email_address, co.contact_name, e.email_type
            FROM customers c
            JOIN emails e ON c.id = e.customer_id
            LEFT JOIN contacts co ON e.contact_id = co.id
            WHERE e.is_active = 1
            AND e.id NOT IN (
                SELECT email_id FROM email_logs 
                WHERE send_status = 'sent' 
                AND sent_at >= date('now', '-30 days')
            )
            ORDER BY RANDOM()
            LIMIT ?
        ''', (limit,))
    
    customers = cursor.fetchall()
    conn.close()
    
    if not customers:
        print("没有找到待处理的客户")
        return
    
    for row in customers:
        customer_id, customer_name, country, website, company_info, \
        email_address, contact_name, email_type = row
        
        print(f"\n{'='*60}")
        print(f"处理客户: {customer_name}")
        print(f"{'='*60}")
        
        # 1. 网站分析
        print(f"\n1. 分析网站: {website}")
        website_data = generator.analyzer.analyze_website(website)
        
        if website_data.get('error'):
            print(f"   网站分析出错: {website_data['error']}")
        else:
            print(f"   网站标题: {website_data.get('title', 'N/A')}")
            print(f"   检测行业: {website_data.get('industry', 'N/A')}")
            print(f"   业务模式: {website_data.get('business_model', 'N/A')}")
        
        # 2. 判断客户类型
        customer_data = {
            'customer_name': customer_name,
            'contact_name': contact_name or 'Team',
            'country': country,
            'website_data': website_data,
            'company_info': company_info
        }
        
        customer_type = generator.analyze_customer_type(customer_data)
        print(f"\n2. 客户类型判断: {'大功率客户' if customer_type == 'large_power' else '小功率客户'}")
        
        # 3. 生成邮件序列
        print(f"\n3. 生成5封邮件序列...")
        email_sequence = generator.generate_email_sequence(customer_data)
        
        # 4. 显示生成的邮件
        for i, email in enumerate(email_sequence['emails'], 1):
            print(f"\n{'='*40}")
            print(f"邮件 {i}: {email['type']}")
            print(f"{'='*40}")
            print(f"主题: {email['subject']}")
            print(f"\n内容:\n{email['body']}")
            
            # 保存到文件
            save_email_to_file(customer_name, i, email)

def save_email_to_file(customer_name, email_index, email_content):
    """保存邮件到文件"""
    output_dir = os.path.join(os.path.dirname(__file__), 'generated_emails')
    os.makedirs(output_dir, exist_ok=True)
    
    safe_name = "".join([c for c in customer_name if c.isalnum() or c in (' ', '-', '_')]).rstrip()
    filename = f"{safe_name}_email_{email_index}_{email_content['type']}.txt"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Subject: {email_content['subject']}\n")
        f.write(f"Type: {email_content['type']}\n")
        f.write("="*50 + "\n\n")
        f.write(email_content['body'])
    
    print(f"\n[已保存到: {filepath}]")

def generate_subjects(customer_id=None, limit=None):
    """为客户生成主题池"""
    print("=" * 60)
    print("生成客户邮件主题池")
    print("=" * 60)
    
    sender = EmailSender()
    conn = get_connection()
    cursor = conn.cursor()
    
    if customer_id:
        cursor.execute('SELECT id, customer_name FROM customers WHERE id = ?', (customer_id,))
    else:
        # 获取没有主题或主题不足的客户
        cursor.execute('''
            SELECT c.id, c.customer_name 
            FROM customers c
            LEFT JOIN (
                SELECT customer_id, COUNT(*) as cnt 
                FROM customer_subjects 
                GROUP BY customer_id
            ) cs ON c.id = cs.customer_id
            WHERE cs.cnt IS NULL OR cs.cnt < 5
            ORDER BY c.id
        ''')
    
    customers = cursor.fetchall()
    conn.close()
    
    if not customers:
        print("所有客户已有完整的主题池")
        return
    
    if limit:
        customers = customers[:limit]
    
    print(f"将为 {len(customers)} 个客户生成主题\n")
    
    for cid, cname in customers:
        print(f"处理: {cname} (ID: {cid})")
        success = sender.ensure_customer_subjects(cid)
        if success:
            # 显示生成的主题
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT subject_index, subject_line, subject_type
                FROM customer_subjects 
                WHERE customer_id = ? ORDER BY subject_index
            ''', (cid,))
            subjects = cursor.fetchall()
            conn.close()
            
            for idx, subject, stype in subjects:
                print(f"  {idx}. [{stype}] {subject}")
        print()

def send_emails(limit=None, dry_run=False, use_scheduler=False):
    """发送邮件"""
    print("=" * 50)
    print("开始发送邮件")
    print("=" * 50)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if use_scheduler:
        print(f"\n[调度模式] 每2分钟发送一封邮件")
    
    if dry_run:
        print("\n[模拟模式] 不会实际发送邮件")
        conn = get_connection()
        cursor = conn.cursor()
        
        if use_scheduler:
            print("\n[调度模式预览]")
            cursor.execute('''
                SELECT COUNT(*) FROM customers c
                JOIN emails e ON c.id = e.customer_id
                WHERE e.is_active = 1
                AND e.id NOT IN (
                    SELECT email_id FROM email_logs 
                    WHERE send_status = 'sent' 
                    AND sent_at >= date('now', '-7 days')
                )
            ''')
            total = cursor.fetchone()[0]
            print(f"待调度邮件总数: {total}")
            if limit:
                print(f"本次限制: {limit} 封")
            print(f"发送间隔: 每2分钟一封")
            if limit:
                print(f"预计完成时间: 约 {(limit * 2) // 60} 小时 {(limit * 2) % 60} 分钟")
            else:
                print(f"预计完成时间: 约 {(total * 2) // 60} 小时 {(total * 2) % 60} 分钟")
        else:
            cursor.execute('''
                SELECT c.customer_name, e.email_address, e.email_type, co.contact_name
                FROM customers c
                JOIN emails e ON c.id = e.customer_id
                LEFT JOIN contacts co ON e.contact_id = co.id
                WHERE e.is_active = 1
                LIMIT 10
            ''')
            rows = cursor.fetchall()
            print(f"\n待发送邮件列表 (前10条):")
            for row in rows:
                print(f"  - {row[0]}: {row[1]} ({row[3] or 'N/A'})")
        conn.close()
        return
    
    sender = EmailSender()
    results = sender.process_daily_emails(limit, use_scheduler=use_scheduler)
    
    if use_scheduler and isinstance(results, dict):
        # 调度模式：已自动启动后台调度器
        print(f"\n调度完成:")
        print(f"  已调度: {results['scheduled']} 封邮件")
        print(f"  批次ID: {results['batch_id']}")
        if results.get('scheduler_running'):
            print(f"  状态: 后台调度器已自动启动")
    else:
        stats = sender.get_statistics()
        print(f"\n发送统计:")
        print(f"  本次发送: {len(results)} 封")
        print(f"  今日总计: {stats['today_sent']} 封")
        print(f"  累计发送: {stats['total_sent']} 封")
        print(f"  失败数量: {stats['total_failed']} 封")

def manage_scheduler(action='status'):
    """管理邮件调度器"""
    print("=" * 50)
    print("邮件调度器管理")
    print("=" * 50)
    
    sender = EmailSender()
    
    if action == 'start':
        print("启动调度器...")
        scheduler = sender.start_scheduler()
        print("✓ 调度器已启动")
        print(f"  发送间隔: 每2分钟一封")
        print(f"\n调度器在后台运行中...")
        print("使用 Ctrl+C 停止或运行 'python main.py schedule --stop'")
        
        # 保持主线程运行
        try:
            while True:
                import time
                time.sleep(10)
                status = sender.get_scheduler_status()
                if status['pending'] == 0:
                    print("\n所有邮件已发送完毕")
                    break
        except KeyboardInterrupt:
            print("\n\n正在停止调度器...")
        finally:
            sender.stop_scheduler()
            print("✓ 调度器已停止")
    
    elif action == 'stop':
        sender.stop_scheduler()
        print("✓ 调度器已停止")
    
    elif action == 'status':
        status = sender.get_scheduler_status()
        print(f"\n队列状态:")
        print(f"  待发送: {status['pending']}")
        print(f"  已发送: {status['sent']}")
        print(f"  失败: {status['failed']}")
        print(f"  逾期: {status['overdue']}")
        if status['next_scheduled']:
            print(f"  下一封: {status['next_scheduled']}")

def show_stats():
    """显示统计信息"""
    print("=" * 50)
    print("系统统计信息")
    print("=" * 50)
    show_statistics()
    
    sender = EmailSender()
    stats = sender.get_statistics()
    
    print(f"\n邮件发送统计:")
    print(f"  今日发送: {stats['today_sent']} 封")
    print(f"  累计发送: {stats['total_sent']} 封")
    print(f"  失败数量: {stats['total_failed']} 封")
    
    if stats['type_stats']:
        print(f"\n按类型统计:")
        for email_type, count in stats['type_stats']:
            print(f"  {email_type}: {count} 封")

def main():
    parser = argparse.ArgumentParser(description='智能邮件自动化系统')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 初始化命令
    init_parser = subparsers.add_parser('init', help='初始化系统')
    
    # 导入命令
    import_parser = subparsers.add_parser('import', help='导入Excel数据')
    import_parser.add_argument('excel_path', help='Excel文件路径')
    
    # 替换命令（用新数据替换旧数据）
    replace_parser = subparsers.add_parser('replace', help='用新Excel数据替换现有客户数据')
    replace_parser.add_argument('excel_path', help='Excel文件路径')
    replace_parser.add_argument('--confirm', action='store_true', help='确认替换（会清空现有数据）')
    
    # 分析生成命令
    analyze_parser = subparsers.add_parser('analyze', help='分析客户并生成邮件')
    analyze_parser.add_argument('--customer-id', type=int, help='指定客户ID')
    analyze_parser.add_argument('--limit', type=int, default=1, help='处理客户数量')
    
    # 发送命令
    send_parser = subparsers.add_parser('send', help='发送邮件')
    send_parser.add_argument('--limit', type=int, help='限制发送数量')
    send_parser.add_argument('--dry-run', action='store_true', help='模拟运行')
    send_parser.add_argument('--scheduler', action='store_true', help='使用调度器模式（每2分钟一封）')
    
    # 主题生成命令
    subjects_parser = subparsers.add_parser('subjects', help='生成客户邮件主题池')
    subjects_parser.add_argument('--customer-id', type=int, help='指定客户ID')
    subjects_parser.add_argument('--limit', type=int, help='限制生成数量')
    subjects_parser.add_argument('--generate', action='store_true', help='为所有客户生成主题')
    
    # 调度器命令
    schedule_parser = subparsers.add_parser('schedule', help='管理邮件发送调度器')
    schedule_parser.add_argument('--start', action='store_true', help='启动调度器')
    schedule_parser.add_argument('--stop', action='store_true', help='停止调度器')
    schedule_parser.add_argument('--status', action='store_true', help='查看队列状态')
    
    # 统计命令
    stats_parser = subparsers.add_parser('stats', help='显示统计信息')
    
    args = parser.parse_args()
    
    if args.command == 'init':
        init_system()
    elif args.command == 'import':
        import_data(args.excel_path)
    elif args.command == 'replace':
        replace_data(args.excel_path, args.confirm)
    elif args.command == 'analyze':
        analyze_and_generate(args.customer_id, args.limit)
    elif args.command == 'send':
        send_emails(args.limit, args.dry_run, args.scheduler)
    elif args.command == 'subjects':
        if args.generate or args.customer_id:
            generate_subjects(args.customer_id, args.limit)
        else:
            subjects_parser.print_help()
    elif args.command == 'schedule':
        if args.start:
            manage_scheduler('start')
        elif args.stop:
            manage_scheduler('stop')
        else:
            manage_scheduler('status')
    elif args.command == 'stats':
        show_stats()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
