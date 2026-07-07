#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API 安全与功能测试脚本
测试客户管理模块的所有 CRUD 操作和安全防护
"""

import requests
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = 'http://localhost:5000'
HEADERS = {'X-Requested-With': 'XMLHttpRequest'}


def test_get_customers():
    """测试获取客户列表"""
    r = requests.get(f'{BASE}/api/customers', headers=HEADERS)
    assert r.status_code == 200, f'期望 200，得到 {r.status_code}: {r.text}'
    data = r.json()
    assert data['success'] == True, f'API 返回失败: {data}'
    assert 'customers' in data['data'], '响应中缺少 customers 字段'
    print('  ✓ GET /api/customers')
    return data['data']


def test_create_customer():
    """测试添加客户"""
    payload = {
        'customer_name': 'API测试客户',
        'country': '中国',
        'website': 'https://example.com',
        'company_info': '测试公司信息',
        'emails': [
            {'email_address': 'test1@example.com', 'email_type': 'public'},
            {'email_address': 'test2@example.com', 'email_type': 'personal', 'contact_name': '张三', 'job_title': '经理'}
        ]
    }
    r = requests.post(f'{BASE}/api/customers', json=payload, headers=HEADERS)
    assert r.status_code == 200, f'期望 200，得到 {r.status_code}: {r.text}'
    data = r.json()
    assert data['success'] == True, f'API 返回失败: {data}'
    assert 'customer_id' in data['data'], '响应中缺少 customer_id'
    print(f'  ✓ POST /api/customers (ID: {data["data"]["customer_id"]})')
    return data['data']['customer_id']


def test_get_customer_detail(customer_id):
    """测试获取客户详情"""
    r = requests.get(f'{BASE}/api/customers/{customer_id}', headers=HEADERS)
    assert r.status_code == 200, f'期望 200，得到 {r.status_code}: {r.text}'
    data = r.json()
    assert data['success'] == True
    assert data['data']['customer']['name'] == 'API测试客户'
    assert len(data['data']['emails']) == 2, f'期望 2 个邮箱，得到 {len(data["data"]["emails"])}'
    print(f'  ✓ GET /api/customers/{customer_id}')
    return data['data']


def test_update_customer(customer_id):
    """测试更新客户"""
    payload = {
        'customer_name': 'API测试客户-已更新',
        'country': 'USA',
        'website': 'https://updated-example.com'
    }
    r = requests.post(f'{BASE}/api/customers/{customer_id}/update', json=payload, headers=HEADERS)
    assert r.status_code == 200, f'期望 200，得到 {r.status_code}: {r.text}'
    data = r.json()
    assert data['success'] == True
    print(f'  ✓ POST /api/customers/{customer_id}/update')


def test_add_email(customer_id):
    """测试为客户添加邮箱"""
    payload = {
        'email_address': 'newemail@example.com',
        'email_type': 'public',
        'contact_name': '李四',
        'job_title': '总监'
    }
    r = requests.post(f'{BASE}/api/customers/{customer_id}/emails', json=payload, headers=HEADERS)
    assert r.status_code == 200, f'期望 200，得到 {r.status_code}: {r.text}'
    data = r.json()
    assert data['success'] == True
    print(f'  ✓ POST /api/customers/{customer_id}/emails')
    return data['data']['email_id']


def test_delete_email(customer_id, email_id):
    """测试删除邮箱"""
    r = requests.delete(f'{BASE}/api/customers/{customer_id}/emails/{email_id}', headers=HEADERS)
    assert r.status_code == 200, f'期望 200，得到 {r.status_code}: {r.text}'
    data = r.json()
    assert data['success'] == True
    print(f'  ✓ DELETE /api/customers/{customer_id}/emails/{email_id}')


def test_delete_customer(customer_id):
    """测试删除客户"""
    r = requests.delete(f'{BASE}/api/customers/{customer_id}', headers=HEADERS)
    assert r.status_code == 200, f'期望 200，得到 {r.status_code}: {r.text}'
    data = r.json()
    assert data['success'] == True
    print(f'  ✓ DELETE /api/customers/{customer_id}')


def test_batch_delete():
    """测试批量删除"""
    # 创建 3 个测试客户
    ids = []
    for i in range(3):
        payload = {'customer_name': f'批量测试客户{i}', 'emails': []}
        r = requests.post(f'{BASE}/api/customers', json=payload, headers=HEADERS)
        assert r.status_code == 200
        ids.append(r.json()['data']['customer_id'])

    # 批量删除
    r = requests.post(f'{BASE}/api/customers/batch-delete', json={'ids': ids}, headers=HEADERS)
    assert r.status_code == 200, f'期望 200，得到 {r.status_code}: {r.text}'
    data = r.json()
    assert data['success'] == True
    assert data['data']['deleted_count'] == 3
    print(f'  ✓ POST /api/customers/batch-delete (删除 {data["data"]["deleted_count"]} 个)')


def test_csrf_protection():
    """测试 CSRF 替代防护（不带 X-Requested-With 的请求应被拒绝）"""
    r = requests.post(f'{BASE}/api/customers', json={'customer_name': 'csrf-test'})
    assert r.status_code == 403, f'期望 403，得到 {r.status_code}'
    data = r.json()
    assert data['success'] == False
    print('  ✓ CSRF 防护生效（无 X-Requested-With 返回 403）')


def test_security_headers():
    """测试安全响应头"""
    r = requests.get(f'{BASE}/api/customers', headers=HEADERS)
    headers = r.headers
    assert headers.get('X-Content-Type-Options') == 'nosniff', '缺少 X-Content-Type-Options'
    assert headers.get('X-Frame-Options') == 'SAMEORIGIN', '缺少 X-Frame-Options'
    assert 'Content-Security-Policy' in headers, '缺少 Content-Security-Policy'
    print('  ✓ 安全响应头已设置')


def test_input_validation():
    """测试输入验证"""
    # 测试无效的网站 URL
    payload = {
        'customer_name': '验证测试',
        'website': 'not-a-valid-url',
        'emails': []
    }
    r = requests.post(f'{BASE}/api/customers', json=payload, headers=HEADERS)
    assert r.status_code == 400, f'期望 400，得到 {r.status_code}'
    data = r.json()
    assert 'website' in data.get('details', {}), '应返回 website 验证错误'
    print('  ✓ 网站 URL 验证生效')

    # 测试 XSS 防护（sanitize_text 应转义 HTML）
    payload = {
        'customer_name': '<script>alert(1)</script>',
        'emails': []
    }
    r = requests.post(f'{BASE}/api/customers', json=payload, headers=HEADERS)
    assert r.status_code == 200, f'期望 200，得到 {r.status_code}: {r.text}'
    customer_id = r.json()['data']['customer_id']

    # 验证存储的文本已被转义
    r = requests.get(f'{BASE}/api/customers/{customer_id}', headers=HEADERS)
    name = r.json()['data']['customer']['name']
    assert '<script>' not in name, f'XSS 防护失败，名称包含未转义的 HTML: {name}'
    assert '&lt;script&gt;' in name, f'HTML 应被转义: {name}'
    print('  ✓ HTML 转义 XSS 防护生效')

    # 清理
    requests.delete(f'{BASE}/api/customers/{customer_id}', headers=HEADERS)


def run_all_tests():
    """运行所有测试"""
    print('\n' + '=' * 50)
    print('Niteo Solar 客户管理 API 测试')
    print('=' * 50)

    tests = [
        ('安全响应头测试', test_security_headers),
        ('CSRF 防护测试', test_csrf_protection),
        ('获取客户列表', test_get_customers),
        ('输入验证测试', test_input_validation),
        ('创建客户', test_create_customer),
        ('获取客户详情', test_get_customer_detail),
        ('更新客户', test_update_customer),
        ('添加邮箱', test_add_email),
        ('删除邮箱', test_delete_email),
        ('删除客户', test_delete_customer),
        ('批量删除', test_batch_delete),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        print(f'\n▶ {name}')
        try:
            if name == '获取客户详情':
                # 需要 customer_id
                test_func(customer_id)
            elif name == '更新客户':
                test_func(customer_id)
            elif name == '添加邮箱':
                email_id = test_func(customer_id)
            elif name == '删除邮箱':
                test_func(customer_id, email_id)
            elif name == '删除客户':
                test_func(customer_id)
            else:
                result = test_func()
                if name == '创建客户':
                    customer_id = result
        except AssertionError as e:
            print(f'  ✗ 失败: {e}')
            failed += 1
        except Exception as e:
            print(f'  ✗ 错误: {e}')
            failed += 1
        else:
            passed += 1

    print('\n' + '=' * 50)
    print(f'测试结果: {passed} 通过, {failed} 失败')
    print('=' * 50)

    return failed == 0


if __name__ == '__main__':
    try:
        # 先测试服务器是否运行
        r = requests.get(f'{BASE}/api/stats', headers=HEADERS, timeout=5)
        if r.status_code != 200:
            print(f'错误: 服务器返回 {r.status_code}，请确保 Flask 服务器已启动')
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f'错误: 无法连接到 {BASE}')
        print('请确保 Flask 服务器已启动: python web_app.py')
        sys.exit(1)
    except Exception as e:
        print(f'连接服务器时出错: {e}')
        sys.exit(1)

    success = run_all_tests()
    sys.exit(0 if success else 1)
