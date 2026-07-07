"""
搜索模块数据库操作层
"""
import json
from typing import List, Optional, Dict
from database.connection import get_connection


# ==================== Search Tasks ====================

def create_search_task(task_id: str, query: str, location: str, platforms: list,
                       config: dict = None, task_name: str = None) -> int:
    """创建搜索任务，返回任务DB ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO search_tasks (task_id, task_name, query_text, location, platforms, config_json, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        task_id,
        task_name or f"{query} - {location or '全球'}",
        query,
        location,
        json.dumps(platforms),
        json.dumps(config or {}),
        'pending'
    ))
    task_db_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_db_id


def update_search_task(task_id: str, **kwargs) -> bool:
    """更新搜索任务字段"""
    allowed = {'task_name', 'status', 'total_targets', 'found_count', 'imported_count',
               'ai_enriched_count', 'pre_filtered_count', 'crawl_rejected_count',
               'ai_skipped_count', 'config_json', 'error_message', 'started_at', 'completed_at'}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    conn = get_connection()
    cursor = conn.cursor()
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    set_clause += ', updated_at = CURRENT_TIMESTAMP'
    cursor.execute(f'UPDATE search_tasks SET {set_clause} WHERE task_id = ?',
                   list(updates.values()) + [task_id])
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def get_search_task(task_id: str) -> Optional[dict]:
    """获取单个任务详情"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM search_tasks WHERE task_id = ?', (task_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _task_row_to_dict(row)


def get_search_tasks(status: str = None, page: int = 1, per_page: int = 20) -> dict:
    """获取任务列表（分页）"""
    conn = get_connection()
    cursor = conn.cursor()

    where_clause = ''
    params = []
    if status:
        where_clause = 'WHERE status = ?'
        params = [status]

    # 总数
    cursor.execute(f'SELECT COUNT(*) FROM search_tasks {where_clause}', params)
    total = cursor.fetchone()[0]

    # 分页数据
    offset = (page - 1) * per_page
    cursor.execute(f'''
        SELECT * FROM search_tasks {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', params + [per_page, offset])
    rows = cursor.fetchall()
    conn.close()

    return {
        'total': total,
        'page': page,
        'per_page': per_page,
        'tasks': [_task_row_to_dict(r) for r in rows]
    }


def delete_search_task(task_id: str) -> bool:
    """删除任务（级联删除结果由外键处理）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM search_tasks WHERE task_id = ?', (task_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# ==================== Search Results ====================

def save_search_result(task_id: str, platform: str, source_url: str, raw_data: dict,
                       company_name: str = '', website: str = '', country: str = '',
                       address: str = '', phone: str = '', email: str = '',
                       industry_type: str = '', business_model: str = '',
                       confidence_score: float = None, ai_analysis: dict = None,
                       search_keyword: str = '', search_location: str = '',
                       emails_json: list = None,
                       validation_status: str = 'pending',
                       validation_reason: str = '',
                       pre_crawl_score: float = None,
                       crawl_validation_passed: bool = False,
                       probe_title: str = '',
                       probe_description: str = '') -> int:
    """保存单条搜索结果，返回结果DB ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO search_results (
            task_id, platform, source_url, raw_data_json,
            company_name, website, country, address, phone, email,
            industry_type, business_model, confidence_score, ai_analysis_json,
            search_keyword, search_location, emails_json,
            validation_status, validation_reason, pre_crawl_score,
            crawl_validation_passed, probe_title, probe_description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        task_id, platform, source_url, json.dumps(raw_data),
        company_name, website, country, address, phone, email,
        industry_type, business_model, confidence_score,
        json.dumps(ai_analysis) if ai_analysis else None,
        search_keyword, search_location,
        json.dumps(emails_json) if emails_json else None,
        validation_status, validation_reason, pre_crawl_score,
        1 if crawl_validation_passed else 0,
        probe_title, probe_description
    ))
    result_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return result_id


def get_search_results(task_id: str = None, status: str = None, platform: str = None,
                       search_keyword: str = None, page: int = 1, per_page: int = 20) -> dict:
    """获取搜索结果列表（分页+筛选）"""
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []
    if task_id:
        conditions.append('task_id = ?')
        params.append(task_id)
    if status:
        conditions.append('import_status = ?')
        params.append(status)
    if platform:
        conditions.append('platform = ?')
        params.append(platform)
    if search_keyword:
        conditions.append('company_name LIKE ?')
        params.append(f'%{search_keyword}%')

    where_clause = 'WHERE ' + ' AND '.join(conditions) if conditions else ''

    # 总数
    cursor.execute(f'SELECT COUNT(*) FROM search_results {where_clause}', params)
    total = cursor.fetchone()[0]

    # 分页数据
    offset = (page - 1) * per_page
    cursor.execute(f'''
        SELECT * FROM search_results {where_clause}
        ORDER BY confidence_score DESC, created_at DESC
        LIMIT ? OFFSET ?
    ''', params + [per_page, offset])
    rows = cursor.fetchall()
    conn.close()

    return {
        'total': total,
        'page': page,
        'per_page': per_page,
        'results': [_result_row_to_dict(r) for r in rows]
    }


def get_search_result(result_id: int) -> Optional[dict]:
    """获取单条结果详情"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM search_results WHERE id = ?', (result_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _result_row_to_dict(row)


def update_result_import_status(result_id: int, status: str, customer_id: int = None) -> bool:
    """更新结果导入状态"""
    conn = get_connection()
    cursor = conn.cursor()
    if customer_id is not None:
        cursor.execute('''
            UPDATE search_results
            SET import_status = ?, imported_customer_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, customer_id, result_id))
    else:
        cursor.execute('''
            UPDATE search_results
            SET import_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, result_id))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def update_result_emails(result_id: int, emails_json: list = None, email: str = None) -> bool:
    """更新结果的邮箱数据"""
    conn = get_connection()
    cursor = conn.cursor()
    sets = ['updated_at = CURRENT_TIMESTAMP']
    params = []
    if emails_json is not None:
        sets.append('emails_json = ?')
        params.append(json.dumps(emails_json))
    if email is not None:
        sets.append('email = ?')
        params.append(email)
    if not sets:
        conn.close()
        return False
    params.append(result_id)
    cursor.execute(f"UPDATE search_results SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def bulk_update_result_status(result_ids: List[int], status: str) -> int:
    """批量更新结果状态，返回更新数量"""
    if not result_ids:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(result_ids))
    cursor.execute(f'''
        UPDATE search_results
        SET import_status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id IN ({placeholders})
    ''', [status] + result_ids)
    conn.commit()
    updated = cursor.rowcount
    conn.close()
    return updated


# ==================== Platform Configs ====================

def get_platform_configs() -> List[dict]:
    """获取所有平台配置"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM search_platform_configs ORDER BY platform')
    rows = cursor.fetchall()
    conn.close()
    return [_platform_row_to_dict(r) for r in rows]


def get_platform_config(platform: str) -> Optional[dict]:
    """获取单个平台配置"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM search_platform_configs WHERE platform = ?', (platform,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _platform_row_to_dict(row)


def update_platform_config(platform: str, **kwargs) -> bool:
    """更新平台配置"""
    allowed = {'is_enabled', 'api_key', 'api_secret', 'base_url', 'config_json',
               'rate_limit_per_minute', 'daily_quota'}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    # 检查是否已存在
    cursor.execute('SELECT id FROM search_platform_configs WHERE platform = ?', (platform,))
    exists = cursor.fetchone()

    if exists:
        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        set_clause += ', updated_at = CURRENT_TIMESTAMP'
        cursor.execute(f'UPDATE search_platform_configs SET {set_clause} WHERE platform = ?',
                       list(updates.values()) + [platform])
    else:
        cols = ['platform'] + list(updates.keys()) + ['created_at', 'updated_at']
        placeholders = ','.join(['?'] * len(cols))
        cursor.execute(f'''
            INSERT INTO search_platform_configs ({','.join(cols)})
            VALUES ({placeholders})
        ''', [platform] + list(updates.values()) + ['CURRENT_TIMESTAMP', 'CURRENT_TIMESTAMP'])

    conn.commit()
    conn.close()
    return True


# ==================== Import to CRM ====================

def import_result_to_customer(result_id: int, import_options: dict = None) -> dict:
    """
    将单条搜索结果导入到customers/emails/contacts表
    返回 {'success': bool, 'customer_id': int or None, 'reason': str}
    """
    import_options = import_options or {}
    skip_duplicate = import_options.get('skip_duplicate_website', True)
    default_country = import_options.get('default_country', '')

    conn = get_connection()
    cursor = conn.cursor()

    # 读取结果
    cursor.execute('SELECT * FROM search_results WHERE id = ?', (result_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {'success': False, 'customer_id': None, 'reason': '结果不存在'}

    result = _result_row_to_dict(row)

    # 检查website重复
    website = result.get('website', '')
    if skip_duplicate and website:
        cursor.execute('SELECT id FROM customers WHERE website = ?', (website,))
        dup = cursor.fetchone()
        if dup:
            conn.close()
            return {'success': False, 'customer_id': None, 'reason': '网站已存在'}

    # 插入customers
    cursor.execute('''
        INSERT INTO customers (
            customer_name, country, address, website, company_info,
            industry_type, source_channel, source_task_id, source_platform
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        result.get('company_name', 'Unknown Company'),
        result.get('country', default_country),
        result.get('address', ''),
        website,
        result.get('ai_analysis_json', {}).get('ai_summary', '') if result.get('ai_analysis_json') else '',
        result.get('industry_type', ''),
        'ai_search',
        result.get('task_id', ''),
        result.get('platform', '')
    ))
    customer_id = cursor.lastrowid

    # 插入email（如有）
    email = result.get('email', '')
    if email:
        email_type = 'public'
        # 简单判断：含个人名特征可能是personal
        local_part = email.split('@')[0].lower()
        public_indicators = ['info', 'sales', 'support', 'contact', 'hello', 'admin', 'service',
                             'marketing', 'business', 'enquiry', 'order']
        if not any(ind in local_part for ind in public_indicators):
            email_type = 'personal'

        cursor.execute('''
            INSERT INTO emails (customer_id, email_address, email_type, is_active)
            VALUES (?, ?, ?, 1)
        ''', (customer_id, email, email_type))

    # 更新结果状态
    cursor.execute('''
        UPDATE search_results
        SET import_status = 'imported', imported_customer_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (customer_id, result_id))

    # 更新任务导入计数
    cursor.execute('''
        UPDATE search_tasks
        SET imported_count = imported_count + 1, updated_at = CURRENT_TIMESTAMP
        WHERE task_id = ?
    ''', (result.get('task_id', ''),))

    conn.commit()
    conn.close()

    return {'success': True, 'customer_id': customer_id, 'reason': ''}


# ==================== Helpers ====================

def _task_row_to_dict(row) -> dict:
    """将search_tasks行转换为字典"""
    return {
        'id': row[0],
        'task_id': row[1],
        'task_name': row[2],
        'query_text': row[3],
        'location': row[4],
        'platforms': json.loads(row[5]) if row[5] else [],
        'status': row[6],
        'total_targets': row[7],
        'found_count': row[8],
        'imported_count': row[9],
        'ai_enriched_count': row[10],
        'config_json': json.loads(row[11]) if row[11] else {},
        'error_message': row[12],
        'created_at': row[13],
        'started_at': row[14],
        'completed_at': row[15],
        'updated_at': row[16],
        'pre_filtered_count': row[17] if row[17] is not None else 0,
        'crawl_rejected_count': row[18] if row[18] is not None else 0,
        'ai_skipped_count': row[19] if row[19] is not None else 0,
    }


def _result_row_to_dict(row) -> dict:
    """将search_results行转换为字典"""
    return {
        'id': row[0],
        'task_id': row[1],
        'platform': row[2],
        'source_url': row[3],
        'raw_data_json': json.loads(row[4]) if row[4] else {},
        'company_name': row[5],
        'website': row[6],
        'country': row[7],
        'address': row[8],
        'phone': row[9],
        'email': row[10],
        'industry_type': row[11],
        'business_model': row[12],
        'confidence_score': row[13],
        'ai_analysis_json': json.loads(row[14]) if row[14] else {},
        'import_status': row[15],
        'imported_customer_id': row[16],
        'search_keyword': row[17],
        'search_location': row[18],
        'created_at': row[19],
        'updated_at': row[20],
        'emails_json': json.loads(row[21]) if row[21] else [],
        'validation_status': row[22] or 'pending',
        'validation_reason': row[23] or '',
        'pre_crawl_score': row[24],
        'crawl_validation_passed': bool(row[25]) if row[25] is not None else False,
        'probe_title': row[26] or '',
        'probe_description': row[27] or '',
    }


def _platform_row_to_dict(row) -> dict:
    """将search_platform_configs行转换为字典"""
    return {
        'id': row[0],
        'platform': row[1],
        'is_enabled': bool(row[2]),
        'api_key': row[3] and '***' or '',  # 脱敏
        'has_api_key': bool(row[3]),
        'api_secret': row[4] and '***' or '',
        'base_url': row[5],
        'config_json': json.loads(row[6]) if row[6] else {},
        'rate_limit_per_minute': row[7],
        'daily_quota': row[8],
        'usage_today': row[9],
        'last_reset_date': row[10],
        'created_at': row[11],
        'updated_at': row[12],
    }


# ============ 拉黑公司管理 ============

def add_blacklist(company_name: str, website: str = '', reason: str = '') -> bool:
    """拉黑公司"""
    conn = get_connection()
    try:
        conn.execute(
            'INSERT OR IGNORE INTO blacklisted_companies (company_name, website, reason) VALUES (?, ?, ?)',
            (company_name, website, reason)
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def remove_blacklist(company_name: str, website: str = '') -> bool:
    """取消拉黑"""
    conn = get_connection()
    try:
        conn.execute(
            'DELETE FROM blacklisted_companies WHERE company_name = ? AND (website = ? OR website = \'\')',
            (company_name, website)
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def is_blacklisted(company_name: str = '', website: str = '') -> bool:
    """检查是否在拉黑列表中"""
    conn = get_connection()
    try:
        # 按域名精确匹配
        if website:
            row = conn.execute(
                'SELECT 1 FROM blacklisted_companies WHERE website = ? AND website != \'\' LIMIT 1',
                (website,)
            ).fetchone()
            if row:
                return True
        # 按公司名匹配（忽略大小写）
        if company_name:
            row = conn.execute(
                'SELECT 1 FROM blacklisted_companies WHERE LOWER(company_name) = LOWER(?) LIMIT 1',
                (company_name,)
            ).fetchone()
            if row:
                return True
        return False
    finally:
        conn.close()


def get_blacklisted_websites() -> set:
    """获取所有拉黑域名集合（用于搜索引擎过滤）"""
    conn = get_connection()
    try:
        rows = conn.execute('SELECT website FROM blacklisted_companies WHERE website != \'\'').fetchall()
        return {r[0].lower().strip() for r in rows if r[0]}
    finally:
        conn.close()


def get_blacklisted_names() -> set:
    """获取所有拉黑公司名集合"""
    conn = get_connection()
    try:
        rows = conn.execute('SELECT LOWER(company_name) FROM blacklisted_companies').fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def get_blacklist(page: int = 1, per_page: int = 20) -> dict:
    """获取拉黑列表（分页）"""
    conn = get_connection()
    try:
        total = conn.execute('SELECT COUNT(*) FROM blacklisted_companies').fetchone()[0]
        rows = conn.execute(
            'SELECT id, company_name, website, reason, created_at FROM blacklisted_companies ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (per_page, (page - 1) * per_page)
        ).fetchall()
        items = [{
            'id': r[0], 'company_name': r[1], 'website': r[2] or '',
            'reason': r[3] or '', 'created_at': r[4]
        } for r in rows]
        return {'items': items, 'total': total, 'page': page, 'per_page': per_page}
    finally:
        conn.close()
