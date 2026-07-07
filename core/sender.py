import smtplib
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import json
import os
from datetime import datetime, timedelta
from database.connection import get_connection

class EmailSender:
    def __init__(self, config_file='config/smtp_config.json'):
        self.config = self._load_config(config_file)
    
    def _load_config(self, config_file):
        """加载SMTP配置"""
        # 从项目根目录查找配置文件（sender.py 在 core/ 子目录中）
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
            msg['Subject'] = Header(subject, 'utf-8')
            msg['From'] = f"{self.config['sender_name']} <{self.config['sender_email']}>"
            msg['To'] = to_email
            
            # 添加邮件正文
            html_body = self._text_to_html(body)
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
            server.send_message(msg)
            server.quit()
            
            return True, "发送成功"
            
        except Exception as e:
            return False, f"发送失败: {str(e)}"
    
    def _text_to_html(self, text):
        """将纯文本转换为HTML格式"""
        html = text.replace('\n', '<br>')
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                {html}
            </div>
        </body>
        </html>
        """
        return html
    

    
    def get_statistics(self):
        """获取发送统计信息"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM email_logs WHERE send_status = 'sent'")
        total_sent = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM email_logs WHERE send_status = 'sent' AND date(sent_at) = date('now')")
        today_sent = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM email_logs WHERE send_status = 'failed'")
        total_failed = cursor.fetchone()[0]
        
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
