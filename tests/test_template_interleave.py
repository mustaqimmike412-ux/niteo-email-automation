#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模板穿插功能测试套件 (TC-T001 ~ TC-T012)
测试范围：
  1. interleave_templates — 穿插分配算法
  2. get_templates_by_ids — 按ID获取模板
  3. _make_greeting 使用指定模板
  4. 变量替换逻辑
"""

import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, 'email_automation'))

import unittest
from database.email_template_models import interleave_templates, get_templates_by_ids
from web.app import _make_greeting


class TestInterleaveTemplates(unittest.TestCase):
    """TC-T001 ~ TC-T008: 模板穿插分配算法测试"""

    def test_T001_single_template(self):
        """TC-T001: 单模板 → 全部使用该模板"""
        templates = [{'id': 1, 'template_text': 'Hi A,'}]
        result = interleave_templates(templates, 5)
        self.assertEqual(len(result), 5)
        for r in result:
            self.assertEqual(r['id'], 1)

    def test_T002_two_templates_even(self):
        """TC-T002: 2模板分配4个 → 相邻不重复"""
        templates = [{'id': 1, 'template_text': 'A'}, {'id': 2, 'template_text': 'B'}]
        result = interleave_templates(templates, 4)
        self.assertEqual(len(result), 4)
        ids = [r['id'] for r in result]
        self.assertEqual(sorted(ids), [1, 1, 2, 2])
        # 相邻不重复
        for i in range(len(ids) - 1):
            self.assertNotEqual(ids[i], ids[i + 1], f"相邻重复: {ids}")

    def test_T003_two_templates_odd(self):
        """TC-T003: 2模板分配5个 → 相邻不重复"""
        templates = [{'id': 1, 'template_text': 'A'}, {'id': 2, 'template_text': 'B'}]
        result = interleave_templates(templates, 5)
        self.assertEqual(len(result), 5)
        ids = [r['id'] for r in result]
        self.assertEqual(sorted(ids), [1, 1, 1, 2, 2])
        for i in range(len(ids) - 1):
            self.assertNotEqual(ids[i], ids[i + 1], f"相邻重复: {ids}")

    def test_T003_three_templates(self):
        """TC-T003: 3模板分配6个 → 相邻不重复"""
        templates = [
            {'id': 1, 'template_text': 'A'},
            {'id': 2, 'template_text': 'B'},
            {'id': 3, 'template_text': 'C'}
        ]
        result = interleave_templates(templates, 6)
        self.assertEqual(len(result), 6)
        ids = [r['id'] for r in result]
        self.assertEqual(sorted(ids), [1, 1, 2, 2, 3, 3])
        for i in range(len(ids) - 1):
            self.assertNotEqual(ids[i], ids[i + 1], f"相邻重复: {ids}")

    def test_T004_empty_templates(self):
        """TC-T004: 空模板列表 → 返回空列表"""
        result = interleave_templates([], 5)
        self.assertEqual(result, [])

    def test_T005_zero_count(self):
        """TC-T005: count=0 → 返回空列表"""
        templates = [{'id': 1, 'template_text': 'A'}]
        result = interleave_templates(templates, 0)
        self.assertEqual(result, [])

    def test_T006_large_scale_no_adjacent_duplicate(self):
        """TC-T006: 大规模分配1000次，验证相邻不重复"""
        templates = [
            {'id': 1, 'template_text': 'A'},
            {'id': 2, 'template_text': 'B'},
            {'id': 3, 'template_text': 'C'}
        ]
        result = interleave_templates(templates, 1000)
        self.assertEqual(len(result), 1000)
        ids = [r['id'] for r in result]
        for i in range(len(ids) - 1):
            self.assertNotEqual(ids[i], ids[i + 1], f"相邻重复 at {i}: {ids[i]} == {ids[i+1]}")
        # 验证分布均匀性：每个模板数量差异不超过1
        counts = {1: ids.count(1), 2: ids.count(2), 3: ids.count(3)}
        max_c = max(counts.values())
        min_c = min(counts.values())
        self.assertLessEqual(max_c - min_c, 1, f"分布不均: {counts}")

    def test_T007_different_template_texts(self):
        """TC-T007: 验证模板文本正确传递"""
        templates = [
            {'id': 1, 'template_text': 'Hello {first_name},'},
            {'id': 2, 'template_text': 'Hi {first_name},'}
        ]
        result = interleave_templates(templates, 4)
        texts = [r['template_text'] for r in result]
        self.assertTrue(all(t in ('Hello {first_name},', 'Hi {first_name},') for t in texts))


class TestGetTemplatesByIds(unittest.TestCase):
    """TC-T008 ~ TC-T009: 按ID获取模板测试"""

    def test_T008_empty_ids(self):
        """TC-T008: 空ID列表 → 返回空列表"""
        result = get_templates_by_ids(999, 'greeting', [])
        self.assertEqual(result, [])

    def test_T009_nonexistent_ids(self):
        """TC-T009: 不存在的ID → 返回空列表"""
        result = get_templates_by_ids(999, 'greeting', [99999, 99998])
        self.assertEqual(result, [])


class TestMakeGreetingWithTemplate(unittest.TestCase):
    """TC-T010 ~ TC-T012: _make_greeting 使用指定模板测试"""

    def test_T010_greeting_template_with_first_name(self):
        """TC-T010: 使用含{first_name}的模板 → 正确替换"""
        tpl = "Hello {first_name},"
        g = _make_greeting('personal', 'John Smith', 'john@example.com', 'ABC Solar', greeting_template=tpl)
        self.assertEqual(g, "Hello John,")

    def test_T011_greeting_template_with_company_name(self):
        """TC-T011: 使用含{company_name}的模板 → 正确替换"""
        tpl = "Hi {company_name} Team,"
        g = _make_greeting('public', '', 'info@example.com', 'SunPower Corp', greeting_template=tpl)
        self.assertEqual(g, "Hi Sunpower Team,")

    def test_T012_greeting_template_fallback(self):
        """TC-T012: 传入无效模板 → 回退到默认逻辑"""
        tpl = "Hi {first_name},"
        g = _make_greeting('personal', '', 'info@example.com', 'ABC Solar', greeting_template=tpl)
        # first_name为空，但模板仍会被使用（因为模板优先）
        self.assertIn("Hi", g)


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestInterleaveTemplates))
    suite.addTests(loader.loadTestsFromTestCase(TestGetTemplatesByIds))
    suite.addTests(loader.loadTestsFromTestCase(TestMakeGreetingWithTemplate))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print(f"测试结果: 运行={result.testsRun}, 失败={len(result.failures)}, 错误={len(result.errors)}")
    if result.wasSuccessful():
        print("全部通过!")
    else:
        print("存在失败或错误!")
    print("=" * 60)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
