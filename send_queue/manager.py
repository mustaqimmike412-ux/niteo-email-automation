import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from database.log_service import log_email_send

class SendTaskItem:
    """单封邮件发送项"""
    def __init__(self, index=0, email_id=0, customer_id=0, email_address='',
                 contact_name='', email_type='', subject='', greeting='', body=''):
        self.index = index
        self.email_id = email_id
        self.customer_id = customer_id
        self.email_address = email_address
        self.contact_name = contact_name
        self.email_type = email_type
        self.subject = subject
        self.greeting = greeting
        self.body = body
        self.status = 'pending'  # pending/sending/sent/failed/retrying/skipped/cancelled
        self.retry_count = 0
        self.max_retries = 2
        self.error_message = ''
        self.scheduled_send_at = None
        self.actual_send_at = None

    def to_dict(self):
        return {
            'index': self.index,
            'email_id': self.email_id,
            'email_address': self.email_address,
            'contact_name': self.contact_name,
            'email_type': self.email_type,
            'status': self.status,
            'retry_count': self.retry_count,
            'error_message': self.error_message,
            'scheduled_send_at': self.scheduled_send_at.isoformat() if self.scheduled_send_at else None,
            'actual_send_at': self.actual_send_at.isoformat() if self.actual_send_at else None,
        }


class SendTask:
    """发送任务"""
    def __init__(self, task_id=''):
        self.task_id = task_id
        self.status = 'pending'  # pending/running/paused/completed/failed/cancelled
        self.config = {}
        self.items: List[SendTaskItem] = []
        self.created_at = time.time()
        self.started_at = None
        self.completed_at = None
        self.pause_event = threading.Event()
        self.cancel_event = threading.Event()
        self.current_index = 0
        self.email_preview = None
        self.step_status = {}
        self.progress = 0
        self.current_step = ''
        self.error = None
        self._lock = threading.Lock()

    def get_stats(self):
        sent = sum(1 for i in self.items if i.status == 'sent')
        failed = sum(1 for i in self.items if i.status == 'failed')
        total = len(self.items)
        remaining = total - sent - failed - sum(1 for i in self.items if i.status in ('cancelled',))
        return {
            'total_emails': total,
            'sent_count': sent,
            'failed_count': failed,
            'current_index': self.current_index,
            'remaining': remaining,
        }

    def get_estimated_completion(self):
        """计算预计完成时间"""
        stats = self.get_stats()
        interval = self.config.get('interval_seconds', 0)
        remaining = stats['remaining']
        if remaining <= 0 or interval <= 0:
            return None
        eta_seconds = remaining * interval
        return (datetime.now() + timedelta(seconds=eta_seconds)).isoformat()


class SendQueueManager:
    """发送队列管理器 - 管理批量邮件的延时发送、暂停恢复、错误隔离和重试"""

    def __init__(self, sender=None):
        self._tasks: Dict[str, SendTask] = {}
        self._lock = threading.Lock()
        self._sender = sender  # 通过构造函数注入，避免循环导入
        self._log_file = None
        try:
            self._log_file = open('send_queue.log', 'a', encoding='utf-8')
        except:
            pass

    def _log(self, msg):
        """同时输出到终端和日志文件"""
        print(msg, flush=True)
        if self._log_file:
            self._log_file.write(msg + '\n')
            self._log_file.flush()

    def __del__(self):
        if self._log_file:
            self._log_file.close()

    def create_task(self, task_id, email_items, send_config, step_status=None, email_preview=None):
        """创建发送任务"""
        task = SendTask(task_id)
        task.config = send_config
        task.step_status = step_status or {}
        task.email_preview = email_preview

        for i, item_data in enumerate(email_items):
            item = SendTaskItem(
                index=i,
                email_id=item_data.get('email_id', 0),
                customer_id=item_data.get('customer_id', 0),
                email_address=item_data.get('email_address', ''),
                contact_name=item_data.get('contact_name', ''),
                email_type=item_data.get('email_type', ''),
                subject=item_data.get('subject', ''),
                greeting=item_data.get('greeting', ''),
                body=item_data.get('body', ''),
            )
            item.max_retries = send_config.get('max_retries', 2)
            task.items.append(item)

        with self._lock:
            self._tasks[task_id] = task
        return task

    def start_task(self, task_id):
        """启动任务（在后台线程中执行）"""
        task = self._tasks.get(task_id)
        if not task:
            self._log(f"  [发送队列] start_task 失败: 任务 {task_id} 不存在")
            return
        # 防重复启动：检查任务是否已在运行中
        if task.status == 'running':
            self._log(f"  [发送队列] start_task: 任务 {task_id} 已在运行中，跳过启动")
            return
        self._log(f"  [发送队列] start_task: 启动线程执行任务 {task_id}")
        thread = threading.Thread(target=self._execute_task, args=(task,), daemon=True)
        thread.start()
        self._log(f"  [发送队列] start_task: 线程已启动, alive={thread.is_alive()}")

    def pause_task(self, task_id) -> bool:
        """暂停任务"""
        task = self._tasks.get(task_id)
        if not task or task.status != 'running':
            return False
        task.pause_event.clear()
        task.status = 'paused'
        return True

    def resume_task(self, task_id) -> bool:
        """恢复任务"""
        task = self._tasks.get(task_id)
        if not task or task.status != 'paused':
            return False
        task.pause_event.set()
        task.status = 'running'
        return True

    def cancel_task(self, task_id) -> bool:
        """取消任务"""
        task = self._tasks.get(task_id)
        if not task or task.status not in ('running', 'paused'):
            return False
        task.cancel_event.set()
        task.pause_event.set()  # 解除暂停阻塞
        task.status = 'cancelled'
        # 标记剩余为 cancelled
        for i in range(task.current_index, len(task.items)):
            if task.items[i].status in ('pending',):
                task.items[i].status = 'cancelled'
        return True

    def get_task(self, task_id) -> Optional[SendTask]:
        """获取任务对象"""
        return self._tasks.get(task_id)

    def get_task_status(self, task_id) -> Optional[Dict]:
        """获取任务状态（供API轮询）"""
        task = self._tasks.get(task_id)
        if not task:
            return None

        stats = task.get_stats()
        eta = task.get_estimated_completion()

        return {
            'id': task.task_id,
            'status': task.status,
            'progress': task.progress,
            'current_step': task.current_step,
            'step_status': dict(task.step_status),
            'email_preview': task.email_preview,
            'error': task.error,
            'total_emails': stats['total_emails'],
            'sent_count': stats['sent_count'],
            'failed_count': stats['failed_count'],
            'current_index': stats['current_index'],
            'items': [item.to_dict() for item in task.items],
            'estimated_completion': eta,
            'interval_seconds': task.config.get('interval_seconds', 0),
            'can_pause': task.status == 'running',
            'can_resume': task.status == 'paused',
            'can_cancel': task.status in ('running', 'paused'),
        }

    def _execute_task(self, task: SendTask):
        """任务执行主循环"""
        task.status = 'running'
        task.started_at = time.time()
        task.pause_event.set()  # 初始为非暂停状态
        task.cancel_event.clear()

        total = len(task.items)
        config = task.config
        interval_seconds = config.get('interval_seconds', 0)
        auto_pause_after = config.get('auto_pause_after', 0)
        pause_on_error = config.get('pause_on_error', False)

        self._log(f"\n  [发送队列] 任务 {task.task_id} 启动: {total} 封邮件, 间隔={interval_seconds}s, 自动暂停={auto_pause_after}, 遇错暂停={pause_on_error}")

        try:
            for i in range(task.current_index, total):
                # 检查取消
                if task.cancel_event.is_set():
                    for j in range(i, total):
                        if task.items[j].status == 'pending':
                            task.items[j].status = 'cancelled'
                    break

                # 检查暂停（阻塞直到恢复或取消）
                while not task.pause_event.is_set():
                    if task.cancel_event.is_set():
                        break
                    task.cancel_event.wait(timeout=0.5)

                if task.cancel_event.is_set():
                    for j in range(i, total):
                        if task.items[j].status == 'pending':
                            task.items[j].status = 'cancelled'
                    break

                item = task.items[i]
                item.status = 'sending'
                task.current_index = i

                # 计算计划发送时间
                item.scheduled_send_at = datetime.now()
                self._log(f"  [发送队列] [{i+1}/{total}] 发送中: {item.email_address} @ {item.scheduled_send_at.strftime('%H:%M:%S')}")

                # 执行发送（含重试）
                success = self._send_single_email(task, item)
                # 更新进度
                task.progress = int(((i + 1) / total) * 100)
                self._log(f"  [发送队列] [{i+1}/{total}] 结果: {item.status} ({item.email_address}) 进度: {task.progress}%")

                if not success and pause_on_error:
                    self._log(f"  [发送队列] 遇错暂停，等待恢复...")
                    task.status = 'paused'
                    task.pause_event.clear()
                    # 等待恢复或取消
                    while not task.pause_event.is_set():
                        if task.cancel_event.is_set():
                            break
                        task.cancel_event.wait(timeout=0.5)
                    if task.cancel_event.is_set():
                        for j in range(i + 1, total):
                            if task.items[j].status == 'pending':
                                task.items[j].status = 'cancelled'
                        break
                    task.status = 'running'
                    self._log(f"  [发送队列] 已恢复发送")

                # 发送间隔延时（最后一封不等待）
                if i < total - 1 and interval_seconds > 0:
                    # 自动暂停检查
                    if auto_pause_after > 0 and (i + 1) % auto_pause_after == 0:
                        self._log(f"  [发送队列] 自动暂停: 已发送 {i+1} 封，达到每 {auto_pause_after} 封暂停阈值")
                        task.status = 'paused'
                        task.pause_event.clear()
                        # 等待恢复或取消
                        while not task.pause_event.is_set():
                            if task.cancel_event.is_set():
                                break
                            task.cancel_event.wait(timeout=0.5)
                        if task.cancel_event.is_set():
                            for j in range(i + 1, total):
                                if task.items[j].status == 'pending':
                                    task.items[j].status = 'cancelled'
                            break
                        task.status = 'running'
                        self._log(f"  [发送队列] 自动暂停已恢复")

                    # 等待间隔（可被取消中断）
                    self._log(f"  [发送队列] 等待间隔 {interval_seconds} 秒... (下次发送: {task.items[i+1].email_address if i+1 < total else '-'})")
                    if not task.cancel_event.wait(timeout=interval_seconds):
                        self._log(f"  [发送队列] 间隔等待结束")
                        pass  # 正常等待结束
                    else:
                        for j in range(i + 1, total):
                            if task.items[j].status == 'pending':
                                task.items[j].status = 'cancelled'
                        break

            else:
                if not task.cancel_event.is_set():
                    task.status = 'completed'
                    task.completed_at = time.time()

            stats = task.get_stats()
            self._log(f"  [发送队列] 任务 {task.task_id} 结束: status={task.status}, 发送={stats['sent_count']}, 失败={stats['failed_count']}")

        except Exception as e:
            task.status = 'failed'
            task.error = str(e)
            self._log(f"  [发送队列] 任务 {task.task_id} 异常: {e}")

        # 持久化到数据库
        self._persist_task(task)

    def _send_single_email(self, task: SendTask, item: SendTaskItem) -> bool:
        """发送单封邮件（含重试逻辑）"""
        max_retries = item.max_retries

        # 兜底：发送前检查该公司是否已在冷却期内发送成功（排除手动解除的）
        try:
            from database.connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            # 检查是否被手动解除冷却
            cursor.execute('SELECT 1 FROM cooldown_override WHERE customer_id = ?', (item.customer_id,))
            if cursor.fetchone():
                conn.close()
                # 被手动解除，跳过冷却期检查
                pass
            else:
                cooldown_days = task.config.get('cooldown_days', 7)
                cutoff = (datetime.now() - timedelta(days=cooldown_days)).isoformat()
                # 同一批量任务内的发送记录不计入冷却期检查（任务完成后统一冷却）
                cursor.execute(
                    'SELECT 1 FROM email_logs WHERE customer_id = ? AND send_status = "sent" AND sent_at >= ? AND (task_id IS NULL OR task_id != ?)',
                    (item.customer_id, cutoff, task.task_id)
                )
                if cursor.fetchone():
                    item.status = 'skipped'
                    item.error_message = f'该公司在{cooldown_days}天内已发送过，已跳过'
                    self._log(f"    [跳过] {item.email_address}: 公司级冷却期内已发送")
                    conn.close()
                    return False
                conn.close()
        except Exception as e:
            self._log(f"    [冷却期检查失败] {item.email_address}: {e}")

        for attempt in range(max_retries + 1):
            if task.cancel_event.is_set():
                item.status = 'cancelled'
                return False

            try:
                if self._sender is None:
                    from core.sender import EmailSender
                    self._sender = EmailSender()

                # 邮件正文已包含称呼（由编排层组装），直接使用
                body = item.body

                success, message = self._sender.send_email(
                    item.email_address,
                    item.subject,
                    body,
                    item.email_type
                )

                if success:
                    item.status = 'sent'
                    item.actual_send_at = datetime.now()
                    self._log_to_email_logs(task, item, True, message)
                    return True
                else:
                    item.error_message = message
                    item.retry_count = attempt + 1
                    self._log(f"    [发送失败] {item.email_address}: {message} (尝试 {attempt+1}/{max_retries+1})")

                    if attempt < max_retries:
                        item.status = 'retrying'
                        retry_delay = min(5 * (2 ** attempt), 60)
                        self._log(f"    [重试] {retry_delay}秒后重试...")
                        task.cancel_event.wait(timeout=retry_delay)
                    else:
                        item.status = 'failed'
                        item.actual_send_at = datetime.now()
                        self._log_to_email_logs(task, item, False, message)
                        return False

            except Exception as e:
                item.error_message = str(e)
                item.retry_count = attempt + 1
                self._log(f"    [发送异常] {item.email_address}: {e} (尝试 {attempt+1}/{max_retries+1})")

                if attempt < max_retries:
                    item.status = 'retrying'
                    retry_delay = min(5 * (2 ** attempt), 60)
                    self._log(f"    [重试] {retry_delay}秒后重试...")
                    task.cancel_event.wait(timeout=retry_delay)
                else:
                    item.status = 'failed'
                    item.actual_send_at = datetime.now()
                    self._log_to_email_logs(task, item, False, str(e))
                    return False

        return False

    def _log_to_email_logs(self, task, item, success, message):
        """记录到 email_logs 表 - 统一通过 log_service 写入"""
        try:
            # 判断来源：scheduled/batch 任务或手动任务
            source = 'scheduled' if any(k in task.task_id for k in ['scheduled', 'batch']) else 'manual'

            log_id = log_email_send(
                customer_id=item.customer_id,
                email_id=item.email_id,
                task_id=task.task_id,
                source=source,
                subject=item.subject,
                content=item.body if item.body else '',
                status='sent' if success else 'failed',
                error_message=message if not success else None,
            )
            self._log(f"  [发送队列] 发送日志已记录: log_id={log_id}, source={source}, status={'sent' if success else 'failed'}, email={item.email_address}")
        except Exception as e:
            self._log(f"  ⚠ 记录发送日志失败: {e}")

    def _persist_task(self, task):
        """持久化任务项到数据库"""
        try:
            from database.connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            for item in task.items:
                cursor.execute('''
                    INSERT OR REPLACE INTO send_task_items
                    (task_id, email_id, customer_id, email_address, contact_name, email_type,
                     subject, greeting, item_status, retry_count, max_retries, error_message,
                     scheduled_send_at, actual_send_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task.task_id, item.email_id, item.customer_id, item.email_address,
                    item.contact_name, item.email_type, item.subject, item.greeting,
                    item.status, item.retry_count, item.max_retries, item.error_message,
                    item.scheduled_send_at.isoformat() if item.scheduled_send_at else None,
                    item.actual_send_at.isoformat() if item.actual_send_at else None,
                ))
            conn.commit()
            conn.close()
        except Exception as e:
            self._log(f"  ⚠ 持久化任务项失败: {e}")


queue_manager = SendQueueManager()
