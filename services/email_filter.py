"""
客户筛选规则引擎
支持按国家、行业、邮箱类型、冷却期、发送状态、公司名称搜索筛选待发送客户
"""
import sqlite3
from datetime import datetime, timedelta
from database.connection import get_connection


class EmailFilter:
    """客户筛选规则引擎"""

    def __init__(self, config=None):
        self.config = config or {}

    def filter_customers(self, config=None, user_id=None, admin=False):
        """
        根据筛选规则获取待发送的客户及其邮箱列表

        Args:
            config: 筛选配置字典，包含:
                - countries: list[str] - 国家列表，空列表表示全部
                - industry_type: str - 行业筛选，空字符串表示全部
                - email_types: list[str] - 邮箱类型列表 ['personal','public','linkedin']，空列表表示全部
                - email_type: str - 兼容旧版: 'all'/'personal'/'public'
                - send_status: str - 发送状态: 'all'/'unsent'/'sent'/'failed'
                - search_keyword: str - 公司名称搜索关键词
                - cooldown_days: int - 冷却期天数
                - daily_limit: int - 每日发送上限
                - limit: int - 返回结果上限，默认200
                - order_by: str - 排序方式: 'default'/'unsent_first'/'recent_sent'
            user_id: 当前用户 ID（数据隔离）
            admin: 是否为管理员

        Returns:
            list[dict]: 待发送的邮件列表
        """
        if config:
            self.config = config

        conn = get_connection()
        cursor = conn.cursor()

        cooldown_days = self.config.get('cooldown_days', 7)
        cutoff_date = (datetime.now() - timedelta(days=cooldown_days)).strftime('%Y-%m-%d %H:%M:%S')
        daily_limit = self.config.get('daily_limit', 200)
        limit = self.config.get('limit', daily_limit)
        countries = self.config.get('countries', [])
        industry_type = self.config.get('industry_type', '')
        # 兼容旧版 email_type 单选
        email_type = self.config.get('email_type', 'all')
        email_types = self.config.get('email_types', [])
        send_status = self.config.get('send_status', 'all')
        search_keyword = self.config.get('search_keyword', '')
        order_by = self.config.get('order_by', 'default')

        # 检查今日已发送数量（按用户隔离）
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        if not admin and user_id:
            cursor.execute('SELECT COUNT(*) FROM email_logs WHERE sent_at >= ? AND user_id = ?', (today_start, user_id))
        else:
            cursor.execute('SELECT COUNT(*) FROM email_logs WHERE sent_at >= ?', (today_start,))
        today_sent = cursor.fetchone()[0]
        remaining = max(0, daily_limit - today_sent)

        if remaining <= 0:
            conn.close()
            return []

        # 构建查询
        conditions = [
            'e.is_active = 1',
            'e.email_address IS NOT NULL',
            'e.email_address != ""',
        ]
        params = []

        # 数据隔离：只查询当前用户的客户和邮箱
        if not admin and user_id:
            conditions.append('c.user_id = ?')
            params.append(user_id)
            conditions.append('e.user_id = ?')
            params.append(user_id)

        # 冷却期逻辑：排除在冷却期内已发送过的客户（排除手动解除的）
        # 但如果 send_status='sent' 或 'failed'，则不应用冷却期（用于查看已发送/失败的记录）
        if send_status not in ('sent', 'failed'):
            # 冷却期逻辑：如果在 cooldown_override 中则跳过冷却检查；否则排除冷却期内已发送的公司
            conditions.append('''(
                c.id IN (SELECT customer_id FROM cooldown_override)
                OR c.id NOT IN (SELECT DISTINCT customer_id FROM email_logs WHERE sent_at >= ?)
            )''')
            params.append(cutoff_date)

        # 按国家筛选（支持多选）
        if countries:
            placeholders = ','.join('?' * len(countries))
            conditions.append(f'c.country IN ({placeholders})')
            params.extend(countries)

        # 按行业筛选
        if industry_type:
            conditions.append('c.industry_type = ?')
            params.append(industry_type)

        # 按邮箱类型筛选（支持多选，兼容旧版单选）
        if email_types:
            placeholders = ','.join('?' * len(email_types))
            conditions.append(f'e.email_type IN ({placeholders})')
            params.extend(email_types)
        elif email_type in ('personal', 'public', 'linkedin'):
            conditions.append('e.email_type = ?')
            params.append(email_type)

        # 按发送状态筛选
        if send_status == 'unsent':
            # 从未发送过（或冷却期内未发送）
            conditions.append(
                'e.id NOT IN (SELECT DISTINCT email_id FROM email_logs WHERE email_id IS NOT NULL)'
            )
        elif send_status == 'sent':
            # 已成功发送过
            conditions.append(
                'e.id IN (SELECT DISTINCT email_id FROM email_logs WHERE send_status = "sent" AND email_id IS NOT NULL)'
            )
        elif send_status == 'failed':
            # 发送失败过
            conditions.append(
                'e.id IN (SELECT DISTINCT email_id FROM email_logs WHERE send_status = "failed" AND email_id IS NOT NULL)'
            )

        # 按公司名称搜索
        if search_keyword:
            conditions.append('c.customer_name LIKE ?')
            params.append(f'%{search_keyword}%')

        # 排除无效数据
        conditions.append("c.country IS NOT NULL AND c.country != '' AND c.country != 'nan' AND c.country != 'NaN'")
        conditions.append("c.customer_name IS NOT NULL AND c.customer_name != '' AND c.customer_name != 'nan'")

        # 排序
        order_clause = 'ORDER BY c.id, e.id'
        if order_by == 'unsent_first':
            order_clause = '''ORDER BY 
                CASE WHEN e.id IN (SELECT DISTINCT email_id FROM email_logs WHERE email_id IS NOT NULL) THEN 1 ELSE 0 END,
                c.id, e.id'''
        elif order_by == 'recent_sent':
            order_clause = '''ORDER BY 
                (SELECT MAX(sent_at) FROM email_logs el WHERE el.email_id = e.id) DESC NULLS LAST,
                c.id, e.id'''

        query = f'''
            SELECT c.id, c.customer_name, c.country, c.website, c.industry_type,
                   e.id, e.email_address, e.email_type, COALESCE(e.contact_name, ct.contact_name) as contact_name,
                   COALESCE(e.job_title, ct.job_title) as job_title
            FROM customers c
            JOIN emails e ON c.id = e.customer_id
            LEFT JOIN contacts ct ON e.contact_id = ct.id
            WHERE {' AND '.join(conditions)}
            {order_clause}
            LIMIT ?
        '''
        params.append(min(limit, remaining) if send_status not in ('sent', 'failed') else limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append({
                'customer_id': row[0],
                'customer_name': row[1],
                'country': row[2],
                'website': row[3],
                'industry_type': row[4],
                'email_id': row[5],
                'email_address': row[6],
                'email_type': row[7],
                'contact_name': row[8],
                'job_title': row[9]
            })

        return results

    def get_customer_emails(self, customer_id, user_id=None, admin=False):
        """获取指定客户的所有邮箱"""
        conn = get_connection()
        cursor = conn.cursor()
        if not admin and user_id:
            cursor.execute('''
                SELECT e.id, e.email_address, e.email_type, e.contact_name, e.job_title, e.is_active,
                       (SELECT COUNT(*) FROM email_logs el WHERE el.email_id = e.id AND el.send_status = 'sent') as sent_count,
                       (SELECT MAX(sent_at) FROM email_logs el WHERE el.email_id = e.id) as last_sent
                FROM emails e
                WHERE e.customer_id = ? AND e.user_id = ?
                ORDER BY e.email_type, e.id
            ''', (customer_id, user_id))
        else:
            cursor.execute('''
                SELECT e.id, e.email_address, e.email_type, e.contact_name, e.job_title, e.is_active,
                       (SELECT COUNT(*) FROM email_logs el WHERE el.email_id = e.id AND el.send_status = 'sent') as sent_count,
                       (SELECT MAX(sent_at) FROM email_logs el WHERE el.email_id = e.id) as last_sent
                FROM emails e
                WHERE e.customer_id = ?
                ORDER BY e.email_type, e.id
            ''', (customer_id,))
        rows = cursor.fetchall()
        conn.close()
        return [{
            'email_id': r[0], 'email_address': r[1], 'email_type': r[2],
            'contact_name': r[3], 'job_title': r[4], 'is_active': r[5],
            'sent_count': r[6], 'last_sent': r[7]
        } for r in rows]

    def preview(self, config=None):
        """预览筛选结果（与 filter_customers 相同，但标记为预览模式）"""
        return self.filter_customers(config)
