#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Niteo Solar 智能邮件自动化系统 - Web 管理界面
Flask 后端 API 服务器
"""

import os
import sys
import json
import sqlite3
import threading
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory, session, redirect, g
from flask_wtf.csrf import CSRFProtect

# 确保能导入项目根目录模块
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

# ==================== Global Async Task Storage ====================

# 全局任务存储（内存中，用于追踪异步发送进度）
send_tasks = {}
send_tasks_lock = threading.Lock()

# 导入任务存储（内存中，用于追踪批量导入进度）
import_tasks = {}
import_tasks_lock = threading.Lock()

# AI分析API速率限制（按IP）
ai_rate_limits = {}
ai_rate_limits_lock = threading.Lock()
MAX_AI_REQUESTS_PER_MINUTE = 5

# 导入步骤定义
IMPORT_STEPS = [
    {'id': 'parse', 'name': '文件解析', 'weight': 10},
    {'id': 'column_detect', 'name': '列名识别', 'weight': 10},
    {'id': 'extract', 'name': '数据提取', 'weight': 20},
    {'id': 'ai_classify', 'name': 'AI智能分类', 'weight': 35},
    {'id': 'clean', 'name': '数据清洗', 'weight': 10},
    {'id': 'import_db', 'name': '导入数据库', 'weight': 15},
]

# 发送队列管理器（通过实例模块避免循环导入）
from send_queue.manager import queue_manager

# ==================== 依赖注入组装层 ====================
# 解除 core/scheduler.py -> core/orchestrator.py -> core/sender.py 循环依赖
from core.sender import EmailSender
from send_queue.manager import SendQueueManager
from core.orchestrator import SendOrchestrator
from generators.workflow import EmailWorkflow
from generators.subjects.manager import SmartSubjectManager
from core.scheduler import EmailScheduler


def _extract_name_from_email(email_address: str) -> str:
    """从邮箱地址中推导联系人姓名。如 jack.ready@halterhq.com → Jack Ready"""
    if not email_address:
        return ''
    local_part = email_address.split('@')[0]
    # 跳过明显非人名的邮箱（纯缩写如 br.store, wh@ui, 单字母如 a, x）
    if len(local_part) <= 2:
        return ''
    parts = local_part.replace('.', ' ').replace('_', ' ').replace('-', ' ').split()
    # 过滤掉明显不是姓名的部分
    skip = {'info', 'sales', 'support', 'admin', 'contact', 'hello', 'team',
            'store', 'mail', 'webmaster', 'noreply', 'post', 'office'}
    names = [p.title() for p in parts if p.lower() not in skip and len(p) > 1]
    if len(names) >= 2:
        return ' '.join(names)
    elif len(names) == 1:
        # 单个名字也可能是真名（如 m.nguyen → M. Nguyen 不太对，但 cathryn 可以）
        if len(names[0]) > 3:
            return names[0]
    return ''


def _make_greeting(email_type: str, contact_name: str, email_address: str, customer_name: str) -> str:
    """生成邮件称呼。个人邮箱有名字用名字，没名字用公司名+Team；公共邮箱直接用公司名+Team。"""
    if email_type == 'personal':
        # 个人邮箱：仅用已有联系人姓名
        name = (contact_name or '').strip()
        if name and name.lower() not in ('', 'n/a', 'unknown', 'none'):
            first_name = name.split()[0] if ' ' in name else name
            return f"Hi {first_name}"
        # 个人邮箱但无联系人姓名 → 回退到公司名+Team
    # 公共邮箱或无名字的个人邮箱 → 用公司名+Team
    clean = customer_name.replace('INC.', '').replace('LLC', '').replace('Ltd.', '').replace('team', '').replace('Team', '').strip()
    # 去掉多余空格
    clean = ' '.join(clean.split())
    return f"Hi {clean} Team"

_sender = EmailSender()
queue_manager = SendQueueManager(sender=_sender)
orchestrator = SendOrchestrator(
    sender=_sender,
    queue_manager=queue_manager,
    workflow=EmailWorkflow(user_id=None),
    subject_manager_instance=SmartSubjectManager()
)
scheduler_instance = EmailScheduler(task_trigger_callback=orchestrator.create_send_task)
# =======================================================

# 发送步骤定义
SEND_STEPS = [
    {'id': 'research', 'name': '公司背调', 'weight': 25},
    {'id': 'pain_points', 'name': '痛点分析', 'weight': 15},
    {'id': 'material', 'name': '素材匹配', 'weight': 20},
    {'id': 'compose', 'name': '邮件生成', 'weight': 20},
    {'id': 'refine', 'name': '邮件润色', 'weight': 10},
    {'id': 'send', 'name': 'SMTP发送', 'weight': 10},
]

# ==================== Security Decorators ====================

def require_ajax(f):
    """验证请求包含 X-Requested-With: XMLHttpRequest 请求头，作为 CSRF 替代防护"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Invalid request origin'}), 403
        return f(*args, **kwargs)
    return decorated

from database.connection import get_connection
from database.operations import get_statistics, persist_send_task_meta, get_active_send_tasks, get_send_task_items
from utils.validators import (
    validate_customer_data, validate_email, validate_file_upload,
    validate_batch_delete_ids, sanitize_text, check_duplicate_customer_name,
    check_duplicate_email
)
from utils.file_parser import parse_file
from database.search_models import (
    get_search_tasks, get_search_task, create_search_task, update_search_task,
    delete_search_task, get_search_results, get_search_result,
    update_result_import_status, bulk_update_result_status,
    get_platform_configs, get_platform_config, update_platform_config,
    import_result_to_customer,
    add_blacklist, remove_blacklist, is_blacklisted, get_blacklist
)
from services.search.engine import get_search_engine
from services.search.registry import SearcherRegistry
from database.api_config_models import (
    get_all_api_configs, get_api_config, get_api_key,
    create_api_config, update_api_config, delete_api_config,
    init_default_configs
)
from database.bounce_service import get_bounce_stats, get_bounce_list
from database.user_settings_models import get_user_setting, save_user_setting, get_all_user_settings
from web.auth import auth_bp, init_oauth, login_required, admin_required

app = Flask(__name__, static_folder='dashboard', static_url_path='')

# SECRET_KEY: 优先从环境变量读取，其次从文件读取/生成，确保多 worker 重启后一致
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    _secret_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.flask_secret')
    if os.path.exists(_secret_file):
        with open(_secret_file, 'r') as f:
            _secret_key = f.read().strip()
    else:
        _secret_key = os.urandom(32).hex()
        with open(_secret_file, 'w') as f:
            f.write(_secret_key)
app.config['SECRET_KEY'] = _secret_key
app.config['WTF_CSRF_ENABLED'] = False  # 禁用全局CSRF，API通过 X-Requested-With 请求头验证保护
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# 注册认证 Blueprint
app.register_blueprint(auth_bp)
init_oauth(app)

# ==================== 全局认证拦截 ====================
PUBLIC_PATHS = {
    '/login.html', '/login/google', '/auth/google/callback', '/logout', '/api/me',
    '/api/admin/users', '/api/admin/stats',
    '/api/admin/send-queue/status', '/api/admin/search-tasks/summary', '/api/admin/system/health',
    '/api/invite/validate', '/login/invite'
}

@app.before_request
def require_auth():
    """未登录用户强制跳转到登录页"""
    path = request.path
    # 静态资源放行
    if path.startswith('/static/') or path.startswith('/assets/') or '.' in path.split('/')[-1]:
        return None
    if path in PUBLIC_PATHS or path.startswith('/auth/'):
        return None
    if 'user_id' not in session:
        if request.is_json or path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized', 'login_url': '/login.html'}), 401
        return redirect('/login.html')

def get_current_user_id() -> int:
    """获取当前登录用户的ID，未登录返回0"""
    return session.get('user_id', 0)

def is_admin() -> bool:
    """检查当前用户是否为管理员"""
    return session.get('role', '') == 'admin' or session.get('user_role', '') == 'admin'

# ==================== Security Headers ====================

@app.after_request
def add_security_headers(response):
    """为所有响应添加安全响应头"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.bootcdn.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "img-src 'self' data:;"
    )
    return response

# ==================== API Routes ====================

@app.route('/')
def index():
    resp = send_from_directory(os.path.join(_project_root, 'dashboard'), 'index.html')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/login.html')
def login_page():
    resp = send_from_directory(os.path.join(_project_root, 'dashboard'), 'login.html')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@app.route('/api/stats')
def api_stats():
    """获取系统统计数据"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        stats = get_statistics(user_id=current_user_id, admin=admin)
        conn = get_connection()
        cursor = conn.cursor()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " AND user_id = ?"
            user_params = [current_user_id]

        # 今日发送
        cursor.execute(f"SELECT COUNT(*) FROM email_logs WHERE send_status = 'sent' AND date(sent_at) = date('now'){user_where}", user_params)
        today_sent = cursor.fetchone()[0]

        # 主题池统计
        cursor.execute(f"SELECT COUNT(DISTINCT customer_id) FROM customer_subjects WHERE 1=1{user_where}", user_params)
        customers_with_subjects = cursor.fetchone()[0]

        # 调度队列状态
        cursor.execute(f"SELECT COUNT(*) FROM send_schedule WHERE status = 'pending'{user_where}", user_params)
        pending_schedule = cursor.fetchone()[0]

        # 邮箱类型分布
        cursor.execute(f"SELECT email_type, COUNT(*) FROM emails WHERE 1=1{user_where} GROUP BY email_type", user_params)
        email_types = dict(cursor.fetchall())

        conn.close()

        return jsonify({
            'success': True,
            'data': {
                'customer_count': stats['customer_count'],
                'contact_count': stats['contact_count'],
                'email_count': stats['email_count'],
                'sent_count': stats['sent_count'],
                'failed_count': stats['failed_count'],
                'today_sent': today_sent,
                'customers_with_subjects': customers_with_subjects,
                'pending_schedule': pending_schedule,
                'email_types': email_types
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customers')
def api_customers():
    """获取客户列表（支持按国家筛选）"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '')
        country = request.args.get('country', '')
        offset = (page - 1) * per_page

        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        # 构建 WHERE 条件
        where_clauses = []
        params = []
        if not admin and current_user_id:
            where_clauses.append('(c.user_id = ? OR c.user_id IS NULL)')
            params.append(current_user_id)
        if search:
            where_clauses.append('c.customer_name LIKE ?')
            params.append(f'%{search}%')
        if country:
            where_clauses.append('c.country = ?')
            params.append(country)

        where_sql = 'WHERE ' + ' AND '.join(where_clauses) if where_clauses else ''

        cursor.execute(f'''
            SELECT c.id, c.customer_name, c.country, c.website, c.company_info, c.industry_type,
                   COUNT(DISTINCT e.id) as email_count,
                   COUNT(DISTINCT co.id) as contact_count,
                   COUNT(DISTINCT CASE WHEN el.send_status = 'sent' THEN el.id END) as sent_count
            FROM customers c
            LEFT JOIN emails e ON c.id = e.customer_id AND e.is_active = 1
            LEFT JOIN contacts co ON c.id = co.customer_id
            LEFT JOIN email_logs el ON c.id = el.customer_id AND el.send_status = 'sent'
            {where_sql}
            GROUP BY c.id
            ORDER BY c.id
            LIMIT ? OFFSET ?
        ''', params + [per_page, offset])

        rows = cursor.fetchall()

        # 计算冷却期信息（默认7天）
        cooldown_days = 7
        cooldown_info = {}
        if rows:
            # 批量查询所有客户的最近发送时间（排除已手动解除冷却的公司）
            customer_ids = [r[0] for r in rows]
            placeholders = ','.join(['?'] * len(customer_ids))
            cursor.execute(f'''
                SELECT el.customer_id, MAX(el.sent_at) as last_sent_at
                FROM email_logs el
                WHERE el.customer_id IN ({placeholders}) AND el.send_status = 'sent'
                  AND (el.user_id IS NULL OR el.user_id = ?)
                  AND NOT EXISTS (
                      SELECT 1 FROM cooldown_override co
                      WHERE co.customer_id = el.customer_id
                        AND (co.user_id IS NULL OR co.user_id = ?)
                  )
                GROUP BY el.customer_id
            ''', customer_ids + [current_user_id, current_user_id])
            last_sent = {}
            for r in cursor.fetchall():
                last_sent[r[0]] = r[1]

            now = datetime.now()
            for cid in customer_ids:
                if cid in last_sent and last_sent[cid]:
                    try:
                        last_dt = datetime.fromisoformat(last_sent[cid].replace('Z', '+00:00').replace('+00:00', ''))
                    except:
                        last_dt = datetime.strptime(last_sent[cid][:19], '%Y-%m-%dT%H:%M:%S')
                    remaining = cooldown_days - (now - last_dt).days
                    if remaining > 0:
                        cooldown_info[cid] = {
                            'in_cooldown': True,
                            'remaining_days': remaining,
                            'last_sent': last_sent[cid]
                        }
                    else:
                        cooldown_info[cid] = {'in_cooldown': False, 'remaining_days': 0}

        # 总数（带筛选条件）
        if where_clauses:
            cursor.execute(f'SELECT COUNT(*) FROM customers c {where_sql}', params)
        else:
            cursor.execute('SELECT COUNT(*) FROM customers')
        total = cursor.fetchone()[0]

        conn.close()

        customers = [{
            'id': r[0],
            'name': r[1],
            'country': r[2],
            'website': r[3],
            'company_info': r[4],
            'industry_type': r[5],
            'email_count': r[6],
            'contact_count': r[7],
            'sent_count': r[8],
            'cooldown': cooldown_info.get(r[0], {'in_cooldown': False, 'remaining_days': 0})
        } for r in rows]

        return jsonify({
            'success': True,
            'data': {
                'customers': customers,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': (total + per_page - 1) // per_page
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers/countries')
def api_customer_countries():
    """获取所有国家列表及客户数量"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " AND user_id = ?"
            user_params = [current_user_id]

        cursor.execute(f'''
            SELECT country, COUNT(*) as count
            FROM customers
            WHERE country IS NOT NULL AND country != ''{user_where}
            GROUP BY country
            ORDER BY count DESC, country
        ''', user_params)
        rows = cursor.fetchall()
        conn.close()
        return jsonify({
            'success': True,
            'countries': [{'name': r[0], 'count': r[1]} for r in rows]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers/<int:customer_id>')
def api_customer_detail(customer_id):
    """获取客户详情"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        # 客户基本信息
        if not admin and current_user_id:
            cursor.execute('SELECT id, customer_name, country, address, website, company_info, industry_type, website_title, website_description FROM customers WHERE id = ? AND user_id = ?', (customer_id, current_user_id))
        else:
            cursor.execute('SELECT id, customer_name, country, address, website, company_info, industry_type, website_title, website_description FROM customers WHERE id = ?', (customer_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': '客户不存在'}), 404
        
        customer = {
            'id': row[0], 'name': row[1], 'country': row[2], 'address': row[3],
            'website': row[4], 'company_info': row[5], 'industry_type': row[6],
            'website_title': row[7], 'website_description': row[8]
        }
        
        # 联系人和邮箱
        if not admin and current_user_id:
            cursor.execute('''
                SELECT e.id, e.email_address, e.email_type, e.is_active, 
                       COALESCE(e.contact_name, co.contact_name) as contact_name,
                       COALESCE(e.job_title, co.job_title) as job_title
                FROM emails e
                LEFT JOIN contacts co ON e.contact_id = co.id
                WHERE e.customer_id = ? AND e.user_id = ?
                ORDER BY e.email_type, e.id
            ''', (customer_id, current_user_id))
        else:
            cursor.execute('''
                SELECT e.id, e.email_address, e.email_type, e.is_active, 
                       COALESCE(e.contact_name, co.contact_name) as contact_name,
                       COALESCE(e.job_title, co.job_title) as job_title
                FROM emails e
                LEFT JOIN contacts co ON e.contact_id = co.id
                WHERE e.customer_id = ?
                ORDER BY e.email_type, e.id
            ''', (customer_id,))
        
        emails = [{
            'id': r[0], 'address': r[1], 'type': r[2], 'active': r[3],
            'contact_name': r[4], 'job_title': r[5]
        } for r in cursor.fetchall()]
        
        # 发送历史
        if not admin and current_user_id:
            cursor.execute('''
                SELECT el.email_subject, el.send_status, el.sent_at, e.email_address
                FROM email_logs el
                JOIN emails e ON el.email_id = e.id
                WHERE el.customer_id = ? AND el.user_id = ?
                ORDER BY el.sent_at DESC
                LIMIT 20
            ''', (customer_id, current_user_id))
        else:
            cursor.execute('''
                SELECT el.email_subject, el.send_status, el.sent_at, e.email_address
                FROM email_logs el
                JOIN emails e ON el.email_id = e.id
                WHERE el.customer_id = ?
                ORDER BY el.sent_at DESC
                LIMIT 20
            ''', (customer_id,))
        
        logs = [{
            'subject': r[0], 'status': r[1], 'sent_at': r[2], 'email': r[3]
        } for r in cursor.fetchall()]
        
        # 主题池
        if not admin and current_user_id:
            cursor.execute('''
                SELECT subject_index, subject_line, subject_type
                FROM customer_subjects
                WHERE customer_id = ? AND user_id = ?
                ORDER BY subject_index
            ''', (customer_id, current_user_id))
        else:
            cursor.execute('''
                SELECT subject_index, subject_line, subject_type
                FROM customer_subjects
                WHERE customer_id = ?
                ORDER BY subject_index
            ''', (customer_id,))
        
        subjects = [{
            'index': r[0], 'line': r[1], 'type': r[2]
        } for r in cursor.fetchall()]

        # 冷却期信息（排除已手动解除冷却的公司）
        cooldown = {'in_cooldown': False, 'remaining_days': 0}
        cooldown_days = 7
        uid_param = current_user_id if (not admin and current_user_id) else None

        # 检查是否有手动解除冷却的记录
        cursor.execute('SELECT 1 FROM cooldown_override WHERE customer_id = ? AND (user_id IS NULL OR user_id = ?)',
                       (customer_id, uid_param or 0))
        if not cursor.fetchone():
            if uid_param:
                cursor.execute('''
                    SELECT MAX(sent_at) FROM email_logs
                    WHERE customer_id = ? AND send_status = 'sent' AND user_id = ?
                ''', (customer_id, uid_param))
            else:
                cursor.execute('''
                    SELECT MAX(sent_at) FROM email_logs
                    WHERE customer_id = ? AND send_status = 'sent'
                ''', (customer_id,))
        last_sent_row = cursor.fetchone()
        if last_sent_row and last_sent_row[0]:
            try:
                last_dt = datetime.fromisoformat(last_sent_row[0].replace('Z', '+00:00').replace('+00:00', ''))
            except:
                last_dt = datetime.strptime(last_sent_row[0][:19], '%Y-%m-%dT%H:%M:%S')
            remaining = cooldown_days - (datetime.now() - last_dt).days
            if remaining > 0:
                cooldown = {'in_cooldown': True, 'remaining_days': remaining, 'last_sent': last_sent_row[0]}

        conn.close()

        return jsonify({
            'success': True,
            'data': {
                'customer_name': customer['name'],
                'cooldown': cooldown,
                'customer': customer,
                'emails': emails,
                'logs': logs,
                'subjects': subjects
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customers/<int:customer_id>/update', methods=['POST'])
@require_ajax
def api_customer_update(customer_id):
    """更新客户信息"""
    try:
        data = request.json or {}

        # 验证数据
        current_user_id = get_current_user_id()
        is_valid, errors = validate_customer_data(data, is_update=True, customer_id=customer_id, user_id=current_user_id)
        if not is_valid:
            return jsonify({'success': False, 'error': '数据验证失败', 'details': errors}), 400

        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        # 检查客户是否存在
        if not admin and current_user_id:
            cursor.execute("SELECT id FROM customers WHERE id = ? AND user_id = ?", (customer_id, current_user_id))
        else:
            cursor.execute("SELECT id FROM customers WHERE id = ?", (customer_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': '客户不存在'}), 404

        updates = []
        params = []
        for field in ['customer_name', 'country', 'address', 'website', 'company_info',
                      'supplier', 'supplier_info', 'customs_data', 'logistics_info', 'industry_type']:
            if field in data:
                updates.append(f"{field} = ?")
                params.append(sanitize_text(data[field]))

        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(customer_id)
            if not admin and current_user_id:
                cursor.execute(f"UPDATE customers SET {', '.join(updates)} WHERE id = ? AND user_id = ?", params + [current_user_id])
            else:
                cursor.execute(f"UPDATE customers SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        conn.close()
        return jsonify({'success': True, 'data': {'updated': True}, 'message': '客户信息已更新'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers', methods=['POST'])
@require_ajax
def api_customer_create():
    """添加单个客户"""
    try:
        data = request.json or {}

        # 验证数据
        current_user_id = get_current_user_id()
        is_valid, errors = validate_customer_data(data, is_update=False, user_id=current_user_id)
        if not is_valid:
            return jsonify({'success': False, 'error': '数据验证失败', 'details': errors}), 400

        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()

        # 去重检查：同名+同国家+同用户下不允许重复创建
        customer_name = sanitize_text(data.get('customer_name', '')).strip()
        country = sanitize_text(data.get('country', '')).strip()
        if customer_name:
            cursor.execute(
                "SELECT id FROM customers WHERE customer_name = ? AND (country = ? OR (country IS NULL AND ? IS NULL)) AND user_id = ?",
                (customer_name, country, country, current_user_id)
            )
            existing = cursor.fetchone()
            if existing:
                conn.close()
                return jsonify({'success': False, 'error': '已存在同名客户，无法重复添加', 'existing_id': existing[0]}), 409

        # 插入客户
        cursor.execute("""
            INSERT INTO customers (customer_name, country, address, website, company_info,
                supplier, supplier_info, customs_data, logistics_info, industry_type, user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            sanitize_text(data.get('customer_name')),
            sanitize_text(data.get('country')),
            sanitize_text(data.get('address')),
            sanitize_text(data.get('website')),
            sanitize_text(data.get('company_info')),
            sanitize_text(data.get('supplier')),
            sanitize_text(data.get('supplier_info')),
            sanitize_text(data.get('customs_data')),
            sanitize_text(data.get('logistics_info')),
            sanitize_text(data.get('industry_type')),
            current_user_id
        ))

        customer_id = cursor.lastrowid

        # 插入邮箱
        emails = data.get('emails', [])
        for email_data in emails:
            email_addr = sanitize_text(email_data.get('email_address'))
            if not email_addr:
                continue

            email_type = email_data.get('email_type', 'public')
            contact_name = sanitize_text(email_data.get('contact_name'))
            job_title = sanitize_text(email_data.get('job_title'))

            # 插入联系人
            contact_id = None
            if contact_name:
                cursor.execute("""
                    INSERT INTO contacts (customer_id, contact_name, job_title, source, user_id, created_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                """, (customer_id, contact_name, job_title, email_data.get('source', 'manual'), current_user_id))
                contact_id = cursor.lastrowid

            # 插入邮箱（同时保存contact_name和job_title到emails表）
            cursor.execute("""
                INSERT INTO emails (customer_id, contact_id, email_address, email_type,
                                    contact_name, job_title, is_active, user_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, datetime('now'))
            """, (customer_id, contact_id, email_addr, email_type, contact_name, job_title, current_user_id))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': '客户添加成功',
            'data': {'customer_id': customer_id}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers/<int:customer_id>', methods=['DELETE'])
@require_ajax
def api_customer_delete(customer_id):
    """删除单个客户"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        # 查询客户信息
        if not admin and current_user_id:
            cursor.execute("SELECT id, customer_name FROM customers WHERE id = ? AND user_id = ?", (customer_id, current_user_id))
        else:
            cursor.execute("SELECT id, customer_name FROM customers WHERE id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': '客户不存在'}), 404

        customer_name = row[1]

        # 删除客户（外键CASCADE会自动清理关联数据）
        if not admin and current_user_id:
            cursor.execute("DELETE FROM customers WHERE id = ? AND user_id = ?", (customer_id, current_user_id))
        else:
            cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'客户 "{customer_name}" 已删除',
            'data': {'deleted_id': customer_id, 'deleted_name': customer_name}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers/batch-delete', methods=['POST'])
@require_ajax
def api_customers_batch_delete():
    """批量删除客户"""
    try:
        data = request.json or {}
        ids = data.get('ids', [])

        # 验证ID列表
        is_valid, error = validate_batch_delete_ids(ids)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400

        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        # 查询要删除的客户名称
        # 注意: f-string 仅用于生成占位符 ?,?,?，实际参数通过 execute() 传递，安全
        placeholders = ','.join('?' * len(ids))
        if not admin and current_user_id:
            cursor.execute(f"SELECT id, customer_name FROM customers WHERE id IN ({placeholders}) AND user_id = ?", ids + [current_user_id])
        else:
            cursor.execute(f"SELECT id, customer_name FROM customers WHERE id IN ({placeholders})", ids)
        customers_to_delete = cursor.fetchall()

        if not customers_to_delete:
            conn.close()
            return jsonify({'success': False, 'error': '未找到要删除的客户'}), 404

        # 执行删除
        # 注意: f-string 仅用于生成占位符 ?,?,?，实际参数通过 execute() 传递，安全
        if not admin and current_user_id:
            cursor.execute(f"DELETE FROM customers WHERE id IN ({placeholders}) AND user_id = ?", ids + [current_user_id])
        else:
            cursor.execute(f"DELETE FROM customers WHERE id IN ({placeholders})", ids)
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'已成功删除 {deleted_count} 个客户',
            'data': {
                'deleted_count': deleted_count,
                'deleted_customers': [{'id': r[0], 'name': r[1]} for r in customers_to_delete]
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers/import', methods=['POST'])
@require_ajax
def api_customers_import():
    """批量导入客户（Excel/CSV/Word）"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '未上传文件'}), 400

        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'success': False, 'error': '未选择文件'}), 400

        # 验证文件
        is_valid, error = validate_file_upload(file)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400

        # 保存到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        try:
            # 解析文件
            customers, error = parse_file(tmp_path, file.filename)
            if error:
                return jsonify({'success': False, 'error': error}), 400

            if not customers:
                return jsonify({'success': False, 'error': '未找到有效的客户数据'}), 400

            # 导入数据库
            conn = get_connection()
            cursor = conn.cursor()

            current_user_id = get_current_user_id()

            success_count = 0
            fail_count = 0
            fail_details = []

            for customer_data in customers:
                try:
                    # 检查客户名是否为空
                    if not customer_data.get('customer_name'):
                        fail_count += 1
                        fail_details.append({'name': '(空)', 'reason': '客户名称为空'})
                        continue

                    # 检查重复
                    is_dup, dup_id = check_duplicate_customer_name(customer_data['customer_name'], user_id=current_user_id)
                    if is_dup:
                        fail_count += 1
                        fail_details.append({
                            'name': customer_data['customer_name'],
                            'reason': f'客户名称已存在 (ID: {dup_id})'
                        })
                        continue

                    # 插入客户
                    cursor.execute("""
                        INSERT INTO customers (customer_name, country, address, website, company_info,
                            supplier, supplier_info, customs_data, logistics_info, user_id, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """, (
                        customer_data.get('customer_name', ''),
                        customer_data.get('country', ''),
                        customer_data.get('address', ''),
                        customer_data.get('website', ''),
                        customer_data.get('company_info', ''),
                        customer_data.get('supplier', ''),
                        customer_data.get('supplier_info', ''),
                        customer_data.get('customs_data', ''),
                        customer_data.get('logistics_info', ''),
                        current_user_id
                    ))

                    customer_id = cursor.lastrowid

                    # 插入邮箱
                    for email_info in customer_data.get('emails', []):
                        email_addr = email_info.get('email_address', '')
                        if not email_addr:
                            continue

                        # 检查邮箱格式
                        valid, _ = validate_email(email_addr)
                        if not valid:
                            continue

                        email_type = email_info.get('email_type', 'public')
                        contact_name = email_info.get('contact_name')
                        job_title = email_info.get('job_title')
                        source = email_info.get('source', 'import')

                        # 插入联系人
                        contact_id = None
                        if contact_name:
                            cursor.execute("""
                                INSERT INTO contacts (customer_id, contact_name, job_title, source, user_id, created_at)
                                VALUES (?, ?, ?, ?, ?, datetime('now'))
                            """, (customer_id, contact_name, job_title, source, current_user_id))
                            contact_id = cursor.lastrowid

                        # 插入邮箱（同时保存contact_name和job_title）
                        cursor.execute("""
                            INSERT INTO emails (customer_id, contact_id, email_address, email_type,
                                                contact_name, job_title, is_active, user_id, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, 1, ?, datetime('now'))
                        """, (customer_id, contact_id, email_addr, email_type, contact_name, job_title, current_user_id))

                    success_count += 1

                except Exception as e:
                    fail_count += 1
                    fail_details.append({
                        'name': customer_data.get('customer_name', '(未知)'),
                        'reason': str(e)
                    })

            conn.commit()
            conn.close()

            return jsonify({
                'success': True,
                'message': f'导入完成: {success_count} 成功, {fail_count} 失败',
                'data': {
                    'total': len(customers),
                    'success_count': success_count,
                    'fail_count': fail_count,
                    'fail_details': fail_details
                }
            })

        finally:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers/check-duplicate')
def api_check_duplicate():
    """检查客户名或邮箱是否重复"""
    try:
        name = request.args.get('name', '').strip()
        email = request.args.get('email', '').strip()

        current_user_id = get_current_user_id()

        result = {'name_duplicate': False, 'email_duplicate': False}

        if name:
            is_dup, dup_id = check_duplicate_customer_name(name, user_id=current_user_id)
            result['name_duplicate'] = is_dup
            result['name_duplicate_id'] = dup_id

        if email:
            is_dup, dup_info = check_duplicate_email(email, user_id=current_user_id)
            result['email_duplicate'] = is_dup
            if dup_info:
                result['email_duplicate_info'] = dup_info

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ 拉黑管理 API ============

@app.route('/api/blacklist', methods=['GET'])
@require_ajax
def api_get_blacklist():
    """获取拉黑列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    current_user_id = get_current_user_id()
    admin = is_admin()
    data = get_blacklist(page=page, per_page=per_page, user_id=current_user_id, admin=admin)
    return jsonify({'success': True, **data})


@app.route('/api/blacklist/add', methods=['POST'])
@require_ajax
def api_add_blacklist():
    """添加拉黑"""
    data = request.json or {}
    company_name = data.get('company_name', '').strip()
    website = data.get('website', '').strip()
    reason = data.get('reason', '').strip()
    if not company_name:
        return jsonify({'success': False, 'error': '公司名称不能为空'}), 400
    current_user_id = get_current_user_id()
    if add_blacklist(company_name, website, reason, user_id=current_user_id):
        return jsonify({'success': True, 'message': '已拉黑'})
    return jsonify({'success': False, 'error': '拉黑失败'}), 500


@app.route('/api/blacklist/remove', methods=['POST'])
@require_ajax
def api_remove_blacklist():
    """取消拉黑"""
    data = request.json or {}
    company_name = data.get('company_name', '').strip()
    website = data.get('website', '').strip()
    if not company_name:
        return jsonify({'success': False, 'error': '公司名称不能为空'}), 400
    current_user_id = get_current_user_id()
    admin = is_admin()
    if remove_blacklist(company_name, website, user_id=current_user_id, admin=admin):
        return jsonify({'success': True, 'message': '已取消拉黑'})
    return jsonify({'success': False, 'error': '取消拉黑失败'}), 500


@app.route('/api/blacklist/check', methods=['GET'])
@require_ajax
def api_check_blacklist():
    """检查是否在拉黑列表"""
    name = request.args.get('company_name', '').strip()
    website = request.args.get('website', '').strip()
    current_user_id = get_current_user_id()
    admin = is_admin()
    return jsonify({'success': True, 'blacklisted': is_blacklisted(name, website, user_id=current_user_id, admin=admin)})


# ============ 退信管理 ============

@app.route('/api/bounces/stats')
@require_ajax
def api_bounce_stats():
    """获取退信统计"""
    current_user_id = get_current_user_id()
    admin = is_admin()
    stats = get_bounce_stats(user_id=current_user_id, admin=admin)
    return jsonify({'success': True, 'data': stats})


@app.route('/api/bounces/list')
@require_ajax
def api_bounce_list():
    """获取退信列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    bounce_type = request.args.get('type', '')
    current_user_id = get_current_user_id()
    admin = is_admin()
    data = get_bounce_list(page, per_page, bounce_type, user_id=current_user_id, admin=admin)
    return jsonify({'success': True, 'data': data})


@app.route('/api/bounces/check', methods=['POST'])
@require_ajax
def api_bounce_check():
    """手动触发退信检查"""
    try:
        from services.imap_bounce_checker import create_bounce_checker
        checker = create_bounce_checker()
        if not checker.is_available():
            return jsonify({'success': False, 'error': 'IMAP 未配置'})
        result = checker.check_bounces()
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bounces/connection')
@require_ajax
def api_bounce_connection():
    """测试 IMAP 连接"""
    if not is_admin():
        return jsonify({'success': False, 'error': '仅管理员可操作'}), 403
    try:
        from services.imap_bounce_checker import create_bounce_checker
        checker = create_bounce_checker()
        result = checker.check_connection()
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': True, 'data': {'ok': False, 'error': str(e)}})


# ============ API 配置管理 ============

@app.route('/api/configs', methods=['GET'])
@require_ajax
def api_get_configs():
    """获取所有 API 配置"""
    current_user_id = get_current_user_id()
    admin = is_admin()
    configs = get_all_api_configs(user_id=current_user_id, admin=admin)
    return jsonify({'success': True, 'configs': configs})


@app.route('/api/configs', methods=['POST'])
@require_ajax
def api_create_config():
    """创建 API 配置"""
    data = request.json or {}
    api_name = data.get('api_name', '').strip()
    api_key = data.get('api_key', '').strip()
    base_url = data.get('base_url', '').strip()
    model = data.get('model', '').strip()
    if not api_name or not api_key:
        return jsonify({'success': False, 'error': 'API名称和Key不能为空'}), 400
    current_user_id = get_current_user_id()
    if create_api_config(api_name, api_key, base_url, model, user_id=current_user_id):
        return jsonify({'success': True, 'message': '创建成功'})
    return jsonify({'success': False, 'error': '创建失败，名称可能已存在'}), 400


@app.route('/api/configs/<api_name>', methods=['PUT'])
@require_ajax
def api_update_config(api_name):
    """更新 API 配置"""
    data = request.json or {}
    kwargs = {}
    if 'api_key' in data:
        kwargs['api_key'] = data['api_key'].strip()
    if 'base_url' in data:
        kwargs['base_url'] = data['base_url'].strip()
    if 'model' in data:
        kwargs['model'] = data['model'].strip()
    if 'is_active' in data:
        kwargs['is_active'] = data['is_active']
    current_user_id = get_current_user_id()
    admin = is_admin()
    kwargs['user_id'] = current_user_id
    kwargs['admin'] = admin
    if update_api_config(api_name, **kwargs):
        return jsonify({'success': True, 'message': '更新成功'})
    return jsonify({'success': False, 'error': '更新失败'}), 400


@app.route('/api/configs/<api_name>', methods=['DELETE'])
@require_ajax
def api_delete_config(api_name):
    """删除 API 配置"""
    current_user_id = get_current_user_id()
    admin = is_admin()
    if delete_api_config(api_name, user_id=current_user_id, admin=admin):
        return jsonify({'success': True, 'message': '删除成功'})
    return jsonify({'success': False, 'error': '删除失败'}), 400


@app.route('/api/customers/<int:customer_id>/emails')
def api_customer_emails(customer_id):
    """获取客户邮箱列表"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = [customer_id]
        if not admin and current_user_id:
            user_where = " AND e.user_id = ?"
            user_params.append(current_user_id)

        cursor.execute(f"""
            SELECT e.id, e.email_address, e.email_type, e.is_active,
                   COALESCE(e.contact_name, co.contact_name) as contact_name,
                   COALESCE(e.job_title, co.job_title) as job_title,
                   e.bounce_status, e.bounce_count, e.bounce_reason
            FROM emails e
            LEFT JOIN contacts co ON e.contact_id = co.id
            WHERE e.customer_id = ?{user_where}
            ORDER BY e.email_type, e.id
        """, user_params)

        emails = [{
            'id': r[0], 'address': r[1], 'type': r[2], 'active': r[3],
            'contact_name': r[4], 'job_title': r[5],
            'bounce_status': r[6] or 'none', 'bounce_count': r[7] or 0,
            'bounce_reason': r[8] or ''
        } for r in cursor.fetchall()]

        conn.close()

        return jsonify({'success': True, 'data': {'emails': emails}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers/<int:customer_id>/emails', methods=['POST'])
@require_ajax
def api_customer_email_add(customer_id):
    """为客户添加邮箱"""
    try:
        data = request.json or {}
        email_addr = sanitize_text(data.get('email_address'))
        email_type = data.get('email_type', 'public')
        contact_name = sanitize_text(data.get('contact_name'))
        job_title = sanitize_text(data.get('job_title'))

        # 验证邮箱
        if not email_addr:
            return jsonify({'success': False, 'error': '邮箱地址不能为空'}), 400

        is_valid, error = validate_email(email_addr)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400

        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        # 检查客户是否存在
        if not admin and current_user_id:
            cursor.execute("SELECT id FROM customers WHERE id = ? AND user_id = ?", (customer_id, current_user_id))
        else:
            cursor.execute("SELECT id FROM customers WHERE id = ?", (customer_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': '客户不存在'}), 404

        # 检查该客户下是否已存在相同邮箱
        is_dup, dup_info = check_duplicate_email(email_addr, customer_id, user_id=current_user_id)
        if is_dup:
            conn.close()
            return jsonify({'success': False, 'error': '该邮箱已存在于此客户'}), 400

        # 插入联系人
        contact_id = None
        if contact_name:
            cursor.execute("""
                INSERT INTO contacts (customer_id, contact_name, job_title, source, user_id, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (customer_id, contact_name, job_title, 'manual', current_user_id))
            contact_id = cursor.lastrowid

        # 插入邮箱（同时保存contact_name和job_title）
        cursor.execute("""
            INSERT INTO emails (customer_id, contact_id, email_address, email_type,
                                contact_name, job_title, is_active, user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, datetime('now'))
        """, (customer_id, contact_id, email_addr, email_type, contact_name, job_title, current_user_id))

        email_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': '邮箱添加成功',
            'data': {'email_id': email_id}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers/<int:customer_id>/emails/<int:email_id>', methods=['DELETE'])
@require_ajax
def api_customer_email_delete(customer_id, email_id):
    """删除客户邮箱"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        # 验证邮箱属于该客户
        if not admin and current_user_id:
            cursor.execute("""
                SELECT id FROM emails WHERE id = ? AND customer_id = ? AND user_id = ?
            """, (email_id, customer_id, current_user_id))
        else:
            cursor.execute("""
                SELECT id FROM emails WHERE id = ? AND customer_id = ?
            """, (email_id, customer_id))

        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': '邮箱不存在或不属于该客户'}), 404

        if not admin and current_user_id:
            cursor.execute("DELETE FROM emails WHERE id = ? AND user_id = ?", (email_id, current_user_id))
        else:
            cursor.execute("DELETE FROM emails WHERE id = ?", (email_id,))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': '邮箱已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/emails/logs')
def api_email_logs():
    """获取邮件发送日志"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status_filter = request.args.get('status', '')
        offset = (page - 1) * per_page

        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " AND (el.user_id = ? OR el.user_id IS NULL)"
            user_params = [current_user_id]

        if status_filter:
            cursor.execute(f'''
                SELECT el.id, c.customer_name, e.email_address, el.email_subject,
                       el.send_status, el.sent_at, el.error_message
                FROM email_logs el
                JOIN customers c ON el.customer_id = c.id
                JOIN emails e ON el.email_id = e.id
                WHERE el.send_status = ?{user_where}
                ORDER BY el.sent_at DESC
                LIMIT ? OFFSET ?
            ''', (status_filter,) + tuple(user_params) + (per_page, offset))
        else:
            cursor.execute(f'''
                SELECT el.id, c.customer_name, e.email_address, el.email_subject,
                       el.send_status, el.sent_at, el.error_message
                FROM email_logs el
                JOIN customers c ON el.customer_id = c.id
                JOIN emails e ON el.email_id = e.id
                WHERE 1=1{user_where}
                ORDER BY el.sent_at DESC
                LIMIT ? OFFSET ?
            ''', tuple(user_params) + (per_page, offset))

        rows = cursor.fetchall()

        if not admin and current_user_id:
            cursor.execute(f"SELECT COUNT(*) FROM email_logs WHERE user_id = ?", (current_user_id,))
        else:
            cursor.execute('SELECT COUNT(*) FROM email_logs')
        total = cursor.fetchone()[0]

        conn.close()

        logs = [{
            'id': r[0], 'customer': r[1], 'email': r[2], 'subject': r[3],
            'status': r[4], 'sent_at': r[5], 'error': r[6]
        } for r in rows]

        return jsonify({
            'success': True,
            'data': {
                'logs': logs,
                'total': total,
                'page': page,
                'per_page': per_page
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/subjects')
def api_subjects():
    """获取主题池统计"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " WHERE user_id = ?"
            user_params = [current_user_id]

        # 有主题池的客户数
        cursor.execute(f'SELECT COUNT(DISTINCT customer_id) FROM customer_subjects{user_where}', user_params)
        with_subjects = cursor.fetchone()[0]

        # 无主题池的客户数
        cursor.execute(f'SELECT COUNT(*) FROM customers{user_where}', user_params)
        total_customers = cursor.fetchone()[0]

        # 主题类型分布
        cursor.execute(f'SELECT subject_type, COUNT(*) FROM customer_subjects{user_where} GROUP BY subject_type', user_params)
        type_dist = dict(cursor.fetchall())

        # 使用历史
        cursor.execute(f'''
            SELECT cs.subject_type, COUNT(*) as usage_count
            FROM subject_usage_log sul
            JOIN customer_subjects cs ON sul.subject_id = cs.id
            {user_where}
            GROUP BY cs.subject_type
            ORDER BY usage_count DESC
        ''', user_params)
        usage_stats = dict(cursor.fetchall())

        # 客户主题列表（带使用次数统计）
        cursor.execute(f'''
            SELECT c.id, c.customer_name, c.country,
                   cs.id as subject_id, cs.subject_line, cs.subject_type, cs.subject_index,
                   cs.generation_strategy,
                   (SELECT COUNT(*) FROM subject_usage_log WHERE subject_id = cs.id) as usage_count
            FROM customers c
            JOIN customer_subjects cs ON c.id = cs.customer_id
            {user_where}
            ORDER BY c.customer_name, cs.subject_index
            LIMIT 200
        ''', user_params)
        rows = cursor.fetchall()

        customer_subjects_map = {}
        for row in rows:
            cid = row[0]
            if cid not in customer_subjects_map:
                customer_subjects_map[cid] = {
                    'customer_id': cid,
                    'customer_name': row[1],
                    'country': row[2],
                    'subjects': []
                }
            customer_subjects_map[cid]['subjects'].append({
                'subject_id': row[3],
                'subject_line': row[4],
                'subject_type': row[5],
                'subject_index': row[6],
                'generation_strategy': row[7],
                'usage_count': row[8]
            })

        # 最近使用的主题
        cursor.execute(f'''
            SELECT sul.subject_line, c.customer_name, sul.used_at
            FROM subject_usage_log sul
            JOIN customers c ON sul.customer_id = c.id
            {user_where}
            ORDER BY sul.used_at DESC
            LIMIT 10
        ''', user_params)
        recent_usage = [{'subject': r[0], 'customer': r[1], 'used_at': r[2]} for r in cursor.fetchall()]

        conn.close()

        return jsonify({
            'success': True,
            'data': {
                'with_subjects': with_subjects,
                'without_subjects': total_customers - with_subjects,
                'total_customers': total_customers,
                'subjects_per_customer': 5,
                'type_distribution': type_dist,
                'usage_stats': usage_stats,
                'customer_subjects': list(customer_subjects_map.values()),
                'recent_usage': recent_usage
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scheduler/status')
def api_scheduler_status():
    """获取调度器状态"""
    if not is_admin():
        return jsonify({'success': False, 'error': '仅管理员可操作'}), 403
    try:
        status = scheduler_instance.get_status()
        return jsonify({'success': True, 'data': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduler/start', methods=['POST'])
@require_ajax
def api_scheduler_start():
    """启动调度器"""
    if not is_admin():
        return jsonify({'success': False, 'error': '仅管理员可操作'}), 403
    try:
        success, message = scheduler_instance.start()
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduler/stop', methods=['POST'])
@require_ajax
def api_scheduler_stop():
    """停止调度器"""
    if not is_admin():
        return jsonify({'success': False, 'error': '仅管理员可操作'}), 403
    try:
        success, message = scheduler_instance.stop()
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduler/config', methods=['POST'])
@require_ajax
def api_scheduler_config():
    """更新调度器配置"""
    try:
        data = request.json or {}
        current_user_id = get_current_user_id()
        if current_user_id:
            save_user_setting(current_user_id, 'scheduler', data)
        scheduler_instance.update_config(data)
        return jsonify({'success': True, 'message': '调度配置已更新', 'data': scheduler_instance.config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduler/run-now', methods=['POST'])
@require_ajax
def api_scheduler_run_now():
    """手动立即执行一次"""
    if not is_admin():
        return jsonify({'success': False, 'error': '仅管理员可操作'}), 403
    try:
        success, message = scheduler_instance.run_now()
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduler/preview')
def api_scheduler_preview():
    """预览本次将发送的邮件列表"""
    try:
        preview = scheduler_instance.get_preview()
        current_user_id = get_current_user_id()
        admin = is_admin()
        if not admin and current_user_id:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM customers WHERE user_id = ?', (current_user_id,))
            allowed_ids = {r[0] for r in cursor.fetchall()}
            conn.close()
            preview = [p for p in preview if p.get('customer_id') in allowed_ids]
        return jsonify({'success': True, 'data': {'emails': preview, 'count': len(preview)}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduler/queue')
def api_scheduler_queue():
    """获取发送队列详情"""
    try:
        queue = scheduler_instance.get_queue()
        current_user_id = get_current_user_id()
        admin = is_admin()
        if not admin and current_user_id:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM customers WHERE user_id = ?', (current_user_id,))
            allowed_ids = {r[0] for r in cursor.fetchall()}
            conn.close()
            queue = [q for q in queue if q.get('customer_id') in allowed_ids]
        return jsonify({'success': True, 'data': {'queue': queue}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/countries')
def api_countries():
    """获取所有有客户的国家列表及每个国家的客户数"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " AND c.user_id = ?"
            user_params = [current_user_id]

        cursor.execute(f'''
            SELECT c.country, COUNT(*) as cnt
            FROM customers c
            WHERE c.country IS NOT NULL AND c.country != '' AND c.country != 'nan' AND c.country != 'NaN' AND c.country != 'None'{user_where}
            GROUP BY c.country
            ORDER BY cnt DESC
        ''', user_params)
        rows = cursor.fetchall()
        conn.close()
        countries = [{'name': r[0], 'count': r[1]} for r in rows]
        return jsonify({'success': True, 'data': {'countries': countries}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/countries/<country>/customers')
def api_country_customers(country):
    """获取指定国家的客户列表（含冷却状态）"""
    try:
        cooldown_days = scheduler_instance.config.get('cooldown_days', 7)
        cutoff = (datetime.now() - timedelta(days=cooldown_days)).strftime('%Y-%m-%d %H:%M:%S')
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = [country]
        if not admin and current_user_id:
            user_where = " AND (c.user_id = ? OR c.user_id IS NULL)"
            user_params.append(current_user_id)

        cursor.execute(f'''
            SELECT c.id, c.customer_name, c.country, c.website,
                   COUNT(DISTINCT CASE WHEN e.is_active = 1 THEN e.id END) as email_count
            FROM customers c
            LEFT JOIN emails e ON c.id = e.customer_id
            WHERE c.country = ?{user_where}
            GROUP BY c.id
            ORDER BY c.customer_name
        ''', user_params)
        rows = cursor.fetchall()

        customers = []
        for r in rows:
            customer_id = r[0]
            # 查询该公司是否在冷却期内（排除已手动解除的）
            cursor.execute('SELECT 1 FROM cooldown_override WHERE customer_id = ? AND (user_id IS NULL OR user_id = ?)',
                           (customer_id, current_user_id or 0))
            if cursor.fetchone():
                in_cooldown = False
                days_remaining = 0
            else:
                cursor.execute('''
                    SELECT MAX(sent_at) FROM email_logs
                    WHERE customer_id = ? AND send_status = 'sent'
                      AND (user_id IS NULL OR user_id = ?)
                ''', (customer_id, current_user_id))
                last_sent = cursor.fetchone()[0]

                in_cooldown = False
                days_remaining = 0
                if last_sent:
                    dt = _parse_datetime(last_sent)
                    if dt and dt.strftime('%Y-%m-%d %H:%M:%S') >= cutoff:
                        in_cooldown = True
                        cooldown_end = dt + timedelta(days=cooldown_days)
                        days_remaining = max(0, (cooldown_end - datetime.now()).days + 1)

            customers.append({
                'id': customer_id,
                'name': r[1],
                'country': r[2],
                'website': r[3],
                'email_count': r[4],
                'in_cooldown': in_cooldown,
                'days_remaining': days_remaining,
                'last_sent': last_sent
            })

        conn.close()
        return jsonify({'success': True, 'data': {'customers': customers}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 增强调度器 API ====================

@app.route('/api/industries')
def api_industries():
    """获取所有行业类型列表"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " AND (c.user_id = ? OR c.user_id IS NULL)"
            user_params = [current_user_id]

        cursor.execute(f'''
            SELECT c.industry_type, COUNT(*) as cnt
            FROM customers c
            WHERE c.industry_type IS NOT NULL AND c.industry_type != ''{user_where}
            GROUP BY c.industry_type
            ORDER BY cnt DESC
        ''', user_params)
        rows = cursor.fetchall()
        conn.close()
        industries = [{'name': r[0], 'count': r[1]} for r in rows]
        return jsonify({'success': True, 'data': {'industries': industries}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers/filter-preview', methods=['POST'])
@require_ajax
def api_customers_filter_preview():
    """预览筛选结果（不写入队列）"""
    try:
        from services.email_filter import EmailFilter
        data = request.json or {}
        current_user_id = get_current_user_id()
        admin = is_admin()
        filter_config = {
            'countries': data.get('countries', []),
            'industry_type': data.get('industry_type', ''),
            'email_types': data.get('email_types', []),
            'email_type': data.get('email_type', 'all'),
            'send_status': data.get('send_status', 'all'),
            'search_keyword': data.get('search_keyword', ''),
            'cooldown_days': data.get('cooldown_days', 7),
            'daily_limit': data.get('daily_limit', 1000),
            'limit': data.get('limit', 200),
            'order_by': data.get('order_by', 'default'),
            'user_id': current_user_id if not admin else None,
        }
        filter_engine = EmailFilter(filter_config)
        results = filter_engine.preview(filter_config)
        return jsonify({'success': True, 'data': {'emails': results, 'count': len(results)}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customers/<int:customer_id>/emails-detail')
def api_customer_emails_detail(customer_id):
    """获取客户邮箱详情（含发送历史）"""
    try:
        from services.email_filter import EmailFilter
        # 验证客户归属当前用户
        current_user_id = get_current_user_id()
        if current_user_id and not is_admin():
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM customers WHERE id = ?', (customer_id,))
            row = cursor.fetchone()
            conn.close()
            if row and row[0] != current_user_id:
                return jsonify({'success': False, 'error': '无权访问该客户'}), 403
        filter_engine = EmailFilter()
        emails = filter_engine.get_customer_emails(customer_id)
        return jsonify({'success': True, 'data': {'emails': emails}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduler/tree')
def api_scheduler_tree():
    """获取调度器树状结构数据：国家 -> 公司 -> 邮箱（含冷却状态）"""
    try:
        cooldown_days = scheduler_instance.config.get('cooldown_days', 7)
        cutoff = (datetime.now() - timedelta(days=cooldown_days)).strftime('%Y-%m-%d %H:%M:%S')
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " AND (c.user_id = ? OR c.user_id IS NULL)"
            user_params = [current_user_id]

        # 获取所有有客户的国家
        cursor.execute(f'''
            SELECT c.country, COUNT(DISTINCT c.id) as company_count
            FROM customers c
            WHERE c.country IS NOT NULL AND c.country != ''
                  AND c.country != 'nan' AND c.country != 'NaN' AND c.country != 'None'{user_where}
            GROUP BY c.country
            ORDER BY company_count DESC
        ''', user_params)
        countries = cursor.fetchall()

        tree = []
        for country_row in countries:
            country_name = country_row[0]
            # 获取该国家下的公司
            cursor.execute(f'''
                SELECT c.id, c.customer_name, c.industry_type,
                       COUNT(DISTINCT CASE WHEN e.is_active = 1 THEN e.id END) as email_count
                FROM customers c
                LEFT JOIN emails e ON c.id = e.customer_id
                WHERE c.country = ?{user_where}
                GROUP BY c.id
                ORDER BY c.customer_name
            ''', [country_name] + user_params)
            companies = cursor.fetchall()

            company_list = []
            for comp in companies:
                comp_id, comp_name, industry, email_count = comp
                # 获取该公司的邮箱
                cursor.execute('''
                    SELECT e.id, e.email_address, e.email_type,
                           COALESCE(e.contact_name, ct.contact_name) as contact_name,
                           COALESCE(e.job_title, ct.job_title) as job_title,
                           e.is_active
                    FROM emails e
                    LEFT JOIN contacts ct ON e.contact_id = ct.id
                    WHERE e.customer_id = ? AND e.is_active = 1
                    ORDER BY e.email_type, e.id
                ''', (comp_id,))
                emails_data = cursor.fetchall()

                email_list = [{
                    'id': e[0],
                    'address': e[1],
                    'type': e[2],
                    'contact_name': e[3] or '',
                    'job_title': e[4] or '',
                    'is_active': e[5]
                } for e in emails_data]

                # 检查该公司是否在冷却期内（排除手动解除的，按用户隔离）
                cursor.execute('SELECT 1 FROM cooldown_override WHERE customer_id = ? AND (user_id IS NULL OR user_id = ?)',
                               (comp_id, current_user_id))
                released = cursor.fetchone() is not None
                in_cooldown = False
                days_remaining = 0
                if not released:
                    cursor.execute('''
                        SELECT MAX(sent_at) FROM email_logs
                        WHERE customer_id = ? AND send_status = 'sent'
                          AND (user_id IS NULL OR user_id = ?)
                    ''', (comp_id, current_user_id))
                    last_sent = cursor.fetchone()[0]
                    if last_sent:
                        dt = _parse_datetime(last_sent)
                        if dt and dt.strftime('%Y-%m-%d %H:%M:%S') >= cutoff:
                            in_cooldown = True
                            cooldown_end = dt + timedelta(days=cooldown_days)
                            days_remaining = max(0, (cooldown_end - datetime.now()).days + 1)

                company_list.append({
                    'id': comp_id,
                    'name': comp_name,
                    'industry': industry or '',
                    'email_count': email_count,
                    'emails': email_list,
                    'in_cooldown': in_cooldown,
                    'days_remaining': days_remaining
                })

            tree.append({
                'country': country_name,
                'company_count': country_row[1],
                'companies': company_list
            })

        conn.close()
        return jsonify({'success': True, 'data': {'tree': tree}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send-tasks', methods=['POST'])
@require_ajax
def api_create_send_task():
    """创建独立发送任务（批量/定向/测试）"""
    try:
        from services.email_filter import EmailFilter
        from core.sender import EmailSender
        from generators.workflow import EmailWorkflow

        data = request.json or {}
        task_type = data.get('task_type', 'batch')  # batch / targeted / test
        email_ids = data.get('email_ids', [])  # 定向发送时指定邮箱ID列表
        filter_config = data.get('filter', {})
        send_config = {
            'interval_seconds': data.get('interval_seconds', 120),
            'auto_pause_after': data.get('auto_pause_after', 0),
            'max_retries': data.get('max_retries', 2),
            'pause_on_error': data.get('pause_on_error', False),
        }
        target_word_count = data.get('target_word_count')
        selected_material_ids = data.get('selected_material_ids')
        sender_material_id = data.get('sender_material_id')

        current_user_id = get_current_user_id()
        admin = is_admin()

        # 检查是否有相同 email_ids 的任务正在运行
        email_ids_set = frozenset(email_ids) if email_ids else frozenset()
        with send_tasks_lock:
            for tid, t in send_tasks.items():
                if t.get('status') in ('running', 'pending') and t.get('email_ids_set') == email_ids_set:
                    return jsonify({'success': False, 'error': '相同邮箱列表的任务正在运行中，请等待完成后再发送'}), 409

        # 生成任务ID
        task_id = f"send_{task_type}_{uuid.uuid4().hex[:8]}"

        # 获取待发送的邮件列表
        if email_ids:
            # 定向发送：按email_ids查询，同时检查公司级冷却期
            conn = get_connection()
            cursor = conn.cursor()
            # 过滤掉冷却期内已发送的公司
            cooldown_days = filter_config.get('cooldown_days', 7)
            cutoff_date = (datetime.now() - timedelta(days=cooldown_days)).strftime('%Y-%m-%d %H:%M:%S')
            placeholders = ','.join('?' * len(email_ids))
            user_where = ""
            user_params = []
            cooldown_user_where = ""
            cooldown_user_params = []
            if not admin and current_user_id:
                user_where = " AND c.user_id = ? AND e.user_id = ?"
                user_params = [current_user_id, current_user_id]
                cooldown_user_where = " AND user_id = ?"
                cooldown_user_params = [current_user_id]
            cursor.execute(f'''
                SELECT c.id, c.customer_name, c.country, c.website,
                       e.id, e.email_address, e.email_type,
                       COALESCE(e.contact_name, ct.contact_name) as contact_name,
                       COALESCE(e.job_title, ct.job_title) as job_title
                FROM customers c
                JOIN emails e ON c.id = e.customer_id
                LEFT JOIN contacts ct ON e.contact_id = ct.id
                WHERE e.id IN ({placeholders}) AND e.is_active = 1{user_where}
                  AND (
                      c.id IN (SELECT customer_id FROM cooldown_override WHERE 1=1{cooldown_user_where})
                      OR c.id NOT IN (
                          SELECT DISTINCT customer_id FROM email_logs
                          WHERE send_status = 'sent' AND sent_at >= ?{cooldown_user_where}
                      )
                  )
                ORDER BY c.id, e.id
            ''', email_ids + user_params + cooldown_user_params + [cutoff_date] + cooldown_user_params)
            rows = cursor.fetchall()
            conn.close()
            emails_to_send = [{
                'customer_id': r[0], 'customer_name': r[1], 'country': r[2], 'website': r[3],
                'email_id': r[4], 'email_address': r[5], 'email_type': r[6],
                'contact_name': r[7], 'job_title': r[8]
            } for r in rows]
        else:
            # 批量/测试发送：使用筛选器
            filter_engine = EmailFilter()
            filter_config['limit'] = 5 if task_type == 'test' else filter_config.get('limit', 1000)
            emails_to_send = filter_engine.filter_customers(filter_config, user_id=current_user_id, admin=admin)

        if not emails_to_send:
            return jsonify({'success': False, 'error': '没有符合条件的邮件（可能已在冷却期内发送过）'}), 400

        # 初始化任务状态
        with send_tasks_lock:
            send_tasks[task_id] = {
                'id': task_id,
                'status': 'running',
                'progress': 0,
                'current_step': '准备发送',
                'step_status': {'send': 'running'},
                'results': [],
                'email_preview': None,
                'error': None,
                'send_config': send_config,
                'email_ids_set': email_ids_set,
                'selected_material_ids': selected_material_ids,
                'sender_material_id': sender_material_id,
                'created_at': time.time()
            }

        current_user_id = get_current_user_id()
        persist_send_task_meta(
            task_id=task_id, task_type=task_type, status='running',
            total_emails=len(emails_to_send),
            step_status={'send': 'running'},
            send_config=send_config,
            user_id=current_user_id,
        )

        # 启动后台线程执行发送
        thread = threading.Thread(
            target=_do_batch_send,
            args=(task_id, emails_to_send, send_config, target_word_count, current_user_id),
            daemon=True
        )
        thread.start()

        return jsonify({'success': True, 'data': {'task_id': task_id, 'total_emails': len(emails_to_send)}})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _do_batch_send(task_id, emails_to_send, send_config, target_word_count=None, user_id=None):
    """后台执行批量发送任务 - 完整邮件工作流"""
    task = send_tasks.get(task_id)
    if not task:
        return

    try:
        from core.sender import EmailSender
        from generators.workflow import EmailWorkflow
        sender = EmailSender(user_id=user_id)
        sender_material_id = task.get('sender_material_id') if task else None
        workflow = EmailWorkflow(user_id=user_id, sender_material_id=sender_material_id)

        # 按客户分组
        from collections import defaultdict
        customer_groups = defaultdict(list)
        for item in emails_to_send:
            customer_groups[item['customer_id']].append(item)

        total_customers = len(customer_groups)
        processed_customers = 0
        all_email_items = []

        def update_task_progress(step, progress, message):
            """更新任务进度"""
            with send_tasks_lock:
                task['current_step'] = step
                task['progress'] = progress
                task['step_status'] = {'send': 'running', 'current': message}
            persist_send_task_meta(
                task_id, 'batch', 'running',
                total_emails=len(emails_to_send),
                progress=progress,
                step_status={'send': 'running', 'current': message},
                user_id=user_id,
            )

        # 导入智能标题管理器
        from generators.subjects.manager import subject_manager

        # 为每个客户执行完整邮件工作流
        for customer_id, items in customer_groups.items():
            customer_name = items[0]['customer_name']
            website = items[0].get('website', '')
            country = items[0].get('country', '')
            processed_customers += 1
            base_progress = int((processed_customers - 1) / total_customers * 50)

            try:
                # Step 1: 公司背调
                update_task_progress(
                    'research',
                    base_progress + 5,
                    f'[{processed_customers}/{total_customers}] 背调: {customer_name}'
                )

                # Step 2-7: 生成邮件内容（包含分类、优势提炼、FABE、生成、润色）
                update_task_progress(
                    'generate',
                    base_progress + 20,
                    f'[{processed_customers}/{total_customers}] 生成邮件: {customer_name}'
                )

                selected_material_ids = task.get('selected_material_ids')
                email_content = workflow.generate_email(
                    customer_name, website or '',
                    target_word_count=target_word_count,
                    selected_material_ids=selected_material_ids
                )

                # Step 8: 智能标题生成与分配
                update_task_progress(
                    'subjects',
                    base_progress + 40,
                    f'[{processed_customers}/{total_customers}] 标题生成: {customer_name}'
                )

                # 为每个邮箱构建基础邮件内容
                email_items_for_customer = []
                for item in items:
                    email_type = item['email_type']
                    contact_name = item.get('contact_name', '') or ''
                    email_addr = item.get('email_address', '') or ''
                    greeting = _make_greeting(email_type, contact_name, email_addr, customer_name)

                    # 组装完整邮件正文
                    full_body = f"{greeting}\n\n{email_content['body']}\n\n{email_content['signature']}"

                    email_items_for_customer.append({
                        'email_id': item['email_id'],
                        'customer_id': customer_id,
                        'email_address': item['email_address'],
                        'email_type': email_type,
                        'contact_name': contact_name,
                        'greeting': greeting,
                        'body': full_body,
                        'customer_name': customer_name,
                    })

                # 使用智能标题管理器：生成多个标题并随机分配给各个邮箱
                subjects, assigned_items = subject_manager.generate_and_assign(
                    customer_id=customer_id,
                    customer_name=customer_name,
                    country=country,
                    industry='',
                    email_items=email_items_for_customer
                )

                print(f"[发送任务 {task_id}] 客户 {customer_name}: 生成 {len(subjects)} 个标题，分配给 {len(items)} 个邮箱")
                for s in subjects:
                    print(f"  - {s}")

                # 将分配好的邮件项加入总列表
                all_email_items.extend(assigned_items)

            except Exception as e:
                print(f"[发送任务 {task_id}] 客户 {customer_name} 邮件生成失败: {e}")
                # 跳过该客户，继续处理其他客户
                continue

        if not all_email_items:
            task['status'] = 'failed'
            task['error'] = '所有客户邮件生成失败'
            persist_send_task_meta(task_id, 'batch', 'failed', error='所有客户邮件生成失败', user_id=user_id)
            return

        # 保存邮件预览（第一个客户的）
        if all_email_items:
            task['email_preview'] = {
                'subject': all_email_items[0]['subject'],
                'body': all_email_items[0]['body'],
            }

        # 使用队列管理器发送
        update_task_progress('send', 50, f'开始发送，共 {len(all_email_items)} 封邮件')

        queue_manager.create_task(
            task_id, all_email_items, send_config,
            step_status=task.get('step_status', {}),
            email_preview=task.get('email_preview')
        )
        queue_manager.start_task(task_id)

        # 等待发送完成，实时更新进度
        while True:
            qt = queue_manager.get_task(task_id)
            if not qt:
                break

            # 更新发送进度 (50% ~ 100%)
            send_progress = qt.progress if qt.progress else 0
            overall_progress = 50 + int(send_progress * 0.5)

            stats = qt.get_stats()
            with send_tasks_lock:
                task['progress'] = overall_progress
                task['step_status'] = {
                    'send': 'running',
                    'current': f'发送中 {stats["sent_count"]}/{stats["total_emails"]}',
                    'sent': stats['sent_count'],
                    'failed': stats['failed_count']
                }

            if qt.status in ('completed', 'failed', 'cancelled'):
                break
            time.sleep(1)

        # 同步结果
        qt = queue_manager.get_task(task_id)
        if qt:
            with send_tasks_lock:
                task['status'] = qt.status
                task['progress'] = 100 if qt.status == 'completed' else qt.progress
                task['error'] = qt.error
                task['results'] = [
                    {'email': item.email_address, 'success': item.status == 'sent',
                     'greeting': item.greeting, 'subject': item.subject,
                     'customer_name': item.customer_name if hasattr(item, 'customer_name') else '',
                     'message': item.error_message or '发送成功'}
                    for item in qt.items
                ]
            persist_send_task_meta(
                task_id, 'batch', qt.status,
                total_emails=len(qt.items),
                sent_count=sum(1 for i in qt.items if i.status == 'sent'),
                failed_count=sum(1 for i in qt.items if i.status == 'failed'),
                progress=100 if qt.status == 'completed' else qt.progress,
                step_status=task.get('step_status', {}),
                email_preview=task.get('email_preview'),
                send_config=send_config,
                error=qt.error,
                user_id=user_id,
            )

    except Exception as e:
        task['status'] = 'failed'
        task['error'] = str(e)
        import traceback
        traceback.print_exc()
        persist_send_task_meta(task_id, 'batch', 'failed', error=str(e), user_id=user_id)


@app.route('/api/send-tasks/<task_id>')
def api_get_send_task(task_id):
    """获取发送任务详情"""
    try:
        # 优先从队列管理器获取
        qm_status = queue_manager.get_task_status(task_id)
        if qm_status:
            return jsonify({'success': True, 'data': qm_status})

        # 从内存获取
        with send_tasks_lock:
            task = send_tasks.get(task_id)
            if task:
                # 验证任务归属
                current_user_id = get_current_user_id()
                if 'user_id' in task and not is_admin() and current_user_id != task.get('user_id'):
                    return jsonify({'success': False, 'error': '无权访问该任务'}), 403
                return jsonify({
                    'success': True,
                    'data': {
                        'task_id': task['id'],
                        'status': task['status'],
                        'progress': task['progress'],
                        'current_step': task['current_step'],
                        'total_emails': len(task.get('results', [])),
                        'sent_count': sum(1 for r in task.get('results', []) if r.get('success')),
                        'failed_count': sum(1 for r in task.get('results', []) if not r.get('success')),
                        'error': task['error'],
                    }
                })

        # 从数据库获取
        current_user_id = get_current_user_id()
        admin = is_admin()
        db_tasks = get_active_send_tasks(user_id=current_user_id, admin=admin)
        db_task = next((t for t in db_tasks if t['task_id'] == task_id), None)
        if db_task:
            return jsonify({'success': True, 'data': {
                'task_id': db_task['task_id'],
                'status': db_task['status'],
                'progress': db_task['progress'],
                'total_emails': db_task['total_emails'],
                'sent_count': db_task['sent_count'],
                'failed_count': db_task['failed_count'],
                'error': db_task['error'],
            }})

        return jsonify({'success': False, 'error': '任务不存在'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send-tasks/<task_id>/action', methods=['POST'])
@require_ajax
def api_send_task_action(task_id):
    """暂停/恢复/取消发送任务"""
    try:
        data = request.json or {}
        action = data.get('action', '')  # pause / resume / cancel

        # 验证任务归属（内存中的任务）
        with send_tasks_lock:
            mem_task = send_tasks.get(task_id)
            if mem_task:
                current_user_id = get_current_user_id()
                if 'user_id' in mem_task and not is_admin() and current_user_id != mem_task.get('user_id'):
                    return jsonify({'success': False, 'error': '无权操作该任务'}), 403

        if action == 'pause':
            success = queue_manager.pause_task(task_id)
            message = '已暂停' if success else '无法暂停'
        elif action == 'resume':
            success = queue_manager.resume_task(task_id)
            message = '已恢复' if success else '无法恢复'
        elif action == 'cancel':
            success = queue_manager.cancel_task(task_id)
            message = '已取消' if success else '无法取消'
        else:
            return jsonify({'success': False, 'error': '无效的操作'}), 400

        if success:
            current_user_id = get_current_user_id()
            persist_send_task_meta(task_id, 'batch', action + 'ed' if action != 'cancel' else 'cancelled', user_id=current_user_id)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email-logs/stats')
def api_email_logs_stats():
    """获取发送统计（按客户聚合）"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()

        conn = get_connection()
        cursor = conn.cursor()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " WHERE el.user_id = ?"
            user_params = [current_user_id]

        # 按客户统计
        cursor.execute(f'''
            SELECT c.id, c.customer_name, c.country,
                   COUNT(DISTINCT CASE WHEN el.send_status = 'sent' THEN el.id END) as sent_count,
                   COUNT(DISTINCT CASE WHEN el.send_status = 'failed' THEN el.id END) as failed_count,
                   MAX(el.sent_at) as last_sent
            FROM customers c
            LEFT JOIN email_logs el ON c.id = el.customer_id
            {user_where}
            GROUP BY c.id
            ORDER BY sent_count DESC
            LIMIT 100
        ''', user_params)
        rows = cursor.fetchall()
        conn.close()

        stats = [{
            'customer_id': r[0], 'customer_name': r[1], 'country': r[2],
            'sent_count': r[3], 'failed_count': r[4], 'last_sent': r[5]
        } for r in rows]

        return jsonify({'success': True, 'data': {'stats': stats}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email-logs/by-customer')
def api_email_logs_by_customer():
    """按公司分组获取手动邮件发送记录（树状结构），支持按国家筛选"""
    try:
        country = request.args.get('country', '')
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        where_clauses = []
        params = []
        if country:
            where_clauses.append('c.country = ?')
            params.append(country)
        if not admin and current_user_id:
            where_clauses.append('el.user_id = ?')
            params.append(current_user_id)
        where_sql = 'WHERE ' + ' AND '.join(where_clauses) if where_clauses else ''

        # 1. 按客户分组聚合（仅查询 email_logs 手动发送表）
        cursor.execute(f'''
            SELECT c.id, c.customer_name, c.country,
                   COUNT(el.id) as total_emails,
                   COUNT(CASE WHEN el.send_status = 'sent' THEN 1 END) as sent_count,
                   COUNT(CASE WHEN el.send_status = 'failed' THEN 1 END) as failed_count,
                   MAX(el.sent_at) as last_sent
            FROM customers c
            JOIN email_logs el ON c.id = el.customer_id
            {where_sql}
            GROUP BY c.id
            ORDER BY MAX(el.sent_at) DESC
            LIMIT 100
        ''', params)
        customer_rows = cursor.fetchall()

        customers = []
        for cr in customer_rows:
            customer_id = cr[0]

            # 2. 查询该客户的详细邮件记录（仅 email_logs 表）
            detail_where = "WHERE el.customer_id = ?"
            detail_params = [customer_id]
            if not admin and current_user_id:
                detail_where += " AND el.user_id = ?"
                detail_params.append(current_user_id)
            cursor.execute(f'''
                SELECT el.id, el.email_id, e.email_address, el.email_subject,
                       el.email_content, el.send_status, el.error_message,
                       el.sent_at, el.task_id, el.source
                FROM email_logs el
                LEFT JOIN emails e ON el.email_id = e.id
                {detail_where}
                ORDER BY el.sent_at DESC
                LIMIT 50
            ''', detail_params)
            email_rows = cursor.fetchall()

            # 按日期分组，同一天同主题邮件合并展示
            from collections import OrderedDict
            send_history_by_date = OrderedDict()
            for er in email_rows:
                sent_at = er[7]
                date_key = sent_at[:10] if sent_at else 'Unknown'
                if date_key not in send_history_by_date:
                    send_history_by_date[date_key] = []

                # 用 subject 作为合并标识（同一公司同一天同主题合并）
                subject_key = er[3] or ''
                # 查找是否已有相同主题的条目
                existing = None
                for item in send_history_by_date[date_key]:
                    if item['subject'] == subject_key:
                        existing = item
                        break

                if existing:
                    # 合并邮箱到现有条目
                    existing['email_addresses'].append(er[2] or '-')
                    existing['email_ids'].append(er[1])
                    existing['log_ids'].append(er[0])
                    if er[5] == 'sent':
                        existing['sent_count'] += 1
                    else:
                        existing['failed_count'] += 1
                else:
                    send_history_by_date[date_key].append({
                        'subject': er[3],
                        'log_id': er[0],
                        'log_ids': [er[0]],
                        'email_ids': [er[1]],
                        'email_addresses': [er[2] or '-'],
                        'body_preview': er[4],
                        'send_status': er[5],
                        'sent_count': 1 if er[5] == 'sent' else 0,
                        'failed_count': 0 if er[5] == 'sent' else 1,
                        'error_message': er[6],
                        'sent_at': er[7],
                        'task_id': er[8],
                        'source': er[9]
                    })

            customers.append({
                'customer_id': customer_id,
                'customer_name': cr[1],
                'country': cr[2],
                'total_emails': cr[3],
                'sent_count': cr[4],
                'failed_count': cr[5],
                'last_sent': cr[6],
                'send_history_by_date': send_history_by_date
            })

        conn.close()
        return jsonify({'success': True, 'data': {'customers': customers}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email-logs/<int:log_id>')
def api_email_log_detail(log_id):
    """获取单条手动邮件记录的完整内容"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()

        conn = get_connection()
        cursor = conn.cursor()

        where_sql = "WHERE el.id = ?"
        params = [log_id]
        if not admin and current_user_id:
            where_sql += " AND el.user_id = ?"
            params.append(current_user_id)

        cursor.execute(f'''
            SELECT el.id, el.customer_id, c.customer_name, el.email_id, e.email_address,
                   el.email_subject, el.email_content, el.send_status, el.error_message,
                   el.sent_at, el.task_id, el.source
            FROM email_logs el
            LEFT JOIN customers c ON el.customer_id = c.id
            LEFT JOIN emails e ON el.email_id = e.id
            {where_sql}
        ''', params)
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'success': False, 'error': '记录不存在'}), 404

        return jsonify({'success': True, 'data': {
            'log_id': row[0], 'customer_id': row[1], 'customer_name': row[2],
            'email_id': row[3], 'email_address': row[4], 'subject': row[5],
            'body': row[6], 'send_status': row[7], 'error_message': row[8],
            'sent_at': row[9], 'task_id': row[10], 'source': row[11]
        }})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email-logs-scheduled/by-customer')
def api_email_logs_scheduled_by_customer():
    """按公司分组获取调度器邮件发送记录，支持按国家筛选"""
    try:
        country = request.args.get('country', '')
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        where_clauses = ["el.source = 'scheduled'"]
        params = []
        if country:
            where_clauses.append('c.country = ?')
            params.append(country)
        if not admin and current_user_id:
            where_clauses.append('el.user_id = ?')
            params.append(current_user_id)
        where_sql = 'WHERE ' + ' AND '.join(where_clauses)

        # 1. 按客户分组聚合（从 email_logs 中筛选 source='scheduled'）
        cursor.execute(f'''
            SELECT c.id, c.customer_name, c.country,
                   COUNT(el.id) as total_emails,
                   COUNT(CASE WHEN el.send_status = 'sent' THEN 1 END) as sent_count,
                   COUNT(CASE WHEN el.send_status = 'failed' THEN 1 END) as failed_count,
                   MAX(el.sent_at) as last_sent
            FROM customers c
            JOIN email_logs el ON c.id = el.customer_id
            {where_sql}
            GROUP BY c.id
            ORDER BY MAX(el.sent_at) DESC
            LIMIT 100
        ''', params)
        customer_rows = cursor.fetchall()

        customers = []
        for cr in customer_rows:
            customer_id = cr[0]

            # 2. 查询该客户的详细邮件记录（从 email_logs 中筛选 source='scheduled'）
            detail_where = "WHERE el.customer_id = ? AND el.source = 'scheduled'"
            detail_params = [customer_id]
            if not admin and current_user_id:
                detail_where += " AND el.user_id = ?"
                detail_params.append(current_user_id)
            cursor.execute(f'''
                SELECT el.id, el.email_id, e.email_address, el.email_subject,
                       el.email_content, el.send_status, el.error_message,
                       el.sent_at, el.task_id, el.source
                FROM email_logs el
                LEFT JOIN emails e ON el.email_id = e.id
                {detail_where}
                ORDER BY el.sent_at DESC
                LIMIT 50
            ''', detail_params)
            email_rows = cursor.fetchall()

            # 按日期分组，同一天同主题邮件合并展示
            from collections import OrderedDict
            send_history_by_date = OrderedDict()
            for er in email_rows:
                sent_at = er[7]
                date_key = sent_at[:10] if sent_at else 'Unknown'
                if date_key not in send_history_by_date:
                    send_history_by_date[date_key] = []

                # 用 subject 作为合并标识（同一公司同一天同主题合并）
                subject_key = er[3] or ''
                existing = None
                for item in send_history_by_date[date_key]:
                    if item['subject'] == subject_key:
                        existing = item
                        break

                if existing:
                    existing['email_addresses'].append(er[2] or '-')
                    existing['email_ids'].append(er[1])
                    existing['log_ids'].append(er[0])
                    if er[5] == 'sent':
                        existing['sent_count'] += 1
                    else:
                        existing['failed_count'] += 1
                else:
                    send_history_by_date[date_key].append({
                        'subject': er[3],
                        'log_id': er[0],
                        'log_ids': [er[0]],
                        'email_ids': [er[1]],
                        'email_addresses': [er[2] or '-'],
                        'body_preview': er[4],
                        'send_status': er[5],
                        'sent_count': 1 if er[5] == 'sent' else 0,
                        'failed_count': 0 if er[5] == 'sent' else 1,
                        'error_message': er[6],
                        'sent_at': er[7],
                        'task_id': er[8],
                        'source': er[9]
                    })

            customers.append({
                'customer_id': customer_id,
                'customer_name': cr[1],
                'country': cr[2],
                'total_emails': cr[3],
                'sent_count': cr[4],
                'failed_count': cr[5],
                'last_sent': cr[6],
                'send_history_by_date': send_history_by_date
            })

        conn.close()
        return jsonify({'success': True, 'data': {'customers': customers}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email-logs/countries')
def api_email_logs_countries():
    """获取发送记录涉及的所有国家及数量（手动+调度器合并）"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()

        conn = get_connection()
        cursor = conn.cursor()

        where_sql = "WHERE c.country IS NOT NULL AND c.country != ''"
        params = []
        if not admin and current_user_id:
            where_sql += " AND el.user_id = ?"
            params.append(current_user_id)

        cursor.execute(f'''
            SELECT c.country, COUNT(*) as count
            FROM customers c
            JOIN email_logs el ON c.id = el.customer_id
            {where_sql}
            GROUP BY c.country
            ORDER BY count DESC, c.country
        ''', params)
        rows = cursor.fetchall()
        conn.close()
        return jsonify({
            'success': True,
            'countries': [{'name': r[0], 'count': r[1]} for r in rows]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email-logs-scheduled/<int:log_id>')
def api_email_log_scheduled_detail(log_id):
    """获取单条调度器邮件记录的完整内容（从 email_logs 中筛选 source='scheduled'）"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()

        conn = get_connection()
        cursor = conn.cursor()

        where_sql = "WHERE el.id = ? AND el.source = 'scheduled'"
        params = [log_id]
        if not admin and current_user_id:
            where_sql += " AND el.user_id = ?"
            params.append(current_user_id)

        cursor.execute(f'''
            SELECT el.id, el.customer_id, c.customer_name, el.email_id, e.email_address,
                   el.email_subject, el.email_content, el.send_status, el.error_message,
                   el.sent_at, el.task_id, el.source
            FROM email_logs el
            LEFT JOIN customers c ON el.customer_id = c.id
            LEFT JOIN emails e ON el.email_id = e.id
            {where_sql}
        ''', params)
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'success': False, 'error': '记录不存在'}), 404

        return jsonify({'success': True, 'data': {
            'log_id': row[0], 'customer_id': row[1], 'customer_name': row[2],
            'email_id': row[3], 'email_address': row[4], 'subject': row[5],
            'body': row[6], 'send_status': row[7], 'error_message': row[8],
            'sent_at': row[9], 'task_id': row[10], 'source': row[11]
        }})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/diagnostics/scheduled-logs')
@require_ajax
def api_diagnostics_scheduled_logs():
    """诊断API：检查email_logs中source='scheduled'的记录"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " AND el.user_id = ?"
            user_params = [current_user_id]

        # 总记录数
        cursor.execute(f'SELECT COUNT(*) FROM email_logs WHERE source = ?{user_where}', ('scheduled',) + tuple(user_params))
        total = cursor.fetchone()[0]

        # 最近10条记录
        cursor.execute(f'''
            SELECT el.id, el.customer_id, c.customer_name, el.email_id, e.email_address,
                   el.email_subject, el.send_status, el.sent_at, el.task_id
            FROM email_logs el
            LEFT JOIN customers c ON el.customer_id = c.id
            LEFT JOIN emails e ON el.email_id = e.id
            WHERE el.source = ?{user_where}
            ORDER BY el.sent_at DESC
            LIMIT 10
        ''', ('scheduled',) + tuple(user_params))
        rows = cursor.fetchall()
        conn.close()

        recent = []
        for r in rows:
            recent.append({
                'log_id': r[0], 'customer_id': r[1], 'customer_name': r[2],
                'email_id': r[3], 'email_address': r[4], 'subject': r[5],
                'send_status': r[6], 'sent_at': r[7], 'task_id': r[8]
            })

        return jsonify({
            'success': True,
            'total_scheduled_logs': total,
            'recent_logs': recent
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _parse_datetime(dt_str):
    """解析多种格式的时间字符串"""
    if not dt_str:
        return None
    formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']
    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


@app.route('/api/cooldown/status')
def api_cooldown_status():
    """获取冷却期状态概览（按公司维度）"""
    try:
        cooldown_days = scheduler_instance.config.get('cooldown_days', 7)
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = []
        co_where = ""
        co_params = []
        if not admin and current_user_id:
            user_where = " AND c.user_id = ? AND e.user_id = ?"
            user_params = [current_user_id, current_user_id]
            co_where = " AND (co.user_id IS NULL OR co.user_id = ?)"
            co_params = [current_user_id]

        # 统计总客户数（有活跃邮箱的客户）
        cursor.execute(f'''
            SELECT COUNT(DISTINCT e.customer_id) FROM emails e
            JOIN customers c ON e.customer_id = c.id
            WHERE e.is_active = 1{user_where}
        ''', user_params)
        total_customers = cursor.fetchone()[0]

        # 查询每个客户的最后发送时间（按公司维度），排除手动解除的
        cursor.execute(f'''
            SELECT c.id, c.customer_name, c.country,
                   COUNT(DISTINCT e.id) as email_count,
                   MAX(el.sent_at) as last_sent
            FROM customers c
            JOIN emails e ON c.id = e.customer_id AND e.is_active = 1
            LEFT JOIN email_logs el ON c.id = el.customer_id AND el.send_status = 'sent'
            WHERE c.id NOT IN (SELECT customer_id FROM cooldown_override co WHERE 1=1{co_where}){user_where}
            GROUP BY c.id
        ''', co_params + user_params)
        rows = cursor.fetchall()

        # 查询被手动解除的公司数量（用于统计，按用户隔离）
        if current_user_id and not admin:
            cursor.execute('SELECT COUNT(DISTINCT customer_id) FROM cooldown_override WHERE (user_id IS NULL OR user_id = ?)',
                           (current_user_id,))
        else:
            cursor.execute('SELECT COUNT(DISTINCT customer_id) FROM cooldown_override')
        released_count = cursor.fetchone()[0] or 0
        conn.close()

        cutoff = datetime.now() - timedelta(days=cooldown_days)
        in_cooldown = 0
        for _, _, _, email_count, last_sent in rows:
            if last_sent:
                dt = _parse_datetime(last_sent)
                if dt and dt >= cutoff:
                    in_cooldown += 1

        available = total_customers - in_cooldown
        return jsonify({
            'success': True,
            'data': {
                'cooldown_days': cooldown_days,
                'total_customers': total_customers,
                'in_cooldown_count': in_cooldown,
                'available_count': available
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cooldown/emails')
def api_cooldown_emails():
    """获取处于冷却期的公司列表，按国家→公司树状结构返回"""
    try:
        cooldown_days = scheduler_instance.config.get('cooldown_days', 7)
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " AND c.user_id = ? AND e.user_id = ?"
            user_params = [current_user_id, current_user_id]

        # 只查询处于冷却期的公司，排除手动解除的
        cursor.execute(f'''
            SELECT
                c.id as customer_id,
                c.customer_name,
                c.country,
                COUNT(DISTINCT e.id) as email_count,
                MAX(el.sent_at) as last_sent,
                COUNT(DISTINCT CASE WHEN el.send_status = 'sent' THEN el.id END) as sent_count
            FROM customers c
            JOIN emails e ON c.id = e.customer_id AND e.is_active = 1
            LEFT JOIN email_logs el ON c.id = el.customer_id AND el.send_status = 'sent'
            WHERE c.id NOT IN (SELECT customer_id FROM cooldown_override co WHERE 1=1{co_where}){user_where}
            GROUP BY c.id
            HAVING MAX(el.sent_at) >= datetime('now', ? || ' days')
            ORDER BY c.country, c.customer_name
        ''', co_params + user_params + [-cooldown_days])
        rows = cursor.fetchall()
        conn.close()

        # 按国家分组，构建树状结构（仅保留冷却天数>0的公司）
        tree = {}
        total = 0
        for row in rows:
            customer_id, customer_name, country, email_count, last_sent, sent_count = row
            dt = _parse_datetime(last_sent) if last_sent else None
            cooldown_end = dt + timedelta(days=cooldown_days)
            cooldown_end_str = cooldown_end.strftime('%Y-%m-%d %H:%M:%S')
            days_remaining = max(0, (cooldown_end - datetime.now()).days + 1)

            # 冷却期已过（天数<=0）的公司不显示
            if days_remaining <= 0:
                continue

            if country not in tree:
                tree[country] = []
            tree[country].append({
                'customer_id': customer_id,
                'customer_name': customer_name,
                'email_count': email_count,
                'sent_count': sent_count or 0,
                'last_sent': last_sent,
                'cooldown_end': cooldown_end_str,
                'days_remaining': days_remaining,
            })
            total += 1

        # 转换为有序列表格式
        countries = sorted(tree.keys())
        country_list = []
        for country in countries:
            country_list.append({
                'country': country,
                'companies': tree[country],
                'count': len(tree[country])
            })

        return jsonify({
            'success': True,
            'data': {
                'countries': country_list,
                'total': total,
                'country_count': len(countries),
                'cooldown_days': cooldown_days
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cooldown/release', methods=['POST'])
@require_ajax
def api_cooldown_release():
    """手动解除公司的冷却期"""
    try:
        data = request.json or {}
        customer_id = data.get('customer_id')
        if not customer_id:
            return jsonify({'success': False, 'error': '缺少客户ID'}), 400

        # 验证客户权限
        current_user_id = get_current_user_id()
        admin = is_admin()
        conn = get_connection()
        cursor = conn.cursor()
        if not admin and current_user_id:
            cursor.execute('SELECT id FROM customers WHERE id = ? AND user_id = ?', (customer_id, current_user_id))
        else:
            cursor.execute('SELECT id FROM customers WHERE id = ?', (customer_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': '客户不存在或无权限访问'}), 403

        cursor.execute('''
            INSERT INTO cooldown_override (customer_id, user_id, released_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (customer_id, current_user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'data': True, 'message': '冷却期已解除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send/test', methods=['POST'])
@require_ajax
def api_send_test():
    """发送测试邮件（异步）"""
    try:
        data = request.json or {}
        customer_id = data.get('customer_id')
        email_addresses = data.get('email_addresses', [])
        target_word_count = data.get('target_word_count')
        selected_material_ids = data.get('selected_material_ids')
        sender_material_id = data.get('sender_material_id')

        if not customer_id:
            return jsonify({'success': False, 'error': '缺少客户ID'}), 400

        # 验证客户权限
        current_user_id = get_current_user_id()
        admin = is_admin()
        conn_check = get_connection()
        cursor_check = conn_check.cursor()
        if not admin and current_user_id:
            cursor_check.execute('SELECT id FROM customers WHERE id = ? AND user_id = ?', (customer_id, current_user_id))
        else:
            cursor_check.execute('SELECT id FROM customers WHERE id = ?', (customer_id,))
        if not cursor_check.fetchone():
            conn_check.close()
            return jsonify({'success': False, 'error': '客户不存在或无权限访问'}), 403
        conn_check.close()

        # 发送配置
        send_config = {
            'interval_seconds': data.get('interval_seconds', 0),
            'auto_pause_after': data.get('auto_pause_after', 0),
            'max_retries': data.get('max_retries', 2),
            'pause_on_error': data.get('pause_on_error', False),
        }

        # 生成任务ID
        task_id = str(uuid.uuid4())[:8]

        # 初始化任务状态
        with send_tasks_lock:
            send_tasks[task_id] = {
                'id': task_id,
                'status': 'running',  # running / completed / failed
                'progress': 0,
                'current_step': '',
                'step_status': {step['id']: 'pending' for step in SEND_STEPS},
                'results': [],
                'email_preview': None,
                'error': None,
                'target_word_count': target_word_count,
                'selected_material_ids': selected_material_ids,
                'sender_material_id': sender_material_id,
                'send_config': send_config,
                'created_at': time.time()
            }

        # 持久化任务元数据
        current_user_id = get_current_user_id()
        persist_send_task_meta(
            task_id=task_id, task_type='manual', status='running',
            customer_id=customer_id,
            total_emails=len(email_addresses) if email_addresses else 0,
            step_status={step['id']: 'pending' for step in SEND_STEPS},
            send_config=send_config,
            user_id=current_user_id,
        )

        # 启动后台线程执行发送
        admin = is_admin()
        thread = threading.Thread(
            target=_do_send_email,
            args=(task_id, customer_id, email_addresses, current_user_id, admin),
            daemon=True
        )
        thread.start()

        return jsonify({'success': True, 'data': {'task_id': task_id}})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _update_task_step(task_id, step_id, status='running', message=''):
    """更新任务步骤状态"""
    with send_tasks_lock:
        if task_id not in send_tasks:
            return
        task = send_tasks[task_id]
        task['step_status'][step_id] = status
        task['current_step'] = SEND_STEPS[[s['id'] for s in SEND_STEPS].index(step_id)]['name'] if status == 'running' else ''

        # 使用 weight 加权计算进度
        total_weight = sum(s['weight'] for s in SEND_STEPS)
        completed_weight = sum(
            SEND_STEPS[[s['id'] for s in SEND_STEPS].index(sid)]['weight']
            for sid, st in task['step_status'].items()
            if st in ('completed', 'skipped')
        )
        task['progress'] = int((completed_weight / total_weight) * 100) if total_weight > 0 else 0


def _do_send_email(task_id, customer_id, email_addresses=None, user_id=None, admin=False):
    """后台执行邮件发送"""
    task = send_tasks.get(task_id)
    if not task:
        return

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 获取客户信息（带user_id验证，与主线程权限逻辑一致）
        if not admin and user_id:
            cursor.execute('SELECT customer_name, website FROM customers WHERE id = ? AND user_id = ?', (customer_id, user_id))
        else:
            cursor.execute('SELECT customer_name, website FROM customers WHERE id = ?', (customer_id,))
        row = cursor.fetchone()
        if not row:
            task['status'] = 'failed'
            task['error'] = '客户不存在或无权限'
            conn.close()
            return

        customer_name, website = row

        persist_send_task_meta(task_id, 'manual', 'running',
                               customer_id=customer_id, customer_name=customer_name,
                               user_id=user_id)

        # 获取邮箱列表（contact_name 在 contacts 表中）
        if email_addresses:
            placeholders = ','.join('?' * len(email_addresses))
            if user_id:
                cursor.execute(f'''
                    SELECT e.id, e.email_address, e.email_type, COALESCE(e.contact_name, c.contact_name) as contact_name
                    FROM emails e
                    LEFT JOIN contacts c ON e.contact_id = c.id
                    WHERE e.customer_id = ? AND e.user_id = ? AND e.is_active = 1
                      AND e.email_address IN ({placeholders})''', [customer_id, user_id] + email_addresses)
            else:
                cursor.execute(f'''
                    SELECT e.id, e.email_address, e.email_type, COALESCE(e.contact_name, c.contact_name) as contact_name
                    FROM emails e
                    LEFT JOIN contacts c ON e.contact_id = c.id
                    WHERE e.customer_id = ? AND e.is_active = 1
                      AND e.email_address IN ({placeholders})
            ''', [customer_id] + email_addresses)
        else:
            # 使用 current_user_id 确保隔离（admin 也应传 user_id）
            uid = current_user_id or user_id
            if uid:
                cursor.execute('''
                    SELECT e.id, e.email_address, e.email_type, COALESCE(e.contact_name, c.contact_name) as contact_name
                    FROM emails e
                    LEFT JOIN contacts c ON e.contact_id = c.id
                    WHERE e.customer_id = ? AND e.user_id = ? AND e.is_active = 1
                ''', (customer_id, uid))
            else:
                cursor.execute('''
                    SELECT e.id, e.email_address, e.email_type, COALESCE(e.contact_name, c.contact_name) as contact_name
                    FROM emails e
                    LEFT JOIN contacts c ON e.contact_id = c.id
                    WHERE e.customer_id = ? AND e.is_active = 1
                ''', (customer_id,))
        emails = cursor.fetchall()
        conn.close()

        if not emails:
            task['status'] = 'failed'
            task['error'] = '客户没有可用邮箱'
            return

        current_user_id = user_id or get_current_user_id()

        # 延迟导入避免循环
        from core.sender import EmailSender
        from generators.workflow import EmailWorkflow

        # 获取 sender_material_id：优先用 task 中已有的，否则从 selected_material_ids 中找 sender_info/personal_info
        sender_material_id = task.get('sender_material_id') if task else None
        if not sender_material_id:
            selected_material_ids = task.get('selected_material_ids') or []
            if selected_material_ids:
                try:
                    conn2 = get_connection()
                    cursor2 = conn2.cursor()
                    placeholders = ','.join('?' * len(selected_material_ids))
                    cursor2.execute(
                        f"SELECT id FROM materials WHERE id IN ({placeholders}) AND material_type IN ('sender_info','personal_info') AND is_active = 1",
                        selected_material_ids
                    )
                    row_sender = cursor2.fetchone()
                    if row_sender:
                        sender_material_id = row_sender[0]
                    conn2.close()
                except Exception as e:
                    print(f"[_do_send_email] sender_material_id 查找失败: {e}")

        current_user_id = get_current_user_id()
        sender = EmailSender(user_id=current_user_id)
        workflow = EmailWorkflow(user_id=current_user_id, sender_material_id=sender_material_id)

        # 生成邮件内容（传递进度回调，让工作流内部更新每个节点的进度）
        def on_progress(step_id, status):
            _update_task_step(task_id, step_id, status)

        selected_material_ids = task.get('selected_material_ids')
        num_subjects = task.get('num_subjects', 0)  # 0 = 自动决定
        email_content = workflow.generate_email(
            customer_name, website or '',
            progress_callback=on_progress,
            target_word_count=task.get('target_word_count'),
            selected_material_ids=selected_material_ids
        )

        # 保存邮件预览（full_text 包含问候语+正文+签名）
        task['email_preview'] = {
            'subject': email_content['subject'],
            'body': email_content.get('full_text', email_content['body']),
            'word_count': email_content.get('word_count', 0)
        }

        # 使用智能标题管理器：生成多个标题并随机分配给各个邮箱
        from generators.subjects.manager import subject_manager
        email_items_raw = []
        for email_row in emails:
            email_id, email_address, email_type, contact_name = email_row
            contact_name = contact_name or ''
            greeting = _make_greeting(email_type, contact_name, email_address, customer_name)
            email_items_raw.append({
                'email_id': email_id,
                'customer_id': customer_id,
                'email_address': email_address,
                'email_type': email_type,
                'contact_name': contact_name,
                'greeting': greeting,
            })

        if len(email_items_raw) > 1:
            subjects, assigned_items = subject_manager.generate_and_assign(
                customer_id=customer_id,
                customer_name=customer_name,
                country=country,
                industry='',
                email_items=email_items_raw,
                email_body=email_content['body'],  # 基于邮件内容生成标题
                num_subjects=num_subjects
            )
            print(f"[单发] 生成 {len(subjects)} 个标题，随机分配给 {len(email_items_raw)} 个邮箱")
        else:
            # 只有一个邮箱，直接用workflow生成的标题
            assigned_items = email_items_raw.copy()
            assigned_items[0]['subject'] = email_content['subject']

        # 组装最终邮件项
        email_items = []
        for item in assigned_items:
            email_items.append({
                'email_id': item['email_id'],
                'customer_id': customer_id,
                'email_address': item['email_address'],
                'email_type': item['email_type'],
                'contact_name': item['contact_name'],
                'greeting': item['greeting'],
                'subject': item.get('subject', email_content['subject']),
                'body': f"{item['greeting']}\n\n{email_content['body']}\n\n{email_content.get('signature', '')}",
                'user_id': current_user_id,
            })

        # 使用队列管理器发送
        send_config = task.get('send_config', {})
        print(f"  [发送任务] task_id={task_id}, 邮件数={len(email_items)}, greetings={[it['greeting'] for it in email_items]}", flush=True)

        persist_send_task_meta(task_id, 'manual', 'running',
                               customer_id=customer_id, customer_name=customer_name,
                               total_emails=len(email_items),
                               step_status=task.get('step_status', {}),
                               email_preview=task.get('email_preview'),
                               send_config=send_config,
                               user_id=user_id)

        # 写入日志文件确保能看到
        with open('send_queue.log', 'a', encoding='utf-8') as lf:
            lf.write(f"[{time.strftime('%H:%M:%S')}] _do_send_email: task_id={task_id}, 邮件数={len(email_items)}, config={send_config}\n")
            lf.flush()

        queue_manager.create_task(
            task_id, email_items, send_config,
            step_status=task.get('step_status', {}),
            email_preview=task['email_preview']
        )
        _update_task_step(task_id, 'send', 'running')
        queue_manager.start_task(task_id)

        # 不再阻塞等待发送完成，让发送线程独立运行
        # 前端通过 /api/send/status 轮询进度和结果

    except Exception as e:
        task['status'] = 'failed'
        task['error'] = str(e)
        import traceback
        traceback.print_exc()
        persist_send_task_meta(task_id, 'manual', 'failed', error=str(e), user_id=user_id)


@app.route('/api/send/tasks')
def api_send_tasks():
    """获取可恢复的发送任务列表"""
    try:
        with send_tasks_lock:
            memory_tasks = {tid: t['status'] for tid, t in send_tasks.items()}
        current_user_id = get_current_user_id()
        admin = is_admin()
        db_tasks = get_active_send_tasks(user_id=current_user_id, admin=admin)
        result = []
        for t in db_tasks:
            in_memory = memory_tasks.get(t['task_id']) == t['status']
            result.append({**t, 'in_memory': in_memory,
                          'can_pause': in_memory and t['status'] == 'running',
                          'can_resume': in_memory and t['status'] == 'paused',
                          'can_cancel': in_memory and t['status'] in ('running', 'paused')})
        return jsonify({'success': True, 'data': {'tasks': result}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send/tasks/<task_id>')
def api_send_task_detail(task_id):
    """获取单个任务详情（含邮件项）"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        # 先校验任务归属
        db_tasks = get_active_send_tasks(user_id=current_user_id, admin=admin)
        task_ids = [str(t['task_id']) for t in db_tasks]
        if not admin and task_id not in task_ids:
            return jsonify({'success': False, 'error': '无权访问此任务'}), 403
        qm_status = queue_manager.get_task_status(task_id)
        task = next((t for t in db_tasks if t['task_id'] == task_id), None)
        if not task:
            return jsonify({'success': False, 'error': '任务不存在'}), 404
        items = get_send_task_items(task_id, user_id=current_user_id, admin=admin)
        return jsonify({'success': True, 'data': {
            'id': task['task_id'], 'status': task['status'],
            'progress': task['progress'], 'current_step': task['current_step'],
            'step_status': task['step_status'],
            'email_preview': task['email_preview'], 'error': task['error'],
            'total_emails': task['total_emails'],
            'sent_count': task['sent_count'], 'failed_count': task['failed_count'],
            'current_index': task['current_index'], 'items': items,
            'can_pause': False, 'can_resume': False, 'can_cancel': False,
            'in_memory': False,
        }})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send/tasks/scheduled')
def api_send_tasks_scheduled():
    """获取调度发送任务记录（包括 scheduled、batch、test 类型）"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_user_id = get_current_user_id()
        admin = is_admin()

        user_where = ""
        user_params = []
        if not admin and current_user_id:
            user_where = " AND user_id = ?"
            user_params = [current_user_id]

        cursor.execute(f'''
            SELECT task_id, task_type, status, customer_name, total_emails, sent_count,
                   failed_count, progress, created_at, completed_at
            FROM send_tasks_meta
            WHERE task_type IN ('scheduled', 'batch', 'test')
               AND created_at > datetime('now', '-7 days'){user_where}
            ORDER BY created_at DESC LIMIT 50
        ''', user_params)
        rows = cursor.fetchall()
        conn.close()
        tasks = [{'task_id': r[0], 'task_type': r[1], 'status': r[2], 'customer_name': r[3],
                 'total_emails': r[4], 'sent_count': r[5], 'failed_count': r[6],
                 'progress': r[7], 'created_at': r[8], 'completed_at': r[9]}
                for r in rows]
        return jsonify({'success': True, 'data': {'tasks': tasks}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send/status/<task_id>')
def api_send_status(task_id):
    """查询发送任务状态（增强版：含单封邮件粒度）"""
    try:
        # 优先从队列管理器获取
        qm_status = queue_manager.get_task_status(task_id)
        if qm_status:
            return jsonify({'success': True, 'data': qm_status})

        with send_tasks_lock:
            task = send_tasks.get(task_id)
            if task:
                # 验证任务归属
                current_user_id = get_current_user_id()
                if 'user_id' in task and not is_admin() and current_user_id != task.get('user_id'):
                    return jsonify({'success': False, 'error': '无权访问该任务'}), 403
            if not task:
                # 数据库回退
                current_user_id = get_current_user_id()
                admin = is_admin()
                db_tasks = get_active_send_tasks(user_id=current_user_id, admin=admin)
                db_task = next((t for t in db_tasks if t['task_id'] == task_id), None)
                if not db_task:
                    return jsonify({'success': False, 'error': '任务不存在'}), 404
                items = get_send_task_items(task_id, user_id=current_user_id, admin=admin)
                return jsonify({
                    'success': True, 'data': {
                        'id': db_task['task_id'], 'status': db_task['status'],
                        'progress': db_task['progress'], 'current_step': db_task['current_step'],
                        'step_status': db_task['step_status'],
                        'email_preview': db_task['email_preview'],
                        'error': db_task['error'],
                        'total_emails': db_task['total_emails'],
                        'sent_count': db_task['sent_count'],
                        'failed_count': db_task['failed_count'],
                        'current_index': db_task['current_index'],
                        'items': items,
                        'can_pause': False, 'can_resume': False, 'can_cancel': False,
                        'in_memory': False,
                    }
                })

            # 清理过期的任务（30分钟后）
            if task['status'] in ('completed', 'failed') and time.time() - task['created_at'] > 1800:
                send_tasks.pop(task_id, None)
                return jsonify({'success': False, 'error': '任务已过期'}), 404

            return jsonify({
                'success': True,
                'data': {
                    'task_id': task['id'],
                    'status': task['status'],
                    'progress': task['progress'],
                    'current_step': task['current_step'],
                    'step_status': task['step_status'],
                    'results': task['results'],
                    'email_preview': task['email_preview'],
                    'error': task['error'],
                    'total_emails': len(task.get('results', [])),
                    'sent_count': sum(1 for r in task.get('results', []) if r.get('success')),
                    'failed_count': sum(1 for r in task.get('results', []) if not r.get('success')),
                    'items': [],
                    'can_pause': False,
                    'can_resume': False,
                    'can_cancel': False,
                }
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 发送控制 API ====================

@app.route('/api/send/<task_id>/pause', methods=['POST'])
@require_ajax
def api_send_pause(task_id):
    """暂停发送任务"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        if not admin and current_user_id:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM send_tasks_meta WHERE task_id = ?', (task_id,))
            row = cursor.fetchone()
            conn.close()
            if not row:
                return jsonify({'success': False, 'error': '任务不存在'}), 404
            if row[0] is not None and row[0] != current_user_id:
                return jsonify({'success': False, 'error': '无权操作此任务'}), 403
        success = queue_manager.pause_task(task_id)
        if success:
            persist_send_task_meta(task_id, 'manual', 'paused', user_id=current_user_id)
        return jsonify({'success': success, 'message': '已暂停' if success else '无法暂停'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/send/<task_id>/resume', methods=['POST'])
@require_ajax
def api_send_resume(task_id):
    """恢复发送任务"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        if not admin and current_user_id:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM send_tasks_meta WHERE task_id = ?', (task_id,))
            row = cursor.fetchone()
            conn.close()
            if not row:
                return jsonify({'success': False, 'error': '任务不存在'}), 404
            if row[0] is not None and row[0] != current_user_id:
                return jsonify({'success': False, 'error': '无权操作此任务'}), 403
        success = queue_manager.resume_task(task_id)
        if success:
            persist_send_task_meta(task_id, 'manual', 'running', user_id=current_user_id)
        return jsonify({'success': success, 'message': '已恢复' if success else '无法恢复'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/send/<task_id>/cancel', methods=['POST'])
@require_ajax
def api_send_cancel(task_id):
    """取消发送任务"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        if not admin and current_user_id:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM send_tasks_meta WHERE task_id = ?', (task_id,))
            row = cursor.fetchone()
            conn.close()
            if not row:
                return jsonify({'success': False, 'error': '任务不存在'}), 404
            if row[0] is not None and row[0] != current_user_id:
                return jsonify({'success': False, 'error': '无权操作此任务'}), 403
        success = queue_manager.cancel_task(task_id)
        if success:
            persist_send_task_meta(task_id, 'manual', 'cancelled', user_id=current_user_id)
        return jsonify({'success': success, 'message': '已取消' if success else '无法取消'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email/polish', methods=['POST'])
@require_ajax
def api_email_polish():
    """独立邮件润色：对已有邮件内容进行LLM润色精修"""
    try:
        data = request.json or {}
        subject = data.get('subject', '').strip()
        body = data.get('body', '').strip()
        target_word_count = data.get('target_word_count')
        customer_name = data.get('customer_name', '')

        if not body:
            return jsonify({'success': False, 'error': '邮件正文不能为空'}), 400

        current_user_id = get_current_user_id()
        from services.llm_client import LLMEmailClient
        llm = LLMEmailClient(user_id=current_user_id)

        result = llm.refine_email(
            subject=subject,
            body=body,
            target_word_count=target_word_count,
            customer_name=customer_name
        )

        if result.get('error'):
            return jsonify({'success': False, 'error': result['error']}), 500

        return jsonify({
            'success': True,
            'data': {
                'subject': result.get('subject', subject),
                'body': result.get('body', body),
                'word_count': len(result.get('body', '').split())
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email/format', methods=['POST'])
@require_ajax
def api_email_format():
    """独立邮件排版：仅调整段落结构，不删改内容"""
    try:
        data = request.json or {}
        body = data.get('body', '').strip()

        if not body:
            return jsonify({'success': False, 'error': '邮件正文不能为空'}), 400

        current_user_id = get_current_user_id()
        from services.llm_client import LLMEmailClient
        llm = LLMEmailClient(user_id=current_user_id)

        # 排版不需要传 target_words，排版不应改变字数
        result = llm.format_email(body=body)

        if result.get('error'):
            return jsonify({'success': False, 'error': result['error']}), 500

        formatted_body = result.get('body', body)

        return jsonify({
            'success': True,
            'data': {
                'body': formatted_body,
                'word_count': len(formatted_body.split())
            }
        })

        return jsonify({
            'success': True,
            'data': {
                'body': formatted_body,
                'word_count': len(formatted_body.split())
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email/preview', methods=['POST'])
@require_ajax
def api_email_preview():
    """仅生成邮件内容预览，不发送"""
    try:
        data = request.json or {}
        customer_id = data.get('customer_id')
        target_word_count = data.get('target_word_count')
        selected_material_ids = data.get('selected_material_ids')
        sender_material_id = data.get('sender_material_id')

        if not customer_id:
            return jsonify({'success': False, 'error': '缺少客户ID'}), 400

        # 验证客户权限
        current_user_id = get_current_user_id()
        admin = is_admin()
        conn_check = get_connection()
        cursor_check = conn_check.cursor()
        if not admin and current_user_id:
            cursor_check.execute('SELECT id FROM customers WHERE id = ? AND user_id = ?', (customer_id, current_user_id))
        else:
            cursor_check.execute('SELECT id FROM customers WHERE id = ?', (customer_id,))
        if not cursor_check.fetchone():
            conn_check.close()
            return jsonify({'success': False, 'error': '客户不存在或无权限访问'}), 403
        conn_check.close()

        # 生成任务ID
        task_id = str(uuid.uuid4())[:8]

        # 初始化任务状态
        with send_tasks_lock:
            send_tasks[task_id] = {
                'id': task_id,
                'status': 'running',
                'progress': 0,
                'current_step': '',
                'step_status': {step['id']: 'pending' for step in SEND_STEPS},
                'results': [],
                'email_preview': None,
                'error': None,
                'target_word_count': target_word_count,
                'selected_material_ids': selected_material_ids,
                'sender_material_id': sender_material_id,
                'created_at': time.time()
            }

        # 启动后台线程生成邮件
        current_user_id = get_current_user_id()
        admin = is_admin()
        thread = threading.Thread(
            target=_do_generate_preview,
            args=(task_id, customer_id, current_user_id, admin),
            daemon=True
        )
        thread.start()

        return jsonify({'success': True, 'data': {'task_id': task_id}})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _do_generate_preview(task_id, customer_id, user_id=None, admin=False):
    """后台生成邮件预览内容"""
    task = send_tasks.get(task_id)
    if not task:
        return

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 获取客户信息（带user_id验证，与主线程权限逻辑一致）
        if not admin and user_id:
            cursor.execute('SELECT customer_name, website FROM customers WHERE id = ? AND user_id = ?', (customer_id, user_id))
        else:
            cursor.execute('SELECT customer_name, website FROM customers WHERE id = ?', (customer_id,))
        row = cursor.fetchone()
        if not row:
            task['status'] = 'failed'
            task['error'] = '客户不存在或无权限'
            conn.close()
            return

        customer_name, website = row

        # 获取 sender_material_id：优先用 task 中已有的，否则从 selected_material_ids 中找 sender_info/personal_info
        sender_material_id = task.get('sender_material_id')
        if not sender_material_id:
            selected_material_ids = task.get('selected_material_ids') or []
            if selected_material_ids:
                placeholders = ','.join('?' * len(selected_material_ids))
                cursor.execute(
                    f"SELECT id FROM materials WHERE id IN ({placeholders}) AND material_type IN ('sender_info','personal_info') AND is_active = 1",
                    selected_material_ids
                )
                row_sender = cursor.fetchone()
                if row_sender:
                    sender_material_id = row_sender[0]

        conn.close()

        # 延迟导入避免循环
        from generators.workflow import EmailWorkflow
        workflow = EmailWorkflow(user_id=user_id, sender_material_id=sender_material_id, is_admin=admin)

        # 生成邮件内容
        def on_progress(step_id, status):
            _update_task_step(task_id, step_id, status)

        selected_material_ids = task.get('selected_material_ids')
        email_content = workflow.generate_email(
            customer_name, website or '',
            progress_callback=on_progress,
            target_word_count=task.get('target_word_count'),
            selected_material_ids=selected_material_ids
        )

        # 保存邮件预览（full_text 包含问候语+正文+签名）
        task['email_preview'] = {
            'subject': email_content['subject'],
            'body': email_content.get('full_text', email_content['body']),
            'html': email_content.get('html', ''),
            'word_count': email_content.get('word_count', 0),
            'customer_name': customer_name
        }

        # 标记生成完成（但不标记 send 步骤）
        task['status'] = 'completed'
        task['progress'] = 100

    except Exception as e:
        task['status'] = 'failed'
        task['error'] = str(e)
        import traceback
        traceback.print_exc()


@app.route('/api/email/send', methods=['POST'])
@require_ajax
def api_email_send():
    """发送用户编辑后的邮件"""
    try:
        data = request.json or {}
        customer_id = data.get('customer_id')
        email_addresses = data.get('email_addresses', [])
        subject = data.get('subject', '')
        body = data.get('body', '')

        if not customer_id:
            return jsonify({'success': False, 'error': '缺少客户ID'}), 400
        if not subject or not body:
            return jsonify({'success': False, 'error': '邮件主题和正文不能为空'}), 400
        if not email_addresses:
            return jsonify({'success': False, 'error': '请至少选择一个邮箱'}), 400

        # 发送配置
        send_config = {
            'interval_seconds': data.get('interval_seconds', 0),
            'auto_pause_after': data.get('auto_pause_after', 0),
            'max_retries': data.get('max_retries', 2),
            'pause_on_error': data.get('pause_on_error', False),
        }

        # 生成任务ID
        task_id = str(uuid.uuid4())[:8]

        # 初始化任务状态
        with send_tasks_lock:
            send_tasks[task_id] = {
                'id': task_id,
                'status': 'running',
                'progress': 0,
                'current_step': 'SMTP发送',
                'step_status': {'send': 'running'},
                'results': [],
                'email_preview': {'subject': subject, 'body': body},
                'error': None,
                'send_config': send_config,
                'created_at': time.time()
            }

        current_user_id = get_current_user_id()
        persist_send_task_meta(
            task_id=task_id, task_type='manual', status='running',
            customer_id=customer_id,
            total_emails=len(email_addresses),
            step_status={'send': 'running'},
            email_preview={'subject': subject, 'body': body},
            send_config=send_config,
            user_id=current_user_id,
        )

        # 启动后台线程执行发送
        admin = is_admin()
        thread = threading.Thread(
            target=_do_send_custom_email,
            args=(task_id, customer_id, email_addresses, subject, body, current_user_id, admin),
            daemon=True
        )
        thread.start()

        return jsonify({'success': True, 'data': {'task_id': task_id}})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _do_send_custom_email(task_id, customer_id, email_addresses, subject, body, user_id=None, admin=False):
    """后台发送用户自定义内容的邮件（使用队列管理器）"""
    task = send_tasks.get(task_id)
    if not task:
        return

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 获取客户信息（带user_id验证，admin可访问所有客户）
        if not admin and user_id:
            cursor.execute('SELECT customer_name FROM customers WHERE id = ? AND user_id = ?', (customer_id, user_id))
        else:
            cursor.execute('SELECT customer_name FROM customers WHERE id = ?', (customer_id,))
        row = cursor.fetchone()
        if not row:
            task['status'] = 'failed'
            task['error'] = '客户不存在或无权限'
            conn.close()
            return

        customer_name = row[0]

        persist_send_task_meta(task_id, 'manual', 'running',
                               customer_id=customer_id, customer_name=customer_name,
                               user_id=user_id)

        # 获取邮箱列表
        placeholders = ','.join('?' * len(email_addresses))
        if not admin and user_id:
            cursor.execute(f'''
                SELECT e.id, e.email_address, e.email_type, COALESCE(e.contact_name, c.contact_name) as contact_name
                FROM emails e
                LEFT JOIN contacts c ON e.contact_id = c.id
                WHERE e.customer_id = ? AND e.user_id = ? AND e.is_active = 1
                  AND e.email_address IN ({placeholders})
            ''', [customer_id, user_id] + email_addresses)
        else:
            cursor.execute(f'''
                SELECT e.id, e.email_address, e.email_type, COALESCE(e.contact_name, c.contact_name) as contact_name
                FROM emails e
                LEFT JOIN contacts c ON e.contact_id = c.id
                WHERE e.customer_id = ? AND e.is_active = 1
                  AND e.email_address IN ({placeholders})
            ''', [customer_id] + email_addresses)
        emails = cursor.fetchall()
        conn.close()

        if not emails:
            task['status'] = 'failed'
            task['error'] = '没有可用的邮箱'
            return

        current_user_id = user_id or get_current_user_id()

        # 构建邮件项列表
        email_items = []
        for email_row in emails:
            email_id, email_address, email_type, contact_name = email_row
            contact_name = contact_name or ''

            greeting = _make_greeting(email_type, contact_name, email_address, customer_name)

            email_items.append({
                'email_id': email_id,
                'customer_id': customer_id,
                'email_address': email_address,
                'email_type': email_type,
                'contact_name': contact_name,
                'greeting': greeting,
                'subject': subject,
                'body': body,
                'user_id': current_user_id,
            })

        # 使用队列管理器发送
        send_config = task.get('send_config', {})
        queue_manager.create_task(
            task_id, email_items, send_config,
            step_status=task.get('step_status', {}),
            email_preview=task.get('email_preview')
        )
        queue_manager.start_task(task_id)

        # 等待发送完成
        while True:
            qt = queue_manager.get_task(task_id)
            if not qt:
                break
            if qt.status in ('completed', 'failed', 'cancelled'):
                break
            time.sleep(0.5)

        # 同步结果回 send_tasks
        qt = queue_manager.get_task(task_id)
        if qt:
            with send_tasks_lock:
                task['status'] = qt.status
                task['progress'] = 100 if qt.status == 'completed' else qt.progress
                task['error'] = qt.error
                task['results'] = [
                    {'email': item.email_address, 'success': item.status == 'sent',
                     'greeting': item.greeting, 'subject': item.subject,
                     'message': item.error_message or '发送成功'}
                    for item in qt.items
                ]
            _update_task_step(task_id, 'send', 'completed' if qt.status == 'completed' else 'failed')
            persist_send_task_meta(
                task_id, 'manual', qt.status,
                customer_id=customer_id, customer_name=customer_name,
                total_emails=len(qt.items),
                sent_count=sum(1 for i in qt.items if i.status == 'sent'),
                failed_count=sum(1 for i in qt.items if i.status == 'failed'),
                progress=100 if qt.status == 'completed' else qt.progress,
                step_status=task.get('step_status', {}),
                email_preview=task.get('email_preview'),
                send_config=send_config,
                error=qt.error,
                user_id=user_id,
            )

    except Exception as e:
        task['status'] = 'failed'
        task['error'] = str(e)
        import traceback
        traceback.print_exc()
        persist_send_task_meta(task_id, 'manual', 'failed', error=str(e), user_id=user_id)


@app.route('/api/config')
def api_config():
    """获取系统配置（按用户隔离）"""
    try:
        current_user_id = get_current_user_id()

        # 严格按用户隔离读取，不回退到全局JSON文件
        user_settings = get_all_user_settings(current_user_id) if current_user_id else {}

        smtp_config = user_settings.get('smtp') or {}
        company_config = user_settings.get('company') or {}
        llm_config = user_settings.get('llm') or {}
        imap_config = user_settings.get('imap') or {}

        # 隐藏密码
        smtp_config['password'] = '****'
        if imap_config.get('password'):
            imap_config['password'] = '****'

        # 隐藏 API Key
        if llm_config.get('api_key'):
            llm_config['api_key_masked'] = llm_config['api_key'][:8] + '****'
        else:
            llm_config['api_key_masked'] = ''

        # 读取调度器配置
        scheduler_config = user_settings.get('scheduler')
        scheduler_send_interval = 120
        scheduler_cooldown_days = 7
        if isinstance(scheduler_config, dict):
            scheduler_send_interval = scheduler_config.get('send_interval', 120)
            scheduler_cooldown_days = scheduler_config.get('cooldown_days', 7)
        else:
            scheduler_config_path = os.path.join(os.path.dirname(__file__), 'config', 'scheduler_config.json')
            if os.path.exists(scheduler_config_path):
                try:
                    with open(scheduler_config_path, 'r', encoding='utf-8') as f:
                        scheduler_cfg = json.load(f)
                        scheduler_send_interval = scheduler_cfg.get('send_interval', 120)
                        scheduler_cooldown_days = scheduler_cfg.get('cooldown_days', 7)
                except Exception:
                    pass

        return jsonify({
            'success': True,
            'data': {
                'smtp': smtp_config,
                'company': company_config,
                'llm': llm_config,
                'imap': imap_config,
                'db_path': os.path.join(os.path.dirname(__file__), 'email_automation.db'),
                'send_interval': scheduler_send_interval,
                'cooldown_days': scheduler_cooldown_days,
                'subjects_per_customer': 5
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
@require_ajax
def api_config_update():
    """更新系统配置（SMTP、公司信息、调度器），按用户隔离"""
    try:
        data = request.json or {}
        config_type = data.get('type')  # 'smtp' 或 'company' 或 'llm' 或 'scheduler'
        config_data = data.get('data', {})
        current_user_id = get_current_user_id()

        if config_type not in ('smtp', 'company', 'llm', 'scheduler', 'imap'):
            return jsonify({'success': False, 'error': '无效的配置类型'}), 400

        # 严格按用户隔离读取已有配置
        existing = get_user_setting(current_user_id, config_type) or {}

        if config_type == 'smtp':
            # 如果前端密码为 **** 或空，保留原密码
            if config_data.get('password') in ('****', '', None):
                config_data['password'] = existing.get('password', '')
        elif config_type == 'imap':
            # 同样处理 IMAP 密码
            if config_data.get('password') in ('****', '', None):
                config_data['password'] = existing.get('password', '')
        elif config_type == 'llm':
            # 保留现有 API Key（如果前端未提供或为空）
            if not config_data.get('api_key'):
                config_data['api_key'] = existing.get('api_key', '')
        elif config_type == 'scheduler':
            # 合并现有配置
            config_data = {**existing, **config_data}

        # 保存到用户隔离表
        save_user_setting(current_user_id, config_type, config_data)

        # 更新调度器实例的内存配置
        if config_type == 'scheduler' and scheduler_instance:
            scheduler_instance.config = config_data

        return jsonify({'success': True, 'message': '配置已更新', 'data': config_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 资料管理 API ====================

from database.material_models import (
    get_materials_list, get_material_by_id, create_material, update_material,
    delete_material, get_material_types, get_material_categories, get_material_tracks,
    get_material_stats, update_attachment, remove_attachment, invalidate_cache
)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads', 'materials')
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'xls', 'xlsx'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/materials')
@require_ajax
def api_materials_list():
    """获取资料列表"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        material_type = request.args.get('type') or None
        category = request.args.get('category') or None
        scope = request.args.get('scope') or None
        track = request.args.get('track') or None
        region = request.args.get('region') or None
        search = request.args.get('search') or None
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        current_user_id = get_current_user_id()
        admin = is_admin()

        tag = request.args.get('tag') or None

        result = get_materials_list(
            material_type=material_type, category=category, scope=scope,
            track=track, region=region, search=search, tag=tag, active_only=active_only,
            page=page, per_page=per_page,
            user_id=current_user_id, admin=admin
        )
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/materials/<int:material_id>')
@require_ajax
def api_material_detail(material_id):
    """获取单个资料详情"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        material = get_material_by_id(material_id, user_id=current_user_id, admin=admin)
        if not material:
            return jsonify({'success': False, 'error': '资料不存在'}), 404
        return jsonify({'success': True, 'data': material})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/materials', methods=['POST'])
@require_ajax
def api_material_create():
    """创建新资料"""
    try:
        data = request.json or {}
        if not data.get('material_key') or not data.get('name') or not data.get('material_type'):
            return jsonify({'success': False, 'error': '缺少必填字段'}), 400

        current_user_id = get_current_user_id()
        material_id = create_material(data, user_id=current_user_id)
        return jsonify({'success': True, 'message': '资料创建成功', 'data': {'id': material_id}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/materials/<int:material_id>', methods=['PUT'])
@require_ajax
def api_material_update(material_id):
    """更新资料"""
    try:
        data = request.json or {}
        current_user_id = get_current_user_id()
        admin = is_admin()
        update_material(material_id, data, user_id=current_user_id, admin=admin)
        return jsonify({'success': True, 'data': {'updated': True}, 'message': '资料更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/materials/<int:material_id>', methods=['DELETE'])
@require_ajax
def api_material_delete(material_id):
    """删除资料"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        delete_material(material_id, user_id=current_user_id, admin=admin)
        return jsonify({'success': True, 'data': {'deleted': True}, 'message': '资料删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/materials/types')
@require_ajax
def api_material_types():
    """获取资料类型枚举"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        types = get_material_types(user_id=current_user_id, admin=admin)
        return jsonify({'success': True, 'data': types})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/materials/categories')
@require_ajax
def api_material_categories():
    """获取分类列表（按用户隔离）"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        categories = get_material_categories(user_id=current_user_id, admin=admin)
        return jsonify({'success': True, 'data': categories})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/materials/tracks')
@require_ajax
def api_material_tracks():
    """获取赛道标签列表（按用户隔离）"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        tracks = get_material_tracks(user_id=current_user_id, admin=admin)
        return jsonify({'success': True, 'data': tracks})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/materials/stats')
@require_ajax
def api_material_stats():
    """获取资料库统计"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        stats = get_material_stats(user_id=current_user_id, admin=admin)
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/materials/<int:material_id>/upload', methods=['POST'])
@require_ajax
def api_material_upload(material_id):
    """上传文件附件"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '未上传文件'}), 400

        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'success': False, 'error': '未选择文件'}), 400

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': '不支持的文件类型'}), 400

        current_user_id = get_current_user_id()
        admin = is_admin()
        material = get_material_by_id(material_id, user_id=current_user_id, admin=admin)
        if not material:
            return jsonify({'success': False, 'error': '资料不存在'}), 404

        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{material_id}_{uuid.uuid4().hex[:8]}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        rel_path = f"uploads/materials/{filename}"
        update_attachment(material_id, rel_path, ext, file.filename)

        return jsonify({
            'success': True,
            'message': '文件上传成功',
            'data': {'attachment_path': rel_path, 'attachment_type': ext, 'attachment_name': file.filename}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/materials/<int:material_id>/upload', methods=['DELETE'])
@require_ajax
def api_material_remove_upload(material_id):
    """删除文件附件"""
    try:
        current_user_id = get_current_user_id()
        admin = is_admin()
        material = get_material_by_id(material_id, user_id=current_user_id, admin=admin)
        if not material:
            return jsonify({'success': False, 'error': '资料不存在'}), 404

        if material.get('attachment_path'):
            full_path = os.path.join(os.path.dirname(__file__), material['attachment_path'])
            if os.path.exists(full_path):
                os.remove(full_path)

        remove_attachment(material_id)
        return jsonify({'success': True, 'message': '附件已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _check_ai_rate_limit(ip_address: str) -> tuple:
    """检查AI分析API速率限制。返回 (允许, 错误信息)"""
    with ai_rate_limits_lock:
        now = time.time()
        window_start = now - 60
        # 获取该IP在60秒内的请求记录
        requests = ai_rate_limits.get(ip_address, [])
        requests = [t for t in requests if t > window_start]
        if len(requests) >= MAX_AI_REQUESTS_PER_MINUTE:
            return False, f'请求过于频繁，请稍后再试（每IP每分钟最多{MAX_AI_REQUESTS_PER_MINUTE}次）'
        requests.append(now)
        ai_rate_limits[ip_address] = requests
        return True, None


# ==================== AI 素材分析导入 API ====================

@app.route('/api/materials/analyze', methods=['POST'])
@require_ajax
def api_materials_analyze():
    """AI分析文件，返回预览列表（不入库，供用户确认后导入）"""
    try:
        from services.ai_material_analyzer import AIMaterialAnalyzer, SUPPORTED_EXTENSIONS

        files = request.files.getlist('files') or request.files.getlist('file')
        if not files or not any(f.filename for f in files):
            return jsonify({'success': False, 'error': '未上传文件'}), 400

        # 验证文件
        valid_files = []
        errors = []
        for f in files:
            if not f.filename:
                continue
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                errors.append(f'{f.filename}: 不支持的格式 {ext}')
                continue
            file_bytes = f.read()
            if len(file_bytes) > 20 * 1024 * 1024:
                errors.append(f'{f.filename}: 超过20MB限制')
                continue
            if len(file_bytes.strip()) == 0:
                errors.append(f'{f.filename}: 文件为空')
                continue
            valid_files.append({'bytes': file_bytes, 'filename': f.filename})

        if not valid_files:
            return jsonify({
                'success': False,
                'error': '没有有效的文件',
                'errors': errors
            }), 400

        # 速率限制检查
        ip = request.remote_addr or 'unknown'
        allowed, msg = _check_ai_rate_limit(ip)
        if not allowed:
            return jsonify({'success': False, 'error': msg}), 429

        analyzer = AIMaterialAnalyzer()
        if not analyzer.is_available():
            return jsonify({'success': False, 'error': 'AI 服务未配置，请检查 API Key'}), 503

        # 分析所有文件，返回预览列表
        previews = []
        for f in valid_files:
            result = analyzer.analyze_file(f['bytes'], f['filename'])
            if result.get('success'):
                analysis = result['analysis']
                previews.append({
                    'filename': f['filename'],
                    'suggested_type': analysis.get('material_type', 'other'),
                    'material_type': analysis.get('material_type_mapped', 'advantage'),
                    'name': analysis.get('name', os.path.splitext(f['filename'])[0]),
                    'summary': analysis.get('summary', ''),
                    'scope': analysis.get('scope', 'all'),
                    'track': analysis.get('track', ''),
                    'region': analysis.get('region', ''),
                    'structured_content': analysis.get('structured_content', {}),
                    'confidence': analysis.get('confidence', 0),
                    'tags': analysis.get('tags', []),
                    'priority': analysis.get('priority', 3),
                    'raw_analysis': analysis
                })
            else:
                errors.append(f"{f['filename']}: {result.get('error', '分析失败')}")

        return jsonify({
            'success': True,
            'data': {
                'previews': previews,
                'total': len(previews),
                'errors': errors if errors else None
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/materials/import', methods=['POST'])
@require_ajax
def api_materials_import():
    """将AI分析结果导入素材库（保留旧版接口，传入user_id）"""
    try:
        from services.ai_material_analyzer import AIMaterialAnalyzer, SUPPORTED_EXTENSIONS

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '未上传文件'}), 400

        file = request.files['file']
        overwrite = request.form.get('overwrite', 'false').lower() == 'true'

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return jsonify({'success': False, 'error': f'不支持的文件格式: {ext}'}), 400

        file_bytes = file.read()
        if len(file_bytes) > 20 * 1024 * 1024:
            return jsonify({'success': False, 'error': '文件大小超过20MB限制'}), 400

        # 速率限制检查
        ip = request.remote_addr or 'unknown'
        allowed, msg = _check_ai_rate_limit(ip)
        if not allowed:
            return jsonify({'success': False, 'error': msg}), 429

        analyzer = AIMaterialAnalyzer()
        if not analyzer.is_available():
            return jsonify({'success': False, 'error': 'AI 服务未配置，请检查 API Key'}), 503

        # 分析 + 导入
        analysis_result = analyzer.analyze_file(file_bytes, file.filename)
        if not analysis_result['success']:
            return jsonify({
                'success': False,
                'error': analysis_result.get('error', '分析失败'),
                'analysis': analysis_result
            })

        current_user_id = get_current_user_id()
        import_result = analyzer.import_analyzed_material(
            analysis_result,
            source_file=file.filename,
            overwrite=overwrite,
            user_id=current_user_id or None
        )

        return jsonify({
            'success': import_result['success'],
            'analysis': analysis_result,
            'import': import_result
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/materials/analyze/confirm', methods=['POST'])
@require_ajax
def api_materials_analyze_confirm():
    """用户确认AI分析预览后，批量正式导入素材库"""
    try:
        from services.ai_material_analyzer import AIMaterialAnalyzer

        data = request.get_json(silent=True) or {}
        previews = data.get('previews', [])

        if not previews:
            return jsonify({'success': False, 'error': '未提供预览数据'}), 400

        current_user_id = get_current_user_id()
        analyzer = AIMaterialAnalyzer()
        results = []
        imported = 0
        skipped = 0
        failed = 0

        for preview in previews:
            try:
                # 构造 analysis_result 格式复用现有导入逻辑
                analysis_result = {
                    'success': True,
                    'filename': preview.get('filename', ''),
                    'analysis': preview.get('raw_analysis', preview)
                }
                # 用用户修改后的字段覆盖
                if preview.get('name'):
                    analysis_result['analysis']['name'] = preview['name']
                if preview.get('material_type'):
                    analysis_result['analysis']['material_type'] = preview['material_type']
                if preview.get('summary'):
                    analysis_result['analysis']['summary'] = preview['summary']
                if preview.get('scope'):
                    analysis_result['analysis']['scope'] = preview['scope']
                if preview.get('track'):
                    analysis_result['analysis']['track'] = preview['track']
                if preview.get('region'):
                    analysis_result['analysis']['region'] = preview['region']
                if preview.get('priority') is not None:
                    analysis_result['analysis']['priority'] = preview['priority']

                res = analyzer.import_analyzed_material(
                    analysis_result,
                    source_file=preview.get('filename'),
                    user_id=current_user_id or None
                )
                results.append(res)
                if res['action'] == 'created':
                    imported += 1
                elif res['action'] == 'skipped':
                    skipped += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                results.append({
                    'success': False,
                    'material_id': None,
                    'action': 'error',
                    'message': str(e)
                })

        return jsonify({
            'success': True,
            'data': {
                'results': results,
                'imported': imported,
                'skipped': skipped,
                'failed': failed
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/materials/batch-import', methods=['POST'])
@require_ajax
def api_materials_batch_import():
    """批量AI分析并导入多个文件"""
    try:
        from services.ai_material_analyzer import (
            AIMaterialAnalyzer, SUPPORTED_EXTENSIONS,
            create_import_task, update_import_task
        )

        files = request.files.getlist('files')
        if not files:
            return jsonify({'success': False, 'error': '未上传文件'}), 400

        overwrite = request.form.get('overwrite', 'false').lower() == 'true'
        current_user_id = get_current_user_id()

        # 验证文件
        valid_files = []
        errors = []
        for f in files:
            if not f.filename:
                continue
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                errors.append(f'{f.filename}: 不支持的格式 {ext}')
                continue
            file_bytes = f.read()
            if len(file_bytes) > 20 * 1024 * 1024:
                errors.append(f'{f.filename}: 超过20MB限制')
                continue
            if len(file_bytes.strip()) == 0:
                errors.append(f'{f.filename}: 文件为空')
                continue
            valid_files.append({'bytes': file_bytes, 'filename': f.filename})

        if not valid_files:
            return jsonify({
                'success': False,
                'error': '没有有效的文件',
                'errors': errors
            }), 400

        # 创建导入任务
        task_id = create_import_task(f'批量AI导入_{len(valid_files)}个文件')
        update_import_task(task_id, status='processing', total_files=len(valid_files),
                           started_at=time.strftime('%Y-%m-%d %H:%M:%S'))

        # 异步执行批量分析导入
        def _run_batch_import():
            analyzer = AIMaterialAnalyzer()
            imported = 0
            skipped = 0
            failed = 0
            error_details = []

            for idx, f in enumerate(valid_files):
                try:
                    result = analyzer.analyze_file(f['bytes'], f['filename'])
                    if not result['success']:
                        failed += 1
                        error_details.append(f"{f['filename']}: {result.get('error', '分析失败')}")
                        update_import_task(task_id, processed_files=idx + 1,
                                           failed_count=failed, error_details='\n'.join(error_details[-20:]))
                        time.sleep(1)
                        continue

                    import_res = analyzer.import_analyzed_material(
                        result, source_file=f['filename'], overwrite=overwrite,
                        user_id=current_user_id or None
                    )
                    if import_res['action'] == 'created':
                        imported += 1
                    elif import_res['action'] == 'skipped':
                        skipped += 1
                    else:
                        failed += 1
                        error_details.append(f"{f['filename']}: {import_res.get('message', '')}")

                    update_import_task(task_id, processed_files=idx + 1,
                                       imported_count=imported, skipped_count=skipped,
                                       failed_count=failed, error_details='\n'.join(error_details[-20:]))
                except Exception as e:
                    failed += 1
                    error_details.append(f"{f['filename']}: {str(e)}")
                    update_import_task(task_id, processed_files=idx + 1,
                                       failed_count=failed, error_details='\n'.join(error_details[-20:]))

                # API调用间隔
                time.sleep(1)

            update_import_task(task_id, status='completed',
                               completed_at=time.strftime('%Y-%m-%d %H:%M:%S'))

        thread = threading.Thread(target=_run_batch_import, daemon=True)
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'total_files': len(valid_files),
            'errors': errors if errors else None
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/materials/batch-status/<int:task_id>')
@require_ajax
def api_materials_batch_status(task_id):
    """查询批量导入任务状态"""
    try:
        from services.ai_material_analyzer import get_import_task

        task = get_import_task(task_id)
        if not task:
            return jsonify({'success': False, 'error': '任务不存在'}), 404

        return jsonify({
            'success': True,
            'task': task
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/materials/selector')
@require_ajax
def api_materials_selector():
    """获取精简版资料列表，供发送页选择器使用"""
    try:
        from database.material_models import get_materials_list

        current_user_id = get_current_user_id()
        admin = is_admin()

        result = get_materials_list(
            active_only=True, page=1, per_page=500,
            user_id=current_user_id, admin=admin
        )

        simplified = []
        for m in result['materials']:
            simplified.append({
                'id': m['id'],
                'name': m['name'],
                'material_key': m['material_key'],
                'material_type': m['material_type'],
                'summary': m['content_summary']
            })

        return jsonify({
            'success': True,
            'data': simplified,
            'total': len(simplified)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/materials/<int:material_id>/content')
@require_ajax
def api_material_content(material_id):
    """获取单个素材的完整 content_json"""
    try:
        from database.material_models import get_material_by_id

        current_user_id = get_current_user_id()
        admin = is_admin()

        material = get_material_by_id(material_id, user_id=current_user_id, admin=admin)
        if not material:
            return jsonify({'success': False, 'error': '素材不存在或无权限'}), 404

        return jsonify({
            'success': True,
            'data': material
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/materials/sender-info/list', methods=['GET'])
@require_ajax
def api_materials_sender_info_list():
    """获取所有发信人模板列表"""
    try:
        from materials.sender_info_service import get_sender_info_list
        current_user_id = get_current_user_id()
        is_admin = getattr(g, 'user_role', None) == 'admin' or getattr(g, 'role', None) == 'admin'
        data = get_sender_info_list(user_id=current_user_id, admin=is_admin)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/materials/sender-info', methods=['GET', 'POST'])
@require_ajax
def api_materials_sender_info():
    """获取或保存当前用户的发信人信息"""
    try:
        from materials.sender_info_service import get_sender_info, save_sender_info

        current_user_id = get_current_user_id()

        if request.method == 'GET':
            info = get_sender_info(user_id=current_user_id)
            return jsonify({
                'success': True,
                'data': info
            })

        # POST: 保存发信人信息
        data = request.get_json(silent=True) or {}
        if not data.get('sender_name'):
            return jsonify({'success': False, 'error': '发信人姓名不能为空'}), 400

        material_id = data.get('material_id')
        saved_id = save_sender_info(data, user_id=current_user_id, material_id=material_id)
        return jsonify({
            'success': True,
            'data': {'material_id': saved_id},
            'message': '发信人信息已保存'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/materials/tags', methods=['GET'])
@require_ajax
def api_materials_tags():
    """获取所有不重复的标签列表"""
    try:
        from database.material_models import get_all_tags
        current_user_id = get_current_user_id()
        admin = is_admin()
        tags = get_all_tags(user_id=current_user_id, admin=admin)
        return jsonify({'success': True, 'data': tags})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/materials/<int:material_id>/tags', methods=['PUT'])
@require_ajax
def api_materials_update_tags(material_id):
    """更新素材标签"""
    try:
        from database.material_models import update_material_tags
        current_user_id = get_current_user_id()
        admin = is_admin()
        data = request.get_json(silent=True) or {}
        tags = data.get('tags', [])
        if not isinstance(tags, list):
            return jsonify({'success': False, 'error': 'tags 必须是字符串数组'}), 400
        ok = update_material_tags(material_id, tags, user_id=current_user_id, admin=admin)
        if not ok:
            return jsonify({'success': False, 'error': '无权修改或资料不存在'}), 403
        return jsonify({'success': True, 'data': {'tags': tags}, 'message': '标签已更新'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# 确保调度相关表存在
with app.app_context():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS send_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id INTEGER,
        customer_id INTEGER,
        scheduled_at TIMESTAMP,
        status TEXT DEFAULT 'pending',
        subject_id INTEGER,
        email_log_id INTEGER,
        priority INTEGER DEFAULT 5
    )''')
    conn.commit()
    conn.close()


# ==================== AI 内容筛选和提取 API ====================

@app.route('/api/ai/extract-contacts', methods=['POST'])
@require_ajax
def api_ai_extract_contacts():
    """AI 从文本中提取联系人信息"""
    try:
        from services.ai_extractor import AIExtractor

        data = request.json or {}
        text = data.get('text', '').strip()
        customer_name = data.get('customer_name', '').strip()

        if not text or len(text) < 5:
            return jsonify({'success': False, 'error': '文本内容太短，无法提取'}), 400

        extractor = AIExtractor()
        if not extractor.is_available():
            return jsonify({'success': False, 'error': 'AI 服务未配置，请检查 API Key'}), 503

        contacts = extractor.extract_contacts_from_text(text, customer_name)

        return jsonify({
            'success': True,
            'data': {
                'contacts': contacts,
                'count': len(contacts)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/classify-customer', methods=['POST'])
@require_ajax
def api_ai_classify_customer():
    """AI 智能分类客户"""
    try:
        from services.ai_extractor import AIExtractor

        data = request.json or {}
        customer_data = {
            'customer_name': data.get('customer_name', ''),
            'country': data.get('country', ''),
            'company_info': data.get('company_info', ''),
            'website': data.get('website', ''),
            'emails': data.get('emails', [])
        }

        if not customer_data['customer_name']:
            return jsonify({'success': False, 'error': '客户名称不能为空'}), 400

        extractor = AIExtractor()
        if not extractor.is_available():
            return jsonify({'success': False, 'error': 'AI 服务未配置，请检查 API Key'}), 503

        classification = extractor.classify_customer_data(customer_data)

        return jsonify({
            'success': True,
            'data': classification
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/detect-email-type', methods=['POST'])
@require_ajax
def api_ai_detect_email_type():
    """AI 智能识别邮箱类型"""
    try:
        from services.ai_extractor import AIExtractor

        data = request.json or {}
        email = data.get('email', '').strip().lower()
        contact_name = data.get('contact_name', '').strip()

        if not email or '@' not in email:
            return jsonify({'success': False, 'error': '请输入有效的邮箱地址'}), 400

        extractor = AIExtractor()
        if not extractor.is_available():
            return jsonify({'success': False, 'error': 'AI 服务未配置，请检查 API Key'}), 503

        email_type = extractor.detect_email_type(email, contact_name)

        return jsonify({
            'success': True,
            'data': {
                'email': email,
                'email_type': email_type,
                'contact_name': contact_name
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/process-batch', methods=['POST'])
@require_ajax
def api_ai_process_batch():
    """AI 批量处理客户数据"""
    try:
        from services.ai_extractor import AIExtractor

        data = request.json or {}
        customers = data.get('customers', [])

        if not customers or not isinstance(customers, list):
            return jsonify({'success': False, 'error': '请提供客户数据列表'}), 400

        extractor = AIExtractor()
        if not extractor.is_available():
            return jsonify({'success': False, 'error': 'AI 服务未配置，请检查 API Key'}), 503

        processed = extractor.process_customer_batch(customers)

        return jsonify({
            'success': True,
            'data': {
                'customers': processed,
                'total': len(processed)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/extract-from-text', methods=['POST'])
@require_ajax
def api_ai_extract_from_text():
    """AI 从非结构化文本中提取完整客户信息"""
    try:
        from services.ai_extractor import AIExtractor

        data = request.json or {}
        text = data.get('text', '').strip()

        if not text or len(text) < 10:
            return jsonify({'success': False, 'error': '文本内容太短，无法提取'}), 400

        extractor = AIExtractor()
        if not extractor.is_available():
            return jsonify({'success': False, 'error': 'AI 服务未配置，请检查 API Key'}), 503

        result = extractor.extract_from_unstructured_text(text)

        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/status')
def api_ai_status():
    """检查 AI 服务状态"""
    try:
        from services.ai_extractor import AIExtractor

        extractor = AIExtractor()
        is_available = extractor.is_available()

        return jsonify({
            'success': True,
            'data': {
                'available': is_available,
                'message': 'AI 服务正常运行' if is_available else 'AI 服务未配置'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/analyze-file', methods=['POST'])
@require_ajax
def api_ai_analyze_file():
    """AI 智能分析上传的文件内容"""
    try:
        from services.file_content_extractor import extract_from_bytes
        from services.ai_extractor import AIExtractor

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '未上传文件'}), 400

        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'success': False, 'error': '未选择文件'}), 400

        # 验证文件类型
        valid_exts = ['.xlsx', '.xls', '.csv', '.docx', '.pdf', '.txt']
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in valid_exts:
            return jsonify({'success': False, 'error': f'不支持的文件格式: {ext}。支持: {", ".join(valid_exts)}'}), 400

        # 读取文件内容
        file_bytes = file.read()
        if len(file_bytes) > 10 * 1024 * 1024:  # 10MB 限制
            return jsonify({'success': False, 'error': '文件大小超过 10MB 限制'}), 400

        # 提取文件文本内容
        text_content, error = extract_from_bytes(file_bytes, file.filename)
        if error:
            return jsonify({'success': False, 'error': error}), 400

        if not text_content or len(text_content.strip()) < 10:
            return jsonify({'success': False, 'error': '文件内容为空或太短'}), 400

        # 使用 AI 分析提取的内容
        extractor = AIExtractor()
        if not extractor.is_available():
            return jsonify({'success': False, 'error': 'AI 服务未配置，请检查 API Key'}), 503

        # 先尝试提取结构化客户信息
        result = extractor.extract_from_unstructured_text(text_content)

        # 如果没有提取到联系人，尝试提取联系人列表
        if not result.get('contacts'):
            contacts = extractor.extract_contacts_from_text(text_content)
            if contacts:
                result['contacts'] = contacts

        # 添加文件信息
        result['file_info'] = {
            'filename': file.filename,
            'size': len(file_bytes),
            'type': ext,
            'text_length': len(text_content)
        }

        # 添加原始文本预览（前 2000 字符）
        result['text_preview'] = text_content[:2000] + ('...' if len(text_content) > 2000 else '')

        return jsonify({
            'success': True,
            'data': result
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 异步批量导入任务 ====================

def _do_batch_import(task_id, temp_path, filename, user_id=None):
    """后台执行批量导入任务"""
    from services.ai_batch_analyzer import AIBatchAnalyzer
    from database.connection import get_connection
    from utils.import_cache import get_cache
    import time

    start_time = time.time()
    cache = get_cache()
    cache_hits = 0
    cache_misses = 0

    def update_progress(step_id, progress, message=''):
        """更新任务进度"""
        with import_tasks_lock:
            if task_id in import_tasks:
                import_tasks[task_id]['current_step'] = message
                import_tasks[task_id]['progress'] = progress
                import_tasks[task_id]['step_status'][step_id] = 'completed'

    def calculate_progress(current_step, step_progress=0):
        """计算总进度百分比"""
        total_weight = sum(s['weight'] for s in IMPORT_STEPS)
        completed_weight = sum(
            s['weight'] for s in IMPORT_STEPS
            if import_tasks[task_id]['step_status'].get(s['id']) == 'completed'
        )
        current_step_weight = next((s['weight'] for s in IMPORT_STEPS if s['id'] == current_step), 0)
        progress = (completed_weight + current_step_weight * step_progress) / total_weight * 100
        return min(100, int(progress))

    try:
        # 步骤1: 文件解析
        update_progress('parse', 0, '正在解析文件...')
        analyzer = AIBatchAnalyzer()

        # 定义AI分类进度回调
        def on_ai_progress(step_id, message):
            if step_id == 'ai_classify':
                update_progress('ai_classify', calculate_progress('ai_classify', 0.3), message)

        # 传递进度回调给分析器
        analyzer.progress_callback = on_ai_progress

        try:
            results = analyzer.analyze_file(temp_path)
        except Exception as analyze_err:
            print(f"[导入任务 {task_id}] 文件解析失败: {analyze_err}")
            with import_tasks_lock:
                import_tasks[task_id]['status'] = 'failed'
                import_tasks[task_id]['error'] = f'文件解析失败: {str(analyze_err)}'
            return

        update_progress('parse', calculate_progress('parse', 1), f'文件解析完成，共 {len(results)} 条记录')

        # 步骤2: 列名识别（已在analyze_file中完成）
        update_progress('column_detect', calculate_progress('column_detect', 1), '列名识别完成')

        # 步骤3: 数据提取（已在analyze_file中完成）
        update_progress('extract', calculate_progress('extract', 1), f'数据提取完成，共 {len(results)} 条记录')

        # 步骤4: AI智能分类（已在analyze_file中完成）
        classified_count = sum(1 for r in results if r.get('classification'))
        update_progress('ai_classify', calculate_progress('ai_classify', 1), f'AI分类完成，{classified_count}/{len(results)} 条已分类')

        # 步骤5: 数据清洗
        update_progress('clean', calculate_progress('clean', 0.5), '正在清洗数据...')
        cleaned = analyzer.clean_results(results)
        print(f"[导入任务 {task_id}] 清洗完成: {len(cleaned)} 个客户, {sum(len(item.get('contacts', [])) for item in cleaned)} 个联系人")
        update_progress('clean', calculate_progress('clean', 1), '数据清洗完成')

        if not cleaned:
            with import_tasks_lock:
                import_tasks[task_id]['status'] = 'failed'
                import_tasks[task_id]['error'] = '未能从文件中提取到有效数据'
            return

        # 步骤6: 导入数据库
        update_progress('import_db', calculate_progress('import_db', 0), '正在导入数据库...')

        conn = get_connection()
        cursor = conn.cursor()
        imported = 0
        imported_contacts = 0
        skipped_customers = 0
        skipped_emails = 0
        imported_customer_ids = []
        failed_items = []

        total_items = len(cleaned)
        for idx, item in enumerate(cleaned):
            customer = item['customer']
            contacts = item['contacts']

            if not customer.get('customer_name') or not contacts:
                failed_items.append({
                    'name': customer.get('customer_name', '(空)'),
                    'reason': '客户名称为空或没有联系人'
                })
                continue

            try:
                # 检查客户是否已存在（按用户隔离）
                if user_id:
                    cursor.execute(
                        'SELECT id FROM customers WHERE customer_name = ? AND user_id = ?',
                        (customer['customer_name'], user_id)
                    )
                else:
                    cursor.execute(
                        'SELECT id FROM customers WHERE customer_name = ?',
                        (customer['customer_name'],)
                    )
                existing = cursor.fetchone()

                if existing:
                    customer_id = existing[0]
                    skipped_customers += 1
                else:
                    # 插入新客户（带user_id）
                    cursor.execute('''
                        INSERT INTO customers
                        (customer_name, country, website, address, company_info, industry_type, user_id, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    ''', (
                        customer['customer_name'],
                        customer.get('country', ''),
                        customer.get('website', ''),
                        customer.get('address', ''),
                        customer.get('company_info', ''),
                        item.get('classification', {}).get('industry', '') if item.get('classification') else '',
                        user_id
                    ))
                    customer_id = cursor.lastrowid
                    imported += 1
                    imported_customer_ids.append(customer_id)

                # 插入联系人邮箱（带user_id）
                for contact in contacts:
                    email = contact['email_address']
                    if not email:
                        continue

                    try:
                        # 检查邮箱是否已存在
                        cursor.execute(
                            'SELECT id FROM emails WHERE email_address = ?',
                            (email,)
                        )
                        existing_email = cursor.fetchone()

                        if not existing_email:
                            cursor.execute('''
                                INSERT INTO emails
                                (customer_id, email_address, email_type, contact_name, job_title, is_active, user_id, created_at)
                                VALUES (?, ?, ?, ?, ?, 1, ?, datetime('now'))
                            ''', (
                                customer_id,
                                email,
                                contact['email_type'],
                                contact.get('contact_name', ''),
                                contact.get('job_title', ''),
                                user_id
                            ))
                            imported_contacts += 1
                        else:
                            skipped_emails += 1
                    except Exception as email_err:
                        print(f"  插入邮箱失败 {email}: {email_err}")
                        skipped_emails += 1

                # 每10条提交一次，避免大事务锁表
                if idx % 10 == 0:
                    conn.commit()

            except Exception as item_err:
                print(f"  导入客户失败 {customer.get('customer_name', '')}: {item_err}")
                failed_items.append({
                    'name': customer.get('customer_name', '(未知)'),
                    'reason': str(item_err)
                })
                continue

            # 更新进度
            if idx % 5 == 0 or idx == total_items - 1:
                step_progress = (idx + 1) / total_items
                update_progress('import_db', calculate_progress('import_db', step_progress),
                              f'正在导入数据库... ({idx + 1}/{total_items})')

        conn.commit()
        conn.close()

        # 统计信息
        total_contacts = sum(len(item['contacts']) for item in cleaned)
        personal_emails = sum(
            1 for item in cleaned
            for c in item['contacts'] if c['email_type'] == 'personal'
        )
        public_emails = total_contacts - personal_emails
        elapsed_time = time.time() - start_time

        # 缓存统计
        cache_stats = cache.get_stats()

        with import_tasks_lock:
            import_tasks[task_id]['status'] = 'completed'
            import_tasks[task_id]['progress'] = 100
            import_tasks[task_id]['current_step'] = '导入完成'
            import_tasks[task_id]['result'] = {
                'customers_analyzed': len(cleaned),
                'customers_imported': imported,
                'customers_skipped': skipped_customers,
                'contacts_imported': imported_contacts,
                'contacts_skipped': skipped_emails,
                'personal_emails': personal_emails,
                'public_emails': public_emails,
                'linkedin_emails': 0,
                'failed_count': len(failed_items),
                'failed_items': failed_items[:50],  # 最多显示50条失败记录
                'elapsed_time': round(elapsed_time, 2),
                'cache_hits': cache_stats['total_hits'],
                'cache_entries': cache_stats['total_entries'],
                'imported_customer_ids': imported_customer_ids,
                'details': cleaned
            }

    except Exception as e:
        print(f"[导入任务 {task_id}] 后台导入异常: {e}")
        import traceback
        traceback.print_exc()
        with import_tasks_lock:
            if task_id in import_tasks:
                import_tasks[task_id]['status'] = 'failed'
                import_tasks[task_id]['error'] = str(e)
                import_tasks[task_id]['current_step'] = f'导入失败: {str(e)}'
    finally:
        # 安全清理临时文件
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


@app.route('/api/ai/batch-analyze-import', methods=['POST'])
@require_ajax
def api_ai_batch_analyze_import():
    """
    AI 批量分析文件并导入数据库（异步模式）
    支持 Excel/CSV 文件，智能识别列名，自动提取联系人信息
    返回 task_id，前端通过 /api/import/status/<task_id> 查询进度
    """
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '未上传文件'}), 400

        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'success': False, 'error': '未选择文件'}), 400

        # 验证文件类型
        valid_exts = ['.xlsx', '.xls', '.csv']
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in valid_exts:
            return jsonify({'success': False, 'error': f'不支持的文件格式: {ext}。支持: {", ".join(valid_exts)}'}), 400

        # 保存临时文件
        temp_dir = tempfile.gettempdir()
        timestamp = int(time.time() * 1000)
        safe_filename = f"{timestamp}_{file.filename}"
        temp_path = os.path.join(temp_dir, safe_filename)
        file.save(temp_path)

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 初始化任务状态
        with import_tasks_lock:
            import_tasks[task_id] = {
                'status': 'running',
                'progress': 0,
                'current_step': '准备中...',
                'step_status': {},
                'filename': file.filename,
                'result': None,
                'error': None,
                'created_at': datetime.now().isoformat()
            }

        # 启动后台线程执行导入
        current_user_id = get_current_user_id()
        thread = threading.Thread(
            target=_do_batch_import,
            args=(task_id, temp_path, file.filename, current_user_id),
            daemon=True
        )
        thread.start()

        return jsonify({
            'success': True,
            'data': {
                'task_id': task_id,
                'message': '导入任务已启动'
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/import/status/<task_id>', methods=['GET'])
@require_ajax
def api_import_status(task_id):
    """查询导入任务状态"""
    with import_tasks_lock:
        task = import_tasks.get(task_id)

    if not task:
        return jsonify({'success': False, 'error': '任务不存在'}), 404

    # 验证任务归属
    current_user_id = get_current_user_id()
    if 'user_id' in task and not is_admin() and current_user_id != task.get('user_id'):
        return jsonify({'success': False, 'error': '无权访问该任务'}), 403

    return jsonify({
        'success': True,
        'data': {
            'status': task['status'],
            'progress': task['progress'],
            'current_step': task['current_step'],
            'step_status': task['step_status'],
            'filename': task['filename']
        }
    })


@app.route('/api/import/result/<task_id>', methods=['GET'])
@require_ajax
def api_import_result(task_id):
    """获取导入任务结果"""
    with import_tasks_lock:
        task = import_tasks.get(task_id)

    if not task:
        return jsonify({'success': False, 'error': '任务不存在'}), 404

    # 验证任务归属
    current_user_id = get_current_user_id()
    if 'user_id' in task and not is_admin() and current_user_id != task.get('user_id'):
        return jsonify({'success': False, 'error': '无权访问该任务'}), 403

    if task['status'] != 'completed':
        return jsonify({
            'success': False,
            'error': '任务尚未完成',
            'status': task['status']
        }), 400

    return jsonify({
        'success': True,
        'data': task['result']
    })


# ==================== 获客搜索模块 API ====================

@app.route('/api/search/tasks', methods=['POST'])
@require_ajax
def api_search_tasks_create():
    """创建搜索任务"""
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    location = data.get('location', '').strip()
    platforms = data.get('platforms', [])
    config = data.get('config', {})
    task_name = data.get('task_name', '')
    queries = data.get('queries', [])  # 支持传入多个关键词

    if not query and not queries:
        return jsonify({'success': False, 'error': '搜索关键词不能为空'}), 400
    if not platforms or not isinstance(platforms, list):
        return jsonify({'success': False, 'error': '请至少选择一个搜索平台'}), 400

    current_user_id = get_current_user_id()

    engine = get_search_engine()
    task_id = engine.create_and_run(
        query=query,
        location=location,
        platforms=platforms,
        config=config,
        task_name=task_name or f"{query} - {location or '全球'}",
        queries=queries if queries else None,
        user_id=current_user_id
    )

    return jsonify({
        'success': True,
        'data': {
            'task_id': task_id,
            'status': 'running',
            'message': '搜索任务已创建并开始执行'
        }
    })


@app.route('/api/search/tasks', methods=['GET'])
@require_ajax
def api_search_tasks_list():
    """获取搜索任务列表"""
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    current_user_id = get_current_user_id()
    admin = is_admin()

    result = get_search_tasks(
        status=status if status else None,
        page=page,
        per_page=per_page,
        user_id=current_user_id,
        admin=admin
    )

    return jsonify({'success': True, 'data': result})


@app.route('/api/search/tasks/<task_id>', methods=['GET'])
@require_ajax
def api_search_task_detail(task_id):
    """获取任务详情"""
    current_user_id = get_current_user_id()
    admin = is_admin()

    # 验证任务是否属于当前用户
    db_task = get_search_task(task_id, user_id=current_user_id, admin=admin)
    if not db_task:
        return jsonify({'success': False, 'error': '任务不存在'}), 404

    engine = get_search_engine()
    task = engine.get_task_status(task_id)
    if not task:
        return jsonify({'success': False, 'error': '任务不存在'}), 404
    return jsonify({'success': True, 'data': task})


@app.route('/api/search/tasks/<task_id>/action', methods=['POST'])
@require_ajax
def api_search_task_action(task_id):
    """任务操作（cancel）"""
    data = request.get_json() or {}
    action = data.get('action', '')
    current_user_id = get_current_user_id()
    admin = is_admin()

    # 验证任务是否属于当前用户
    db_task = get_search_task(task_id, user_id=current_user_id, admin=admin)
    if not db_task:
        return jsonify({'success': False, 'error': '任务不存在'}), 404

    engine = get_search_engine()
    if action == 'cancel':
        if engine.cancel_task(task_id):
            return jsonify({'success': True, 'message': '任务已取消'})
        return jsonify({'success': False, 'error': '任务无法取消'}), 400

    return jsonify({'success': False, 'error': '未知操作'}), 400


@app.route('/api/search/tasks/<task_id>', methods=['DELETE'])
@require_ajax
def api_search_task_delete(task_id):
    """删除任务"""
    current_user_id = get_current_user_id()
    admin = is_admin()
    if delete_search_task(task_id, user_id=current_user_id, admin=admin):
        return jsonify({'success': True, 'message': '任务已删除'})
    return jsonify({'success': False, 'error': '任务不存在'}), 404


@app.route('/api/search/tasks/<task_id>/results', methods=['GET'])
@require_ajax
def api_search_task_results(task_id):
    """获取任务结果列表"""
    platform = request.args.get('platform', '')
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    current_user_id = get_current_user_id()
    admin = is_admin()

    result = get_search_results(
        task_id=task_id,
        platform=platform if platform else None,
        status=status if status else None,
        search_keyword=search if search else None,
        page=page,
        per_page=per_page,
        user_id=current_user_id,
        admin=admin
    )

    return jsonify({'success': True, 'data': result})


@app.route('/api/search/results/<int:result_id>', methods=['GET'])
@require_ajax
def api_search_result_detail(result_id):
    """获取单条结果详情"""
    print(f"[API] Fetching result detail: result_id={result_id}, type={type(result_id)}")
    current_user_id = get_current_user_id()
    admin = is_admin()
    result = get_search_result(result_id, user_id=current_user_id, admin=admin)
    print(f"[API] Query result: {'FOUND' if result else 'NOT FOUND'}, id={result.get('id') if result else None}")
    if not result:
        return jsonify({'success': False, 'error': '结果不存在'}), 404
    return jsonify({'success': True, 'data': result})


@app.route('/api/search/results/<int:result_id>/deep-email', methods=['POST'])
@require_ajax
def api_deep_email_search(result_id):
    """手动触发邮箱深挖（Hunter API + 全网搜索）"""
    current_user_id = get_current_user_id()
    admin = is_admin()
    result = get_search_result(result_id, user_id=current_user_id, admin=admin)
    if not result:
        return jsonify({'success': False, 'error': '结果不存在'}), 404

    company_name = result.get('company_name', '')
    website = result.get('website', '')
    country = result.get('country', '')

    if not company_name:
        return jsonify({'success': False, 'error': '公司名称为空'}), 400

    # 收集已有的邮箱
    existing_emails = set()
    old_emails = result.get('emails_json') or []
    for e in old_emails:
        existing_emails.add(e.get('email', '').lower())
    if result.get('email'):
        existing_emails.add(result['email'].lower())

    # Hunter API 搜索
    new_emails = []
    hunter_error = None
    try:
        from services.search.hunter_api import create_hunter_searcher
        hunter = create_hunter_searcher()
        if hunter.is_available():
            hunter_results = hunter.find_all_emails(company_name, website)
            for e in hunter_results:
                key = e['email'].lower()
                if key not in existing_emails:
                    existing_emails.add(key)
                    new_emails.append(e)
        else:
            hunter_error = 'Hunter API Key 未配置'
    except Exception as e:
        hunter_error = str(e)

    # 全网邮箱搜索（作为补充）
    if not new_emails and website:
        try:
            from services.search.email_finder import EmailFinder
            finder = EmailFinder()
            finder_results = finder.find_emails(company_name, website, country)
            for e in finder_results:
                key = e['email'].lower()
                if key not in existing_emails:
                    existing_emails.add(key)
                    new_emails.append(e)
        except Exception as e:
            print(f"[DeepEmail] 全网搜索失败: {e}")

    if not new_emails:
        msg = hunter_error or '未找到新的邮箱'
        return jsonify({'success': True, 'new_count': 0, 'emails': [], 'message': msg})

    # 合并到已有邮箱列表
    all_emails = old_emails + new_emails

    # 更新数据库
    from database.search_models import update_result_emails
    emails_json = all_emails if all_emails else None
    if not result.get('email') and new_emails:
        role_emails = [e for e in new_emails if e.get('type') == 'role']
        primary = role_emails[0] if role_emails else new_emails[0]
        update_result_emails(result_id, emails_json=emails_json, email=primary.get('email', ''))
    else:
        update_result_emails(result_id, emails_json=emails_json)

    return jsonify({
        'success': True,
        'new_count': len(new_emails),
        'emails': all_emails,
        'message': f'找到 {len(new_emails)} 个新邮箱'
    })


@app.route('/api/search/results/bulk-review', methods=['POST'])
@require_ajax
def api_search_results_bulk_review():
    """批量审核结果"""
    data = request.get_json() or {}
    result_ids = data.get('result_ids', [])
    status = data.get('status', '')
    current_user_id = get_current_user_id()
    admin = is_admin()

    if not result_ids or status not in ('approved', 'rejected'):
        return jsonify({'success': False, 'error': '参数错误'}), 400

    updated = bulk_update_result_status(result_ids, status, user_id=current_user_id, admin=admin)
    return jsonify({'success': True, 'data': {'updated_count': updated}})


@app.route('/api/search/results/import', methods=['POST'])
@require_ajax
def api_search_results_import():
    """批量导入CRM"""
    data = request.get_json() or {}
    result_ids = data.get('result_ids', [])
    options = data.get('import_options', {})
    current_user_id = get_current_user_id()

    if not result_ids:
        return jsonify({'success': False, 'error': '请选择要导入的结果'}), 400

    imported = 0
    skipped = 0
    failed = 0
    details = []

    for rid in result_ids:
        try:
            result = import_result_to_customer(rid, options, user_id=current_user_id)
            if result['success']:
                imported += 1
                details.append({'result_id': rid, 'customer_id': result['customer_id'], 'status': 'imported'})
            else:
                if result.get('reason') == '网站已存在':
                    skipped += 1
                else:
                    failed += 1
                details.append({'result_id': rid, 'status': 'failed', 'reason': result.get('reason', '')})
        except Exception as e:
            failed += 1
            details.append({'result_id': rid, 'status': 'failed', 'reason': str(e)})

    return jsonify({
        'success': True,
        'data': {
            'imported_count': imported,
            'skipped_count': skipped,
            'failed_count': failed,
            'details': details
        }
    })


@app.route('/api/search/expand-keywords', methods=['POST'])
@require_ajax
def api_expand_keywords():
    """AI 关键词拓展 — 可视化分析"""
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({'success': False, 'error': '缺少 query 参数'}), 400

    query = data['query'].strip()
    location = data.get('location', '').strip()
    max_keywords = data.get('max_keywords', 12)

    if not query:
        return jsonify({'success': False, 'error': '关键词不能为空'}), 400

    try:
        from services.search.keyword_expander import KeywordExpander
        expander = KeywordExpander()
        keywords = expander.expand(query, location, max_keywords=max_keywords)

        # 分类：原始词 vs 拓展词
        base_lower = query.strip().lower()
        categories = {
            'original': [],
            'product': [],
            'business_model': [],
            'location': [],
            'other': []
        }

        business_terms = ['manufacturer', 'supplier', 'distributor', 'wholesaler', 'dealer', 'factory', 'vendor', 'exporter', 'importer', 'trader', 'reseller', 'oem', 'odm', 'producer']
        location_terms = ['usa', 'us', 'america', 'europe', 'china', 'india', 'germany', 'uk', 'japan', 'australia', 'canada', 'france', 'italy', 'spain', 'mexico', 'brazil']

        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower == base_lower:
                categories['original'].append(kw)
            elif any(term in kw_lower for term in business_terms):
                categories['business_model'].append(kw)
            elif any(term in kw_lower for term in location_terms):
                categories['location'].append(kw)
            elif kw_lower != base_lower and query.lower() in kw_lower:
                categories['product'].append(kw)
            else:
                categories['other'].append(kw)

        return jsonify({
            'success': True,
            'data': {
                'base_keyword': query,
                'keywords': keywords,
                'categories': categories,
                'total': len(keywords)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'关键词拓展失败: {str(e)}'}), 500


@app.route('/api/search/platforms', methods=['GET'])
@require_ajax
def api_search_platforms():
    """获取所有平台配置状态（按用户隔离）"""
    current_user_id = get_current_user_id()
    admin = is_admin()
    registry = SearcherRegistry()
    configs = get_platform_configs(user_id=current_user_id, admin=admin)
    available = registry.list_available()

    return jsonify({
        'success': True,
        'data': {
            'platforms': registry.get_platform_info(),
            'configs': configs,
            'available': available
        }
    })


@app.route('/api/search/platforms/<platform>', methods=['GET'])
@require_ajax
def api_search_platform_detail(platform):
    """获取单个平台配置（按用户隔离）"""
    current_user_id = get_current_user_id()
    admin = is_admin()
    config = get_platform_config(platform, user_id=current_user_id, admin=admin)
    if not config:
        return jsonify({'success': False, 'error': '平台不存在'}), 404
    return jsonify({'success': True, 'data': config})


@app.route('/api/search/platforms/<platform>', methods=['PUT'])
@require_ajax
def api_search_platform_update(platform):
    """更新平台配置（仅admin可操作全局配置）"""
    current_user_id = get_current_user_id()
    admin = is_admin()
    data = request.get_json() or {}
    updates = {}

    for key in ['is_enabled', 'api_key', 'api_secret', 'base_url', 'config_json',
                'rate_limit_per_minute', 'daily_quota']:
        if key in data:
            updates[key] = data[key]

    if update_platform_config(platform, user_id=current_user_id, admin=admin, **updates):
        return jsonify({'success': True, 'message': '配置已更新'})
    return jsonify({'success': False, 'error': '更新失败'}), 400


@app.route('/api/search/platforms/<platform>/test', methods=['POST'])
@require_ajax
def api_search_platform_test(platform):
    """测试平台连接"""
    try:
        registry = SearcherRegistry()
        searcher = registry.get_searcher(platform)
        available = searcher.is_available()
        return jsonify({
            'success': True,
            'data': {
                'platform': platform,
                'available': available,
                'message': '连接正常' if available else '未配置API Key或不可用'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/search/ai-analyze', methods=['POST'])
@require_ajax
def api_search_ai_analyze():
    """对单条原始结果进行AI分析"""
    data = request.get_json() or {}
    raw_data = data.get('raw_data', {})
    platform = data.get('platform', 'web_search')

    if not raw_data:
        return jsonify({'success': False, 'error': 'raw_data不能为空'}), 400

    from services.search.ai_enricher import SearchAIEnricher
    from services.search.base import SearchResult

    enricher = SearchAIEnricher()
    if not enricher.is_available():
        return jsonify({'success': False, 'error': 'AI服务不可用'}), 503

    result = SearchResult(platform=platform, source_url='', raw_data=raw_data)
    analysis = enricher.enrich_result(result)

    if analysis:
        return jsonify({'success': True, 'data': analysis})
    return jsonify({'success': False, 'error': 'AI分析失败'}), 500


@app.route('/api/search/batch-ai-analyze', methods=['POST'])
@require_ajax
def api_search_batch_ai_analyze():
    """批量AI分析"""
    data = request.get_json() or {}
    result_ids = data.get('result_ids', [])

    if not result_ids:
        return jsonify({'success': False, 'error': 'result_ids不能为空'}), 400

    from services.search.ai_enricher import SearchAIEnricher
    enricher = SearchAIEnricher()
    if not enricher.is_available():
        return jsonify({'success': False, 'error': 'AI服务不可用'}), 503

    # 读取结果数据
    current_user_id = get_current_user_id()
    admin = is_admin()
    results = []
    for rid in result_ids:
        r = get_search_result(rid, user_id=current_user_id, admin=admin)
        if r:
            from services.search.base import SearchResult
            sr = SearchResult(
                platform=r.get('platform', ''),
                source_url=r.get('source_url', ''),
                raw_data=r.get('raw_data_json', {})
            )
            results.append((rid, sr))

    analyzed = 0
    failed = 0
    for rid, sr in results:
        try:
            analysis = enricher.enrich_result(sr)
            if analysis:
                update_search_task(rid)  # 这里不需要更新task
                analyzed += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return jsonify({
        'success': True,
        'data': {'analyzed_count': analyzed, 'failed_count': failed}
    })


# ==================== 邮件规范 API ====================

@app.route('/api/email-guidelines', methods=['GET'])
@login_required
def get_email_guidelines_api():
    """获取当前用户的邮件规范"""
    from database.email_guidelines_models import get_or_create_guidelines
    user_id = get_current_user_id()
    guidelines = get_or_create_guidelines(user_id)
    return jsonify({'success': True, 'data': guidelines})


@app.route('/api/email-guidelines', methods=['PUT'])
@login_required
def update_email_guidelines_api():
    """更新当前用户的邮件规范"""
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'success': False, 'error': '缺少 content 字段'}), 400
    from database.email_guidelines_models import update_email_guidelines
    user_id = get_current_user_id()
    update_email_guidelines(data['content'], data.get('is_active', True), user_id=user_id)
    return jsonify({'success': True, 'message': '邮件规范已更新'})


# ==================== 跟进邮件模块 API ====================

@app.route('/api/follow-up/sequences', methods=['POST'])
@require_ajax
def api_follow_up_create():
    """创建跟进序列
    body: {customer_id, strategy_type, first_email_log_id, config_json}
    config_json 可选，包含 {word_count, custom_steps: [{purpose, interval_days, subject_mode}]}
    """
    from database.follow_up_models import create_sequence, STRATEGY_TEMPLATES
    from database.material_models import get_sender_info_material
    from database.connection import get_connection

    data = request.get_json() or {}
    customer_id = data.get('customer_id')
    strategy_type = data.get('strategy_type', 'standard')
    first_email_log_id = data.get('first_email_log_id')
    config_json = data.get('config_json')

    if not customer_id:
        return jsonify({'success': False, 'error': 'customer_id 不能为空'}), 400

    current_user_id = get_current_user_id()
    admin = is_admin()

    # 获取策略模板确定总步数
    template = STRATEGY_TEMPLATES.get(strategy_type, STRATEGY_TEMPLATES['standard'])
    total_steps = len(template) + 1  # +1 是第一封邮件

    # 构建 generation_context
    generation_context = {}

    # 1. 读取第一封邮件内容
    conn = get_connection()
    cursor = conn.cursor()

    if first_email_log_id:
        cursor.execute('''
            SELECT id, email_subject, email_content, sent_at FROM email_logs
            WHERE id = ? AND (user_id IS NULL OR user_id = ?)
        ''', (first_email_log_id, current_user_id))
        log = cursor.fetchone()
    else:
        # 没有指定 first_email_log_id，自动查找客户最近一次成功发送的邮件
        cursor.execute('''
            SELECT id, email_subject, email_content, sent_at FROM email_logs
            WHERE customer_id = ? AND send_status = 'sent'
            AND (user_id IS NULL OR user_id = ?)
            ORDER BY sent_at DESC LIMIT 1
        ''', (customer_id, current_user_id))
        log = cursor.fetchone()

    if log and first_email_log_id is None:
        first_email_log_id = log[0]

    # 获取客户信息
    cursor.execute('''
        SELECT id, customer_name, country, website, industry_type FROM customers
        WHERE id = ? AND (user_id IS NULL OR user_id = ?)
    ''', (customer_id, current_user_id))
    customer = cursor.fetchone()

    conn.close()

    if log:
        generation_context['first_email'] = {
            'subject': log[1],
            'body': log[2],
            'sent_at': str(log[3]) if log[3] else ''
        }

    if customer:
        generation_context['customer_info'] = {
            'name': customer[1],
            'country': customer[2] or '',
            'website': customer[3] or '',
            'industry': customer[4] or ''
        }
    else:
        generation_context['customer_info'] = {}

    # 2. 获取发信人信息
    sender = get_sender_info_material(user_id=current_user_id, admin=admin)
    if sender:
        generation_context['sender_info'] = {
            'sender_name': sender.get('content', {}).get('name', ''),
            'company_name': sender.get('content', {}).get('company', ''),
            'position': sender.get('content', {}).get('position', '')
        }
    else:
        generation_context['sender_info'] = {}

    # 创建序列
    try:
        sequence_id = create_sequence(
            customer_id=customer_id,
            user_id=current_user_id,
            strategy_type=strategy_type,
            total_steps=total_steps,
            first_email_log_id=first_email_log_id,
            generation_context=generation_context,
            config_json=config_json
        )
        return jsonify({
            'success': True,
            'sequence_id': sequence_id
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'创建序列失败: {str(e)}'}), 500


@app.route('/api/follow-up/sequences', methods=['GET'])
@require_ajax
def api_follow_up_list():
    """列表查询，支持 ?status=active&customer_id=123&page=1&per_page=20"""
    from database.follow_up_models import list_sequences

    current_user_id = get_current_user_id()
    admin = is_admin()

    status = request.args.get('status', '')
    customer_id = request.args.get('customer_id', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))

    result = list_sequences(
        user_id=current_user_id,
        status=status if status else None,
        customer_id=int(customer_id) if customer_id else None,
        page=page,
        per_page=per_page,
        admin=admin
    )

    return jsonify({
        'success': True,
        'items': result['items'],
        'total': result['total']
    })


@app.route('/api/follow-up/sequences/<int:seq_id>', methods=['GET'])
@require_ajax
def api_follow_up_detail(seq_id):
    """获取序列详情（含所有步骤）"""
    from database.follow_up_models import get_sequence

    current_user_id = get_current_user_id()
    admin = is_admin()

    sequence = get_sequence(seq_id, user_id=current_user_id, admin=admin)
    if not sequence:
        return jsonify({'success': False, 'error': '序列不存在'}), 404

    return jsonify({
        'success': True,
        'data': sequence
    })


@app.route('/api/follow-up/sequences/<int:seq_id>', methods=['PUT'])
@require_ajax
def api_follow_up_update(seq_id):
    """更新序列配置"""
    from database.follow_up_models import update_sequence

    data = request.get_json() or {}
    current_user_id = get_current_user_id()
    admin = is_admin()

    # 提取可更新字段
    kwargs = {}
    if 'config_json' in data:
        kwargs['config_json'] = data['config_json']
    if 'generation_context' in data:
        kwargs['generation_context'] = data['generation_context']

    success = update_sequence(seq_id, user_id=current_user_id, admin=admin, **kwargs)
    if not success:
        return jsonify({'success': False, 'error': '更新失败，序列不存在或无权操作'}), 404

    return jsonify({'success': True, 'message': '序列已更新'})


@app.route('/api/follow-up/sequences/<int:seq_id>', methods=['DELETE'])
@require_ajax
def api_follow_up_delete(seq_id):
    """删除序列（仅 draft/cancelled）"""
    from database.follow_up_models import delete_sequence

    current_user_id = get_current_user_id()
    admin = is_admin()

    success, error = delete_sequence(seq_id, user_id=current_user_id, admin=admin)
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({'success': True, 'message': '序列已删除'})


# ==================== 序列操作 ====================

@app.route('/api/follow-up/sequences/<int:seq_id>/activate', methods=['POST'])
@require_ajax
def api_follow_up_activate(seq_id):
    """激活序列（生成步骤 + 计算发送时间）"""
    from database.follow_up_models import activate_sequence

    current_user_id = get_current_user_id()
    admin = is_admin()

    success, error = activate_sequence(seq_id, user_id=current_user_id, admin=admin)
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({'success': True, 'message': '序列已激活'})


@app.route('/api/follow-up/sequences/<int:seq_id>/pause', methods=['POST'])
@require_ajax
def api_follow_up_pause(seq_id):
    """暂停序列"""
    from database.follow_up_models import pause_sequence

    current_user_id = get_current_user_id()
    admin = is_admin()

    success, error = pause_sequence(seq_id, user_id=current_user_id, admin=admin)
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({'success': True, 'message': '序列已暂停'})


@app.route('/api/follow-up/sequences/<int:seq_id>/resume', methods=['POST'])
@require_ajax
def api_follow_up_resume(seq_id):
    """恢复序列"""
    from database.follow_up_models import resume_sequence

    current_user_id = get_current_user_id()
    admin = is_admin()

    success, error = resume_sequence(seq_id, user_id=current_user_id, admin=admin)
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({'success': True, 'message': '序列已恢复'})


@app.route('/api/follow-up/sequences/<int:seq_id>/cancel', methods=['POST'])
@require_ajax
def api_follow_up_cancel(seq_id):
    """取消序列"""
    from database.follow_up_models import cancel_sequence

    current_user_id = get_current_user_id()
    admin = is_admin()

    success, error = cancel_sequence(seq_id, user_id=current_user_id, admin=admin)
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({'success': True, 'message': '序列已取消'})


# ==================== 步骤管理 ====================

@app.route('/api/follow-up/steps/<int:step_id>', methods=['GET'])
@require_ajax
def api_follow_up_step_detail(step_id):
    """获取步骤详情"""
    from database.follow_up_models import get_step

    current_user_id = get_current_user_id()
    admin = is_admin()

    step = get_step(step_id, user_id=current_user_id, admin=admin)
    if not step:
        return jsonify({'success': False, 'error': '步骤不存在'}), 404

    return jsonify({
        'success': True,
        'data': step
    })


@app.route('/api/follow-up/steps/<int:step_id>', methods=['PUT'])
@require_ajax
def api_follow_up_step_update(step_id):
    """编辑步骤（手动修改标题/正文/间隔）"""
    from database.follow_up_models import update_step

    data = request.get_json() or {}
    current_user_id = get_current_user_id()
    admin = is_admin()

    # 提取可更新字段
    allowed_fields = ['subject', 'body', 'greeting', 'signature',
                      'interval_days', 'strategy', 'subject_mode', 'purpose', 'word_count']
    kwargs = {}
    for field in allowed_fields:
        if field in data:
            kwargs[field] = data[field]

    if 'material_ids' in data:
        kwargs['material_ids'] = data['material_ids']

    success = update_step(step_id, user_id=current_user_id, admin=admin, **kwargs)
    if not success:
        return jsonify({'success': False, 'error': '更新失败，步骤不存在或无权操作'}), 404

    return jsonify({'success': True, 'message': '步骤已更新'})


@app.route('/api/follow-up/steps/<int:step_id>/generate', methods=['POST'])
@require_ajax
def api_follow_up_step_generate(step_id):
    """手动触发 AI 生成跟进邮件"""
    from database.follow_up_models import get_step
    from generators.workflow import EmailWorkflow

    current_user_id = get_current_user_id()
    admin = is_admin()

    # 获取步骤信息以得到 sequence_id
    step = get_step(step_id, user_id=current_user_id, admin=admin)
    if not step:
        return jsonify({'success': False, 'error': '步骤不存在'}), 404

    sequence_id = step['sequence_id']

    try:
        workflow = EmailWorkflow()
        workflow.is_admin = admin
        result = workflow.generate_follow_up_email(sequence_id, step_id, user_id=current_user_id)

        if not result:
            return jsonify({'success': False, 'error': '生成失败，请检查步骤和序列状态'}), 500

        return jsonify({
            'success': True,
            'data': {
                'subject': result.get('subject', ''),
                'body': result.get('body', ''),
                'greeting': result.get('greeting', ''),
                'signature': result.get('signature', '')
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'生成异常: {str(e)}'}), 500


@app.route('/api/follow-up/steps/<int:step_id>/approve', methods=['POST'])
@require_ajax
def api_follow_up_step_approve(step_id):
    """审批步骤"""
    from database.follow_up_models import approve_step

    current_user_id = get_current_user_id()
    admin = is_admin()

    success, error = approve_step(step_id, user_id=current_user_id, admin=admin)
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({'success': True, 'message': '步骤已审批'})


@app.route('/api/follow-up/steps/<int:step_id>/skip', methods=['POST'])
@require_ajax
def api_follow_up_step_skip(step_id):
    """跳过步骤"""
    from database.follow_up_models import skip_step

    current_user_id = get_current_user_id()
    admin = is_admin()

    success, error = skip_step(step_id, user_id=current_user_id, admin=admin)
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({'success': True, 'message': '步骤已跳过'})


@app.route('/api/follow-up/steps/<int:step_id>/send-now', methods=['POST'])
@require_ajax
def api_follow_up_step_send_now(step_id):
    """立即发送（不等 scheduled_at）"""
    from database.follow_up_models import (
        get_step, update_step, approve_step, mark_step_sent, mark_step_failed
    )
    from database.connection import get_connection
    from generators.workflow import EmailWorkflow
    from send_queue.manager import send_queue_manager

    current_user_id = get_current_user_id()
    admin = is_admin()

    # 获取步骤信息
    step = get_step(step_id, user_id=current_user_id, admin=admin)
    if not step:
        return jsonify({'success': False, 'error': '步骤不存在'}), 404

    sequence_id = step['sequence_id']

    # 如果步骤还不是 approved 状态，先尝试审批
    if step['status'] == 'pending':
        success, error = approve_step(step_id, user_id=current_user_id, admin=admin)
        if not success:
            return jsonify({'success': False, 'error': f'审批失败: {error}'}), 400

    # 将 scheduled_at 设为当前时间
    from datetime import datetime
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    update_step(step_id, user_id=current_user_id, admin=admin, status='approved')
    # 直接更新 scheduled_at（通过 SQL）
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE follow_up_steps SET scheduled_at = ? WHERE id = ?
    ''', (now_str, step_id))
    conn.commit()
    conn.close()

    try:
        # 获取客户信息
        conn = get_connection()
        cursor = conn.cursor()

        # 获取序列的 customer_id
        cursor.execute('''
            SELECT customer_id FROM follow_up_sequences WHERE id = ?
        ''', (sequence_id,))
        seq_row = cursor.fetchone()
        if not seq_row:
            conn.close()
            return jsonify({'success': False, 'error': '序列不存在'}), 404
        customer_id = seq_row[0]

        # 生成跟进邮件
        workflow = EmailWorkflow()
        workflow.is_admin = admin
        result = workflow.generate_follow_up_email(sequence_id, step_id, user_id=current_user_id)
        if not result:
            conn.close()
            return jsonify({'success': False, 'error': '邮件生成失败'}), 500

        # 获取该客户的所有活跃邮箱
        cursor.execute('''
            SELECT id, email_address, contact_name, email_type
            FROM emails WHERE customer_id = ? AND is_active = 1
        ''', (customer_id,))
        emails = cursor.fetchall()
        conn.close()

        if not emails:
            return jsonify({'success': False, 'error': '客户无活跃邮箱'}), 400

        # 为每个邮箱创建发送任务
        send_config = {
            'interval_seconds': 0,
            'max_retries': 2,
        }
        task_id = f"followup_now_{sequence_id}_{step_id}"

        email_items = []
        for e in emails:
            email_items.append({
                'email_id': e[0],
                'customer_id': customer_id,
                'email_address': e[1],
                'contact_name': e[2] or '',
                'email_type': e[3],
                'subject': result['subject'],
                'greeting': result.get('greeting', ''),
                'body': result['body'],
            })

        send_queue_manager.create_task(task_id, email_items, send_config)

        # 启动发送（在后台线程中）
        import threading
        if task_id in send_queue_manager._tasks:
            t = threading.Thread(
                target=send_queue_manager._execute_task,
                args=(send_queue_manager._tasks[task_id],),
                daemon=True
            )
            t.start()

        return jsonify({
            'success': True,
            'message': f'跟进邮件已加入发送队列（{len(emails)}封）'
        })

    except Exception as e:
        mark_step_failed(step_id, str(e))
        return jsonify({'success': False, 'error': f'发送失败: {str(e)}'}), 500


# ==================== 仪表盘和批量 ====================

@app.route('/api/follow-up/dashboard', methods=['GET'])
@require_ajax
def api_follow_up_dashboard():
    """获取跟进邮件仪表盘统计"""
    from database.follow_up_models import get_follow_up_dashboard

    current_user_id = get_current_user_id()
    admin = is_admin()

    data = get_follow_up_dashboard(user_id=current_user_id, admin=admin)

    return jsonify({
        'success': True,
        'data': data
    })


@app.route('/api/follow-up/batch-create', methods=['POST'])
@require_ajax
def api_follow_up_batch_create():
    """批量创建跟进序列
    body: {customer_ids: [1,2,3], strategy_type, config_json}
    """
    from database.follow_up_models import batch_create_sequences
    from database.material_models import get_sender_info_material
    from database.connection import get_connection

    data = request.get_json() or {}
    customer_ids = data.get('customer_ids', [])
    strategy_type = data.get('strategy_type', 'standard')
    config_json = data.get('config_json')

    if not customer_ids or not isinstance(customer_ids, list):
        return jsonify({'success': False, 'error': 'customer_ids 不能为空且必须是数组'}), 400

    current_user_id = get_current_user_id()
    admin = is_admin()

    try:
        created_ids = batch_create_sequences(
            customer_ids=customer_ids,
            user_id=current_user_id,
            strategy_type=strategy_type,
            config_json=config_json
        )

        return jsonify({
            'success': True,
            'data': {
                'created_count': len(created_ids),
                'sequence_ids': created_ids
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'批量创建失败: {str(e)}'}), 500


@app.route('/api/follow-up/customer-status/<int:customer_id>', methods=['GET'])
@require_ajax
def api_follow_up_customer_status(customer_id):
    """获取客户的跟进状态"""
    from database.follow_up_models import get_customer_follow_status

    current_user_id = get_current_user_id()
    admin = is_admin()

    data = get_customer_follow_status(customer_id, user_id=current_user_id, admin=admin)

    return jsonify({
        'success': True,
        'data': data
    })


# ==================== Main ====================

if __name__ == '__main__':
    print("=" * 50)
    print("Niteo Solar 智能邮件自动化系统")
    print("Web 管理界面已启动")
    print("=" * 50)
    print(f"访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务器")
    print()

    # 初始化默认 API 配置（从 JSON 文件迁移到数据库）
    try:
        init_default_configs()
    except Exception as e:
        print(f"[API Config] 默认配置初始化失败: {e}")

    app.run(host='0.0.0.0', port=5000, debug=False)
