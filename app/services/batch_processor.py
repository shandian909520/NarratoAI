#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
批量处理器 - NarratoAI
提供视频队列管理、批量任务调度和队列状态持久化功能
"""

import json
import os
import threading
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pydantic
from loguru import logger

from app.config import config
from app.models import const
from app.services import state as sm
from app.utils import utils


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"       # 等待中
    PROCESSING = "processing" # 处理中
    COMPLETE = "complete"    # 已完成
    FAILED = "failed"        # 失败
    PAUSED = "paused"        # 暂停
    CANCELLED = "cancelled"  # 已取消


class ProcessingMode(str, Enum):
    """处理模式枚举"""
    SERIAL = "serial"     # 串行处理
    PARALLEL = "parallel" # 并行处理


class QueueItem(pydantic.BaseModel):
    """队列项数据模型"""
    id: str = pydantic.Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""                              # 任务名称
    video_path: str = ""                        # 视频路径
    script_path: str = ""                       # 脚本路径
    status: TaskStatus = TaskStatus.PENDING      # 任务状态
    progress: float = 0.0                       # 进度 0-100
    error_message: str = ""                      # 错误信息
    created_at: str = ""                        # 创建时间
    started_at: Optional[str] = None           # 开始时间
    completed_at: Optional[str] = None          # 完成时间
    result_video: Optional[str] = None          # 结果视频路径
    processing_time: Optional[float] = None     # 处理耗时(秒)
    # 各阶段进度
    stage_progress: Dict[str, Any] = pydantic.Field(default_factory=dict)

    class Config:
        use_enum_values = True


class BatchProgressCallback:
    """批量处理进度回调"""

    def __init__(self, queue_item_id: str, callback: Optional[Callable] = None):
        self.queue_item_id = queue_item_id
        self.callback = callback
        self._lock = threading.Lock()

    def __call__(self, stage: str, step: str, progress: float, **kwargs):
        """进度回调函数

        Args:
            stage: 阶段名称 (script/tts/clip/subtitle/merge)
            step: 步骤名称
            progress: 进度值 0-100
            **kwargs: 额外参数
        """
        with self._lock:
            try:
                # 更新队列项的阶段进度
                queue = QueueManager.get_instance()
                item = queue.get_item(self.queue_item_id)
                if item:
                    if stage not in item.stage_progress:
                        item.stage_progress[stage] = {}
                    item.stage_progress[stage][step] = {
                        "progress": progress,
                        "updated_at": datetime.now().isoformat(),
                        **kwargs
                    }
                    # 计算总进度
                    total_progress = self._calculate_total_progress(item.stage_progress)
                    item.progress = total_progress
                    queue.update_item(item)

                    # 如果有回调，调用回调
                    if self.callback:
                        self.callback(self.queue_item_id, stage, step, progress, **kwargs)

                    # 更新任务状态
                    sm.state.update_task(
                        self.queue_item_id,
                        state=const.TASK_STATE_PROCESSING,
                        progress=total_progress
                    )
            except Exception as e:
                logger.error(f"进度回调更新失败: {e}")

    def _calculate_total_progress(self, stage_progress: Dict[str, Any]) -> float:
        """计算总进度"""
        if not stage_progress:
            return 0.0

        # 定义各阶段的权重
        stage_weights = {
            "script": 15,   # 文案生成 15%
            "tts": 20,      # TTS 20%
            "clip": 30,     # 剪辑 30%
            "subtitle": 10, # 字幕 10%
            "merge": 25,    # 合成 25%
        }

        total_weight = sum(stage_weights.values())
        total_progress = 0.0

        for stage, steps in stage_progress.items():
            if stage in stage_weights:
                stage_p = 0.0
                if isinstance(steps, dict):
                    step_count = len(steps)
                    if step_count > 0:
                        stage_p = sum(
                            s.get("progress", 0) for s in steps.values()
                        ) / step_count
                total_progress += (stage_weights[stage] / total_weight) * stage_p

        return min(100.0, total_progress)


class QueueManager:
    """队列管理器 - 单例模式"""

    _instance: Optional['QueueManager'] = None
    _lock = threading.Lock()

    def __init__(self):
        self._queue: Dict[str, QueueItem] = {}
        self._processing_lock = threading.Lock()
        self._persist_path = os.path.join(utils.storage_dir("queue"), "queue_state.json")
        self._load_queue()

    @classmethod
    def get_instance(cls) -> 'QueueManager':
        """获取单例实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load_queue(self):
        """从磁盘加载队列状态"""
        try:
            if os.path.exists(self._persist_path):
                with open(self._persist_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item_data in data.get("queue", []):
                        item = QueueItem(**item_data)
                        self._queue[item.id] = item
                logger.info(f"已从 {self._persist_path} 加载队列状态，共 {len(self._queue)} 个任务")
        except Exception as e:
            logger.error(f"加载队列状态失败: {e}")

    def _save_queue(self):
        """保存队列状态到磁盘"""
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            data = {
                "queue": [item.model_dump() for item in self._queue.values()],
                "saved_at": datetime.now().isoformat()
            }
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存队列状态失败: {e}")

    def add_item(self, item: QueueItem) -> str:
        """添加队列项

        Args:
            item: 队列项

        Returns:
            队列项ID
        """
        with self._processing_lock:
            item.created_at = datetime.now().isoformat()
            self._queue[item.id] = item
            self._save_queue()
            logger.info(f"添加任务到队列: {item.id} - {item.name}")
        return item.id

    def add_items(self, items: List[QueueItem]) -> List[str]:
        """批量添加队列项

        Args:
            items: 队列项列表

        Returns:
            队列项ID列表
        """
        return [self.add_item(item) for item in items]

    def get_item(self, item_id: str) -> Optional[QueueItem]:
        """获取队列项

        Args:
            item_id: 队列项ID

        Returns:
            队列项，如果不存在返回None
        """
        return self._queue.get(item_id)

    def update_item(self, item: QueueItem):
        """更新队列项

        Args:
            item: 队列项
        """
        with self._processing_lock:
            self._queue[item.id] = item
            self._save_queue()

    def remove_item(self, item_id: str) -> bool:
        """移除队列项

        Args:
            item_id: 队列项ID

        Returns:
            是否成功移除
        """
        with self._processing_lock:
            if item_id in self._queue:
                del self._queue[item_id]
                self._save_queue()
                return True
            return False

    def get_queue(self) -> List[QueueItem]:
        """获取队列列表

        Returns:
            队列项列表
        """
        return list(self._queue.values())

    def get_pending_items(self) -> List[QueueItem]:
        """获取等待中的任务

        Returns:
            等待中的任务列表
        """
        return [
            item for item in self._queue.values()
            if item.status == TaskStatus.PENDING
        ]

    def get_processing_items(self) -> List[QueueItem]:
        """获取处理中的任务

        Returns:
            处理中的任务列表
        """
        return [
            item for item in self._queue.values()
            if item.status == TaskStatus.PROCESSING
        ]

    def get_completed_items(self) -> List[QueueItem]:
        """获取已完成的任务

        Returns:
            已完成的任务列表
        """
        return [
            item for item in self._queue.values()
            if item.status == TaskStatus.COMPLETE
        ]

    def get_failed_items(self) -> List[QueueItem]:
        """获取失败的任务

        Returns:
            失败的任务列表
        """
        return [
            item for item in self._queue.values()
            if item.status == TaskStatus.FAILED
        ]

    def clear_completed(self):
        """清除已完成的任务"""
        with self._processing_lock:
            self._queue = {
                k: v for k, v in self._queue.items()
                if v.status not in [TaskStatus.COMPLETE, TaskStatus.FAILED]
            }
            self._save_queue()

    def clear_all(self):
        """清除所有任务"""
        with self._processing_lock:
            self._queue.clear()
            self._save_queue()

    def reorder(self, item_ids: List[str]):
        """重新排序队列

        Args:
            item_ids: 新的顺序ID列表
        """
        with self._processing_lock:
            new_queue = {}
            for item_id in item_ids:
                if item_id in self._queue:
                    new_queue[item_id] = self._queue[item_id]
            # 添加不在列表中的项
            for item_id, item in self._queue.items():
                if item_id not in new_queue:
                    new_queue[item_id] = item
            self._queue = new_queue
            self._save_queue()


class BatchProcessor:
    """批量处理器"""

    def __init__(self, mode: ProcessingMode = ProcessingMode.SERIAL, max_workers: int = 2):
        """
        初始化批量处理器

        Args:
            mode: 处理模式 (串行/并行)
            max_workers: 最大并行 worker 数
        """
        self.mode = mode
        self.max_workers = max_workers
        self._is_running = False
        self._is_paused = False
        self._current_item_id: Optional[str] = None
        self._lock = threading.Lock()
        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(self, callback: Callable):
        """设置进度回调函数

        Args:
            callback: 回调函数，签名: callback(item_id, stage, step, progress, **kwargs)
        """
        self._progress_callback = callback

    def _create_progress_callback(self, item_id: str) -> BatchProgressCallback:
        """创建进度回调"""
        return BatchProgressCallback(item_id, self._progress_callback)

    def process_item(self, item: QueueItem) -> bool:
        """
        处理单个队列项

        Args:
            item: 队列项

        Returns:
            是否处理成功
        """
        from app.services import task as tm
        from app.models.schema import VideoClipParams

        item.status = TaskStatus.PROCESSING
        item.started_at = datetime.now().isoformat()
        item.progress = 0
        QueueManager.get_instance().update_item(item)

        logger.info(f"开始处理任务: {item.id} - {item.name}")

        try:
            # 创建参数对象
            params = VideoClipParams(
                video_clip_json_path=item.script_path,
                video_origin_path=item.video_path,
            )

            # 创建进度回调
            progress_cb = self._create_progress_callback(item.id)

            # 动态导入和执行任务
            # 由于 start_subclip_unified 现在支持 progress_callback，
            # 我们通过状态管理来跟踪进度
            sm.state.update_task(
                item.id,
                state=const.TASK_STATE_PROCESSING,
                progress=0
            )

            # 在新线程中执行任务
            def run_task():
                try:
                    tm.start_subclip_unified(
                        task_id=item.id,
                        params=params,
                        progress_callback=progress_cb
                    )
                    # 更新状态为完成
                    item.status = TaskStatus.COMPLETE
                    item.completed_at = datetime.now().isoformat()
                    item.progress = 100
                    item.result_video = sm.state.get_task(item.id).get("videos", [None])[0]
                    if item.result_video:
                        item.result_video = item.result_video[0] if isinstance(item.result_video, list) else item.result_video
                    sm.state.update_task(
                        item.id,
                        state=const.TASK_STATE_COMPLETE,
                        progress=100
                    )
                except Exception as e:
                    logger.error(f"任务执行失败: {e}")
                    item.status = TaskStatus.FAILED
                    item.error_message = str(e)
                    item.completed_at = datetime.now().isoformat()
                    sm.state.update_task(
                        item.id,
                        state=const.TASK_STATE_FAILED,
                        message=str(e)
                    )

            thread = threading.Thread(target=run_task)
            thread.start()
            thread.join()

            success = item.status == TaskStatus.COMPLETE
            if success:
                logger.success(f"任务完成: {item.id} - {item.name}")
            else:
                logger.error(f"任务失败: {item.id} - {item.name}, 错误: {item.error_message}")

            QueueManager.get_instance().update_item(item)
            return success

        except Exception as e:
            logger.error(f"处理任务异常: {item.id} - {e}")
            item.status = TaskStatus.FAILED
            item.error_message = str(e)
            item.completed_at = datetime.now().isoformat()
            QueueManager.get_instance().update_item(item)
            sm.state.update_task(
                item.id,
                state=const.TASK_STATE_FAILED,
                message=str(e)
            )
            return False

    def process_all(self, queue_ids: Optional[List[str]] = None):
        """
        处理队列中的所有任务

        Args:
            queue_ids: 要处理的任务ID列表，None表示处理所有待处理任务
        """
        with self._lock:
            self._is_running = True

        try:
            queue = QueueManager.get_instance()

            if queue_ids:
                items = [queue.get_item(id) for id in queue_ids if queue.get_item(id)]
            else:
                items = queue.get_pending_items()

            if not items:
                logger.info("没有待处理的任务")
                return

            logger.info(f"开始批量处理，共 {len(items)} 个任务，模式: {self.mode.value}")

            if self.mode == ProcessingMode.SERIAL:
                self._process_serial(items)
            else:
                self._process_parallel(items)

        finally:
            with self._lock:
                self._is_running = False

    def _process_serial(self, items: List[QueueItem]):
        """串行处理"""
        for item in items:
            if not self._is_running:
                logger.info("批量处理已停止")
                break
            while self._is_paused:
                logger.info("批量处理已暂停")
                threading.Event().wait(1)
            self.process_item(item)

    def _process_parallel(self, items: List[QueueItem]):
        """并行处理"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.process_item, item): item
                for item in items
            }
            for future in as_completed(futures):
                if not self._is_running:
                    logger.info("批量处理已停止")
                    executor.shutdown(wait=False)
                    break

    def pause(self):
        """暂停处理"""
        with self._lock:
            self._is_paused = True
        logger.info("批量处理已暂停")

    def resume(self):
        """继续处理"""
        with self._lock:
            self._is_paused = False
        logger.info("批量处理已继续")

    def stop(self):
        """停止处理"""
        with self._lock:
            self._is_running = False
        logger.info("批量处理已停止")

    def is_running(self) -> bool:
        """是否正在运行"""
        return self._is_running

    def is_paused(self) -> bool:
        """是否已暂停"""
        return self._is_paused


# 全局批量处理器实例
_batch_processor: Optional[BatchProcessor] = None


def get_batch_processor() -> BatchProcessor:
    """获取全局批量处理器实例"""
    global _batch_processor
    if _batch_processor is None:
        _batch_processor = BatchProcessor()
    return _batch_processor


def create_queue_item(
    name: str,
    video_path: str,
    script_path: str,
    **kwargs
) -> QueueItem:
    """创建队列项的便捷函数

    Args:
        name: 任务名称
        video_path: 视频路径
        script_path: 脚本路径
        **kwargs: 其他参数

    Returns:
        QueueItem: 队列项
    """
    return QueueItem(
        name=name,
        video_path=video_path,
        script_path=script_path,
        **kwargs
    )


def add_to_queue(
    name: str,
    video_path: str,
    script_path: str,
    **kwargs
) -> str:
    """添加任务到队列的便捷函数

    Args:
        name: 任务名称
        video_path: 视频路径
        script_path: 脚本路径
        **kwargs: 其他参数

    Returns:
        str: 队列项ID
    """
    item = create_queue_item(name, video_path, script_path, **kwargs)
    return QueueManager.get_instance().add_item(item)


def get_queue_status() -> Dict[str, Any]:
    """获取队列状态的便捷函数

    Returns:
        Dict: 队列状态信息
    """
    queue = QueueManager.get_instance()
    all_items = queue.get_queue()

    return {
        "total": len(all_items),
        "pending": len(queue.get_pending_items()),
        "processing": len(queue.get_processing_items()),
        "completed": len(queue.get_completed_items()),
        "failed": len(queue.get_failed_items()),
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "status": item.status.value if isinstance(item.status, Enum) else item.status,
                "progress": item.progress,
                "error_message": item.error_message,
                "stage_progress": item.stage_progress,
                "created_at": item.created_at,
                "started_at": item.started_at,
                "completed_at": item.completed_at,
                "processing_time": item.processing_time,
                "result_video": item.result_video,
            }
            for item in all_items
        ]
    }
