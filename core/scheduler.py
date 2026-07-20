"""
邮件调度器 - 基于 APScheduler
支持 cron 定时和 interval 间隔两种触发模式
"""
import json
import os
import sqlite3
import time
import threading
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from database.connection import get_connection
from services.email_filter import EmailFilter


class EmailScheduler:
    """基于 APScheduler 的邮件调度器"""

    def __init__(self, task_trigger_callback=None):
        self.scheduler = BackgroundScheduler()
        self.config = self._load_config()
        self.filter_engine = EmailFilter(self.config)
        self._running = False
        self._job_id = 'daily_email_task'
        self._lock = threading.Lock()
        self.task_trigger_callback = task_trigger_callback  # 通过回调解耦循环依赖

    def _load_config(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'scheduler_config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'mode': 'interval',
            'cron_hour': 9,
            'cron_minute': 0,
            'send_interval': 120,
            'daily_limit': 200,
            'cooldown_days': 7,
            'filter': {'countries': [], 'industry': '', 'email_type': 'all'},
            'generation': 'template'
        }

    def _save_config(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'scheduler_config.json')
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

    def update_config(self, new_config):
        self.config.update(new_config)
        self._save_config()
        self.filter_engine = EmailFilter(self.config)
        # 如果调度器正在运行，重新调度任务
        if self._running:
            self.scheduler.remove_job(self._job_id)
            self._add_job()

    def start(self):
        if self._running and self.scheduler.running:
            return False, '调度器已在运行'
        try:
            # 如果 scheduler 实例已死亡，重新创建
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            self.scheduler = BackgroundScheduler()
            self._add_job()
            self.scheduler.start()
            self._running = True
            return True, '调度器已启动'
        except Exception as e:
            self._running = False
            return False, str(e)

    def stop(self):
        if not self._running and not self.scheduler.running:
            return False, '调度器未在运行'
        try:
            self.scheduler.shutdown(wait=False)
            self._running = False
            # 重新创建 scheduler 实例以便可以再次启动
            self.scheduler = BackgroundScheduler()
            return True, '调度器已停止'
        except Exception as e:
            return False, str(e)

    def _add_job(self):
        mode = self.config.get('mode', 'interval')
        if mode == 'cron':
            trigger = CronTrigger(
                hour=self.config.get('cron_hour', 9),
                minute=self.config.get('cron_minute', 0)
            )
        else:
            trigger = IntervalTrigger(seconds=self.config.get('send_interval', 120))

        self.scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            id=self._job_id,
            replace_existing=True,
            max_instances=1
        )

    def run_now(self):
        """手动立即执行一次任务"""
        try:
            # 确保调度器在运行状态
            if not self.scheduler.running:
                self.scheduler = BackgroundScheduler()
                self.scheduler.start()
                self._running = True

            self.scheduler.add_job(
                self._execute_task,
                id='manual_run_' + str(int(time.time())),
                max_instances=1
            )
            return True, '手动任务已加入队列'
        except Exception as e:
            self._running = False
            return False, str(e)

    def _execute_task(self):
        """执行一次邮件发送任务 - 调度器只负责触发，发送逻辑通过 callback 交给外部编排器。
        支持多用户：为每个有 pending 任务的 user_id 分别触发发送。"""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 调度器触发发送任务")

        # 获取所有有 pending 任务的 user_id（去重）
        user_ids = []
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT c.user_id
                FROM send_schedule ss
                JOIN customers c ON ss.customer_id = c.id
                WHERE ss.status = 'pending' AND c.user_id IS NOT NULL
            ''')
            rows = cursor.fetchall()
            user_ids = [r[0] for r in rows if r[0] is not None]
            conn.close()
        except Exception as e:
            print(f"  读取任务 user_id 失败: {e}")

        if not user_ids:
            print("  没有 pending 的调度任务")
            return

        send_config = {
            'interval_seconds': self.config.get('send_interval', 120),
            'auto_pause_after': 0,
            'max_retries': 2,
            'pause_on_error': False,
        }

        for task_user_id in user_ids:
            filter_config = {
                'countries': self.config.get('filter', {}).get('countries', []),
                'industry': self.config.get('filter', {}).get('industry', ''),
                'email_type': self.config.get('filter', {}).get('email_type', 'all'),
                'cooldown_days': self.config.get('cooldown_days', 7),
                'daily_limit': self.config.get('daily_limit', 200),
                'user_id': task_user_id
            }

            print(f"  为 user_id={task_user_id} 触发调度任务")
            try:
                if self.task_trigger_callback:
                    # 通过回调调用外部编排器，避免循环导入
                    result = self.task_trigger_callback(
                        filter_config=filter_config,
                        send_config=send_config,
                        task_type='scheduled',
                        target_word_count=self.config.get('word_count', 200),
                        user_id=task_user_id,
                        sender_material_id=self.config.get('sender_material_id'),
                        num_subjects=self.config.get('num_subjects', 0)
                    )
                else:
                    # 兼容旧模式：运行时动态导入（fallback）
                    from core.orchestrator import orchestrator
                    result = orchestrator.create_send_task(
                        filter_config=filter_config,
                        send_config=send_config,
                        task_type='scheduled',
                        target_word_count=self.config.get('word_count', 200),
                        user_id=task_user_id,
                        sender_material_id=self.config.get('sender_material_id'),
                        num_subjects=self.config.get('num_subjects', 0)
                    )

                if result and result.get('task_id'):
                    print(f"  user_id={task_user_id}: 已创建发送任务 {result['task_id']}, 客户: {result['total_customers']} 家")
                else:
                    print(f"  user_id={task_user_id}: 创建发送任务失败: {result.get('error', '未知错误') if result else '无结果'}")
            except Exception as e:
                print(f"  user_id={task_user_id}: 调度异常: {e}")

        # ========== 执行到期的跟进步骤 ==========
        try:
            from database.follow_up_models import get_due_steps
            from generators.workflow import EmailWorkflow
            from database.connection import get_connection
            from send_queue.manager import log_email_send

            due_steps = get_due_steps()  # 获取所有到期的 approved 步骤
            if due_steps:
                print(f"  发现 {len(due_steps)} 个到期跟进步骤")
                workflow = EmailWorkflow()

                for step in due_steps:
                    seq = step.get('sequence', {})
                    user_id = seq.get('user_id')
                    customer_id = seq.get('customer_id')
                    step_id = step['id']
                    sequence_id = step['sequence_id']

                    try:
                        # 1. 生成跟进邮件
                        result = workflow.generate_follow_up_email(sequence_id, step_id, user_id=user_id)
                        if not result:
                            print(f"    步骤{step_id}: 生成失败")
                            continue

                        # 2. 获取该客户的所有活跃邮箱
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute('''
                            SELECT id, email_address, contact_name, email_type
                            FROM emails WHERE customer_id = ? AND is_active = 1
                        ''', (customer_id,))
                        emails = cursor.fetchall()

                        if not emails:
                            print(f"    步骤{step_id}: 客户{customer_id}无活跃邮箱")
                            continue

                        # 3. 为每个邮箱发送
                        send_config = {
                            'interval_seconds': self.config.get('send_interval', 120),
                            'max_retries': 2,
                        }

                        from send_queue.manager import send_queue_manager
                        task_id = f"followup_{sequence_id}_{step_id}"

                        email_items = []
                        for e in emails:
                            email_items.append({
                                'email_id': e[0],
                                'customer_id': customer_id,
                                'email_address': e[1],
                                'contact_name': e[2] or '',
                                'email_type': e[3],
                                'subject': result['subject'],
                                'greeting': result.get('greeting', ''),
                                'body': result['body'],
                            })

                        send_queue_manager.create_task(task_id, email_items, send_config)
                        # 启动发送（非阻塞）
                        import threading
                        t = threading.Thread(target=send_queue_manager._execute_task, args=(send_queue_manager._tasks[task_id],), daemon=True)
                        t.start()

                        conn.close()
                        print(f"    步骤{step_id}: 已创建发送任务 ({len(emails)}封)")

                    except Exception as e:
                        print(f"    步骤{step_id}: 执行异常 - {e}")
                        from database.follow_up_models import mark_step_failed
                        mark_step_failed(step_id, str(e))

        except Exception as e:
            print(f"  跟进步骤执行异常: {e}")

        print(f"  [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 调度器触发完毕")

    def get_preview(self):
        """预览本次将发送的邮件列表"""
        filter_config = {
            'countries': self.config.get('filter', {}).get('countries', []),
            'industry': self.config.get('filter', {}).get('industry', ''),
            'email_type': self.config.get('filter', {}).get('email_type', 'all'),
            'cooldown_days': self.config.get('cooldown_days', 7),
            'daily_limit': self.config.get('daily_limit', 200)
        }
        return self.filter_engine.preview(filter_config)

    def get_status(self, user_id=None):
        """获取调度器状态

        Args:
            user_id: 用户ID，用于数据隔离。为None时返回全局统计（管理员视图）。
        """
        conn = get_connection()
        cursor = conn.cursor()

        # 构建 user_id 过滤条件（通过 customers 表 join）
        user_join = ""
        user_where = ""
        params_list = []
        if user_id is not None:
            user_join = "JOIN customers c ON ss.customer_id = c.id"
            user_where = "AND c.user_id = ?"
            params_list = [user_id]

        # 队列统计
        cursor.execute(
            f"SELECT COUNT(*) FROM send_schedule ss {user_join} WHERE ss.status = 'pending' {user_where}",
            params_list
        )
        pending = cursor.fetchone()[0]

        cursor.execute(
            f"SELECT COUNT(*) FROM send_schedule ss {user_join} WHERE ss.status = 'sent' {user_where}",
            params_list
        )
        sent = cursor.fetchone()[0]

        cursor.execute(
            f"SELECT COUNT(*) FROM send_schedule ss {user_join} WHERE ss.status = 'failed' {user_where}",
            params_list
        )
        failed = cursor.fetchone()[0]

        # 逾期（pending 且 scheduled_at 已过）
        cursor.execute(
            f"SELECT COUNT(*) FROM send_schedule ss {user_join} WHERE ss.status = 'pending' AND ss.scheduled_at < datetime('now') {user_where}",
            params_list
        )
        overdue = cursor.fetchone()[0]

        # 今日发送统计（通过 email_logs 关联 customers）
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        if user_id is not None:
            cursor.execute('''
                SELECT COUNT(*)
                FROM email_logs el
                JOIN emails e ON el.email_id = e.id
                JOIN customers c ON e.customer_id = c.id
                WHERE el.sent_at >= ? AND c.user_id = ?
            ''', (today_start, user_id))
        else:
            cursor.execute("SELECT COUNT(*) FROM email_logs WHERE sent_at >= ?", (today_start,))
        today_sent = cursor.fetchone()[0]

        conn.close()

        # 下次执行时间
        next_run = None
        if self._running:
            try:
                job = self.scheduler.get_job(self._job_id)
                if job and job.next_run_time:
                    next_run = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

        return {
            'running': self._running,
            'mode': self.config.get('mode', 'interval'),
            'config': self.config,
            'pending': pending,
            'sent': sent,
            'failed': failed,
            'overdue': overdue,
            'today_sent': today_sent,
            'daily_limit': self.config.get('daily_limit', 200),
            'next_run': next_run
        }

    def get_queue(self, user_id=None):
        """获取发送队列详情

        Args:
            user_id: 用户ID，用于数据隔离。为None时返回全局队列（管理员视图）。
        """
        conn = get_connection()
        cursor = conn.cursor()

        if user_id is not None:
            cursor.execute('''
                SELECT ss.id, ss.email_id, ss.customer_id, ss.scheduled_at, ss.status,
                       c.customer_name, e.email_address
                FROM send_schedule ss
                LEFT JOIN customers c ON ss.customer_id = c.id
                LEFT JOIN emails e ON ss.email_id = e.id
                WHERE c.user_id = ?
                ORDER BY ss.scheduled_at DESC
                LIMIT 50
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT ss.id, ss.email_id, ss.customer_id, ss.scheduled_at, ss.status,
                       c.customer_name, e.email_address
                FROM send_schedule ss
                LEFT JOIN customers c ON ss.customer_id = c.id
                LEFT JOIN emails e ON ss.email_id = e.id
                ORDER BY ss.scheduled_at DESC
                LIMIT 50
            ''')
        rows = cursor.fetchall()
        conn.close()

        return [{
            'id': r[0], 'email_id': r[1], 'customer_id': r[2],
            'scheduled_at': r[3], 'status': r[4],
            'customer_name': r[5], 'email_address': r[6]
        } for r in rows]


# 全局调度器实例
scheduler_instance = EmailScheduler()
