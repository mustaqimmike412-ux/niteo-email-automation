"""
邮件规范（Email Guidelines）数据模型
存储 AI 生成邮件时必须遵循的规则和约束
支持多用户各自独立的邮件规范
"""
from database.connection import get_connection


DEFAULT_GUIDELINES = """## Sender Introduction (MANDATORY)
- MUST introduce yourself at the start, but VARY the phrasing each time. Pick ONE from these templates (do NOT use the same template for every email):
  1. "My name is Travis, and I am the Business Development Manager at Niteo Solar."
  2. "I'm Travis, Business Development Manager at Niteo Solar."
  3. "This is Travis from Niteo Solar — I handle business development here."
  4. "I'm Travis with Niteo Solar, reaching out about a potential collaboration."
  5. "My name is Travis, Business Development Manager at Niteo Solar. I came across {Company Name} while researching {industry} solutions."
- Include your name (Travis) and your title in the introduction, never skip this.
- The introduction should feel natural, not forced — weave it into the opening of the email.

## Greeting Rules (MANDATORY)
- For personal emails with a known contact name: VARY the greeting — rotate among:
  - "Hi {First Name}," (most common)
  - "Hello {First Name},"
  - "Good day {First Name},"
  NEVER use "Dear", "Hey", or leave it blank. NEVER use "Hi" alone without the name.
- For public/company emails: VARY the greeting — rotate among:
  - "Hi {Company Name} Team,"
  - "Hello {Company Name} Team,"
  - "Greetings {Company Name},"
  NEVER use just "Hi" or "Hello" without the company name.

## Spam Avoidance (CRITICAL — emails that trigger spam filters will be rejected)
- NEVER use these words/phrases in subject lines or body: "Free", "Discount", "Special offer", "Limited time", "Act now", "Click here", "Urgent", "100%", "Risk free", "No cost", "Best price", "Lowest price", "Guaranteed", "Winner", "Selected", "Exclusive", "Don't miss", "Last chance", "Order now", "Buy now", "Save big", "Amazing", "Incredible", "Revolutionary"
- NEVER use excessive punctuation (!!!, ???, $$$)
- NEVER use ALL CAPS for emphasis (use bold/italic sparingly if needed)
- NEVER use "This is not spam" or similar disclaimers
- Keep subject lines under 60 characters
- Do NOT include pricing, discount percentages, or "$" amounts in cold emails
- Do NOT use pressure tactics ("Don't wait", "Before it's too late", "Time is running out")
- Keep email body concise (under 250 words for cold outreach)

## Tone & Style
- Write in professional business American English.
- Be direct, concise, and specific to the recipient's business.
- MUST NOT use generic openers like "How are you", "I hope this email finds you well", "Hope you're doing well".
- Avoid cliché phrases like "We are a leading manufacturer", "We have X years of experience" in the opening.
- Write as if you are a real person writing to another real person — avoid template-sounding language.

## Content Rules
- Focus on how our solar solutions benefit THEIR specific business.
- MUST mention the customer company name and at least one of their core products in the email body.
- Use the FABE points as the core value proposition.
- Address their specific pain points with concrete solutions.
- MUST end with a complete CTA (call-to-action) and do NOT truncate the email.

## Closing & Signature
- Closing line: VARY among — "Best regards,", "Kind regards,", "Regards,", "Thank you," (pick one, don't always use "Best regards,")
- Then left-aligned, each on its own line:
  Travis
  Business Development Manager
  Niteo Solar
  www.niteowork.com"""


def init_email_guidelines_table():
    """初始化邮件规范表（支持多用户）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_guidelines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id)
        )
    ''')
    conn.commit()
    conn.close()


def get_email_guidelines(user_id=None):
    """
    获取指定用户的邮件规范
    
    Args:
        user_id: 用户ID，如果为None则返回第一条（向后兼容）
    
    Returns:
        dict: {content, is_active, updated_at} 或 None
    """
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute('SELECT content, is_active, updated_at FROM email_guidelines WHERE user_id = ?', (user_id,))
    else:
        cursor.execute('SELECT content, is_active, updated_at FROM email_guidelines LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'content': row[0],
            'is_active': bool(row[1]),
            'updated_at': row[2]
        }
    return None


def get_or_create_guidelines(user_id):
    """
    获取用户的邮件规范，如果不存在则创建默认规范
    
    Args:
        user_id: 用户ID
    
    Returns:
        dict: {content, is_active, updated_at}
    """
    existing = get_email_guidelines(user_id)
    if existing:
        return existing
    
    # 为该用户创建默认规范
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO email_guidelines (user_id, content, is_active)
        VALUES (?, ?, 1)
    ''', (user_id, DEFAULT_GUIDELINES))
    conn.commit()
    conn.close()
    return {
        'content': DEFAULT_GUIDELINES,
        'is_active': True,
        'updated_at': None
    }


def update_email_guidelines(content, is_active=True, user_id=None):
    """
    更新邮件规范
    
    Args:
        content: 规则文本
        is_active: 是否启用
        user_id: 用户ID
    """
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute('''
            INSERT INTO email_guidelines (user_id, content, is_active, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                content = excluded.content,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
        ''', (user_id, content, 1 if is_active else 0))
    else:
        # 向后兼容：更新第一条
        cursor.execute('''
            INSERT INTO email_guidelines (user_id, content, is_active, updated_at)
            VALUES (0, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                content = excluded.content,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
        ''', (content, 1 if is_active else 0))
    conn.commit()
    conn.close()
    return True


def get_active_guidelines_text(user_id=None):
    """
    获取当前启用的规范文本（用于注入 prompt）
    
    Args:
        user_id: 用户ID，如果为None则使用默认规范
    
    Returns:
        str: 规范文本
    """
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute('SELECT content FROM email_guidelines WHERE user_id = ? AND is_active = 1', (user_id,))
    else:
        cursor.execute('SELECT content FROM email_guidelines WHERE is_active = 1 LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else DEFAULT_GUIDELINES


def migrate_to_multi_user():
    """
    数据库迁移：将旧的 id=1 单条记录转为 user_id=0 的记录
    支持平滑升级
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 检查是否有旧的 id 列
    cursor.execute("PRAGMA table_info(email_guidelines)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'id' in columns and 'user_id' not in columns:
        # 旧表结构，需要迁移
        print("[email_guidelines] 检测到旧表结构，执行迁移...")
        
        # 读取旧数据
        cursor.execute('SELECT content, is_active FROM email_guidelines WHERE id = 1')
        old_row = cursor.fetchone()
        old_content = old_row[0] if old_row else DEFAULT_GUIDELINES
        old_active = old_row[1] if old_row else 1
        
        # 重建表
        cursor.execute('DROP TABLE IF EXISTS email_guidelines')
        cursor.execute('''
            CREATE TABLE email_guidelines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
        ''')
        
        # 将旧数据存为 user_id=0（系统默认）
        cursor.execute('''
            INSERT INTO email_guidelines (user_id, content, is_active)
            VALUES (0, ?, ?)
        ''', (old_content, old_active))
        
        conn.commit()
        print("[email_guidelines] 迁移完成：旧 id=1 记录 → user_id=0")
    
    conn.close()
