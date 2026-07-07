#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材库迁移工具
将硬编码的 MATERIAL_LIBRARY 迁移到数据库
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from materials.seed_data import MATERIAL_LIBRARY
from database.connection import get_connection


def migrate_materials():
    """执行迁移"""
    conn = get_connection()
    cursor = conn.cursor()

    # 确保 materials 表存在
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            material_type TEXT NOT NULL,
            category TEXT,
            scope TEXT,
            track TEXT,
            region TEXT,
            content_json TEXT NOT NULL,
            content_summary TEXT,
            priority INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            has_attachment INTEGER DEFAULT 0,
            attachment_path TEXT,
            attachment_type TEXT,
            attachment_name TEXT,
            tags TEXT,
            source TEXT DEFAULT 'import',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 确保索引存在
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_type ON materials(material_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_scope ON materials(scope)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_track ON materials(track)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_active ON materials(is_active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_priority ON materials(priority DESC)')

    migrated = 0
    skipped = 0

    # 1. 迁移公司简介
    company_intro = MATERIAL_LIBRARY.get('company_intro', {})
    intro_text = company_intro.get('intro_text', '')

    cursor.execute('''
        INSERT OR REPLACE INTO materials
        (material_key, name, material_type, category, scope, content_json, content_summary, priority, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        'company_intro',
        'Company Introduction',
        'company_intro',
        'company',
        'all',
        json.dumps(company_intro, ensure_ascii=False),
        intro_text[:500] if intro_text else '',
        100,
        'import'
    ))
    migrated += 1

    # 2. 迁移优势素材
    advantages = company_intro.get('advantages', {})
    for key, adv in advantages.items():
        scope = adv.get('scope', 'all')
        content_json = json.dumps(adv, ensure_ascii=False)
        summary = f"{adv.get('name', '')}: {adv.get('tech_features', '')[:200]}"

        cursor.execute('''
            INSERT OR REPLACE INTO materials
            (material_key, name, material_type, category, scope, content_json, content_summary, priority, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            key,
            adv.get('name', key),
            'advantage',
            'company',
            scope,
            content_json,
            summary,
            90,
            'import'
        ))
        migrated += 1

    # 3. 迁移太阳能板宣传册
    brochure = MATERIAL_LIBRARY.get('solar_panel_brochure', {})
    for key, item in brochure.items():
        scope = item.get('scope', 'all')
        content_json = json.dumps(item, ensure_ascii=False)
        summary = f"{item.get('name', key)}: {str(item.get('content', ''))[:200]}"

        cursor.execute('''
            INSERT OR REPLACE INTO materials
            (material_key, name, material_type, category, scope, content_json, content_summary, priority, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"solar_brochure_{key}",
            item.get('name', key),
            'brochure',
            'solar_panel',
            scope,
            content_json,
            summary,
            80,
            'import'
        ))
        migrated += 1

    # 4. 迁移储能宣传册
    storage = MATERIAL_LIBRARY.get('energy_storage_brochure', {})
    for key, item in storage.items():
        scope = item.get('scope', 'all')
        content_json = json.dumps(item, ensure_ascii=False)
        summary = f"{item.get('name', key)}: {str(item.get('core_info', ''))[:200]}"

        cursor.execute('''
            INSERT OR REPLACE INTO materials
            (material_key, name, material_type, category, scope, content_json, content_summary, priority, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"storage_{key}",
            item.get('name', key),
            'storage',
            'energy_storage',
            scope,
            content_json,
            summary,
            80,
            'import'
        ))
        migrated += 1

    # 5. 迁移客户案例
    case_keys = ['case_ring', 'case_arlo', 'case_eufy']
    for case_key in case_keys:
        case = MATERIAL_LIBRARY.get(case_key, {})
        if not case:
            continue

        scope = case.get('scope', 'specific')
        track = 'security_hardware' if scope == 'security_hardware' else ''
        content_json = json.dumps(case, ensure_ascii=False)

        # 提取核心优势作为摘要
        core_advantages = case.get('core_advantages', [])
        summary = '; '.join([a.get('title', '') for a in core_advantages[:3]])

        cursor.execute('''
            INSERT OR REPLACE INTO materials
            (material_key, name, material_type, category, scope, track, content_json, content_summary, priority, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            case_key,
            case.get('name', case_key),
            'case_study',
            'case',
            scope,
            track,
            content_json,
            summary,
            85,
            'import'
        ))
        migrated += 1

    # 6. 迁移规则引擎
    rules = MATERIAL_LIBRARY.get('material_rules', {})

    # 按功率类型规则
    by_power = rules.get('by_power_type', {})
    for power_type, rule in by_power.items():
        cursor.execute('''
            INSERT OR REPLACE INTO materials
            (material_key, name, material_type, category, scope, content_json, content_summary, priority, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"rule_power_{power_type}",
            f"Rule: Power Type {power_type}",
            'rule',
            'rule',
            power_type,
            json.dumps(rule, ensure_ascii=False),
            f"Power type rule for {power_type}",
            70,
            'import'
        ))
        migrated += 1

    # 按赛道规则
    by_track = rules.get('by_track', {})
    for track, rule in by_track.items():
        cursor.execute('''
            INSERT OR REPLACE INTO materials
            (material_key, name, material_type, category, track, content_json, content_summary, priority, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"rule_track_{track}",
            f"Rule: Track {track}",
            'rule',
            'rule',
            track,
            json.dumps(rule, ensure_ascii=False),
            f"Track rule for {track}",
            70,
            'import'
        ))
        migrated += 1

    # 按地区规则
    by_region = rules.get('by_region', {})
    for region, rule in by_region.items():
        cursor.execute('''
            INSERT OR REPLACE INTO materials
            (material_key, name, material_type, category, region, content_json, content_summary, priority, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"rule_region_{region}",
            f"Rule: Region {region}",
            'rule',
            'rule',
            region,
            json.dumps(rule, ensure_ascii=False),
            f"Region rule for {region}",
            70,
            'import'
        ))
        migrated += 1

    conn.commit()
    conn.close()

    print(f"迁移完成: {migrated} 条素材已导入数据库")
    print(f"跳过: {skipped} 条")
    return migrated


if __name__ == '__main__':
    count = migrate_materials()
    print(f"\n共迁移 {count} 条素材")
