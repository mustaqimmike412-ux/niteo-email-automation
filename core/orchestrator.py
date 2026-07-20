"""
SendOrchestrator - 邮件发送编排层
负责将调度器的触发信号转化为完整的发送任务
包含：客户筛选、邮件生成、任务创建、进度监控
与调度器完全隔离，只通过接口交互
"""
import time
import uuid
from collections import defaultdict
from datetime import datetime

from database.connection import get_connection
from services.email_filter import EmailFilter
from generators.workflow import EmailWorkflow
from generators.subjects.manager import subject_manager


class SendOrchestrator:
    """邮件发送编排器 - 隔离调度器和发送引擎"""

    def __init__(self, sender=None, queue_manager=None, workflow=None, subject_manager_instance=None):
        self.workflow = workflow or EmailWorkflow()
        self.sender = sender  # 通过参数注入，避免循环导入
        self._queue_manager = queue_manager  # 通过参数注入，避免循环导入
        self._subject_manager = subject_manager_instance or subject_manager

    def create_send_task(self, filter_config, send_config, task_type='scheduled', target_word_count=None, user_id=None, sender_material_id=None, num_subjects=0):
        """
        创建发送任务（编排入口）

        Args:
            filter_config: 筛选配置（传给 EmailFilter）
            send_config: 发送配置（传给 SendQueueManager）
            task_type: 任务类型 'scheduled' | 'batch' | 'test'
            target_word_count: 目标字数
            user_id: 用户ID，用于数据隔离
            sender_material_id: 指定发信人素材ID
            num_subjects: 标题数量（0=自动决定）

        Returns:
            dict: {'task_id': str, 'total_emails': int, 'total_customers': int}
        """
        # 1. 筛选客户（注入 user_id 到 filter_config 以实现数据隔离）
        filter_config_with_user = dict(filter_config)
        if user_id is not None:
            filter_config_with_user['user_id'] = user_id
        filter_engine = EmailFilter(filter_config_with_user)
        emails_to_send = filter_engine.filter_customers(filter_config_with_user)

        if not emails_to_send:
            return {'task_id': None, 'total_emails': 0, 'total_customers': 0, 'error': '没有符合条件的邮件'}

        # 2. 生成任务ID
        task_id = f"{task_type}_{uuid.uuid4().hex[:8]}_{int(time.time())}"

        # 3. 按客户分组
        customer_groups = defaultdict(list)
        for item in emails_to_send:
            customer_groups[item['customer_id']].append(item)

        total_customers = len(customer_groups)
        all_email_items = []

        # 4. 为每个客户执行完整邮件工作流
        for customer_id, items in customer_groups.items():
            customer_name = items[0]['customer_name']
            website = items[0].get('website', '')
            country = items[0].get('country', '')

            try:
                # 为该客户创建使用指定发信人的工作流
                task_workflow = EmailWorkflow(user_id=user_id, sender_material_id=sender_material_id, is_admin=(user_id is None))

                # 完整工作流：背调、分类、优势、FABE、生成、排版（调度器跳过润色）
                email_content = task_workflow.generate_email(
                    customer_name, website or '',
                    target_word_count=target_word_count,
                    skip_refine=True
                )

                # 为每个邮箱构建个性化邮件（先构建基础内容）
                email_items_for_customer = []
                for item in items:
                    email_type = item['email_type']
                    contact_name = item.get('contact_name', '') or ''

                    # 生成称呼
                    if email_type == 'personal' and contact_name.strip():
                        first_name = contact_name.split()[0] if ' ' in contact_name else contact_name
                        greeting = f"Hi {first_name}"
                    else:
                        clean_name = customer_name.replace('INC.', '').replace('LLC', '').replace('Ltd.', '').strip()
                        greeting = f"Hi {clean_name} Team"

                    # 组装完整邮件正文
                    full_body = f"{greeting}\n\n{email_content['body']}\n\n{email_content['signature']}"

                    email_items_for_customer.append({
                        'email_id': item['email_id'],
                        'customer_id': customer_id,
                        'email_address': item['email_address'],
                        'email_type': email_type,
                        'contact_name': contact_name,
                        'greeting': greeting,
                        'body': full_body,
                        'customer_name': customer_name,
                    })

                # 使用智能标题管理器：生成多个标题并随机分配给各个邮箱
                subjects, assigned_items = self._subject_manager.generate_and_assign(
                    customer_id=customer_id,
                    customer_name=customer_name,
                    country=country,
                    industry='',  # 行业信息可从website_data获取，暂时留空
                    email_items=email_items_for_customer,
                    email_body=email_content['body'],
                    num_subjects=num_subjects
                )

                print(f"[编排器] 客户 {customer_name}: 生成 {len(subjects)} 个标题，分配给 {len(items)} 个邮箱")

                # 将分配好的邮件项加入总列表
                all_email_items.extend(assigned_items)

            except Exception as e:
                print(f"[编排器] 客户 {customer_name} 邮件生成失败: {e}")
                continue

        if not all_email_items:
            return {'task_id': None, 'total_emails': 0, 'total_customers': 0, 'error': '所有客户邮件生成失败'}

        # 5. 创建队列任务并启动
        if self._queue_manager is None:
            from send_queue.manager import queue_manager
            self._queue_manager = queue_manager
        self._queue_manager.create_task(
            task_id, all_email_items, send_config
        )
        self._queue_manager.start_task(task_id)

        # 6. 持久化任务元数据
        self._persist_task_meta(task_id, task_type, all_email_items, send_config, user_id=user_id)

        return {
            'task_id': task_id,
            'total_emails': len(all_email_items),
            'total_customers': total_customers
        }

    def get_task_progress(self, task_id):
        """获取任务实时进度"""
        if self._queue_manager is None:
            from send_queue.manager import queue_manager
            self._queue_manager = queue_manager
        return self._queue_manager.get_task_status(task_id)

    def pause_task(self, task_id):
        """暂停任务"""
        if self._queue_manager is None:
            from send_queue.manager import queue_manager
            self._queue_manager = queue_manager
        return self._queue_manager.pause_task(task_id)

    def resume_task(self, task_id):
        """恢复任务"""
        if self._queue_manager is None:
            from send_queue.manager import queue_manager
            self._queue_manager = queue_manager
        return self._queue_manager.resume_task(task_id)

    def cancel_task(self, task_id):
        """取消任务"""
        if self._queue_manager is None:
            from send_queue.manager import queue_manager
            self._queue_manager = queue_manager
        return self._queue_manager.cancel_task(task_id)

    def _persist_task_meta(self, task_id, task_type, email_items, send_config, user_id=None):
        """持久化任务元数据到 send_tasks_meta 表"""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # 获取第一个客户名作为任务名称
            customer_name = email_items[0].get('customer_name', '批量任务') if email_items else '批量任务'

            cursor.execute('''
                INSERT OR REPLACE INTO send_tasks_meta (
                    task_id, task_type, status, customer_id, customer_name,
                    total_emails, sent_count, failed_count, current_index, progress,
                    current_step, step_status, email_preview_subject, email_preview_body,
                    send_config, created_at, updated_at, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task_id, task_type, 'running', email_items[0].get('customer_id') if email_items else None,
                customer_name, len(email_items), 0, 0, 0, 0,
                '发送中', '{"send": "running"}',
                email_items[0].get('subject', '') if email_items else '',
                email_items[0].get('body', '')[:500] if email_items else '',
                str(send_config),
                datetime.now().isoformat(), datetime.now().isoformat(),
                user_id
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[编排器] 持久化任务元数据失败: {e}")


# 全局编排器实例
orchestrator = SendOrchestrator()
