"""
抽象接口定义 - 用于解耦核心模块间的循环依赖
"""
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, List, Optional


class ISender(ABC):
    """邮件发送器接口"""

    @abstractmethod
    def send_email(self, to_email, subject, body, email_type='personal', source='manual') -> Tuple[bool, str]:
        """
        发送单封邮件
        Returns: (success: bool, message: str)
        """
        pass


class IQueueManager(ABC):
    """发送队列管理器接口"""

    @abstractmethod
    def create_task(self, task_id, email_items, send_config, step_status=None, email_preview=None):
        pass

    @abstractmethod
    def start_task(self, task_id):
        pass

    @abstractmethod
    def pause_task(self, task_id) -> bool:
        pass

    @abstractmethod
    def resume_task(self, task_id) -> bool:
        pass

    @abstractmethod
    def cancel_task(self, task_id) -> bool:
        pass

    @abstractmethod
    def get_task_status(self, task_id) -> Optional[Dict]:
        pass
