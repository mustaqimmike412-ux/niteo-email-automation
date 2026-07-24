from database.connection import get_connection


def get_or_create_user(email, name=None, avatar=None, oauth_provider='google', oauth_id=None):
    """获取或创建用户。第一个注册的用户自动设为管理员。"""
    conn = get_connection()
    cursor = conn.cursor()

    # 检查用户是否已存在
    cursor.execute('SELECT id, email, name, avatar, role, is_active FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()

    if user:
        # 更新最后登录时间
        cursor.execute('UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?', (user[0],))
        conn.commit()
        conn.close()
        return {
            'id': user[0],
            'email': user[1],
            'name': user[2],
            'avatar': user[3],
            'role': user[4],
            'is_active': user[5]
        }

    # 检查是否已有用户（第一个用户设为管理员）
    cursor.execute('SELECT COUNT(*) FROM users')
    user_count = cursor.fetchone()[0]
    role = 'admin' if user_count == 0 else 'user'

    # 创建新用户
    cursor.execute('''
        INSERT INTO users (email, name, avatar, oauth_provider, oauth_id, role, last_login_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (email, name, avatar, oauth_provider, oauth_id, role))

    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        'id': user_id,
        'email': email,
        'name': name,
        'avatar': avatar,
        'role': role,
        'is_active': 1
    }


def get_user_by_id(user_id):
    """通过ID获取用户信息"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, email, name, avatar, role, is_active FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'id': row[0],
            'email': row[1],
            'name': row[2],
            'avatar': row[3],
            'role': row[4],
            'is_active': row[5]
        }
    return None


def get_all_users():
    """获取所有用户列表（管理员用）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, email, name, avatar, role, is_active, created_at, last_login_at
        FROM users ORDER BY created_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            'id': r[0],
            'email': r[1],
            'name': r[2],
            'avatar': r[3],
            'role': r[4],
            'is_active': r[5],
            'created_at': r[6],
            'last_login_at': r[7]
        }
        for r in rows
    ]


def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    # 客户信息主表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            country TEXT,
            address TEXT,
            website TEXT,
            company_info TEXT,
            supplier TEXT,
            supplier_info TEXT,
            customs_data TEXT,
            logistics_info TEXT,
            industry_type TEXT,
            website_title TEXT,
            website_description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 联系人表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            contact_name TEXT,
            job_title TEXT,
            source TEXT CHECK(source IN ('customer_email', 'linkedin', 'manual')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    ''')

    # 邮箱表（支持多个邮箱）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            contact_id INTEGER,
            email_address TEXT NOT NULL,
            email_type TEXT CHECK(email_type IN ('public', 'personal', 'linkedin')),
            contact_name TEXT,
            job_title TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
        )
    ''')

    # 邮件发送记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            email_id INTEGER,
            contact_id INTEGER,
            task_id TEXT,
            source TEXT DEFAULT 'manual',
            email_subject TEXT,
            email_content TEXT,
            send_status TEXT CHECK(send_status IN ('pending', 'sent', 'failed')),
            error_message TEXT,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE SET NULL,
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
        )
    ''')

    # 迁移：为已有表添加 task_id 和 source 字段
    try:
        cursor.execute('ALTER TABLE email_logs ADD COLUMN task_id TEXT')
    except:
        pass
    try:
        cursor.execute('ALTER TABLE email_logs ADD COLUMN source TEXT DEFAULT \'manual\'')
    except:
        pass

    # 邮件模板表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_name TEXT NOT NULL,
            subject_template TEXT NOT NULL,
            body_template TEXT NOT NULL,
            email_type TEXT CHECK(email_type IN ('public', 'personal')),
            industry_type TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 用户邮件模板池表（开场白 + 问候语）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_email_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            template_type TEXT NOT NULL CHECK(template_type IN ('greeting', 'opening')),
            template_text TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_templates_user ON user_email_templates(user_id, template_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_templates_active ON user_email_templates(user_id, template_type, is_active)')

    # 客户主题池表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customer_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            subject_line TEXT NOT NULL,
            subject_index INTEGER NOT NULL,
            subject_type TEXT NOT NULL,
            generation_strategy TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            UNIQUE(customer_id, subject_index)
        )
    ''')

    # 主题使用记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subject_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            email_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            subject_line TEXT NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE,
            FOREIGN KEY (subject_id) REFERENCES customer_subjects(id) ON DELETE CASCADE
        )
    ''')

    # 发送调度表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS send_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            scheduled_at TIMESTAMP NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'failed', 'cancelled')),
            subject_id INTEGER,
            email_log_id INTEGER,
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (subject_id) REFERENCES customer_subjects(id) ON DELETE SET NULL,
            FOREIGN KEY (email_log_id) REFERENCES email_logs(id) ON DELETE SET NULL
        )
    ''')

    # 创建索引优化查询
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(customer_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_emails_address ON emails(email_address)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_emails_customer ON emails(customer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_customer ON contacts(customer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_logs_sent ON email_logs(sent_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_logs_status ON email_logs(send_status)')


    # 冷却期手动解除记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cooldown_override (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            released_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cooldown_override_customer ON cooldown_override(customer_id)')

    # 新表索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_customer_subjects_customer ON customer_subjects(customer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_subject_usage_customer ON subject_usage_log(customer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_subject_usage_email ON subject_usage_log(email_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_send_schedule_status ON send_schedule(status, scheduled_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_send_schedule_time ON send_schedule(scheduled_at)')

    # 资料管理表
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
            source TEXT DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 迁移：为素材表添加AI分析相关字段
    try:
        cursor.execute('ALTER TABLE materials ADD COLUMN source_file TEXT')
    except:
        pass
    try:
        cursor.execute('ALTER TABLE materials ADD COLUMN ai_confidence REAL')
    except:
        pass

    # 迁移：为素材表添加公共/私有、使用次数、适用范围字段
    try:
        cursor.execute('ALTER TABLE materials ADD COLUMN is_public INTEGER DEFAULT 0')
    except:
        pass
    try:
        cursor.execute('ALTER TABLE materials ADD COLUMN usage_count INTEGER DEFAULT 0')
    except:
        pass
    try:
        cursor.execute('ALTER TABLE materials ADD COLUMN material_scope TEXT')
    except:
        pass

    # AI批量导入任务表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS import_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
            total_files INTEGER DEFAULT 0,
            processed_files INTEGER DEFAULT 0,
            imported_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            error_details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_import_tasks_status ON import_tasks(status)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS material_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            customer_id INTEGER,
            email_log_id INTEGER,
            usage_context TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
            FOREIGN KEY (email_log_id) REFERENCES email_logs(id) ON DELETE SET NULL
        )
    ''')

    # 资料表索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_type ON materials(material_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_category ON materials(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_scope ON materials(scope)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_track ON materials(track)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_active ON materials(is_active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_priority ON materials(priority DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_type_scope ON materials(material_type, scope, is_active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_type_track ON materials(material_type, track, is_active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_material ON material_usage_log(material_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_customer ON material_usage_log(customer_id)')

    # 发送任务项表（单封邮件粒度追踪）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS send_task_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            email_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            email_address TEXT NOT NULL,
            contact_name TEXT,
            email_type TEXT,
            subject TEXT,
            greeting TEXT,
            item_status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 2,
            error_message TEXT,
            scheduled_send_at TIMESTAMP,
            actual_send_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_items_task ON send_task_items(task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_items_status ON send_task_items(task_id, item_status)')

    # 发送任务元数据表（用于刷新页面后恢复进度）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS send_tasks_meta (
            task_id TEXT PRIMARY KEY,
            task_type TEXT NOT NULL DEFAULT 'manual',
            status TEXT DEFAULT 'pending',
            customer_id INTEGER,
            customer_name TEXT,
            total_emails INTEGER DEFAULT 0,
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            current_index INTEGER DEFAULT 0,
            progress INTEGER DEFAULT 0,
            current_step TEXT DEFAULT '',
            step_status TEXT DEFAULT '{}',
            email_preview_subject TEXT,
            email_preview_body TEXT,
            email_preview_word_count INTEGER,
            send_config TEXT DEFAULT '{}',
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_send_tasks_meta_status ON send_tasks_meta(status, created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_send_tasks_meta_created ON send_tasks_meta(created_at DESC)')

    # ==================== 获客模块表 ====================

    # 搜索任务表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL UNIQUE,
            task_name TEXT,
            query_text TEXT NOT NULL,
            location TEXT,
            platforms TEXT NOT NULL DEFAULT '[]',
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),
            total_targets INTEGER DEFAULT 0,
            found_count INTEGER DEFAULT 0,
            imported_count INTEGER DEFAULT 0,
            ai_enriched_count INTEGER DEFAULT 0,
            pre_filtered_count INTEGER DEFAULT 0,
            crawl_rejected_count INTEGER DEFAULT 0,
            ai_skipped_count INTEGER DEFAULT 0,
            config_json TEXT DEFAULT '{}',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_tasks_status ON search_tasks(status, created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_tasks_task_id ON search_tasks(task_id)')

    # 搜索结果表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('google_places', 'web_search', 'facebook', 'instagram', 'tiktok', 'website_crawl')),
            source_url TEXT,
            raw_data_json TEXT NOT NULL,
            company_name TEXT,
            website TEXT,
            country TEXT,
            address TEXT,
            phone TEXT,
            email TEXT,
            industry_type TEXT,
            business_model TEXT,
            confidence_score REAL,
            ai_analysis_json TEXT,
            import_status TEXT DEFAULT 'pending' CHECK(import_status IN ('pending', 'review', 'approved', 'rejected', 'imported')),
            imported_customer_id INTEGER,
            search_keyword TEXT,
            search_location TEXT,
            emails_json TEXT,                 -- 多邮箱存储 [{email, type, role, source, confidence}]
            validation_status TEXT DEFAULT 'pending',
            validation_reason TEXT,
            pre_crawl_score REAL,
            crawl_validation_passed INTEGER DEFAULT 0,
            probe_title TEXT,
            probe_description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES search_tasks(task_id) ON DELETE CASCADE,
            FOREIGN KEY (imported_customer_id) REFERENCES customers(id) ON DELETE SET NULL
        )
    ''')

    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_results_task ON search_results(task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_results_platform ON search_results(platform)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_results_import ON search_results(import_status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_results_company ON search_results(company_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_results_email ON search_results(email)')

    # 平台配置表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_platform_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL UNIQUE CHECK(platform IN ('google_places', 'web_search', 'facebook', 'instagram', 'tiktok')),
            is_enabled INTEGER DEFAULT 1,
            api_key TEXT,
            api_secret TEXT,
            base_url TEXT,
            config_json TEXT DEFAULT '{}',
            rate_limit_per_minute INTEGER DEFAULT 60,
            daily_quota INTEGER DEFAULT 1000,
            usage_today INTEGER DEFAULT 0,
            last_reset_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 拉黑公司表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blacklisted_companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            website TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_name, website)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_blacklist_website ON blacklisted_companies(website)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_blacklist_name ON blacklisted_companies(company_name)')

    # 迁移：为customers表添加来源追踪字段
    try:
        cursor.execute("ALTER TABLE customers ADD COLUMN source_channel TEXT DEFAULT 'manual'")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE customers ADD COLUMN source_task_id TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE customers ADD COLUMN source_platform TEXT")
    except:
        pass
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_customers_source ON customers(source_channel, source_platform)')

    # === 搜索模块验证字段迁移 ===
    def _add_column_safe(cursor, table, column, col_type):
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except Exception:
            pass  # 字段已存在

    # search_tasks 新增统计字段
    _add_column_safe(cursor, 'search_tasks', 'pre_filtered_count', 'INTEGER DEFAULT 0')
    _add_column_safe(cursor, 'search_tasks', 'crawl_rejected_count', 'INTEGER DEFAULT 0')
    _add_column_safe(cursor, 'search_tasks', 'ai_skipped_count', 'INTEGER DEFAULT 0')
    _add_column_safe(cursor, 'search_tasks', 'expanded_keywords', 'TEXT')

    # ==================== 数据隔离：为所有业务表添加 user_id 字段 ====================
    _add_column_safe(cursor, 'customers', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'contacts', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'emails', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'email_logs', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'email_templates', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'customer_subjects', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'subject_usage_log', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'send_schedule', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'cooldown_override', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'materials', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'import_tasks', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'material_usage_log', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'send_task_items', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'send_tasks_meta', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'search_tasks', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'search_results', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'blacklisted_companies', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'api_configs', 'user_id', 'INTEGER')
    _add_column_safe(cursor, 'bounce_logs', 'user_id', 'INTEGER')

    # ==================== 修复 api_configs UNIQUE 约束：从 api_name 改为 (api_name, user_id) ====================
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='api_configs' AND sql LIKE '%UNIQUE%' AND sql LIKE '%api_name%' AND sql NOT LIKE '%user_id%'")
    old_unique_indexes = [r[0] for r in cursor.fetchall()]
    for idx_name in old_unique_indexes:
        try:
            cursor.execute(f'DROP INDEX IF EXISTS {idx_name}')
            print(f"[Schema] 已删除旧 UNIQUE 索引: {idx_name}")
        except Exception:
            pass
    # 创建新的组合唯一索引（如果还不存在）
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='api_configs' AND sql LIKE '%api_name%' AND sql LIKE '%user_id%'")
    if not cursor.fetchone():
        try:
            cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_api_configs_name_user ON api_configs(api_name, user_id)')
            print("[Schema] 已创建组合唯一索引: (api_name, user_id)")
        except Exception as e:
            print(f"[Schema] 创建组合索引失败（可能已有重复数据）: {e}")
    conn.commit()

    # ==================== 退信追踪：为 emails 表添加退信相关字段 ====================
    _add_column_safe(cursor, 'emails', 'bounce_status', "TEXT CHECK(bounce_status IN ('none', 'soft', 'hard')) DEFAULT 'none'")
    _add_column_safe(cursor, 'emails', 'bounce_count', 'INTEGER DEFAULT 0')
    _add_column_safe(cursor, 'emails', 'last_bounce_at', 'INTEGER')
    _add_column_safe(cursor, 'emails', 'bounce_reason', 'TEXT')

    # ==================== 退信追踪：为 email_logs 表添加 recipient_email 字段 ====================
    _add_column_safe(cursor, 'email_logs', 'recipient_email', 'TEXT')

    # ==================== 数据隔离：为 search_platform_configs 添加 user_id ====================
    _add_column_safe(cursor, 'search_platform_configs', 'user_id', 'INTEGER')

    # ==================== 数据隔离：为 email_logs_scheduled 添加 user_id ====================
    _add_column_safe(cursor, 'email_logs_scheduled', 'user_id', 'INTEGER')

    # search_results 新增验证字段
    _add_column_safe(cursor, 'search_results', 'validation_status', "TEXT DEFAULT 'pending'")
    _add_column_safe(cursor, 'search_results', 'validation_reason', 'TEXT')
    _add_column_safe(cursor, 'search_results', 'pre_crawl_score', 'REAL')
    _add_column_safe(cursor, 'search_results', 'crawl_validation_passed', 'INTEGER DEFAULT 0')
    _add_column_safe(cursor, 'search_results', 'probe_title', 'TEXT')
    _add_column_safe(cursor, 'search_results', 'probe_description', 'TEXT')

    # API 配置管理表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            base_url TEXT,
            model TEXT,
            extra_config TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 退信记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bounce_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT UNIQUE,
            email_log_id INTEGER,
            email_id INTEGER,
            customer_id INTEGER,
            bounce_type TEXT,
            recipient_email TEXT NOT NULL,
            original_subject TEXT,
            diagnostic_code TEXT,
            status_code TEXT,
            action TEXT,
            bounce_subject TEXT,
            bounce_from TEXT,
            raw_bounce_snippet TEXT,
            matched_log INTEGER DEFAULT 0,
            processed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email_log_id) REFERENCES email_logs(id) ON DELETE SET NULL,
            FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE SET NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bounce_type ON bounce_logs(bounce_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bounce_recipient ON bounce_logs(recipient_email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bounce_created ON bounce_logs(created_at)')

    # email_logs 新增 bounce_status 字段
    try:
        cursor.execute('ALTER TABLE email_logs ADD COLUMN bounce_status TEXT DEFAULT NULL')
    except Exception:
        pass

    # ==================== 用户认证表 ====================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT,
            avatar TEXT,
            oauth_provider TEXT DEFAULT 'google',
            oauth_id TEXT,
            role TEXT DEFAULT 'user' CHECK(role IN ('admin', 'user')),
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_oauth ON users(oauth_provider, oauth_id)')

    # ==================== 管理员面板查询优化索引 ====================
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_customers_country ON customers(country)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_customers_industry ON customers(industry_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_customers_created ON customers(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_logs_customer ON email_logs(customer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_logs_customer_status ON email_logs(customer_id, send_status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_logs_sent_at_status ON email_logs(sent_at, send_status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_source ON contacts(source)')

    # 邮件规范表
    from database.email_guidelines_models import init_email_guidelines_table, migrate_to_multi_user
    init_email_guidelines_table()
    migrate_to_multi_user()

    # 邀请码表
    from database.invite_code_models import init_invite_codes_table
    init_invite_codes_table()
    
    # 邀请码使用日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_code_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invite_logs_code ON invite_code_logs(code)')

    # ==================== 用户设置隔离表 ====================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            setting_type TEXT NOT NULL,
            setting_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, setting_type)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_settings_user ON user_settings(user_id, setting_type)')

    # 邮件限定预设表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pc_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            preset_json TEXT NOT NULL DEFAULT '{}',
            is_default INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pc_presets_user ON pc_presets(user_id)')

    # ==================== 跟进邮件模块表 ====================

    # 跟进序列表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS follow_up_sequences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            user_id INTEGER,
            strategy_type TEXT NOT NULL DEFAULT 'standard',
            total_steps INTEGER NOT NULL DEFAULT 5,
            current_step INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'draft',
            first_email_log_id INTEGER,
            generation_context TEXT,
            config_json TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (first_email_log_id) REFERENCES email_logs(id)
        )
    ''')

    # 跟进步骤表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS follow_up_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sequence_id INTEGER NOT NULL,
            step_number INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            strategy TEXT,
            subject_mode TEXT NOT NULL DEFAULT 'reply',
            interval_days INTEGER NOT NULL DEFAULT 3,
            subject TEXT,
            body TEXT,
            greeting TEXT,
            signature TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            scheduled_at TIMESTAMP,
            sent_at TIMESTAMP,
            email_log_id INTEGER,
            error_message TEXT,
            material_ids TEXT,
            word_count INTEGER DEFAULT 200,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sequence_id) REFERENCES follow_up_sequences(id) ON DELETE CASCADE,
            FOREIGN KEY (email_log_id) REFERENCES email_logs(id)
        )
    ''')

    # 跟进调度表（用于批量删除时清理关联数据）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS follow_up_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            user_id INTEGER,
            sequence_id INTEGER,
            scheduled_at TIMESTAMP,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (sequence_id) REFERENCES follow_up_sequences(id)
        )
    ''')

    # 跟进模块索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_follow_up_sequences_customer ON follow_up_sequences(customer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_follow_up_sequences_user ON follow_up_sequences(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_follow_up_sequences_status ON follow_up_sequences(user_id, status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_follow_up_steps_sequence ON follow_up_steps(sequence_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_follow_up_steps_status ON follow_up_steps(status, scheduled_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_follow_up_schedules_customer ON follow_up_schedules(customer_id)')

    # email_logs 新增跟进相关字段
    try:
        cursor.execute('ALTER TABLE email_logs ADD COLUMN follow_up_sequence_id INTEGER')
    except Exception:
        pass  # 字段已存在
    try:
        cursor.execute('ALTER TABLE email_logs ADD COLUMN follow_up_step_number INTEGER')
    except Exception:
        pass
    try:
        cursor.execute('ALTER TABLE email_logs ADD COLUMN is_follow_up INTEGER DEFAULT 0')
    except Exception:
        pass

    conn.commit()
    conn.close()
    print("数据库初始化完成")
