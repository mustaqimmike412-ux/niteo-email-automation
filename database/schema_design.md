# 数据库设计方案

## 当前Excel数据结构分析

### 原始列
- 序号、发信状态、客户、国家、地址、官网
- 公司信息和客户主要产品、供应商、供应商信息
- 海关数据购买产品名、物流信息
- 领英邮箱、客户邮箱
- 第一次发信、第二次发信、第三次发信、第四次发信

### 邮箱数据特点
1. **客户邮箱**：包含联系人姓名、职位、邮箱地址
2. **领英邮箱**：同样包含姓名、职位、邮箱
3. **公共邮箱**：如 info@, support@, sales@ 等，无具体联系人姓名
4. **个人邮箱**：标注了具体联系人姓名和职位

## 数据库表结构设计

### 1. customers（客户主表）
```sql
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,          -- 客户公司名称
    country TEXT,                          -- 国家
    address TEXT,                          -- 地址
    website TEXT,                          -- 官网
    company_info TEXT,                     -- 公司信息和主要产品
    supplier TEXT,                         -- 供应商
    supplier_info TEXT,                    -- 供应商信息
    customs_data TEXT,                     -- 海关数据购买产品名
    logistics_info TEXT,                   -- 物流信息
    industry_type TEXT,                    -- 行业类型（自动识别）
    website_title TEXT,                    -- 网站标题
    website_description TEXT,              -- 网站描述
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. contacts（联系人表）
```sql
CREATE TABLE contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    contact_name TEXT,                     -- 联系人姓名
    job_title TEXT,                        -- 职位
    source TEXT,                           -- 来源：customer_email / linkedin
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

### 3. emails（邮箱表）
```sql
CREATE TABLE emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    contact_id INTEGER,                    -- 关联联系人（可选）
    email_address TEXT NOT NULL,           -- 邮箱地址
    email_type TEXT CHECK(email_type IN ('public', 'personal', 'linkedin')),
    is_active INTEGER DEFAULT 1,           -- 是否启用
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);
```

### 4. email_logs（邮件发送记录表）
```sql
CREATE TABLE email_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    email_id INTEGER,
    contact_id INTEGER,
    email_subject TEXT,
    email_content TEXT,
    send_status TEXT CHECK(send_status IN ('pending', 'sent', 'failed')),
    error_message TEXT,
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (email_id) REFERENCES emails(id),
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);
```

### 5. email_templates（邮件模板表）
```sql
CREATE TABLE email_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL,
    subject_template TEXT NOT NULL,
    body_template TEXT NOT NULL,
    email_type TEXT CHECK(email_type IN ('public', 'personal')),
    industry_type TEXT,                    -- 适用行业（NULL表示通用）
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 数据导入逻辑

### 邮箱类型识别规则
1. **公共邮箱**：包含以下关键词的邮箱
   - info@, support@, sales@, contact@, service@
   - account@, orders@, marketing@, warehouse@
   - admin@, help@, hello@

2. **个人邮箱**：
   - 有具体联系人姓名的邮箱
   - 域名非公共邮箱服务商的个性化邮箱

3. **领英邮箱**：
   - 从领英邮箱列导入的邮箱
   - 标记 source 为 'linkedin'

### 联系人信息提取
从文本中提取：
- 姓名：姓名：xxx 或 Name: xxx
- 职位：职位：xxx 或 Title: xxx
- 邮箱：邮箱：xxx 或 Email: xxx

## 优化建议

1. **数据清洗**：
   - 去除重复邮箱
   - 验证邮箱格式
   - 标准化公司名称

2. **索引优化**：
   - customers(customer_name)
   - emails(email_address)
   - email_logs(customer_id, sent_at)

3. **数据完整性**：
   - 外键约束
   - 级联删除/更新
