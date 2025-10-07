"""
バッチ解析処理キューサービス
"""

import asyncio
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """タスクステータス"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class TaskPriority(Enum):
    """タスク優先度"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class Task:
    """タスククラス"""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        retry_delay: int = 60
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.payload = payload
        self.priority = priority
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.status = TaskStatus.PENDING
        self.created_at = datetime.utcnow()
        self.started_at = None
        self.completed_at = None
        self.retries = 0
        self.error_message = None
        self.result = None

    def to_dict(self) -> Dict:
        """タスクを辞書形式に変換"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "payload": json.dumps(self.payload),
            "priority": self.priority.value,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "completed_at": self.completed_at.isoformat() if self.completed_at else "",
            "retries": self.retries,
            "error_message": self.error_message or "",
            "result": json.dumps(self.result) if self.result is not None else ""
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Task':
        """辞書からタスクを復元"""
        task = cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            payload=json.loads(data["payload"]),
            priority=TaskPriority(int(data["priority"])),
            max_retries=int(data["max_retries"]),
            retry_delay=int(data["retry_delay"])
        )
        task.status = TaskStatus(data["status"])
        task.created_at = datetime.fromisoformat(data["created_at"])
        task.started_at = datetime.fromisoformat(data["started_at"]) if data["started_at"] and data["started_at"] != "" else None
        task.completed_at = datetime.fromisoformat(data["completed_at"]) if data["completed_at"] and data["completed_at"] != "" else None
        task.retries = int(data["retries"])
        task.error_message = data["error_message"] or None
        task.result = json.loads(data["result"]) if data["result"] and data["result"] != "" else None
        return task


class TaskQueue:
    """タスクキューマネージャー"""

    def __init__(self):
        self.redis_client = None
        self.task_handlers: Dict[str, Callable] = {}
        self.worker_tasks: List[asyncio.Task] = []
        self.is_running = False

    async def connect(self):
        """Redis接続"""
        try:
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("Task queue connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self):
        """Redis接続切断"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Task queue disconnected from Redis")

    def register_handler(self, task_type: str, handler: Callable):
        """タスクハンドラー登録"""
        self.task_handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")

    async def enqueue_task(
        self,
        task_type: str,
        payload: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        retry_delay: int = 60
    ) -> str:
        """タスクをキューに追加"""
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            priority=priority,
            max_retries=max_retries,
            retry_delay=retry_delay
        )

        # Redisにタスクを保存
        task_key = f"task:{task_id}"
        await self.redis_client.hset(task_key, mapping=task.to_dict())
        await self.redis_client.expire(task_key, 86400 * 7)  # 7日で期限切れ

        # 優先度キューに追加
        queue_key = f"queue:{priority.name.lower()}"
        await self.redis_client.lpush(queue_key, task_id)

        logger.info(f"Task enqueued: {task_id} ({task_type})")
        return task_id

    async def dequeue_task(self) -> Optional[Task]:
        """優先度順でタスクを取得"""
        # 優先度順にキューをチェック
        for priority in [TaskPriority.URGENT, TaskPriority.HIGH, TaskPriority.NORMAL, TaskPriority.LOW]:
            queue_key = f"queue:{priority.name.lower()}"
            task_id = await self.redis_client.rpop(queue_key)

            if task_id:
                task_key = f"task:{task_id}"
                task_data = await self.redis_client.hgetall(task_key)

                if task_data:
                    return Task.from_dict(task_data)

        return None

    async def update_task_status(self, task_id: str, status: TaskStatus, **kwargs):
        """タスクステータス更新"""
        task_key = f"task:{task_id}"
        updates = {"status": status.value}

        if status == TaskStatus.RUNNING:
            updates["started_at"] = datetime.utcnow().isoformat()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            updates["completed_at"] = datetime.utcnow().isoformat()

        # 追加の更新項目
        for key, value in kwargs.items():
            if key in ["error_message", "result", "retries"]:
                if key == "result" and value is not None:
                    updates[key] = json.dumps(value)
                else:
                    updates[key] = value

        await self.redis_client.hset(task_key, mapping=updates)
        logger.debug(f"Task {task_id} status updated to {status.value}")

    async def get_task_status(self, task_id: str) -> Optional[Dict]:
        """タスクステータス取得"""
        task_key = f"task:{task_id}"
        task_data = await self.redis_client.hgetall(task_key)

        if task_data:
            # JSONフィールドをパース
            if task_data.get("payload"):
                task_data["payload"] = json.loads(task_data["payload"])
            if task_data.get("result"):
                task_data["result"] = json.loads(task_data["result"])
            return task_data

        return None

    async def retry_task(self, task: Task):
        """タスクリトライ"""
        if task.retries < task.max_retries:
            task.retries += 1
            task.status = TaskStatus.RETRYING

            # リトライ遅延後にキューに戻す
            await asyncio.sleep(task.retry_delay)

            queue_key = f"queue:{task.priority.name.lower()}"
            await self.redis_client.lpush(queue_key, task.task_id)

            await self.update_task_status(
                task.task_id,
                TaskStatus.PENDING,
                retries=task.retries
            )

            logger.info(f"Task {task.task_id} retried ({task.retries}/{task.max_retries})")
        else:
            await self.update_task_status(
                task.task_id,
                TaskStatus.FAILED,
                error_message=f"Max retries ({task.max_retries}) exceeded"
            )
            logger.error(f"Task {task.task_id} failed after {task.max_retries} retries")

    async def process_task(self, task: Task):
        """タスク処理"""
        if task.task_type not in self.task_handlers:
            await self.update_task_status(
                task.task_id,
                TaskStatus.FAILED,
                error_message=f"No handler for task type: {task.task_type}"
            )
            return

        handler = self.task_handlers[task.task_type]

        try:
            await self.update_task_status(task.task_id, TaskStatus.RUNNING)

            # ハンドラー実行
            result = await handler(task.payload)

            await self.update_task_status(
                task.task_id,
                TaskStatus.COMPLETED,
                result=result
            )

            logger.info(f"Task {task.task_id} completed successfully")

        except Exception as e:
            error_message = f"Task execution failed: {str(e)}"
            logger.error(f"Task {task.task_id} error: {error_message}")

            await self.update_task_status(
                task.task_id,
                TaskStatus.FAILED,
                error_message=error_message
            )

            # リトライ判定
            await self.retry_task(task)

    async def worker(self, worker_id: str):
        """ワーカープロセス"""
        logger.info(f"Task worker {worker_id} started")

        while self.is_running:
            try:
                task = await self.dequeue_task()

                if task:
                    logger.info(f"Worker {worker_id} processing task {task.task_id}")
                    await self.process_task(task)
                else:
                    # タスクがない場合は短時間待機
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(5)

        logger.info(f"Task worker {worker_id} stopped")

    async def start_workers(self, num_workers: int = 3):
        """ワーカー開始"""
        if self.is_running:
            return

        self.is_running = True

        for i in range(num_workers):
            worker_task = asyncio.create_task(self.worker(f"worker-{i}"))
            self.worker_tasks.append(worker_task)

        logger.info(f"Started {num_workers} task workers")

    async def stop_workers(self):
        """ワーカー停止"""
        self.is_running = False

        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
            self.worker_tasks.clear()

        logger.info("All task workers stopped")

    async def get_queue_stats(self) -> Dict:
        """キュー統計情報"""
        stats = {
            "queues": {},
            "total_pending": 0
        }

        for priority in TaskPriority:
            queue_key = f"queue:{priority.name.lower()}"
            count = await self.redis_client.llen(queue_key)
            stats["queues"][priority.name.lower()] = count
            stats["total_pending"] += count

        return stats


# シングルトンインスタンス
task_queue = TaskQueue()