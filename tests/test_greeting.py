#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件问候语功能测试套件 (TC-G001 ~ TC-G012)
测试范围：
  1. _make_greeting 函数 — 各种边界情况
  2. _extract_first_name 函数 — 名字提取
  3. send_queue 问候语组装逻辑 — 正则去除 + 重新拼接
  4. 健康检查端点 — /api/health/greeting
"""

import re
import sys
import os
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from web.app import _make_greeting, _extract_first_name, _is_valid_name


class TestGreetingGeneration(unittest.TestCase):
    """TC-G001 ~ TC-G006: 问候语生成测试"""

    def test_G001_personal_with_valid_name(self):
        """TC-G001: 个人邮箱 + 有效联系人姓名 → 使用名字"""
        g = _make_greeting('personal', 'John Smith', 'john@example.com', 'ABC Solar')
        self.assertIn('John', g)
        self.assertTrue(g.startswith('Hi ') or g.startswith('Hello ') or g.startswith('Good day '))

    def test_G002_personal_with_empty_name(self):
        """TC-G002: 个人邮箱 + 空联系人姓名 → 回退到公司名+Team"""
        g = _make_greeting('personal', '', 'info@example.com', 'ABC Solar')
        self.assertIn('Abc Solar', g)
        self.assertIn('Team', g)

    def test_G003_personal_with_invalid_name(self):
        """TC-G003: 个人邮箱 + 无效名字(n/a/unknown/123) → 回退到公司名+Team"""
        for invalid in ['n/a', 'unknown', 'N/A', '123', ',', '.']:
            g = _make_greeting('personal', invalid, 'test@example.com', 'ABC Solar')
            self.assertIn('Abc Solar', g)
            self.assertIn('Team', g)

    def test_G004_public_email_uses_company(self):
        """TC-G004: 公共邮箱 → 使用公司名+Team，不使用个人名字"""
        g = _make_greeting('public', 'John', 'info@example.com', 'ABC Solar')
        self.assertIn('Abc Solar', g)
        self.assertIn('Team', g)
        self.assertNotIn('John', g)

    def test_G005_empty_customer_name(self):
        """TC-G005: 空公司名 → 使用 Valued 兜底"""
        g = _make_greeting('public', '', 'info@example.com', '')
        self.assertIn('Valued', g)
        self.assertIn('Team', g)

    def test_G006_no_bad_patterns(self):
        """TC-G006: 问候语不应出现 'Hi ,' 'Hello ,' 等缺失名字的情况"""
        bad_patterns = ['hi ,', 'hello ,', 'good day ,', 'greetings ,', 'dear ,']
        test_cases = [
            ('personal', '', 'Test Co'),
            ('personal', '   ', 'Test Co'),
            ('public', '', ''),
            ('public', 'John', ''),
        ]
        for email_type, contact_name, customer_name in test_cases:
            g = _make_greeting(email_type, contact_name, 'test@example.com', customer_name)
            for p in bad_patterns:
                self.assertNotIn(p, g.lower(), f"问候语包含不良模式 '{p}': {g}")


class TestFirstNameExtraction(unittest.TestCase):
    """TC-G007 ~ TC-G008: 名字提取测试"""

    def test_G007_valid_names(self):
        """TC-G007: 有效名字正确提取 first_name"""
        self.assertEqual(_extract_first_name('John Smith'), 'John')
        self.assertEqual(_extract_first_name('Mary-Jane'), 'Mary-Jane')
        self.assertEqual(_extract_first_name('Jean-Luc'), 'Jean-Luc')

    def test_G008_invalid_names(self):
        """TC-G008: 无效名字返回空字符串"""
        invalid = ['', '   ', 'n/a', 'N/A', 'unknown', '123', ',', '.', '-', 'Team']
        for name in invalid:
            self.assertEqual(_extract_first_name(name), '', f"'{name}' 应返回空字符串")


class TestSendQueueGreetingAssembly(unittest.TestCase):
    """TC-G009 ~ TC-G012: send_queue 问候语组装逻辑测试"""

    def _assemble(self, body, greeting):
        """模拟 send_queue 的问候语组装逻辑（使用修复后的代码）"""
        original_body = body
        actual_greeting = greeting
        assembled = body

        if body:
            import re
            # greeting 为空时先尝试从 body 开头提取已有问候语复用
            if not actual_greeting:
                m = re.match(r'^(Hi|Dear|Hello|Good day)\s+([^,\n]{1,50})(?:,?)', body.lstrip(), re.IGNORECASE)
                if m:
                    actual_greeting = m.group(0).strip().rstrip(',')
                else:
                    actual_greeting = 'Hi Team'
            # 去除 body 开头可能残留的问候语行
            body = re.sub(
                r'^(Hi|Dear|Hello|Good day)\s+[^,\n]{1,50}(?:,?)\s*\n*',
                '', body.lstrip(), flags=re.IGNORECASE
            ).strip()
            assembled = f"{actual_greeting}\n\n{body}" if body else actual_greeting
        else:
            assembled = actual_greeting or 'Hi Team'

        return assembled, actual_greeting

    def test_G009_body_with_greeting_comma(self):
        """TC-G009: body 含问候语+逗号 → 正确去除并重新拼接"""
        assembled, g = self._assemble("Hi Alice,\n\nThis is the body.", "Hi Alice")
        self.assertTrue(assembled.startswith("Hi Alice\n\n"))
        self.assertNotIn("Hi Alice,\n\nHi Alice", assembled)  # 不应重复

    def test_G010_body_with_greeting_no_comma(self):
        """TC-G010: body 含问候语无逗号 → 正确去除并重新拼接"""
        assembled, g = self._assemble("Hi Alice\n\nThis is the body.", "Hi Alice")
        self.assertTrue(assembled.startswith("Hi Alice\n\n"))

    def test_G011_empty_greeting_extract_from_body(self):
        """TC-G011: greeting 为空但 body 含问候语 → 提取复用"""
        assembled, g = self._assemble("Dear Bob,\n\nThis is the body.", "")
        self.assertEqual(g, "Dear Bob")
        self.assertTrue(assembled.startswith("Dear Bob\n\n"))

    def test_G012_empty_greeting_no_greeting_in_body(self):
        """TC-G012: greeting 为空且 body 不含问候语 → 兜底为 Hi Team"""
        assembled, g = self._assemble("This is the body.", "")
        self.assertEqual(g, "Hi Team")
        self.assertTrue(assembled.startswith("Hi Team\n\n"))


class TestHealthCheckEndpoint(unittest.TestCase):
    """TC-G013: 健康检查端点测试"""

    def test_G013_health_endpoint(self):
        """TC-G013: /api/health/greeting 返回 healthy"""
        import requests
        try:
            resp = requests.get('https://exim-flow.com/api/health/greeting', timeout=15)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data.get('status'), 'healthy')
            self.assertTrue(data.get('all_passed'))
            self.assertGreaterEqual(len(data.get('greeting_tests', [])), 10)
            self.assertGreaterEqual(len(data.get('assemble_tests', [])), 5)
        except requests.RequestException as e:
            self.fail(f"健康检查请求失败: {e}")


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestGreetingGeneration))
    suite.addTests(loader.loadTestsFromTestCase(TestFirstNameExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestSendQueueGreetingAssembly))
    suite.addTests(loader.loadTestsFromTestCase(TestHealthCheckEndpoint))

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
