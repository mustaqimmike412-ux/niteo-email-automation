import smtplib
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid, parseaddr
import json
import os
import time
import socket
from datetime import datetime, timedelta
from database.connection import get_connection

class EmailSender:
    def __init__(self, config_file='config/smtp_config.json', user_id=None):
        self.config = self._load_config(config_file, user_id=user_id)

    def _load_config(self, config_file, user_id=None):
        """加载SMTP配置：优先从数据库读取用户配置，其次本地文件"""
        # 优先从数据库 user_settings 加载
        if user_id:
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT setting_json FROM user_settings WHERE user_id = ? AND setting_type = 'smtp' ORDER BY updated_at DESC LIMIT 1",
                    (user_id,)
                )
                row = cursor.fetchone()
                conn.close()
                if row:
                    db_config = json.loads(row[0])
                    # 统一字段名映射（数据库字段 → 代码使用的字段名）
                    return {
                        "smtp_server": db_config.get("smtp_server", db_config.get("smtp_host", "")),
                        "smtp_port": db_config.get("smtp_port", 465),
                        "username": db_config.get("sender_email", db_config.get("smtp_username", "")),
                        "password": db_config.get("password", ""),
                        "sender_name": db_config.get("sender_name", ""),
                        "sender_email": db_config.get("sender_email", ""),
                        "use_ssl": db_config.get("use_ssl", True),
                        "use_tls": db_config.get("use_tls", False),
                    }
            except Exception:
                pass

        # 其次尝试从最新用户的数据库配置加载（兼容不传user_id的场景）
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT setting_json FROM user_settings WHERE setting_type = 'smtp' ORDER BY updated_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                db_config = json.loads(row[0])
                return {
                    "smtp_server": db_config.get("smtp_server", db_config.get("smtp_host", "")),
                    "smtp_port": db_config.get("smtp_port", 465),
                    "username": db_config.get("sender_email", db_config.get("smtp_username", "")),
                    "password": db_config.get("password", ""),
                    "sender_name": db_config.get("sender_name", ""),
                    "sender_email": db_config.get("sender_email", ""),
                    "use_ssl": db_config.get("use_ssl", True),
                    "use_tls": db_config.get("use_tls", False),
                }
        except Exception:
            pass

        # 最后回退到本地配置文件
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, config_file)
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "your_email@gmail.com",
                "password": "your_app_password",
                "sender_name": "Your Name",
                "sender_email": "your_email@gmail.com",
                "use_tls": True
            }
    
    def record_subject_usage(self, customer_id, email_id, subject_id, subject_line, conn=None):
        """记录主题使用情况"""
        own_conn = conn is None
        if own_conn:
            conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO subject_usage_log
            (customer_id, email_id, subject_id, subject_line, used_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (customer_id, email_id, subject_id, subject_line, datetime.now()))

        if own_conn:
            conn.commit()
            conn.close()
    
    def send_email(self, to_email, subject, body, email_type='personal', source='manual'):
        """发送单封邮件
        source: 'manual' | 'scheduled' | 'batch' | 'cli'
        """
        try:
            # 创建邮件
            msg = MIMEMultipart('alternative')

            # 使用 formataddr 正确编码发件人名称（避免被标记为垃圾邮件）
            sender_name = self.config.get('sender_name', '')
            sender_email = self.config.get('sender_email', '')
            _, sender_domain = parseaddr(sender_email)
            msg['From'] = formataddr((sender_name, sender_email))
            msg['To'] = to_email
            msg['Subject'] = Header(subject, 'utf-8')
            msg['Date'] = formatdate(localtime=True)
            msg['Message-ID'] = make_msgid(domain=sender_domain if sender_domain else 'localhost')
            msg['MIME-Version'] = '1.0'

            # Reply-To 使用发件邮箱
            msg['Reply-To'] = sender_email

            # 反垃圾邮件关键头部
            msg['X-Mailer'] = 'TradeLink Mail Client'
            msg['X-Priority'] = '3'  # 普通优先级，不要设1（高优先级容易被过滤）
            msg['X-Auto-Response-Suppress'] = 'All'  # 防止自动回复循环

            # 预退信头（RFC 8058），提高送达率
            # 同时提供 mailto 和 HTTPS 两种退订方式
            msg['List-Unsubscribe'] = '<mailto:%s?subject=unsubscribe>, <https://exim-flow.com/unsubscribe>' % sender_email
            msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
            msg['Feedback-ID'] = 'tradelink:%s' % (str(int(time.time()))[-8:])

            # 添加邮件正文
            html_body = self._text_to_html(body, sender_name=sender_name)
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            # 根据配置选择连接方式
            if self.config.get('use_ssl', False):
                server = smtplib.SMTP_SSL(self.config['smtp_server'], self.config['smtp_port'])
            else:
                server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
                if self.config.get('use_tls', True):
                    server.starttls()

            server.login(self.config['username'], self.config['password'])

            # 发送并检查SMTP响应码
            send_result = server.send_message(msg)
            server.quit()

            # 检查每个收件人的SMTP响应
            if send_result:
                for recipient, (code, resp_msg) in send_result.items():
                    if code is not None and (code < 200 or code >= 300):
                        error_detail = f"SMTP返回错误码 {code}: {resp_msg.decode('utf-8', 'replace') if isinstance(resp_msg, bytes) else resp_msg}"
                        print(f"  ⚠ SMTP投递失败 [{to_email}]: {error_detail}")
                        return False, error_detail
                    else:
                        print(f"  ✓ SMTP投递成功 [{to_email}]: code={code}")
            else:
                print(f"  ✓ SMTP投递成功 [{to_email}] (无详细响应)")

            return True, "发送成功"

        except Exception as e:
            error_str = str(e)
            # SMTP发送失败时自动处理退信
            try:
                from services.bounce_handler import handle_smtp_failure
                result = handle_smtp_failure(to_email, error_str)
                if result['action'] == 'disabled':
                    error_str += f" (退信：已自动禁用该邮箱)"
                elif result['action'] == 'incremented':
                    error_str += f" (退信：软退信计数+1)"
            except Exception:
                pass
            return False, f"发送失败: {error_str}"

    def _text_to_html(self, text, sender_name=''):
        """将纯文本转换为专业HTML格式（模拟自然手写邮件结构，降低垃圾邮件评分）"""
        lines = text.strip().split('\n')
        # 合并空行作为段落分隔，连续非空行合并为一个段落
        paragraphs = []
        current_para = []
        for line in lines:
            if not line.strip():
                if current_para:
                    paragraphs.append(' '.join(current_para))
                    current_para = []
            else:
                current_para.append(line.strip())
        if current_para:
            paragraphs.append(' '.join(current_para))

        # 生成段落HTML（自然的段落间距）
        html_paragraphs = []
        for para in paragraphs:
            escaped = para.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            html_paragraphs.append(
                f'<p style="margin:0 0 14px 0;line-height:1.65;color:#333;font-size:14px;">{escaped}</p>'
            )

        body_content = '\n'.join(html_paragraphs)
        brand = sender_name or 'TradeLink'
        html = f"""<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,Helvetica,sans-serif;line-height:1.65;color:#333;background:#ffffff;margin:0;padding:20px;">
<div style="max-width:600px;margin:0 auto;font-size:14px;">
{body_content}
<div style="margin-top:24px;padding-top:16px;border-top:1px solid #eee;">
<p style="margin:0;font-size:12px;color:#999;">{brand}</p>
</div>
</div>
</body>
</html>"""
        return html
    

    
    def get_statistics(self, user_id=None):
        """获取发送统计信息

        Args:
            user_id: 用户ID，用于数据隔离。为None时返回全局统计（管理员视图）。
        """
        conn = get_connection()
        cursor = conn.cursor()

        # 构建 user_id 过滤条件
        user_filter = ""
        params_prefix = []
        if user_id is not None:
            user_filter = "AND user_id = ?"
            params_prefix = [user_id]

        cursor.execute(
            f"SELECT COUNT(*) FROM email_logs WHERE send_status = 'sent' {user_filter}",
            params_prefix
        )
        total_sent = cursor.fetchone()[0]

        cursor.execute(
            f"SELECT COUNT(*) FROM email_logs WHERE send_status = 'sent' AND date(sent_at) = date('now') {user_filter}",
            params_prefix
        )
        today_sent = cursor.fetchone()[0]

        cursor.execute(
            f"SELECT COUNT(*) FROM email_logs WHERE send_status = 'failed' {user_filter}",
            params_prefix
        )
        total_failed = cursor.fetchone()[0]

        # type_stats 查询需要通过 customers 表获取 user_id
        if user_id is not None:
            cursor.execute('''
                SELECT e.email_type, COUNT(*)
                FROM email_logs el
                JOIN emails e ON el.email_id = e.id
                JOIN customers c ON e.customer_id = c.id
                WHERE el.send_status = 'sent' AND c.user_id = ?
                GROUP BY e.email_type
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT e.email_type, COUNT(*)
                FROM email_logs el
                JOIN emails e ON el.email_id = e.id
                WHERE el.send_status = 'sent'
                GROUP BY e.email_type
            ''')
        type_stats = cursor.fetchall()

        conn.close()

        return {
            'total_sent': total_sent,
            'today_sent': today_sent,
            'total_failed': total_failed,
            'type_stats': type_stats
        }

def create_config_template():
    """创建配置文件模板"""
    config = {
        "smtp_server": "smtp.qiye.aliyun.com",
        "smtp_port": 465,
        "username": "travis@niteowork.com",
        "password": "YOUR_APP_PASSWORD_HERE",
        "sender_name": "travis",
        "sender_email": "travis@niteowork.com",
        "use_tls": False,
        "use_ssl": True,
        "daily_limit": 50,
        "send_interval": 30
    }
    
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
    os.makedirs(config_dir, exist_ok=True)
    
    config_path = os.path.join(config_dir, 'smtp_config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    
    print(f"SMTP配置文件已创建: {config_path}")

if __name__ == '__main__':
    create_config_template()
