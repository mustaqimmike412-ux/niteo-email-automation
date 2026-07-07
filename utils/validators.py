#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据验证模块
提供邮箱验证、重复检测、输入清理等功能
"""

import re
import html
from database.connection import get_connection

# 邮箱格式正则
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'.xlsx', '.xls', '.csv', '.docx'}

# 扩展名到 MIME 类型的映射
EXTENSION_TO_MIME = {
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls': 'application/vnd.ms-excel',
    '.csv': 'text/csv',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}

# 允许的文件MIME类型
ALLOWED_MIME_TYPES = set(EXTENSION_TO_MIME.values())

# 网站 URL 格式正则
WEBSITE_REGEX = re.compile(
    r'^https?://'
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
    r'localhost|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
    r'(?::\d+)?'
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

# 最大文件大小 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024


def validate_email(email):
    """
    验证邮箱格式
    返回: (is_valid: bool, error_message: str or None)
    """
    if not email or not isinstance(email, str):
        return False, "邮箱不能为空"

    email = email.strip()

    if len(email) > 254:
        return False, "邮箱长度不能超过254字符"

    if not EMAIL_REGEX.match(email):
        return False, "邮箱格式不正确"

    # 检查域名部分至少有一个点
    parts = email.split('@')
    if len(parts) != 2 or '.' not in parts[1]:
        return False, "邮箱域名格式不正确"

    return True, None


def validate_customer_name(name):
    """
    验证客户名称
    返回: (is_valid: bool, error_message: str or None)
    """
    if not name or not isinstance(name, str):
        return False, "客户名称不能为空"

    name = name.strip()

    if not name:
        return False, "客户名称不能为空"

    if len(name) > 200:
        return False, "客户名称不能超过200字符"

    return True, None


def validate_text_length(text, max_length, field_name="文本"):
    """
    验证文本长度
    """
    if text and len(text) > max_length:
        return False, f"{field_name}不能超过{max_length}字符"
    return True, None


def check_duplicate_customer_name(name, exclude_id=None):
    """
    检查客户名是否已存在（不区分大小写）
    返回: (is_duplicate: bool, existing_id: int or None)
    """
    conn = get_connection()
    cursor = conn.cursor()

    if exclude_id:
        cursor.execute(
            "SELECT id FROM customers WHERE LOWER(customer_name) = LOWER(?) AND id != ?",
            (name.strip(), exclude_id)
        )
    else:
        cursor.execute(
            "SELECT id FROM customers WHERE LOWER(customer_name) = LOWER(?)",
            (name.strip(),)
        )

    row = cursor.fetchone()
    conn.close()

    if row:
        return True, row[0]
    return False, None


def check_duplicate_email(email, customer_id=None):
    """
    检查邮箱是否已存在
    如果指定了customer_id，则只检查该客户下的邮箱
    返回: (is_duplicate: bool, existing_info: dict or None)
    """
    conn = get_connection()
    cursor = conn.cursor()

    if customer_id:
        cursor.execute(
            "SELECT id, customer_id FROM emails WHERE LOWER(email_address) = LOWER(?) AND customer_id = ?",
            (email.strip().lower(), customer_id)
        )
    else:
        cursor.execute(
            "SELECT id, customer_id FROM emails WHERE LOWER(email_address) = LOWER(?)",
            (email.strip().lower(),)
        )

    row = cursor.fetchone()
    conn.close()

    if row:
        return True, {'email_id': row[0], 'customer_id': row[1]}
    return False, None


def validate_file_upload(file_obj):
    """
    验证上传文件
    返回: (is_valid: bool, error_message: str or None)
    """
    import os

    if not file_obj:
        return False, "未选择文件"

    # 检查文件大小
    file_obj.seek(0, os.SEEK_END)
    file_size = file_obj.tell()
    file_obj.seek(0)

    if file_size > MAX_FILE_SIZE:
        return False, f"文件大小不能超过10MB"

    if file_size == 0:
        return False, "文件不能为空"

    # 检查扩展名
    filename = getattr(file_obj, 'filename', '')
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return False, f"不支持的文件格式: {ext}，请上传 {', '.join(ALLOWED_EXTENSIONS)} 格式的文件"

    # 检查文件头签名（防止扩展名伪造）
    header = file_obj.read(4)
    file_obj.seek(0)

    # ZIP 格式文件头 (xlsx, docx 都是 ZIP)
    if ext in ('.xlsx', '.docx'):
        if header[:2] != b'PK':
            return False, '文件格式与扩展名不匹配，请上传有效的 Office 文件'
    # CSV 文件头检查（CSV 没有固定签名，但至少确保不是可执行文件）
    elif ext == '.csv':
        # 检查是否包含常见的可执行文件签名
        executable_signatures = (b'MZ', b'\x7fELF', b'\xca\xfe\xba\xbe', b'\xcf\xfa\xed\xfe')
        if header.startswith(executable_signatures):
            return False, '文件格式异常，请不要上传可执行文件'
    # XLS 文件头检查
    elif ext == '.xls':
        if header[:8] != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            return False, '文件格式与扩展名不匹配，请上传有效的 Excel 文件'

    return True, None


def sanitize_text(text, max_length=None):
    """
    清理文本输入：去除首尾空白，并进行 HTML 实体编码防止 XSS
    """
    if text is None:
        return None

    if not isinstance(text, str):
        text = str(text)

    text = text.strip()
    text = html.escape(text)  # HTML 实体编码，防止 XSS

    if max_length and len(text) > max_length:
        text = text[:max_length]

    return text


def validate_website(url):
    """
    验证网站 URL 格式
    返回: (is_valid: bool, error_message: str or None)
    """
    if not url:
        return True, None
    if not WEBSITE_REGEX.match(url):
        return False, '网站 URL 格式无效，必须以 http:// 或 https:// 开头'
    return True, None


def validate_customer_data(data, is_update=False, customer_id=None):
    """
    验证客户数据（用于添加/更新）
    返回: (is_valid: bool, errors: dict)
    """
    errors = {}

    # 验证客户名称
    if 'customer_name' in data or not is_update:
        name = data.get('customer_name', '')
        valid, msg = validate_customer_name(name)
        if not valid:
            errors['customer_name'] = msg
        else:
            # 检查重复
            is_dup, dup_id = check_duplicate_customer_name(name, customer_id)
            if is_dup:
                errors['customer_name'] = f"客户名称已存在 (ID: {dup_id})"

    # 验证网站 URL
    if 'website' in data and data['website']:
        valid, msg = validate_website(data['website'])
        if not valid:
            errors['website'] = msg

    # 验证邮箱列表
    if 'emails' in data and data['emails']:
        email_errors = []
        for i, email_data in enumerate(data['emails']):
            email = email_data.get('email_address', '')
            valid, msg = validate_email(email)
            if not valid:
                email_errors.append(f"邮箱[{i+1}]: {msg}")
            else:
                # 检查重复
                is_dup, dup_info = check_duplicate_email(
                    email,
                    customer_id if is_update else None
                )
                if is_dup and (not is_update or dup_info['customer_id'] != customer_id):
                    email_errors.append(f"邮箱[{i+1}]: {email} 已存在")

        if email_errors:
            errors['emails'] = email_errors

    # 验证文本字段长度
    text_fields = {
        'country': 500,
        'address': 500,
        'website': 500,
        'company_info': 2000,
        'industry_type': 200,
    }

    for field, max_len in text_fields.items():
        if field in data and data[field]:
            valid, msg = validate_text_length(data[field], max_len, field)
            if not valid:
                errors[field] = msg

    return len(errors) == 0, errors


def validate_batch_delete_ids(ids):
    """
    验证批量删除的ID列表
    返回: (is_valid: bool, error_message: str or None)
    """
    if not isinstance(ids, list):
        return False, "ids必须是数组"

    if not ids:
        return False, "ids不能为空"

    if len(ids) > 100:
        return False, "单次最多删除100条"

    if not all(isinstance(i, int) and i > 0 for i in ids):
        return False, "ids必须为正整数数组"

    return True, None
