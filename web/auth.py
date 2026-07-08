#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google OAuth 2.0 认证模块
"""

import os
import sys
import json
import time
import secrets
from functools import wraps
from flask import Blueprint, redirect, request, session, url_for, jsonify

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from authlib.integrations.flask_client import OAuth
from database.schema import get_or_create_user, get_user_by_id, get_all_users

# ==================== 配置 ====================
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
OAUTH_REDIRECT_URI = os.environ.get('OAUTH_REDIRECT_URI', 'https://exim-flow.com/auth/google/callback')

# ==================== OAuth 初始化 ====================
oauth = OAuth()

def init_oauth(app):
    """在 Flask app 上初始化 OAuth"""
    oauth.init_app(app)

    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile',
            'prompt': 'select_account'
        }
    )


# ==================== Blueprint ====================
auth_bp = Blueprint('auth', __name__)

# ==================== 模块级缓存 ====================
_stats_cache = {'data': None, 'timestamp': 0, 'key': ''}
_START_TIME = time.time()  # 进程启动时间，用于 uptime 计算


# ==================== 登录保护装饰器 ====================
def login_required(f):
    """要求用户登录才能访问"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized', 'login_url': '/login.html'}), 401
            return redirect('/login.html')
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """要求管理员权限才能访问"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        user = get_user_by_id(session['user_id'])
        if not user or user['role'] != 'admin':
            return jsonify({'error': 'Forbidden - Admin only'}), 403
        return f(*args, **kwargs)
    return decorated_function


# ==================== 路由 ====================

@auth_bp.route('/login/google')
def login_google():
    """重定向到 Google 登录页"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({'error': 'Google OAuth not configured'}), 500

    redirect_uri = OAUTH_REDIRECT_URI
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/auth/google/callback')
def google_callback():
    """Google OAuth 回调处理"""
    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get('userinfo')

        if not userinfo:
            return redirect('/login.html?error=oauth_failed')

        email = userinfo.get('email')
        name = userinfo.get('name', email.split('@')[0] if email else 'User')
        avatar = userinfo.get('picture', '')
        oauth_id = userinfo.get('sub')

        if not email:
            return redirect('/login.html?error=no_email')

        # 获取或创建用户
        user = get_or_create_user(
            email=email,
            name=name,
            avatar=avatar,
            oauth_provider='google',
            oauth_id=oauth_id
        )

        if not user['is_active']:
            return redirect('/login.html?error=account_disabled')

        # 设置 session
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        session['user_name'] = user['name']
        session['user_role'] = user['role']

        return redirect('/')

    except Exception as e:
        print(f"[OAuth Error] {e}")
        return redirect('/login.html?error=oauth_error')


# ==================== 邀请码登录 ====================

@auth_bp.route('/login/invite', methods=['POST'])
def login_with_invite_code():
    """通过邀请码登录（内测渠道）"""
    data = request.get_json(silent=True) or {}
    code = data.get('code', '').strip().upper()
    name = data.get('name', '').strip()
    
    if not code:
        return jsonify({'error': '请输入邀请码'}), 400
    
    if len(name) < 2:
        return jsonify({'error': '请输入您的名称（至少2个字符）'}), 400
    
    # 验证邀请码
    from database.invite_code_models import validate_invite_code, use_invite_code
    validation = validate_invite_code(code)
    
    if not validation['valid']:
        return jsonify({'error': validation['reason']}), 403
    
    # 检查是否已注册（通过 session 残留的 email 匹配）
    # 内测用户没有 email，用 invite_xxx 格式作为标识
    from database.connection import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    
    # 先查找是否有通过此邀请码创建的用户
    invite_email = f"invite_{code.lower()}@internal.local"
    cursor.execute('SELECT id, email, name, avatar, role, is_active FROM users WHERE email = ?', (invite_email,))
    user = cursor.fetchone()
    
    if user:
        # 已有用户，直接登录
        cursor.execute('UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?', (user[0],))
        conn.commit()
        conn.close()
        
        session['user_id'] = user[0]
        session['user_email'] = user[1]
        session['user_name'] = user[2]
        session['user_role'] = user[4]
        
        return jsonify({'success': True, 'message': '登录成功'})
    
    # 新用户，创建账号
    cursor.execute('SELECT COUNT(*) FROM users')
    user_count = cursor.fetchone()[0]
    role = 'admin' if user_count == 0 else 'user'
    
    cursor.execute('''
        INSERT INTO users (email, name, avatar, oauth_provider, oauth_id, role, last_login_at)
        VALUES (?, ?, '', 'invite_code', ?, ?, CURRENT_TIMESTAMP)
    ''', (invite_email, name, code, role))
    
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # 消耗邀请码
    use_invite_code(code, user_id)
    
    # 设置 session
    session['user_id'] = user_id
    session['user_email'] = invite_email
    session['user_name'] = name
    session['user_role'] = role
    
    return jsonify({'success': True, 'message': '注册成功，欢迎使用'})


@auth_bp.route('/api/invite/validate', methods=['POST'])
def api_validate_invite_code():
    """前端实时验证邀请码（无需登录）"""
    data = request.get_json(silent=True) or {}
    code = data.get('code', '').strip()
    
    if not code:
        return jsonify({'valid': False, 'reason': '请输入邀请码'})
    
    from database.invite_code_models import validate_invite_code
    result = validate_invite_code(code)
    return jsonify(result)


@auth_bp.route('/api/admin/invite-codes', methods=['GET', 'POST'])
@admin_required
def api_admin_invite_codes():
    """管理员获取/生成邀请码"""
    if request.method == 'GET':
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        from database.invite_code_models import get_invite_codes_list
        result = get_invite_codes_list(page, per_page)
        return jsonify(result)
    
    # POST: 生成邀请码
    data = request.get_json(silent=True) or {}
    count = min(data.get('count', 1), 50)  # 最多一次生成50个
    max_uses = max(1, data.get('max_uses', 1))
    note = data.get('note', '')
    expires_days = data.get('expires_days', None)
    if expires_days is not None:
        expires_days = max(1, int(expires_days))
    
    from database.invite_code_models import generate_invite_codes
    codes = generate_invite_codes(
        created_by=session['user_id'],
        count=count,
        max_uses=max_uses,
        note=note,
        expires_days=expires_days
    )
    
    return jsonify({'success': True, 'codes': codes, 'count': len(codes)})


@auth_bp.route('/api/admin/invite-codes/<int:code_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_invite_code(code_id):
    """管理员删除邀请码"""
    from database.invite_code_models import delete_invite_code
    if delete_invite_code(code_id):
        return jsonify({'success': True})
    return jsonify({'error': '邀请码不存在'}), 404


@auth_bp.route('/api/admin/invite-codes/<int:code_id>/toggle', methods=['PUT'])
@admin_required
def api_admin_toggle_invite_code(code_id):
    """管理员启用/禁用邀请码"""
    from database.invite_code_models import toggle_invite_code_status
    if toggle_invite_code_status(code_id):
        return jsonify({'success': True})
    return jsonify({'error': '邀请码不存在'}), 404


@auth_bp.route('/api/admin/invite-codes/stats')
@admin_required
def api_admin_invite_codes_stats():
    """邀请码使用统计"""
    from database.invite_code_models import get_invite_code_stats
    return jsonify(get_invite_code_stats())


@auth_bp.route('/logout')
def logout():
    """登出"""
    session.clear()
    return redirect('/login.html')


@auth_bp.route('/api/me')
@login_required
def api_me():
    """获取当前登录用户信息"""
    user = get_user_by_id(session['user_id'])
    if not user:
        session.clear()
        return jsonify({'error': 'User not found'}), 401

    return jsonify({
        'id': user['id'],
        'email': user['email'],
        'name': user['name'],
        'avatar': user['avatar'],
        'role': user['role']
    })


@auth_bp.route('/api/admin/users')
@admin_required
def api_admin_users():
    """管理员获取所有用户列表"""
    users = get_all_users()
    return jsonify({'users': users})


@auth_bp.route('/api/admin/stats')
@admin_required
def api_admin_stats():
    """管理员获取统计数据（优化版：合并 SQL、支持 period/trend_days 参数、内存缓存）"""
    from database.connection import get_connection

    period = request.args.get('period', 'all')
    trend_days = request.args.get('trend_days', 7, type=int)
    if trend_days not in (7, 30, 90):
        trend_days = 7

    # 缓存 key 由 period + trend_days 组成
    cache_key = f'{period}:{trend_days}'
    now = time.time()
    if _stats_cache['key'] == cache_key and (now - _stats_cache['timestamp']) < 30:
        return jsonify(_stats_cache['data'])

    # 根据 period 生成 WHERE 子句片段
    # period_sent_filter: 用于 total_sent / total_failed（AND 开头）
    # today_sent_filter: today_sent / today_failed 始终按今日过滤（AND 开头）
    if period == 'today':
        period_sent_filter = "AND date(sent_at) = date('now', 'localtime')"
    elif period == 'week':
        period_sent_filter = "AND sent_at >= datetime('now', '-7 days', 'localtime')"
    elif period == 'month':
        period_sent_filter = "AND sent_at >= datetime('now', '-30 days', 'localtime')"
    else:
        period_sent_filter = ""

    today_sent_filter = "AND date(sent_at) = date('now', 'localtime')"

    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    # ---- 第 1 条 SQL：合并所有基础统计子查询 ----
    cursor.execute(f'''
        SELECT
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*) FROM users WHERE role = ?) AS admin_count,
            (SELECT COUNT(*) FROM users WHERE last_login_at >= date('now', '-7 days')) AS active_weekly,
            (SELECT COUNT(*) FROM customers) AS total_customers,
            (SELECT COUNT(DISTINCT country) FROM customers WHERE country IS NOT NULL AND country != '') AS total_countries,
            (SELECT COUNT(*) FROM contacts) AS total_contacts,
            (SELECT COUNT(*) FROM emails) AS total_emails,
            (SELECT COUNT(*) FROM emails WHERE email_type = 'personal') AS personal_emails,
            (SELECT COUNT(*) FROM emails WHERE email_type = 'public') AS public_emails,
            (SELECT COUNT(*) FROM email_logs WHERE send_status = 'sent' {period_sent_filter}) AS total_sent,
            (SELECT COUNT(*) FROM email_logs WHERE send_status = 'failed' {period_sent_filter}) AS total_failed,
            (SELECT COUNT(*) FROM email_logs WHERE 1=1 {today_sent_filter} AND send_status = 'sent') AS today_sent,
            (SELECT COUNT(*) FROM email_logs WHERE 1=1 {today_sent_filter} AND send_status = 'failed') AS today_failed,
            (SELECT COUNT(*) FROM search_tasks) AS total_search_tasks,
            (SELECT COUNT(*) FROM materials) AS total_materials,
            (SELECT COUNT(*) FROM blacklisted_companies) AS total_blacklisted
    ''', ('admin',))
    row = cursor.fetchone()
    stats['total_users'] = row[0]
    stats['admin_count'] = row[1]
    stats['active_weekly'] = row[2]
    stats['total_customers'] = row[3]
    stats['total_countries'] = row[4]
    stats['total_contacts'] = row[5]
    stats['total_emails'] = row[6]
    stats['personal_emails'] = row[7]
    stats['public_emails'] = row[8]
    stats['total_sent'] = row[9]
    stats['total_failed'] = row[10]
    stats['today_sent'] = row[11]
    stats['today_failed'] = row[12]
    stats['total_search_tasks'] = row[13]
    stats['total_materials'] = row[14]
    stats['total_blacklisted'] = row[15]

    # ---- 第 2 条 SQL：国家分布 TOP 10 ----
    cursor.execute('''
        SELECT country, COUNT(*) as cnt FROM customers
        WHERE country IS NOT NULL AND country != ''
        GROUP BY country ORDER BY cnt DESC LIMIT 10
    ''')
    stats['country_distribution'] = [{'country': r[0], 'count': r[1]} for r in cursor.fetchall()]

    # ---- 第 3 条 SQL：发送趋势（可配置天数） ----
    cursor.execute('''
        SELECT date(sent_at) as d, send_status, COUNT(*)
        FROM email_logs
        WHERE sent_at >= date('now', ?, 'localtime')
        GROUP BY d, send_status
        ORDER BY d ASC
    ''', (f'-{trend_days} days',))
    daily_data = {}
    for row in cursor.fetchall():
        d = row[0]
        if d not in daily_data:
            daily_data[d] = {'sent': 0, 'failed': 0}
        daily_data[d][row[1]] = row[2]
    stats['daily_trend'] = [{'date': d, 'sent': v['sent'], 'failed': v['failed']} for d, v in sorted(daily_data.items())]

    # ---- 第 4 条 SQL：来源分布 ----
    cursor.execute('SELECT source, COUNT(*) as cnt FROM contacts GROUP BY source ORDER BY cnt DESC')
    stats['contact_sources'] = [{'source': r[0] or '未知', 'count': r[1]} for r in cursor.fetchall()]

    # ---- 第 5 条 SQL：行业分布 TOP 10 ----
    cursor.execute('''
        SELECT industry_type, COUNT(*) as cnt FROM customers
        WHERE industry_type IS NOT NULL AND industry_type != ''
        GROUP BY industry_type ORDER BY cnt DESC LIMIT 10
    ''')
    stats['industry_distribution'] = [{'industry': r[0], 'count': r[1]} for r in cursor.fetchall()]

    # ---- 第 6 条 SQL：邮件类型分布 ----
    cursor.execute("SELECT email_type, COUNT(*) FROM emails GROUP BY email_type")
    stats['email_type_distribution'] = [{'type': r[0] or '未知', 'count': r[1]} for r in cursor.fetchall()]

    conn.close()

    # 写入缓存
    _stats_cache['data'] = stats
    _stats_cache['timestamp'] = now
    _stats_cache['key'] = cache_key

    return jsonify(stats)


@auth_bp.route('/api/admin/users/<int:user_id>/role', methods=['PUT'])
@admin_required
def api_admin_update_user_role(user_id):
    """修改用户角色"""
    from database.connection import get_connection

    data = request.get_json(silent=True) or {}
    role = data.get('role', '')

    if role not in ('admin', 'user'):
        return jsonify({'error': 'Invalid role, must be admin or user'}), 400

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))
    conn.commit()
    conn.close()

    if cursor.rowcount == 0:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({'message': 'User role updated', 'user_id': user_id, 'role': role})


@auth_bp.route('/api/admin/users/<int:user_id>/status', methods=['PUT'])
@admin_required
def api_admin_update_user_status(user_id):
    """启用/禁用用户"""
    from database.connection import get_connection

    data = request.get_json(silent=True) or {}
    is_active = data.get('is_active')

    if is_active is None or is_active not in (0, 1):
        return jsonify({'error': 'Invalid is_active, must be 0 or 1'}), 400

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_active = ? WHERE id = ?', (is_active, user_id))
    conn.commit()
    conn.close()

    if cursor.rowcount == 0:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({'message': 'User status updated', 'user_id': user_id, 'is_active': is_active})


@auth_bp.route('/api/admin/system/health')
@admin_required
def api_admin_system_health():
    """系统健康状态"""
    memory_used_mb = 0
    memory_total_mb = 0
    disk_used_gb = 0
    disk_total_gb = 0

    try:
        import psutil
        mem = psutil.virtual_memory()
        memory_used_mb = round(mem.used / 1024 / 1024, 1)
        memory_total_mb = round(mem.total / 1024 / 1024, 1)
        disk = psutil.disk_usage('/')
        disk_used_gb = round(disk.used / 1024 / 1024 / 1024, 1)
        disk_total_gb = round(disk.total / 1024 / 1024 / 1024, 1)
    except ImportError:
        # 回退：读取 /proc/meminfo（Linux）
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(':')
                        value_kb = int(parts[1])
                        meminfo[key] = value_kb
                total_kb = meminfo.get('MemTotal', 0)
                available_kb = meminfo.get('MemAvailable', 0)
                memory_total_mb = round(total_kb / 1024, 1)
                memory_used_mb = round((total_kb - available_kb) / 1024, 1)
        except Exception:
            pass

    # 数据库大小
    db_size_mb = 0
    try:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database', 'email_automation.db')
        if os.path.exists(db_path):
            db_size_mb = round(os.path.getsize(db_path) / 1024 / 1024, 2)
    except Exception:
        pass

    uptime_seconds = int(time.time() - _START_TIME)

    # 格式化显示
    memory_percent = f"{round(memory_used_mb / memory_total_mb * 100, 1)}%" if memory_total_mb > 0 else '-'
    memory_used = f"{memory_used_mb}MB / {memory_total_mb}MB" if memory_total_mb > 0 else '-'
    disk_percent = f"{round(disk_used_gb / disk_total_gb * 100, 1)}%" if disk_total_gb > 0 else '-'
    disk_used = f"{disk_used_gb}GB / {disk_total_gb}GB" if disk_total_gb > 0 else '-'
    db_size = f"{db_size_mb}MB" if db_size_mb > 0 else '-'

    # 格式化运行时间
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    mins = (uptime_seconds % 3600) // 60
    uptime = f"{days}天{hours}小时" if days > 0 else f"{hours}小时{mins}分"
    uptime_detail = f"{uptime_seconds}秒" if uptime_seconds < 3600 else uptime

    return jsonify({
        'memory_percent': memory_percent,
        'memory_used': memory_used,
        'disk_percent': disk_percent,
        'disk_used': disk_used,
        'db_size': db_size,
        'uptime': uptime,
        'uptime_detail': uptime_detail
    })


@auth_bp.route('/api/admin/send-queue/status')
@admin_required
def api_admin_send_queue_status():
    """发送队列状态"""
    from database.connection import get_connection

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM send_tasks_meta WHERE status = ?', ('pending',))
    pending_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM send_tasks_meta WHERE status = ?', ('running',))
    running_count = cursor.fetchone()[0]

    # 今日邮件发送统计
    cursor.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN send_status = 'sent' THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN send_status = 'failed' THEN 1 ELSE 0 END) as failed
        FROM email_logs
        WHERE date(sent_at) = date('now', 'localtime')
    ''')
    today_row = cursor.fetchone()

    conn.close()

    return jsonify({
        'pending': pending_count,
        'running': running_count,
        'today_total': today_row[0] or 0,
        'today_sent': today_row[1] or 0,
        'today_failed': today_row[2] or 0
    })


@auth_bp.route('/api/admin/search-tasks/summary')
@admin_required
def api_admin_search_tasks_summary():
    """搜索任务汇总"""
    from database.connection import get_connection

    conn = get_connection()
    cursor = conn.cursor()

    # 各状态数量
    cursor.execute('''
        SELECT status, COUNT(*) as cnt FROM search_tasks GROUP BY status
    ''')
    status_counts = {row[0]: row[1] for row in cursor.fetchall()}

    # 总发现/导入数
    cursor.execute('''
        SELECT
            SUM(found_count) as total_found,
            SUM(imported_count) as total_imported
        FROM search_tasks
    ''')
    totals = cursor.fetchone()

    conn.close()

    return jsonify({
        'running': status_counts.get('running', 0),
        'completed': status_counts.get('completed', 0),
        'failed': status_counts.get('failed', 0),
        'total_found': totals[0] or 0,
        'total_imported': totals[1] or 0
    })


@auth_bp.route('/api/admin/customers')
@admin_required
def api_admin_customers():
    """管理员获取客户列表（含邮箱数、发送统计）"""
    from database.connection import get_connection

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    country = request.args.get('country', '')
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'recent_sent')
    offset = (page - 1) * per_page

    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []
    if country:
        where_clauses.append('c.country = ?')
        params.append(country)
    if search:
        where_clauses.append('(c.customer_name LIKE ? OR c.website LIKE ?)')
        params.extend([f'%{search}%', f'%{search}%'])
    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''

    # 排序
    sort_map = {
        'name': 'c.customer_name ASC',
        'country': 'c.country ASC',
        'email_count': 'email_count DESC',
        'sent_count': 'sent_count DESC',
        'recent_sent': 'last_sent DESC NULLS LAST',
        'created': 'c.created_at DESC'
    }
    order_sql = sort_map.get(sort, 'last_sent DESC NULLS LAST')

    # 总数
    cursor.execute(f'SELECT COUNT(DISTINCT c.id) FROM customers c {where_sql}', params)
    total = cursor.fetchone()[0]

    # 数据
    cursor.execute(f'''
        SELECT c.id, c.customer_name, c.country, c.website, c.industry_type, c.created_at,
               COUNT(DISTINCT e.id) as email_count,
               COUNT(DISTINCT ct.id) as contact_count,
               COUNT(DISTINCT CASE WHEN el.send_status = 'sent' THEN el.id END) as sent_count,
               COUNT(DISTINCT CASE WHEN el.send_status = 'failed' THEN el.id END) as failed_count,
               MAX(el.sent_at) as last_sent
        FROM customers c
        LEFT JOIN emails e ON e.customer_id = c.id AND e.is_active = 1
        LEFT JOIN contacts ct ON ct.customer_id = c.id
        LEFT JOIN email_logs el ON el.customer_id = c.id
        {where_sql}
        GROUP BY c.id
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    ''', params + [per_page, offset])

    rows = cursor.fetchall()
    customers = []
    for r in rows:
        customers.append({
            'id': r[0], 'name': r[1], 'country': r[2], 'website': r[3],
            'industry': r[4], 'created_at': r[5], 'email_count': r[6],
            'contact_count': r[7], 'sent_count': r[8], 'failed_count': r[9],
            'last_sent': r[10]
        })

    # 可用国家列表
    cursor.execute('SELECT DISTINCT country FROM customers WHERE country IS NOT NULL AND country != "" ORDER BY country')
    countries = [r[0] for r in cursor.fetchall()]

    conn.close()
    return jsonify({
        'customers': customers,
        'total': total,
        'page': page,
        'per_page': per_page,
        'countries': countries
    })


@auth_bp.route('/api/admin/customer/<int:customer_id>')
@admin_required
def api_admin_customer_detail(customer_id):
    """管理员获取单个客户详细信息"""
    from database.connection import get_connection

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id, customer_name, country, address, website, company_info, industry_type, website_title, website_description, created_at FROM customers WHERE id = ?', (customer_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Customer not found'}), 404

    customer = {
        'id': row[0], 'name': row[1], 'country': row[2], 'address': row[3],
        'website': row[4], 'company_info': row[5], 'industry': row[6],
        'website_title': row[7], 'website_description': row[8], 'created_at': row[9]
    }

    # 邮箱列表
    cursor.execute('SELECT email_address, email_type, contact_name, job_title, is_active FROM emails WHERE customer_id = ?', (customer_id,))
    customer['emails'] = [{'address': r[0], 'type': r[1], 'contact': r[2], 'job': r[3], 'active': r[4]} for r in cursor.fetchall()]

    # 联系人列表
    cursor.execute('SELECT contact_name, job_title, source FROM contacts WHERE customer_id = ?', (customer_id,))
    customer['contacts'] = [{'name': r[0], 'job': r[1], 'source': r[2]} for r in cursor.fetchall()]

    # 发送记录
    cursor.execute('SELECT email_subject, send_status, sent_at, source FROM email_logs WHERE customer_id = ? ORDER BY sent_at DESC LIMIT 20', (customer_id,))
    customer['email_logs'] = [{'subject': r[0], 'status': r[1], 'sent_at': r[2], 'source': r[3]} for r in cursor.fetchall()]

    # 发送统计汇总
    cursor.execute('SELECT send_status, COUNT(*) FROM email_logs WHERE customer_id = ? GROUP BY send_status', (customer_id,))
    customer['send_summary'] = {r[0]: r[1] for r in cursor.fetchall()}

    # 是否在冷却期
    cursor.execute('''
        SELECT cs.status FROM cooldown_status cs WHERE cs.customer_id = ?
        UNION
        SELECT 'none' LIMIT 1
    ''', (customer_id,))
    cool_row = cursor.fetchone()
    customer['cooldown_status'] = cool_row[0] if cool_row else 'none'

    # 是否拉黑
    cursor.execute('SELECT 1 FROM blacklisted_companies WHERE customer_id = ?', (customer_id,))
    customer['is_blacklisted'] = cursor.fetchone() is not None

    conn.close()
    return jsonify(customer)
