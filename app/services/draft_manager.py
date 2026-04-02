"""
草稿管理服务模块
提供工作进度自动保存、断点续传、异常退出后自动保存等功能
"""
import os
import json
import shutil
import atexit
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
from loguru import logger

from app.utils.utils import storage_dir


class DraftStatus(str, Enum):
    """草稿状态枚举"""
    IN_PROGRESS = "in_progress"     # 进行中
    COMPLETED = "completed"         # 已完成
    FAILED = "failed"               # 失败
    ABANDONED = "abandoned"         # 已废弃


class StepType(str, Enum):
    """步骤类型枚举"""
    SCRIPT_GENERATION = "script_generation"   # 脚本生成
    TTS_GENERATION = "tts_generation"         # TTS生成
    VIDEO_CLIP = "video_clip"                 # 视频剪辑
    SUBTITLE_GENERATION = "subtitle_generation"  # 字幕生成
    VIDEO_MERGE = "video_merge"               # 视频合并
    FINAL_EXPORT = "final_export"            # 最终导出


class StepResult:
    """步骤结果"""

    def __init__(
        self,
        step_type: StepType,
        status: DraftStatus,
        data: Dict[str, Any] = None,
        error: str = None,
        output_files: List[str] = None,
        metadata: Dict[str, Any] = None,
    ):
        self.step_type = step_type
        self.status = status
        self.data = data or {}
        self.error = error
        self.output_files = output_files or []
        self.metadata = metadata or {}
        self.completed_at = datetime.now().isoformat() if status in [DraftStatus.COMPLETED, DraftStatus.FAILED] else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_type": self.step_type.value if isinstance(self.step_type, Enum) else self.step_type,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "data": self.data,
            "error": self.error,
            "output_files": self.output_files,
            "metadata": self.metadata,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepResult":
        return cls(
            step_type=StepType(data["step_type"]),
            status=DraftStatus(data["status"]),
            data=data.get("data", {}),
            error=data.get("error"),
            output_files=data.get("output_files", []),
            metadata=data.get("metadata", {}),
        )


class Draft:
    """草稿模型"""

    def __init__(
        self,
        draft_id: str,
        name: str,
        project_id: str = None,
        status: DraftStatus = DraftStatus.IN_PROGRESS,
        current_step: StepType = None,
        step_results: List[StepResult] = None,
        context: Dict[str, Any] = None,
        created_at: str = None,
        updated_at: str = None,
        user_id: str = None,
    ):
        self.draft_id = draft_id
        self.name = name
        self.project_id = project_id
        self.status = status
        self.current_step = current_step
        self.step_results = step_results or []
        self.context = context or {}
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
        self.user_id = user_id

    def add_step_result(self, result: StepResult):
        """添加步骤结果"""
        self.step_results.append(result)
        self.current_step = result.step_type
        self.updated_at = datetime.now().isoformat()
        if result.status == DraftStatus.FAILED:
            self.status = DraftStatus.FAILED

    def get_last_successful_step(self) -> Optional[StepResult]:
        """获取最后成功的步骤"""
        for result in reversed(self.step_results):
            if result.status == DraftStatus.COMPLETED:
                return result
        return None

    def can_resume(self) -> bool:
        """是否可以恢复"""
        return self.status == DraftStatus.IN_PROGRESS and len(self.step_results) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "name": self.name,
            "project_id": self.project_id,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "current_step": self.current_step.value if isinstance(self.current_step, Enum) else self.current_step,
            "step_results": [s.to_dict() if isinstance(s, StepResult) else s for s in self.step_results],
            "context": self.context,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Draft":
        step_results = []
        for s in data.get("step_results", []):
            if isinstance(s, StepResult):
                step_results.append(s)
            else:
                step_results.append(StepResult.from_dict(s))

        current_step = data.get("current_step")
        if current_step:
            current_step = StepType(current_step)

        return cls(
            draft_id=data["draft_id"],
            name=data["name"],
            project_id=data.get("project_id"),
            status=DraftStatus(data.get("status", "in_progress")),
            current_step=current_step,
            step_results=step_results,
            context=data.get("context", {}),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            user_id=data.get("user_id"),
        )


class DraftManager:
    """草稿管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._drafts_dir = os.path.join(storage_dir(create=True), "drafts")
        self._drafts_index_file = os.path.join(self._drafts_dir, "index.json")
        self._drafts: Dict[str, Draft] = {}
        self._current_draft: Optional[Draft] = None
        self._auto_save_enabled = True
        self._load_drafts()
        atexit.register(self._emergency_save)

    def _load_drafts(self):
        """加载草稿索引"""
        if not os.path.exists(self._drafts_index_file):
            logger.info("草稿索引文件不存在，创建新索引")
            return

        try:
            with open(self._drafts_index_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for draft_id, draft_data in data.items():
                try:
                    draft = Draft.from_dict(draft_data)
                    self._drafts[draft_id] = draft
                except Exception as e:
                    logger.error(f"加载草稿 {draft_id} 失败: {e}")

            logger.info(f"已加载 {len(self._drafts)} 个草稿")
        except Exception as e:
            logger.error(f"加载草稿索引失败: {e}")

    def _save_drafts_index(self):
        """保存草稿索引"""
        try:
            os.makedirs(self._drafts_dir, exist_ok=True)
            data = {draft_id: draft.to_dict() for draft_id, draft in self._drafts.items()}
            with open(self._drafts_index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存草稿索引失败: {e}")

    def _get_draft_dir(self, draft_id: str) -> str:
        """获取草稿目录"""
        return os.path.join(self._drafts_dir, draft_id)

    def _ensure_draft_dir(self, draft_id: str) -> str:
        """确保草稿目录存在"""
        draft_dir = self._get_draft_dir(draft_id)
        os.makedirs(draft_dir, exist_ok=True)
        return draft_dir

    def create_draft(self, name: str, project_id: str = None, user_id: str = None, context: Dict[str, Any] = None) -> Draft:
        """
        创建新草稿

        Args:
            name: 草稿名称
            project_id: 项目ID
            user_id: 用户ID
            context: 初始上下文数据

        Returns:
            Draft: 创建的草稿对象
        """
        from uuid import uuid4
        import copy

        draft_id = str(uuid4())
        draft = Draft(
            draft_id=draft_id,
            name=name,
            project_id=project_id,
            user_id=user_id,
            context=copy.deepcopy(context) if context else {},
        )

        self._drafts[draft_id] = draft
        self._current_draft = draft
        self._ensure_draft_dir(draft_id)
        self._save_drafts_index()

        # 保存初始上下文
        self._save_context(draft_id, context or {})

        logger.info(f"创建新草稿: {name} ({draft_id})")
        return draft

    def _save_context(self, draft_id: str, context: Dict[str, Any]):
        """保存草稿上下文"""
        draft_dir = self._get_draft_dir(draft_id)
        context_file = os.path.join(draft_dir, "context.json")
        try:
            with open(context_file, "w", encoding="utf-8") as f:
                json.dump(context, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存上下文失败: {e}")

    def save_checkpoint(
        self,
        step_type: StepType,
        status: DraftStatus,
        data: Dict[str, Any] = None,
        error: str = None,
        output_files: List[str] = None,
        metadata: Dict[str, Any] = None,
    ):
        """
        保存检查点

        Args:
            step_type: 步骤类型
            status: 状态
            data: 步骤数据
            error: 错误信息
            output_files: 输出文件列表
            metadata: 元数据
        """
        if not self._current_draft or not self._auto_save_enabled:
            return

        result = StepResult(
            step_type=step_type,
            status=status,
            data=data,
            error=error,
            output_files=output_files,
            metadata=metadata,
        )

        self._current_draft.add_step_result(result)

        # 如果有上下文更新，保存上下文
        if data:
            self._current_draft.context.update(data)
            self._save_context(self._current_draft.draft_id, self._current_draft.context)

        # 保存步骤结果
        draft_dir = self._get_draft_dir(self._current_draft.draft_id)
        step_file = os.path.join(draft_dir, f"step_{len(self._current_draft.step_results)}.json")
        try:
            with open(step_file, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存步骤结果失败: {e}")

        self._save_drafts_index()
        logger.debug(f"保存检查点: {step_type.value} - {status.value}")

    def complete_draft(self):
        """标记草稿为完成"""
        if not self._current_draft:
            return

        self._current_draft.status = DraftStatus.COMPLETED
        self._current_draft.updated_at = datetime.now().isoformat()
        self._save_drafts_index()
        logger.info(f"草稿完成: {self._current_draft.name}")

    def abandon_draft(self, draft_id: str = None):
        """废弃草稿"""
        target_id = draft_id or (self._current_draft.draft_id if self._current_draft else None)
        if not target_id:
            return

        if target_id in self._drafts:
            self._drafts[target_id].status = DraftStatus.ABANDONED
            self._drafts[target_id].updated_at = datetime.now().isoformat()
            self._save_drafts_index()
            logger.info(f"草稿已废弃: {target_id}")

        if self._current_draft and self._current_draft.draft_id == target_id:
            self._current_draft = None

    def get_draft(self, draft_id: str) -> Optional[Draft]:
        """获取草稿"""
        return self._drafts.get(draft_id)

    def get_current_draft(self) -> Optional[Draft]:
        """获取当前草稿"""
        return self._current_draft

    def set_current_draft(self, draft_id: str):
        """设置当前草稿"""
        if draft_id in self._drafts:
            self._current_draft = self._drafts[draft_id]

    def list_drafts(
        self,
        status: DraftStatus = None,
        project_id: str = None,
        user_id: str = None,
    ) -> List[Draft]:
        """列出草稿"""
        drafts = list(self._drafts.values())

        if status:
            drafts = [d for d in drafts if d.status == status]
        if project_id:
            drafts = [d for d in drafts if d.project_id == project_id]
        if user_id:
            drafts = [d for d in drafts if d.user_id == user_id]

        # 按更新时间倒序
        drafts.sort(key=lambda x: x.updated_at, reverse=True)
        return drafts

    def delete_draft(self, draft_id: str):
        """删除草稿"""
        if draft_id in self._drafts:
            # 删除草稿目录
            draft_dir = self._get_draft_dir(draft_id)
            if os.path.exists(draft_dir):
                shutil.rmtree(draft_dir)

            del self._drafts[draft_id]
            self._save_drafts_index()

            if self._current_draft and self._current_draft.draft_id == draft_id:
                self._current_draft = None

            logger.info(f"删除草稿: {draft_id}")

    def resume_draft(self, draft_id: str) -> tuple[bool, str, Optional[Draft]]:
        """
        恢复草稿

        Returns:
            (success, message, draft)
        """
        draft = self._drafts.get(draft_id)
        if not draft:
            return False, "草稿不存在", None

        if not draft.can_resume():
            return False, f"草稿无法恢复，状态: {draft.status.value}", None

        self._current_draft = draft
        logger.info(f"恢复草稿: {draft.name} ({draft_id})")
        return True, "草稿已恢复", draft

    def get_resume_info(self, draft_id: str) -> Dict[str, Any]:
        """
        获取恢复信息

        Returns:
            包含恢复所需信息的字典
        """
        draft = self._drafts.get(draft_id)
        if not draft:
            return {}

        last_step = draft.get_last_successful_step()

        return {
            "draft_id": draft.draft_id,
            "name": draft.name,
            "status": draft.status.value,
            "current_step": draft.current_step.value if draft.current_step else None,
            "last_successful_step": last_step.step_type.value if last_step else None,
            "context": draft.context,
            "step_count": len(draft.step_results),
            "created_at": draft.created_at,
            "updated_at": draft.updated_at,
        }

    def _emergency_save(self):
        """紧急保存（程序退出时）"""
        if self._current_draft and self._auto_save_enabled:
            try:
                self._current_draft.status = DraftStatus.IN_PROGRESS
                self._current_draft.updated_at = datetime.now().isoformat()
                self._save_drafts_index()
                logger.info("紧急保存草稿完成")
            except Exception as e:
                logger.error(f"紧急保存失败: {e}")

    def enable_auto_save(self):
        """启用自动保存"""
        self._auto_save_enabled = True

    def disable_auto_save(self):
        """禁用自动保存"""
        self._auto_save_enabled = False

    def cleanup_old_drafts(self, days: int = 30):
        """清理旧草稿"""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        to_delete = []

        for draft_id, draft in self._drafts.items():
            updated = datetime.fromisoformat(draft.updated_at)
            if updated < cutoff and draft.status in [DraftStatus.COMPLETED, DraftStatus.ABANDONED]:
                to_delete.append(draft_id)

        for draft_id in to_delete:
            self.delete_draft(draft_id)

        if to_delete:
            logger.info(f"清理了 {len(to_delete)} 个旧草稿")


# 全局草稿管理器实例
_draft_manager: Optional[DraftManager] = None


def get_draft_manager() -> DraftManager:
    """获取草稿管理器单例"""
    global _draft_manager
    if _draft_manager is None:
        _draft_manager = DraftManager()
    return _draft_manager


class DraftContext:
    """草稿上下文管理器（用于with语句）"""

    def __init__(self, step_type: StepType, draft_id: str = None):
        self.step_type = step_type
        self.draft_id = draft_id
        self.draft_manager = get_draft_manager()
        self.success = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # 发生异常，保存失败状态
            error_msg = f"{exc_type.__name__}: {str(exc_val)}\n{traceback.format_exc()}"
            self.draft_manager.save_checkpoint(
                step_type=self.step_type,
                status=DraftStatus.FAILED,
                error=error_msg,
            )
            self.success = False
        else:
            # 正常完成
            self.draft_manager.save_checkpoint(
                step_type=self.step_type,
                status=DraftStatus.COMPLETED,
            )
            self.success = True
        return False  # 不吞没异常
