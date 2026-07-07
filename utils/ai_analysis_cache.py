#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI素材分析结果缓存模块"""
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict
from database.connection import get_connection


class AIMaterialAnalysisCache:
    """AI素材分析结果缓存管理器"""

    def __init__(self, max_entries: int = 5000, ttl_days: int = 7):
        self.max_entries = max_entries
        self.ttl_days = ttl_days
        self._init_table()

    def _init_table(self):
        """初始化缓存表"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_material_analysis_cache (
                cache_key TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                filename TEXT,
                file_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hit_count INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()

    def _make_key(self, file_bytes: bytes) -> str:
        """生成缓存键"""
        return hashlib.sha256(file_bytes[:8192]).hexdigest()[:16]

    def get(self, file_bytes: bytes) -> Optional[Dict]:
        """
        获取缓存的分析结果

        Returns:
            分析结果字典 或 None（未命中或已过期）
        """
        cache_key = self._make_key(file_bytes)

        conn = get_connection()
        cursor = conn.cursor()

        # 查询缓存
        cursor.execute('''
            SELECT result_json, created_at, hit_count
            FROM ai_material_analysis_cache
            WHERE cache_key = ?
        ''', (cache_key,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        result_json, created_at, hit_count = row

        # 检查是否过期
        created_time = datetime.fromisoformat(created_at)
        if datetime.now() - created_time > timedelta(days=self.ttl_days):
            # 删除过期缓存
            cursor.execute('DELETE FROM ai_material_analysis_cache WHERE cache_key = ?', (cache_key,))
            conn.commit()
            conn.close()
            return None

        # 更新命中次数
        cursor.execute('''
            UPDATE ai_material_analysis_cache
            SET hit_count = hit_count + 1
            WHERE cache_key = ?
        ''', (cache_key,))
        conn.commit()
        conn.close()

        return json.loads(result_json)

    def set(self, file_bytes: bytes, result: Dict, filename: str, file_size: int):
        """
        设置缓存的分析结果
        """
        cache_key = self._make_key(file_bytes)
        result_json = json.dumps(result, ensure_ascii=False)

        conn = get_connection()
        cursor = conn.cursor()

        # 插入或更新缓存
        cursor.execute('''
            INSERT OR REPLACE INTO ai_material_analysis_cache
            (cache_key, result_json, filename, file_size, created_at, hit_count)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, COALESCE(
                (SELECT hit_count FROM ai_material_analysis_cache WHERE cache_key = ?), 0
            ))
        ''', (cache_key, result_json, filename, file_size, cache_key))

        conn.commit()
        conn.close()

        # 检查是否需要淘汰旧缓存
        self._evict_if_needed()

    def _evict_if_needed(self):
        """如果缓存条目超过限制，淘汰最旧的条目"""
        conn = get_connection()
        cursor = conn.cursor()

        # 获取当前条目数
        cursor.execute('SELECT COUNT(*) FROM ai_material_analysis_cache')
        count = cursor.fetchone()[0]

        if count > self.max_entries:
            # 删除最旧的条目（按created_at排序）
            to_delete = count - self.max_entries
            cursor.execute('''
                DELETE FROM ai_material_analysis_cache
                WHERE cache_key IN (
                    SELECT cache_key FROM ai_material_analysis_cache
                    ORDER BY created_at ASC
                    LIMIT ?
                )
            ''', (to_delete,))
            conn.commit()

        conn.close()

    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*), SUM(hit_count) FROM ai_material_analysis_cache')
        total_entries, total_hits = cursor.fetchone()

        conn.close()

        return {
            'total_entries': total_entries or 0,
            'total_hits': total_hits or 0,
            'max_entries': self.max_entries,
            'ttl_days': self.ttl_days
        }

    def clear(self):
        """清空所有缓存"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM ai_material_analysis_cache')
        conn.commit()
        conn.close()


# 全局缓存实例
_cache_instance = None

def get_cache() -> AIMaterialAnalysisCache:
    """获取全局缓存实例"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = AIMaterialAnalysisCache()
    return _cache_instance
