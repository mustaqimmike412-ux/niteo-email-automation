#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 config/company_info.json 中的发信人信息迁移到 materials 表作为系统公共素材。
幂等设计：可重复运行，已存在时跳过。
"""

import json
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from database.connection import get_connection


def migrate():
    config_path = os.path.join(_project_root, 'config', 'company_info.json')
    if not os.path.exists(config_path):
        print(f"[migrate_sender_info] 配置文件不存在: {config_path}")
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        info = json.load(f)

    conn = get_connection()
    cursor = conn.cursor()

    # 检查是否已存在系统公共 sender_info
    cursor.execute(
        "SELECT id FROM materials WHERE material_type = 'sender_info' AND user_id IS NULL"
    )
    existing = cursor.fetchone()

    if existing:
        print(f"[migrate_sender_info] 系统公共 sender_info 已存在 (id={existing[0]})，跳过迁移")
        conn.close()
        return

    # 插入系统公共 sender_info
    material_key = 'system_sender_info'
    name = f"{info.get('sender_name', 'Sender')} - 发信人资料"
    content_json = json.dumps(info, ensure_ascii=False)
    content_summary = f"{info.get('sender_name')} at {info.get('company_name')}, {info.get('job_title')}"

    cursor.execute("""
        INSERT INTO materials (material_key, name, material_type, category, scope,
                               content_json, content_summary, priority, is_active,
                               tags, source, user_id, is_public, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
    """, (
        material_key, name, 'sender_info', 'sender_profile', 'all',
        content_json, content_summary, 10, 1,
        'sender,profile,system', 'migration', None, 1
    ))

    material_id = cursor.lastrowid
    conn.commit()
    conn.close()

    print(f"[migrate_sender_info] 迁移成功：发信人信息已写入 materials 表 (id={material_id})")
    print(f"  - 名称: {name}")
    print(f"  - 公司: {info.get('company_name')}")
    print(f"  - 发信人: {info.get('sender_name')} ({info.get('job_title')})")


if __name__ == '__main__':
    migrate()
