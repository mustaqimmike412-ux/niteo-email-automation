"""
DSN 退信邮件解析器
基于 Python 标准库 email 模块，零依赖解析 RFC 3464 multipart/report 退信通知
"""
from email import policy
from email.parser import BytesParser
from email.header import decode_header
from email.message import Message
from typing import List, Optional, Dict


def is_bounce_email(msg: Message) -> bool:
    """快速判断是否为退信邮件"""
    ct = msg.get_content_type()
    if ct == 'multipart/report':
        return True
    # 非标准退信：通过 Subject 和 From 启发式判断
    subject = get_decoded_header(msg, 'Subject', '').lower()
    from_addr = (msg.get('From', '') or '').lower()
    bounce_subjects = [
        'delivery status notification', 'undelivered', 'returned mail',
        'failure notice', 'mail delivery failed', 'undeliverable',
        'delivery failure', 'returned to sender', '退信', '无法投递'
    ]
    bounce_senders = ['mailer-daemon', 'postmaster', 'mail-daemon']
    subject_match = any(kw in subject for kw in bounce_subjects)
    sender_match = any(s in from_addr for s in bounce_senders)
    return subject_match and sender_match


def parse_bounce_email(raw_bytes: bytes) -> Optional[Dict]:
    """
    解析退信邮件，返回结构化信息
    返回 None 表示非退信邮件
    """
    msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)

    if not is_bounce_email(msg):
        return None

    recipients_info = []
    # 查找 message/delivery-status 部分
    for part in msg.walk():
        if part.get_content_type() == 'message/delivery-status':
            payload = part.get_payload()
            if isinstance(payload, list):
                for sub in payload:
                    if isinstance(sub, Message):
                        info = _extract_dsn_fields(sub)
                        if info and info.get('recipient'):
                            recipients_info.append(info)
            elif isinstance(payload, Message):
                info = _extract_dsn_fields(payload)
                if info and info.get('recipient'):
                    recipients_info.append(info)

    if not recipients_info:
        # 兜底：尝试从正文正则提取邮箱
        recipient = _extract_email_from_body(msg)
        if recipient:
            recipients_info.append({
                'recipient': recipient,
                'action': 'failed',
                'status_code': '',
                'diagnostic_code': '',
                'remote_mta': '',
                'bounce_type': 'unknown'
            })
        else:
            return None

    # 提取原始邮件的 To 和 Subject（用于关联发送记录）
    original_to = None
    original_subject = None
    for part in msg.walk():
        if part.get_content_type() == 'message/rfc822':
            orig = part.get_payload()
            if isinstance(orig, list) and orig:
                orig = orig[0]
            if isinstance(orig, Message):
                original_to = get_decoded_header(orig, 'To', '')
                original_subject = get_decoded_header(orig, 'Subject', '')
            break

    # 提取人类可读部分
    raw_snippet = _extract_readable_snippet(msg)

    return {
        'recipients': recipients_info,
        'original_to': original_to,
        'original_subject': original_subject,
        'bounce_subject': get_decoded_header(msg, 'Subject', ''),
        'bounce_from': get_decoded_header(msg, 'From', ''),
        'bounce_date': get_decoded_header(msg, 'Date', ''),
        'message_id': msg.get('Message-ID', ''),
        'raw_snippet': raw_snippet[:2000]
    }


def get_decoded_header(msg: Message, header: str, default: str = '') -> str:
    """解码邮件头，处理编码问题"""
    raw = msg.get(header, default)
    if not raw:
        return default
    parts = decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded.append(part)
    return ''.join(decoded)


def _extract_dsn_fields(dsn_part: Message) -> Dict:
    """从 DSN 单个收件人部分提取字段"""
    final_recipient = dsn_part.get('Final-Recipient', '')
    diagnostic_code = dsn_part.get('Diagnostic-Code', '')
    action = dsn_part.get('Action', '').strip().lower()
    status = dsn_part.get('Status', '').strip()
    remote_mta = dsn_part.get('Remote-MTA', '')

    # 提取邮箱地址（格式 "rfc822; user@domain.com"）
    email_addr = final_recipient
    if ';' in final_recipient:
        email_addr = final_recipient.split(';', 1)[1].strip().lower()
    email_addr = email_addr.strip('<>').strip()

    if not email_addr or '@' not in email_addr:
        return None

    bounce_type = _classify_bounce(status, diagnostic_code)

    return {
        'recipient': email_addr,
        'action': action,
        'status_code': status,
        'diagnostic_code': diagnostic_code,
        'remote_mta': remote_mta,
        'bounce_type': bounce_type
    }


def _classify_bounce(status_code: str, diagnostic_code: str) -> str:
    """退信类型分类：hard / soft / unknown"""
    status = status_code.strip()
    diag = diagnostic_code.strip().lower()

    # 硬退信
    hard_patterns = [
        status.startswith('5.1.1'),  # 收件人不存在
        status.startswith('5.1.2'),  # 域名不存在
        status.startswith('5.7.1'),  # 被拒收
        'user unknown' in diag,
        'recipient not found' in diag,
        'no such user' in diag,
        'account does not exist' in diag,
        'mailbox unavailable' in diag,
        'permanent failure' in diag,
        '550' in diag and ('5.1.1' in diag or 'no such user' in diag),
    ]
    if any(hard_patterns):
        return 'hard'

    # 软退信
    soft_patterns = [
        status.startswith('4.'),     # 临时性错误
        status.startswith('5.2.1'),  # 邮箱已满
        status.startswith('5.2.2'),  # 邮箱超限
        status.startswith('5.4.4'),  # 主机不可达
        status.startswith('5.5.0'),  # 语法错误
        'mailbox full' in diag,
        'quota exceeded' in diag,
        'temporary failure' in diag,
        'retry' in diag,
        'greylist' in diag,
    ]
    if any(soft_patterns):
        return 'soft'

    return 'unknown'


def _extract_email_from_body(msg: Message) -> Optional[str]:
    """兜底：从邮件正文提取退回的邮箱地址"""
    import re
    for part in msg.walk():
        if part.get_content_type() in ('text/plain', 'text/html'):
            try:
                body = part.get_content_text()
                # 匹配 "to: xxx@xxx.com" 或 "<xxx@xxx.com>" 格式
                patterns = [
                    r'[Tt][Oo]:\s*<([^>]+)>',
                    r'[Tt][Oo]:\s*(\S+@\S+)',
                    r'<(\S+@\S+)>',
                ]
                for p in patterns:
                    m = re.search(p, body[:3000])
                    if m:
                        addr = m.group(1).lower()
                        if '@' in addr:
                            return addr
            except Exception:
                continue
    return None


def _extract_readable_snippet(msg: Message) -> str:
    """提取退信邮件中人类可读的部分"""
    for part in msg.walk():
        if part.get_content_type() == 'text/plain':
            try:
                return part.get_content_text()
            except Exception:
                continue
    return ''
