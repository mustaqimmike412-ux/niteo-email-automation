"""
邮件规范（Email Guidelines）数据模型
存储 AI 生成邮件时必须遵循的规则和约束
"""
from database.connection import get_connection


DEFAULT_GUIDELINES = """## Sender Introduction (MANDATORY)
- ALWAYS start by introducing yourself: "My name is Travis, and I am the Business Development Manager at Niteo Solar."
- Include your name (Travis) and your title in the introduction, never skip this.
- The introduction should feel natural, not forced — weave it into the opening of the email.

## Greeting Rules (MANDATORY)
- For personal emails with a known contact name: "Hi {First Name}," — MUST use the actual first name, never "Hi" alone.
- For public/company emails: "Hi {Company Name} Team," — MUST include the company name, never just "Hi" or "Hello".
- NEVER use "Dear", "Hello", "Hey", or any other greeting besides "Hi".
- NEVER leave the greeting blank or use a generic greeting without a name.

## Tone & Style
- Write in professional business American English.
- Be direct, concise, and specific to the recipient's business.
- MUST NOT use generic openers like "How are you", "I hope this email finds you well", "Hope you're doing well", "I came across your website".
- Avoid cliché phrases like "We are a leading manufacturer", "We have X years of experience" in the opening.

## Content Rules
- Focus on how our solar solutions benefit THEIR specific business.
- MUST mention the customer company name and at least one of their core products in the email body.
- Use the FABE points as the core value proposition.
- Address their specific pain points with concrete solutions.
- MUST end with a complete CTA (call-to-action) and do NOT truncate the email.

## Closing & Signature (FIXED order, NEVER change)
- Closing line: "Best regards," (exactly this, nothing else)
- Then left-aligned, each on its own line:
  Travis
  Business Development Manager
  Niteo Solar"""


def init_email_guidelines_table():
    """初始化邮件规范表"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_guidelines (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            content TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 插入默认规则（如果不存在）
    cursor.execute('SELECT COUNT(*) FROM email_guidelines WHERE id = 1')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO email_guidelines (id, content, is_active) VALUES (1, ?, 1)
        ''', (DEFAULT_GUIDELINES,))
    conn.commit()
    conn.close()


def get_email_guidelines():
    """获取当前邮件规范（单条记录）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT content, is_active, updated_at FROM email_guidelines WHERE id = 1')
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'content': row[0],
            'is_active': bool(row[1]),
            'updated_at': row[2]
        }
    return None


def update_email_guidelines(content, is_active=True):
    """更新邮件规范"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO email_guidelines (id, content, is_active, updated_at)
        VALUES (1, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            content = excluded.content,
            is_active = excluded.is_active,
            updated_at = excluded.updated_at
    ''', (content, 1 if is_active else 0))
    conn.commit()
    conn.close()
    return True


def get_active_guidelines_text():
    """获取当前启用的规范文本（用于注入 prompt）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT content FROM email_guidelines WHERE id = 1 AND is_active = 1')
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else DEFAULT_GUIDELINES
