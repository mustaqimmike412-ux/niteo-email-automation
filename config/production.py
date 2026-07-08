"""
生产环境配置
所有敏感信息通过环境变量传入，避免明文存储在代码中
"""
import os

# Flask 基础配置
DEBUG = False
SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())

# 数据库路径（生产环境固定位置）
DATABASE_PATH = os.environ.get(
    'DATABASE_PATH',
    '/var/www/email_automation/database/email_automation.db'
)

# SMTP 配置（从环境变量读取，覆盖本地配置文件）
SMTP_CONFIG = {
    'smtp_server': os.environ.get('SMTP_SERVER', 'smtp.qiye.aliyun.com'),
    'smtp_port': int(os.environ.get('SMTP_PORT', 465)),
    'sender_email': os.environ.get('SENDER_EMAIL', ''),
    'sender_password': os.environ.get('SMTP_PASSWORD', ''),
    'use_ssl': os.environ.get('SMTP_USE_SSL', 'true').lower() == 'true'
}

# IMAP 配置（退信检查）
IMAP_CONFIG = {
    'imap_server': os.environ.get('IMAP_SERVER', 'imap.qiye.aliyun.com'),
    'imap_port': int(os.environ.get('IMAP_PORT', 993)),
    'use_ssl': os.environ.get('IMAP_USE_SSL', 'true').lower() == 'true',
    'username': os.environ.get('IMAP_USERNAME', SMTP_CONFIG['sender_email']),
    'password': os.environ.get('IMAP_PASSWORD', SMTP_CONFIG['sender_password'])
}

# API 配置（DeepSeek / Google Places）
API_CONFIGS = {
    'deepseek_api_key': os.environ.get('DEEPSEEK_API_KEY', ''),
    'deepseek_base_url': os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
    'deepseek_model': os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-pro'),
    'google_places_api_key': os.environ.get('GOOGLE_PLACES_API_KEY', '')
}

# Google OAuth 配置
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
OAUTH_REDIRECT_URI = os.environ.get('OAUTH_REDIRECT_URI', 'https://exim-flow.com/auth/google/callback')

# 发送间隔（秒）
SEND_INTERVAL = int(os.environ.get('SEND_INTERVAL', 120))
