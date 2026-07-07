import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'email_automation.db')


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    conn.execute('PRAGMA foreign_keys=ON')  # 启用外键约束，确保级联删除生效
    return conn
