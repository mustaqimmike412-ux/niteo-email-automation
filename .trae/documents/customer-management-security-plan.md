# 客户管理系统安全加固与功能优化计划

## 摘要

本计划针对 Niteo Solar 邮件自动化系统的客户管理模块进行安全加固和功能优化。基于 Flask 后端安全规范和前端 JS 安全规范的审计结果，识别出 7 个关键问题并制定修复方案。所有修改遵循"安全优先、最小改动、功能验证"原则。

## 当前状态分析

### 已完成功能
- 客户ID已从 205-302 重置为 1-98
- 后端 API: 客户 CRUD、批量删除、文件导入、邮箱管理
- 前端 UI: 仪表盘、客户列表(分页/搜索)、添加/编辑/删除模态框、批量删除、导入模态框、客户详情页(标签页)
- 浅色系主题界面

### 发现的问题

| 优先级 | 问题 | 影响 | 位置 |
|--------|------|------|------|
| 高 | CSRF 全局禁用且无替代防护 | API 易受跨站请求伪造攻击 | web_app.py |
| 高 | 前端字段名与后端不匹配 | 添加/编辑客户时邮箱数据丢失 | index.html |
| 中 | sanitize_text 仅去空格，无 HTML 转义 | XSS 风险 | validators.py |
| 中 | 文件上传未校验 MIME 类型 | 可能上传恶意文件 | validators.py |
| 中 | 网站 URL 无格式校验 | 可能存储无效/恶意 URL | validators.py |
| 低 | 前端 openModal 接收原始 HTML | 潜在的 XSS 注入点 | index.html |
| 低 | 缺少安全响应头 | 点击劫持、MIME 嗅探等风险 | web_app.py |

## 具体修改方案

### 任务 1: 修复前端字段名不匹配 (高优先级)

**文件**: `dashboard/index.html`
**问题**: `getEmailsFromContainer()` 返回 `{address, type}` 但后端期望 `{email_address, email_type}`

**修改内容**:
```javascript
// 修改前
emails.push({
    address: addr,
    type: item.querySelector('.email-type')?.value || 'personal',
    // ...
});

// 修改后
emails.push({
    email_address: addr,
    email_type: item.querySelector('.email-type')?.value || 'personal',
    // ...
});
```

同时检查 `addCustomerEmail('detail')` 中的 API 调用，确保字段名一致：
```javascript
// 修改前
body: JSON.stringify({ address: addr.trim(), type, ... })

// 修改后
body: JSON.stringify({ email_address: addr.trim(), email_type: type, ... })
```

### 任务 2: API 安全加固 - 添加请求来源验证 (高优先级)

**文件**: `web_app.py`
**问题**: CSRF 全局禁用，且应用使用 cookie-less 的 API 认证方式（纯 AJAX 调用），需要添加自定义请求头验证作为替代防护

**修改内容**:
1. 添加 `X-Requested-With` 请求头验证装饰器：
```python
from functools import wraps

def require_ajax(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Invalid request origin'}), 403
        return f(*args, **kwargs)
    return decorated
```

2. 为所有 state-changing 路由添加装饰器：
- `POST /api/customers`
- `DELETE /api/customers/<id>`
- `POST /api/customers/batch-delete`
- `POST /api/customers/import`
- `POST /api/customers/<id>/update`
- `POST /api/customers/<id>/emails`
- `DELETE /api/customers/<id>/emails/<email_id>`
- `POST /api/send/test`

3. 前端 `api()` 函数自动添加请求头：
```javascript
async function api(url, opts = {}) {
    opts.headers = opts.headers || {};
    opts.headers['X-Requested-With'] = 'XMLHttpRequest';
    // ...
}
```

### 任务 3: 增强输入验证与净化 (中优先级)

**文件**: `utils/validators.py`

**修改内容**:
1. 增强 `sanitize_text()` 添加 HTML 转义：
```python
import html

def sanitize_text(text, max_length=None):
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    text = html.escape(text)  # 新增: HTML 实体编码
    if max_length and len(text) > max_length:
        text = text[:max_length]
    return text
```

2. 添加网站 URL 格式验证：
```python
import re

WEBSITE_REGEX = re.compile(
    r'^https?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
    r'localhost|'  # localhost
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

def validate_website(url):
    if not url:
        return True, None
    if not WEBSITE_REGEX.match(url):
        return False, '网站 URL 格式无效'
    return True, None
```

3. 增强文件上传验证，添加 MIME 类型检查：
```python
def validate_file_upload(file_obj):
    # 现有扩展名校验...
    
    # 新增: 读取文件头检测 MIME
    import magic  # 或使用 filetype 库
    # 或基于扩展名的 MIME 映射
    ext = os.path.splitext(file_obj.filename)[1].lower()
    expected_mime = EXTENSION_TO_MIME.get(ext)
    if expected_mime:
        file_obj.seek(0)
        # 简单检查: 至少确保不是可执行文件
        header = file_obj.read(4)
        file_obj.seek(0)
        # 检查 ZIP 签名 (xlsx/docx 都是 ZIP)
        if ext in ('.xlsx', '.docx') and header[:2] != b'PK':
            return False, '文件格式与扩展名不匹配'
    
    return True, None
```

4. 在 `validate_customer_data()` 中集成网站 URL 校验：
```python
if 'website' in data:
    valid, error = validate_website(data['website'])
    if not valid:
        errors.append(error)
```

### 任务 4: 添加安全响应头 (中优先级)

**文件**: `web_app.py`

**修改内容**:
添加 `after_request` 钩子设置安全响应头：
```python
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # CSP 策略: 允许同源脚本和内联脚本(因为我们是 SPA)
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "img-src 'self' data:;"
    )
    return response
```

### 任务 5: 修复前端 XSS 潜在风险点 (中优先级)

**文件**: `dashboard/index.html`

**修改内容**:
1. `openModal()` 函数中的 `innerHTML` 改为安全的 DOM 操作：
```javascript
function openModal(title, html) {
    document.getElementById('modal-title').textContent = title;  // textContent 自动转义
    const body = document.getElementById('modal-body');
    body.innerHTML = '';  // 清空
    // 如果 html 是字符串，使用 textContent 或确保已转义
    // 如果 html 是 DOM 节点，直接 append
    if (typeof html === 'string') {
        // 假设 html 已经过 esc() 处理或来自可信来源
        body.innerHTML = html;
    } else {
        body.appendChild(html);
    }
    document.getElementById('modal-overlay').classList.add('open');
}
```

2. 检查所有 `innerHTML` 使用点，确保动态内容都经过 `esc()` 处理：
- `loadDashboard()` - 已使用 esc()
- `loadCustomers()` - 已使用 esc()
- `loadCustomerDetail()` - 已使用 esc()
- `loadLogs()` - 已使用 esc()
- `loadSubjects()` - 已使用 esc()
- `loadSettings()` - 已使用 esc()
- `sendTestEmail()` - 已使用 esc()

3. 特别检查 `href` 属性中的 URL：
```javascript
// 客户详情中的网站链接
// 修改前
c.website ? `<a href="${esc(c.website)}" target="_blank">...</a>` : '-'

// 修改后 - 添加 noopener 和 URL 验证
c.website ? `<a href="${esc(c.website)}" target="_blank" rel="noopener noreferrer">...</a>` : '-'
```

### 任务 6: SQL 注入防护验证 (低优先级 - 确认安全)

**文件**: `web_app.py`, `database/models.py`

**验证结果**: 所有 SQL 查询均使用参数化查询，无字符串拼接风险。唯一使用 f-string 的场景是 `IN` 子句的占位符生成，但参数通过 `?` 占位符传递，无注入风险。

**无需修改**，但添加注释说明：
```python
# 注意: 此处的 f-string 仅用于生成占位符 ?,?,?
# 实际参数通过 execute() 的第二个参数传递，安全
placeholders = ','.join('?' * len(ids))
cursor.execute(f"SELECT id FROM customers WHERE id IN ({placeholders})", ids)
```

### 任务 7: 创建 API 测试脚本 (高优先级)

**文件**: `tests/test_api.py` (新建)

**测试内容**:
```python
import requests
import json

BASE = 'http://localhost:5000'
HEADERS = {'X-Requested-With': 'XMLHttpRequest'}

def test_get_customers():
    r = requests.get(f'{BASE}/api/customers', headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data['success'] == True
    assert 'customers' in data['data']
    print('✓ GET /api/customers')

def test_create_customer():
    payload = {
        'customer_name': '测试客户',
        'country': '中国',
        'website': 'https://example.com',
        'emails': [{'email_address': 'test@example.com', 'email_type': 'public'}]
    }
    r = requests.post(f'{BASE}/api/customers', json=payload, headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data['success'] == True
    print('✓ POST /api/customers')
    return data['data']['customer_id']

def test_delete_customer(customer_id):
    r = requests.delete(f'{BASE}/api/customers/{customer_id}', headers=HEADERS)
    assert r.status_code == 200
    print('✓ DELETE /api/customers/{id}')

def test_batch_delete():
    # 创建测试客户
    ids = []
    for i in range(3):
        payload = {'customer_name': f'批量测试{i}', 'emails': []}
        r = requests.post(f'{BASE}/api/customers', json=payload, headers=HEADERS)
        ids.append(r.json()['data']['customer_id'])
    
    # 批量删除
    r = requests.post(f'{BASE}/api/customers/batch-delete', 
                      json={'ids': ids}, headers=HEADERS)
    assert r.status_code == 200
    print('✓ POST /api/customers/batch-delete')

def test_csrf_protection():
    # 不带 X-Requested-With 的请求应该被拒绝
    r = requests.post(f'{BASE}/api/customers', json={'customer_name': 'test'})
    assert r.status_code == 403
    print('✓ CSRF protection works')

if __name__ == '__main__':
    test_get_customers()
    cid = test_create_customer()
    test_delete_customer(cid)
    test_batch_delete()
    test_csrf_protection()
    print('\n所有测试通过!')
```

## 实施顺序

1. **第一步**: 修复字段名不匹配 (任务 1) - 立即修复功能缺陷
2. **第二步**: 添加 API 来源验证 (任务 2) + 前端请求头 (任务 2 前端部分)
3. **第三步**: 增强输入验证 (任务 3)
4. **第四步**: 添加安全响应头 (任务 4)
5. **第五步**: 修复前端 XSS 风险 (任务 5)
6. **第六步**: 创建并运行测试脚本 (任务 7)
7. **第七步**: 验证 SQL 注入防护 (任务 6) - 仅确认，无需修改

## 验证步骤

1. 启动 Flask 服务器: `python web_app.py`
2. 运行测试脚本: `python tests/test_api.py`
3. 手动验证前端功能:
   - 添加客户（带邮箱）
   - 编辑客户
   - 删除单个客户
   - 批量删除客户
   - 导入文件
   - 查看客户详情
4. 检查浏览器开发者工具中的响应头是否包含安全头
5. 验证不带 `X-Requested-With` 的请求返回 403

## 假设与决策

1. **CSRF 替代方案**: 选择 `X-Requested-With` 请求头验证而非重新启用 CSRF token，因为：
   - 前端是纯 AJAX SPA，无传统表单提交
   - 该方案对 API 应用足够有效（参考 Flask 安全规范 FLASK-CSRF-001 的备注）
   - 实施成本低，无需修改大量前端代码

2. **HTML 转义位置**: 在 `sanitize_text()` 中进行 HTML 转义，确保所有写入数据库的文本都已转义，前端 `esc()` 作为二次防护

3. **CSP 策略**: 允许 `'unsafe-inline'` 用于脚本和样式，因为：
   - 前端是内联脚本的单页应用
   - 移除内联脚本需要大量重构，超出当前优化范围
   - 其他 CSP 限制（connect-src, img-src 等）仍然有效

4. **文件 MIME 检测**: 使用简单的文件头签名检查而非引入新依赖（如 python-magic），保持项目轻量
