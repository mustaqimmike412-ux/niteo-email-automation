"""
IMAP 退信检查器
通过 IMAP 连接阿里企业邮箱收件箱，搜索并解析退信通知邮件
"""
import imaplib
import json
import os
from email import policy as email_policy
from email.parser import BytesParser
from email.header import decode_header
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from services.bounce_parser import parse_bounce_email, is_bounce_email
from database.bounce_service import (
    save_bounce_log, update_email_log_bounce, get_processed_message_ids
)
from database.connection import get_connection


class IMAPBounceChecker:
    def __init__(self, config_file='config/imap_config.json'):
        self.config = self._load_config(config_file)

    def _load_config(self, config_file):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, config_file)
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def is_available(self) -> bool:
        return self.config is not None

    def check_connection(self) -> Dict:
        """测试 IMAP 连接是否正常"""
        if not self.is_available():
            return {'ok': False, 'error': 'IMAP 配置文件不存在'}
        try:
            if self.config.get('use_ssl', True):
                mail = imaplib.IMAP4_SSL(self.config['imap_server'], self.config['imap_port'])
            else:
                mail = imaplib.IMAP4(self.config['imap_server'], self.config['imap_port'])
            mail.login(self.config['username'], self.config['password'])
            mail.select(self.config.get('check_folder', 'INBOX'))
            status, data = mail.search(None, 'ALL')
            count = len(data[0].split()) if data[0] else 0
            mail.logout()
            return {'ok': True, 'total_emails': count}
        except imaplib.IMAP4.error as e:
            return {'ok': False, 'error': f'IMAP 登录失败: {str(e)}'}
        except Exception as e:
            return {'ok': False, 'error': f'连接失败: {str(e)}'}

    def check_bounces(self) -> Dict:
        """执行一次退信检查，返回统计结果"""
        if not self.is_available():
            return {'checked': 0, 'found': 0, 'saved': 0, 'error': 'IMAP 未配置'}

        try:
            if self.config.get('use_ssl', True):
                mail = imaplib.IMAP4_SSL(self.config['imap_server'], self.config['imap_port'])
            else:
                mail = imaplib.IMAP4(self.config['imap_server'], self.config['imap_port'])
            mail.login(self.config['username'], self.config['password'])
            mail.select(self.config.get('check_folder', 'INBOX'))

            # 搜索最近 7 天的邮件
            since_date = (datetime.now() - timedelta(days=7)).strftime('%d-%b-%Y')
            _, message_ids = mail.search(None, f'(SINCE {since_date})')

            if not message_ids[0]:
                mail.logout()
                return {'checked': 0, 'found': 0, 'saved': 0}

            id_list = message_ids[0].split()
            max_check = self.config.get('max_emails_per_check', 50)
            if len(id_list) > max_check:
                id_list = id_list[-max_check:]  # 检查最新的

            processed = get_processed_message_ids()
            keywords = [kw.lower() for kw in self.config.get('bounce_subject_keywords', [])]
            sender_patterns = [p.lower() for p in self.config.get('bounce_sender_patterns', [])]

            checked = 0
            found = 0
            saved = 0

            for mid in id_list:
                checked += 1
                _, data = mail.fetch(mid, '(RFC822)')
                if not data or not data[0] or not data[0][1]:
                    continue

                raw_email = data[0][1]
                if isinstance(raw_email, str):
                    raw_email = raw_email.encode('utf-8')

                # 快速过滤：检查 Subject 和 From
                msg = BytesParser(policy=email_policy.default).parsebytes(raw_email)
                subject = self._decode_header(msg.get('Subject', '')).lower()
                from_addr = msg.get('From', '').lower()

                subject_match = any(kw in subject for kw in keywords)
                sender_match = any(p in from_addr for p in sender_patterns)

                if not subject_match and not sender_match:
                    continue

                # 检查 Message-ID 是否已处理
                msg_id = msg.get('Message-ID', '')
                if msg_id and msg_id in processed:
                    continue

                # 解析退信
                result = parse_bounce_email(raw_email)
                if not result:
                    continue

                found += 1

                # 处理每个被退回的收件人
                for rec in result.get('recipients', []):
                    # 尝试匹配原始发送记录
                    log_id = update_email_log_bounce(
                        rec['recipient'],
                        rec['bounce_type'],
                        result.get('original_subject')
                    )

                    # 查找关联的 email_id 和 customer_id
                    email_id, customer_id = self._find_email_customer(rec['recipient'])

                    save_bounce_log({
                        'message_id': msg_id,
                        'email_log_id': log_id,
                        'email_id': email_id,
                        'customer_id': customer_id,
                        'bounce_type': rec['bounce_type'],
                        'recipient_email': rec['recipient'],
                        'original_subject': result.get('original_subject'),
                        'diagnostic_code': rec.get('diagnostic_code'),
                        'status_code': rec.get('status_code'),
                        'action': rec.get('action'),
                        'bounce_subject': result.get('bounce_subject'),
                        'bounce_from': result.get('bounce_from'),
                        'raw_snippet': result.get('raw_snippet', ''),
                        'matched_log': 1 if log_id else 0
                    })
                    saved += 1

            mail.logout()
            print(f"[BounceChecker] 检查 {checked} 封, 发现 {found} 封退信, 保存 {saved} 条记录")
            return {'checked': checked, 'found': found, 'saved': saved}

        except imaplib.IMAP4.error as e:
            return {'checked': 0, 'found': 0, 'saved': 0, 'error': f'IMAP 错误: {str(e)}'}
        except Exception as e:
            print(f"[BounceChecker] 异常: {e}")
            return {'checked': 0, 'found': 0, 'saved': 0, 'error': str(e)}

    def _find_email_customer(self, recipient_email: str):
        """根据邮箱地址查找 email_id 和 customer_id"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT e.id, e.customer_id FROM emails e
                WHERE e.email_address = ? LIMIT 1
            ''', (recipient_email,))
            row = cursor.fetchone()
            conn.close()
            return (row[0], row[1]) if row else (None, None)
        except Exception:
            return (None, None)

    def _decode_header(self, raw: str) -> str:
        """解码邮件头"""
        if not raw:
            return ''
        parts = decode_header(raw)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or 'utf-8', errors='replace'))
            else:
                decoded.append(part)
        return ''.join(decoded)


def create_bounce_checker() -> IMAPBounceChecker:
    return IMAPBounceChecker()
