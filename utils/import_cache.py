#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI分类缓存模块

缓存AI客户分类结果，避免重复分析相同客户
缓存策略：
- 缓存键：hash(customer_name + country + company_info[:50])
- 有效期：7天
- 最大条目：10000条
- 淘汰策略：LRU（最近最少使用）
"""

import json
import hashlib
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict
from database.connection import get_connection


class AIClassificationCache:
    """AI分类结果缓存管理器"""

    def __init__(self, max_entries: int = 10000, ttl_days: int = 7):
        self.max_entries = max_entries
        self.ttl_days = ttl_days
        self._init_table()

    def _init_table(self):
        """初始化缓存表"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_classification_cache (
                cache_key TEXT PRIMARY KEY,
                classification_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hit_count INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()

    def _make_key(self, customer_name: str, country: str = '', company_info: str = '') -> str:
        """生成缓存键"""
        # 使用客户名称 + 国家 + 公司信息前50字符生成哈希
        info = f"{customer_name}|{country}|{company_info[:50]}"
        return hashlib.md5(info.encode('utf-8')).hexdigest()

    def get(self, customer_name: str, country: str = '', company_info: str = '') -> Optional[Dict]:
        """
        获取缓存的分类结果
        
        Returns:
            分类结果字典 或 None（未命中或已过期）
        """
        cache_key = self._make_key(customer_name, country, company_info)
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # 查询缓存
        cursor.execute('''
            SELECT classification_json, created_at, hit_count
            FROM ai_classification_cache
            WHERE cache_key = ?
        ''', (cache_key,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        classification_json, created_at, hit_count = row
        
        # 检查是否过期
        created_time = datetime.fromisoformat(created_at)
        if datetime.now() - created_time > timedelta(days=self.ttl_days):
            # 删除过期缓存
            cursor.execute('DELETE FROM ai_classification_cache WHERE cache_key = ?', (cache_key,))
            conn.commit()
            conn.close()
            return None
        
        # 更新命中次数
        cursor.execute('''
            UPDATE ai_classification_cache
            SET hit_count = hit_count + 1
            WHERE cache_key = ?
        ''', (cache_key,))
        conn.commit()
        conn.close()
        
        return json.loads(classification_json)

    def set(self, customer_name: str, country: str, company_info: str, classification: Dict):
        """
        设置缓存的分类结果
        """
        cache_key = self._make_key(customer_name, country, company_info)
        classification_json = json.dumps(classification, ensure_ascii=False)
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # 插入或更新缓存
        cursor.execute('''
            INSERT OR REPLACE INTO ai_classification_cache
            (cache_key, classification_json, created_at, hit_count)
            VALUES (?, ?, CURRENT_TIMESTAMP, COALESCE(
                (SELECT hit_count FROM ai_classification_cache WHERE cache_key = ?), 0
            ))
        ''', (cache_key, classification_json, cache_key))
        
        conn.commit()
        conn.close()
        
        # 检查是否需要淘汰旧缓存
        self._evict_if_needed()

    def _evict_if_needed(self):
        """如果缓存条目超过限制，淘汰最旧的条目"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # 获取当前条目数
        cursor.execute('SELECT COUNT(*) FROM ai_classification_cache')
        count = cursor.fetchone()[0]
        
        if count > self.max_entries:
            # 删除最旧的条目（按created_at排序）
            to_delete = count - self.max_entries
            cursor.execute('''
                DELETE FROM ai_classification_cache
                WHERE cache_key IN (
                    SELECT cache_key FROM ai_classification_cache
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
        
        cursor.execute('SELECT COUNT(*), SUM(hit_count) FROM ai_classification_cache')
        total_entries, total_hits = cursor.fetchone()
        
        # 计算命中率（需要外部传入总查询次数）
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
        cursor.execute('DELETE FROM ai_classification_cache')
        conn.commit()
        conn.close()


# 全局缓存实例
_cache_instance = None

def get_cache() -> AIClassificationCache:
    """获取全局缓存实例"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = AIClassificationCache()
    return _cache_instance
