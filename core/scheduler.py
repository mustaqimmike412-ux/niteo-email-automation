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
        """执行一次邮件发送任务 - 调度器只负责触发，发送逻辑通过 callback 交给外部编排器"""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 调度器触发发送任务")

        filter_config = {
            'countries': self.config.get('filter', {}).get('countries', []),
            'industry': self.config.get('filter', {}).get('industry', ''),
            'email_type': self.config.get('filter', {}).get('email_type', 'all'),
            'cooldown_days': self.config.get('cooldown_days', 7),
            'daily_limit': self.config.get('daily_limit', 200)
        }

        send_config = {
            'interval_seconds': self.config.get('send_interval', 120),
            'auto_pause_after': 0,
            'max_retries': 2,
            'pause_on_error': False,
        }

        try:
            if self.task_trigger_callback:
                # 通过回调调用外部编排器，避免循环导入
                result = self.task_trigger_callback(
                    filter_config=filter_config,
                    send_config=send_config,
                    task_type='scheduled'
                )
            else:
                # 兼容旧模式：运行时动态导入（fallback）
                from core.orchestrator import orchestrator
                result = orchestrator.create_send_task(
                    filter_config=filter_config,
                    send_config=send_config,
                    task_type='scheduled'
                )

            if result.get('task_id'):
                print(f"  已创建发送任务: {result['task_id']}, 客户: {result['total_customers']} 家, 邮箱: {result['total_emails']} 个")
                # 调度器不等待发送完成，立即返回
                # 发送进度由 SendQueueManager 独立维护，前端通过 /api/send-tasks/<task_id> 查询
            else:
                print(f"  创建发送任务失败: {result.get('error', '未知错误')}")
        except Exception as e:
            print(f"  调度器执行异常: {e}")
            import traceback
            traceback.print_exc()

        print(f"  [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 调度器触发完毕，发送任务在后台独立运行")

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

    def get_status(self):
        """获取调度器状态"""
        conn = get_connection()
        cursor = conn.cursor()

        # 队列统计
        cursor.execute("SELECT COUNT(*) FROM send_schedule WHERE status = 'pending'")
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM send_schedule WHERE status = 'sent'")
        sent = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM send_schedule WHERE status = 'failed'")
        failed = cursor.fetchone()[0]

        # 逾期（pending 且 scheduled_at 已过）
        cursor.execute("SELECT COUNT(*) FROM send_schedule WHERE status = 'pending' AND scheduled_at < datetime('now')")
        overdue = cursor.fetchone()[0]

        # 今日发送统计
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
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

    def get_queue(self):
        """获取发送队列详情"""
        conn = get_connection()
        cursor = conn.cursor()
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
