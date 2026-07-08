"""
邀请码管理模块
"""
from database.connection import get_connection
import secrets
import time


def init_invite_codes_table():
    """初始化邀请码表"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            created_by INTEGER NOT NULL,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            note TEXT DEFAULT '',
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invite_codes_code ON invite_codes(code)')
    conn.commit()
    conn.close()


def generate_invite_codes(created_by: int, count: int = 1, max_uses: int = 1,
                           note: str = '', expires_days: int = None) -> list:
    """
    批量生成邀请码
    
    Args:
        created_by: 创建者（管理员）用户ID
        count: 生成数量
        max_uses: 每个码最大使用次数
        note: 备注
        expires_days: 过期天数（None表示永不过期）
    
    Returns:
        list: 生成的邀请码列表
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    codes = []
    for _ in range(count):
        # 生成8位大写字母+数字的邀请码
        code = secrets.token_urlsafe(6).upper()[:8]
        # 确保不重复
        while True:
            cursor.execute('SELECT 1 FROM invite_codes WHERE code = ?', (code,))
            if not cursor.fetchone():
                break
            code = secrets.token_urlsafe(6).upper()[:8]
        
        expires_at = f"datetime('now', '+{expires_days} days')" if expires_days else None
        
        if expires_at:
            cursor.execute('''
                INSERT INTO invite_codes (code, created_by, max_uses, note, expires_at)
                VALUES (?, ?, ?, ?, datetime('now', '+' || ? || ' days'))
            ''', (code, created_by, max_uses, note, expires_days))
        else:
            cursor.execute('''
                INSERT INTO invite_codes (code, created_by, max_uses, note)
                VALUES (?, ?, ?, ?)
            ''', (code, created_by, max_uses, note))
        
        codes.append(code)
    
    conn.commit()
    conn.close()
    return codes


def validate_invite_code(code: str) -> dict:
    """
    验证邀请码是否可用
    
    Returns:
        dict: {'valid': bool, 'reason': str}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, max_uses, used_count, is_active, expires_at
        FROM invite_codes WHERE code = ?
    ''', (code.strip().upper(),))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return {'valid': False, 'reason': '邀请码不存在'}
    
    code_id, max_uses, used_count, is_active, expires_at = row
    
    if not is_active:
        conn.close()
        return {'valid': False, 'reason': '邀请码已被禁用'}
    
    if max_uses > 0 and used_count >= max_uses:
        conn.close()
        return {'valid': False, 'reason': '邀请码已用完'}
    
    if expires_at:
        cursor.execute("SELECT datetime('now') > ?", (expires_at,))
        if cursor.fetchone()[0]:
            conn.close()
            return {'valid': False, 'reason': '邀请码已过期'}
    
    conn.close()
    return {'valid': True, 'reason': ''}


def use_invite_code(code: str, user_id: int) -> bool:
    """使用邀请码（增加已用次数）"""
    conn = get_connection()
    cursor = conn.cursor()
    
    validation = validate_invite_code(code)
    if not validation['valid']:
        conn.close()
        return False
    
    cursor.execute('UPDATE invite_codes SET used_count = used_count + 1 WHERE code = ?',
                   (code.strip().upper(),))
    
    # 记录使用日志
    cursor.execute('''
        INSERT INTO invite_code_logs (code, user_id, used_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (code.strip().upper(), user_id))
    
    conn.commit()
    conn.close()
    return True


def get_invite_codes_list(page: int = 1, per_page: int = 20) -> dict:
    """获取邀请码列表（管理员用）"""
    conn = get_connection()
    cursor = conn.cursor()
    
    offset = (page - 1) * per_page
    cursor.execute('SELECT COUNT(*) FROM invite_codes')
    total = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT ic.id, ic.code, ic.max_uses, ic.used_count, ic.is_active,
               ic.note, ic.expires_at, ic.created_at, u.name as created_by_name
        FROM invite_codes ic
        LEFT JOIN users u ON ic.created_by = u.id
        ORDER BY ic.created_at DESC
        LIMIT ? OFFSET ?
    ''', (per_page, offset))
    
    codes = []
    for r in cursor.fetchall():
        # 检查是否过期
        is_expired = False
        if r[6]:  # expires_at
            cursor.execute("SELECT datetime('now') > ?", (r[6],))
            is_expired = cursor.fetchone()[0]
        
        codes.append({
            'id': r[0],
            'code': r[1],
            'max_uses': r[2],
            'used_count': r[3],
            'remaining': max(0, r[2] - r[3]) if r[2] > 0 else -1,  # -1 = unlimited
            'is_active': r[4],
            'is_expired': is_expired,
            'note': r[5],
            'expires_at': r[6],
            'created_at': r[7],
            'created_by_name': r[8]
        })
    
    conn.close()
    return {'codes': codes, 'total': total, 'page': page, 'per_page': per_page}


def delete_invite_code(code_id: int) -> bool:
    """删除邀请码"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM invite_codes WHERE id = ?', (code_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def toggle_invite_code_status(code_id: int) -> bool:
    """启用/禁用邀请码"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE invite_codes SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?',
                   (code_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_invite_code_stats() -> dict:
    """获取邀请码统计"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM invite_codes')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM invite_codes WHERE is_active = 1')
    active = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(used_count) FROM invite_codes')
    total_used = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM invite_code_logs')
    unique_users = cursor.fetchone()[0]
    
    conn.close()
    return {
        'total': total,
        'active': active,
        'total_used': total_used,
        'unique_users': unique_users
    }
