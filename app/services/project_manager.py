"""
项目管理服务模块
提供多项目管理、项目文件夹自动整理、历史参数模板化等功能
"""
import os
import json
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
from loguru import logger

from app.utils.utils import storage_dir


class ProjectStatus(str, Enum):
    """项目状态枚举"""
    ACTIVE = "active"           # 进行中
    COMPLETED = "completed"     # 已完成
    ARCHIVED = "archived"       # 已归档


class ProjectTemplate:
    """项目模板"""

    def __init__(
        self,
        template_id: str,
        name: str,
        description: str = "",
        config: Dict[str, Any] = None,
        created_at: str = None,
    ):
        self.template_id = template_id
        self.name = name
        self.description = description
        self.config = config or {}
        self.created_at = created_at or datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "config": self.config,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectTemplate":
        return cls(**data)


class Project:
    """项目模型"""

    def __init__(
        self,
        project_id: str,
        name: str,
        description: str = "",
        status: ProjectStatus = ProjectStatus.ACTIVE,
        created_at: str = None,
        updated_at: str = None,
        user_id: str = None,
        config: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None,
        tags: List[str] = None,
        parent_project_id: str = None,  # 用于模板复制
    ):
        self.project_id = project_id
        self.name = name
        self.description = description
        self.status = status
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
        self.user_id = user_id
        self.config = config or {}
        self.metadata = metadata or {}
        self.tags = tags or []
        self.parent_project_id = parent_project_id

    @property
    def project_dir(self) -> str:
        """获取项目目录"""
        return os.path.join(self._get_base_dir(), self.project_id)

    def _get_base_dir(self) -> str:
        return os.path.join(storage_dir(create=True), "projects")

    def _ensure_dirs(self):
        """确保项目目录结构存在"""
        dirs = [
            "",  # 项目根目录
            "materials",    # 素材目录
            "output",        # 输出目录
            "temp",          # 临时文件目录
            "logs",          # 日志目录
            "drafts",        # 草稿目录
        ]
        for d in dirs:
            path = os.path.join(self.project_dir, d)
            os.makedirs(path, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "user_id": self.user_id,
            "config": self.config,
            "metadata": self.metadata,
            "tags": self.tags,
            "parent_project_id": self.parent_project_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        status = data.get("status", "active")
        if isinstance(status, str):
            status = ProjectStatus(status)

        return cls(
            project_id=data["project_id"],
            name=data["name"],
            description=data.get("description", ""),
            status=status,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            user_id=data.get("user_id"),
            config=data.get("config", {}),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            parent_project_id=data.get("parent_project_id"),
        )


class ProjectManager:
    """项目管理器"""

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
        self._projects_dir = os.path.join(storage_dir(create=True), "projects")
        self._projects_index_file = os.path.join(self._projects_dir, "index.json")
        self._templates_file = os.path.join(self._projects_dir, "templates.json")
        self._projects: Dict[str, Project] = {}
        self._templates: Dict[str, ProjectTemplate] = {}
        self._load_projects()
        self._load_templates()

    def _load_projects(self):
        """加载项目索引"""
        if not os.path.exists(self._projects_index_file):
            logger.info("项目索引文件不存在，创建新索引")
            return

        try:
            with open(self._projects_index_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for project_id, project_data in data.items():
                try:
                    project = Project.from_dict(project_data)
                    self._projects[project_id] = project
                    # 确保目录存在
                    project._ensure_dirs()
                except Exception as e:
                    logger.error(f"加载项目 {project_id} 失败: {e}")

            logger.info(f"已加载 {len(self._projects)} 个项目")
        except Exception as e:
            logger.error(f"加载项目索引失败: {e}")

    def _load_templates(self):
        """加载项目模板"""
        if not os.path.exists(self._templates_file):
            logger.info("项目模板文件不存在")
            return

        try:
            with open(self._templates_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for template_id, template_data in data.items():
                try:
                    template = ProjectTemplate.from_dict(template_data)
                    self._templates[template_id] = template
                except Exception as e:
                    logger.error(f"加载模板 {template_id} 失败: {e}")

            logger.info(f"已加载 {len(self._templates)} 个项目模板")
        except Exception as e:
            logger.error(f"加载项目模板失败: {e}")

    def _save_projects_index(self):
        """保存项目索引"""
        try:
            os.makedirs(os.path.dirname(self._projects_index_file), exist_ok=True)
            data = {pid: p.to_dict() for pid, p in self._projects.items()}
            with open(self._projects_index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存项目索引失败: {e}")

    def _save_templates(self):
        """保存模板"""
        try:
            os.makedirs(os.path.dirname(self._templates_file), exist_ok=True)
            data = {tid: t.to_dict() for tid, t in self._templates.items()}
            with open(self._templates_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存模板失败: {e}")

    def create_project(
        self,
        name: str,
        description: str = "",
        user_id: str = None,
        config: Dict[str, Any] = None,
        tags: List[str] = None,
        template_id: str = None,
    ) -> Project:
        """
        创建新项目

        Args:
            name: 项目名称
            description: 项目描述
            user_id: 用户ID
            config: 项目配置
            tags: 标签列表
            template_id: 模板ID（从模板创建）

        Returns:
            Project: 创建的项目对象
        """
        from uuid import uuid4

        project_id = str(uuid4())

        # 如果从模板创建，复制模板配置
        if template_id and template_id in self._templates:
            template = self._templates[template_id]
            project_config = template.config.copy()
            if config:
                project_config.update(config)
            description = description or template.description
        else:
            project_config = config or {}

        project = Project(
            project_id=project_id,
            name=name,
            description=description,
            user_id=user_id,
            config=project_config,
            tags=tags or [],
            parent_project_id=template_id,
        )

        project._ensure_dirs()
        self._projects[project_id] = project
        self._save_projects_index()

        logger.info(f"创建新项目: {name} ({project_id})")
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """获取项目"""
        return self._projects.get(project_id)

    def update_project(self, project: Project):
        """更新项目"""
        project.updated_at = datetime.now().isoformat()
        self._save_projects_index()
        logger.debug(f"更新项目: {project.name}")

    def delete_project(self, project_id: str, delete_files: bool = True):
        """
        删除项目

        Args:
            project_id: 项目ID
            delete_files: 是否删除项目文件
        """
        if project_id not in self._projects:
            return

        project = self._projects[project_id]

        if delete_files and os.path.exists(project.project_dir):
            shutil.rmtree(project.project_dir)

        del self._projects[project_id]
        self._save_projects_index()
        logger.info(f"删除项目: {project.name}")

    def list_projects(
        self,
        status: ProjectStatus = None,
        user_id: str = None,
        tag: str = None,
    ) -> List[Project]:
        """列出项目"""
        projects = list(self._projects.values())

        if status:
            projects = [p for p in projects if p.status == status]
        if user_id:
            projects = [p for p in projects if p.user_id == user_id]
        if tag:
            projects = [p for p in projects if tag in p.tags]

        # 按更新时间倒序
        projects.sort(key=lambda x: x.updated_at, reverse=True)
        return projects

    def archive_project(self, project_id: str):
        """归档项目"""
        project = self._projects.get(project_id)
        if project:
            project.status = ProjectStatus.ARCHIVED
            project.updated_at = datetime.now().isoformat()
            self._save_projects_index()
            logger.info(f"归档项目: {project.name}")

    def duplicate_project(self, project_id: str, new_name: str = None) -> Optional[Project]:
        """复制项目"""
        original = self._projects.get(project_id)
        if not original:
            return None

        return self.create_project(
            name=new_name or f"{original.name} (副本)",
            description=original.description,
            user_id=original.user_id,
            config=original.config.copy(),
            tags=original.tags.copy(),
        )

    def get_project_stats(self, project_id: str) -> Dict[str, Any]:
        """获取项目统计信息"""
        project = self._projects.get(project_id)
        if not project:
            return {}

        stats = {
            "project_id": project_id,
            "name": project.name,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }

        # 统计各目录文件
        if os.path.exists(project.project_dir):
            for subdir in ["materials", "output", "temp", "logs", "drafts"]:
                subdir_path = os.path.join(project.project_dir, subdir)
                if os.path.exists(subdir_path):
                    file_count = sum(len(files) for _, _, files in os.walk(subdir_path))
                    stats[f"{subdir}_file_count"] = file_count

                    # 计算目录大小
                    total_size = sum(
                        os.path.getsize(os.path.join(dirpath, f))
                        for dirpath, _, files in os.walk(subdir_path)
                        for f in files
                    )
                    stats[f"{subdir}_size"] = total_size

        return stats

    # ===== 模板管理 =====

    def create_template(
        self,
        name: str,
        description: str = "",
        config: Dict[str, Any] = None,
        from_project_id: str = None,
    ) -> ProjectTemplate:
        """
        创建项目模板

        Args:
            name: 模板名称
            description: 模板描述
            config: 模板配置
            from_project_id: 从现有项目创建模板

        Returns:
            ProjectTemplate: 创建的模板对象
        """
        from uuid import uuid4

        template_id = str(uuid4())

        # 如果从项目创建，使用项目的配置
        if from_project_id and from_project_id in self._projects:
            source_project = self._projects[from_project_id]
            template_config = source_project.config.copy()
            if config:
                template_config.update(config)
            description = description or f"从项目 {source_project.name} 创建的模板"
        else:
            template_config = config or {}

        template = ProjectTemplate(
            template_id=template_id,
            name=name,
            description=description,
            config=template_config,
        )

        self._templates[template_id] = template
        self._save_templates()

        logger.info(f"创建项目模板: {name} ({template_id})")
        return template

    def get_template(self, template_id: str) -> Optional[ProjectTemplate]:
        """获取模板"""
        return self._templates.get(template_id)

    def delete_template(self, template_id: str):
        """删除模板"""
        if template_id in self._templates:
            del self._templates[template_id]
            self._save_templates()
            logger.info(f"删除模板: {template_id}")

    def list_templates(self, user_id: str = None) -> List[ProjectTemplate]:
        """列出模板"""
        templates = list(self._templates.values())
        templates.sort(key=lambda x: x.created_at, reverse=True)
        return templates

    def apply_template(self, template_id: str, project_id: str = None, project_name: str = None) -> Optional[Project]:
        """
        应用模板创建项目

        Args:
            template_id: 模板ID
            project_id: 如果提供，更新现有项目配置
            project_name: 新项目名称

        Returns:
            Project: 创建或更新的项目对象
        """
        template = self._templates.get(template_id)
        if not template:
            return None

        if project_id and project_id in self._projects:
            # 更新现有项目
            project = self._projects[project_id]
            project.config.update(template.config)
            project.updated_at = datetime.now().isoformat()
            self._save_projects_index()
            logger.info(f"应用模板到项目: {project.name}")
            return project
        else:
            # 创建新项目
            return self.create_project(
                name=project_name or template.name,
                description=template.description,
                config=template.config.copy(),
                template_id=template_id,
            )

    def cleanup_old_projects(self, days: int = 90, keep_archived: bool = True):
        """清理旧项目"""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        to_delete = []

        for project_id, project in self._projects.items():
            updated = datetime.fromisoformat(project.updated_at)
            if updated < cutoff:
                if keep_archived and project.status == ProjectStatus.ARCHIVED:
                    continue
                to_delete.append(project_id)

        for project_id in to_delete:
            self.delete_project(project_id)

        if to_delete:
            logger.info(f"清理了 {len(to_delete)} 个旧项目")


# 全局项目管理器实例
_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    """获取项目管理器单例"""
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager()
    return _project_manager
