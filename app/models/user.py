"""
用户模型模块
定义用户、会员等级、配额等数据模型
"""
import hashlib
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import pydantic
from loguru import logger

from app.utils.utils import storage_dir


class MembershipLevel(str, Enum):
    """会员等级枚举"""
    FREE = "free"       # 免费用户
    BASIC = "basic"     # 基础会员
    PREMIUM = "premium" # 高级会员
    PRO = "pro"         # 专业会员


class QuotaType(str, Enum):
    """配额类型枚举"""
    DAILY_GENERATIONS = "daily_generations"      # 每日生成次数
    VIDEO_DURATION = "video_duration"             # 视频时长限制（秒）
    PROJECT_COUNT = "project_count"               # 项目数量
    STORAGE_SIZE = "storage_size"                # 存储空间（字节）


# 会员等级配置
MEMBERSHIP_CONFIG: Dict[MembershipLevel, Dict[str, Any]] = {
    MembershipLevel.FREE: {
        "name": "免费用户",
        "name_en": "Free",
        "daily_generations": 5,
        "video_duration_limit": 300,  # 5分钟
        "project_count": 3,
        "storage_limit": 1024 * 1024 * 1024,  # 1GB
        "features": [
            "basic_script_generation",
            "basic_video_generation",
            "community_support",
        ],
        "price": 0,
    },
    MembershipLevel.BASIC: {
        "name": "基础会员",
        "name_en": "Basic",
        "daily_generations": 20,
        "video_duration_limit": 900,  # 15分钟
        "project_count": 10,
        "storage_limit": 5 * 1024 * 1024 * 1024,  # 5GB
        "features": [
            "basic_script_generation",
            "basic_video_generation",
            "priority_support",
            "draft_save",
        ],
        "price": 29,
    },
    MembershipLevel.PREMIUM: {
        "name": "高级会员",
        "name_en": "Premium",
        "daily_generations": 50,
        "video_duration_limit": 1800,  # 30分钟
        "project_count": 30,
        "storage_limit": 20 * 1024 * 1024 * 1024,  # 20GB
        "features": [
            "advanced_script_generation",
            "advanced_video_generation",
            "priority_support",
            "draft_save",
            "project_template",
            "analytics_dashboard",
        ],
        "price": 99,
    },
    MembershipLevel.PRO: {
        "name": "专业会员",
        "name_en": "Pro",
        "daily_generations": 200,
        "video_duration_limit": 3600,  # 60分钟
        "project_count": -1,  # 无限制
        "storage_limit": 100 * 1024 * 1024 * 1024,  # 100GB
        "features": [
            "unlimited_script_generation",
            "unlimited_video_generation",
            "priority_support",
            "draft_save",
            "project_template",
            "analytics_dashboard",
            "api_access",
            "batch_processing",
            "custom_branding",
        ],
        "price": 299,
    },
}


class QuotaInfo(pydantic.BaseModel):
    """配额信息模型"""
    quota_type: QuotaType
    used: int = 0
    limit: int = 0
    reset_date: Optional[datetime] = None

    @property
    def remaining(self) -> int:
        """剩余配额"""
        if self.limit == -1:  # 无限制
            return -1
        return max(0, self.limit - self.used)

    @property
    def is_exhausted(self) -> bool:
        """配额是否已用完"""
        if self.limit == -1:
            return False
        return self.used >= self.limit

    @property
    def usage_percent(self) -> float:
        """配额使用百分比"""
        if self.limit == -1:
            return 0.0
        if self.limit == 0:
            return 100.0
        return min(100.0, (self.used / self.limit) * 100)


class UsageRecord(pydantic.BaseModel):
    """使用记录模型"""
    timestamp: datetime
    action: str  # 如 "script_generation", "video_generation", etc.
    details: Dict[str, Any] = {}
    token_count: int = 0
    video_duration: float = 0.0  # 视频时长（秒）


class User(pydantic.BaseModel):
    """用户模型"""
    user_id: str
    username: str
    password_hash: str
    email: Optional[str] = None
    membership_level: MembershipLevel = MembershipLevel.FREE
    created_at: datetime = pydantic.Field(default_factory=datetime.now)
    last_login: Optional[datetime] = None

    # 配额相关
    daily_generations_used: int = 0
    daily_generations_reset: Optional[datetime] = None
    total_video_duration: float = 0.0  # 累计视频时长（秒）
    total_token_usage: int = 0

    # 项目相关
    project_ids: List[str] = []

    # 使用历史
    usage_history: List[UsageRecord] = []

    class Config:
        use_enum_values = True

    @staticmethod
    def hash_password(password: str) -> str:
        """密码哈希"""
        return hashlib.sha256(password.encode()).hexdigest()

    def verify_password(self, password: str) -> bool:
        """验证密码"""
        return self.password_hash == self.hash_password(password)

    def get_membership_config(self) -> Dict[str, Any]:
        """获取会员配置"""
        return MEMBERSHIP_CONFIG.get(MembershipLevel(self.membership_level), MEMBERSHIP_CONFIG[MembershipLevel.FREE])

    def get_quota_info(self, quota_type: QuotaType) -> QuotaInfo:
        """获取配额信息"""
        config = self.get_membership_config()
        reset_date = self._get_daily_reset_date()

        if quota_type == QuotaType.DAILY_GENERATIONS:
            return QuotaInfo(
                quota_type=quota_type,
                used=self.daily_generations_used,
                limit=config.get("daily_generations", 0),
                reset_date=reset_date,
            )
        elif quota_type == QuotaType.VIDEO_DURATION:
            return QuotaInfo(
                quota_type=quota_type,
                used=int(self.total_video_duration),
                limit=config.get("video_duration_limit", 0),
                reset_date=None,
            )
        elif quota_type == QuotaType.PROJECT_COUNT:
            return QuotaInfo(
                quota_type=quota_type,
                used=len(self.project_ids),
                limit=config.get("project_count", 0),
                reset_date=None,
            )
        return QuotaInfo(quota_type=quota_type, used=0, limit=0)

    def _get_daily_reset_date(self) -> datetime:
        """获取每日配额重置日期（次日0点）"""
        now = datetime.now()
        tomorrow = now.date() + timedelta(days=1)
        return datetime.combine(tomorrow, datetime.min.time())

    def check_quota(self, quota_type: QuotaType, amount: int = 1) -> bool:
        """检查配额是否足够"""
        quota_info = self.get_quota_info(quota_type)
        if quota_info.limit == -1:  # 无限制
            return True
        return quota_info.remaining >= amount

    def consume_quota(self, quota_type: QuotaType, amount: int = 1) -> bool:
        """消耗配额"""
        if not self.check_quota(quota_type, amount):
            return False

        if quota_type == QuotaType.DAILY_GENERATIONS:
            self.daily_generations_used += amount
        elif quota_type == QuotaType.VIDEO_DURATION:
            self.total_video_duration += amount
        elif quota_type == QuotaType.PROJECT_COUNT:
            pass  # 项目数量在项目创建/删除时管理
        return True

    def add_usage_record(self, action: str, details: Dict[str, Any] = None,
                         token_count: int = 0, video_duration: float = 0.0):
        """添加使用记录"""
        record = UsageRecord(
            timestamp=datetime.now(),
            action=action,
            details=details or {},
            token_count=token_count,
            video_duration=video_duration,
        )
        self.usage_history.append(record)
        self.total_token_usage += token_count

        # 只保留最近100条记录
        if len(self.usage_history) > 100:
            self.usage_history = self.usage_history[-100:]

    def reset_daily_quota_if_needed(self):
        """如果需要，重置每日配额"""
        if self.daily_generations_reset is None:
            self.daily_generations_reset = self._get_daily_reset_date()
            return

        now = datetime.now()
        if now >= self.daily_generations_reset:
            self.daily_generations_used = 0
            self.daily_generations_reset = self._get_daily_reset_date()
            logger.info(f"用户 {self.username} 每日配额已重置")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "password_hash": self.password_hash,
            "email": self.email,
            "membership_level": self.membership_level,
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "daily_generations_used": self.daily_generations_used,
            "daily_generations_reset": self.daily_generations_reset.isoformat() if self.daily_generations_reset else None,
            "total_video_duration": self.total_video_duration,
            "total_token_usage": self.total_token_usage,
            "project_ids": self.project_ids,
            "usage_history": [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "action": r.action,
                    "details": r.details,
                    "token_count": r.token_count,
                    "video_duration": r.video_duration,
                }
                for r in self.usage_history
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """从字典创建"""
        # 处理日期时间字段
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("last_login"), str):
            data["last_login"] = datetime.fromisoformat(data["last_login"])
        if isinstance(data.get("daily_generations_reset"), str):
            data["daily_generations_reset"] = datetime.fromisoformat(data["daily_generations_reset"])

        # 处理使用历史
        if "usage_history" in data:
            usage_history = []
            for r in data["usage_history"]:
                if isinstance(r["timestamp"], str):
                    r["timestamp"] = datetime.fromisoformat(r["timestamp"])
                usage_history.append(UsageRecord(**r))
            data["usage_history"] = usage_history

        return cls(**data)


class UserStore:
    """用户存储管理类"""

    _instance = None
    _users_file = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._users_file = os.path.join(storage_dir(create=True), "users.json")
        self._users: Dict[str, User] = {}
        self._username_index: Dict[str, str] = {}  # username -> user_id
        self._load_users()

    def _load_users(self):
        """从文件加载用户数据"""
        if not os.path.exists(self._users_file):
            logger.info("用户数据文件不存在，创建新存储")
            return

        try:
            import json
            with open(self._users_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for user_id, user_data in data.items():
                try:
                    user = User.from_dict(user_data)
                    self._users[user_id] = user
                    self._username_index[user.username] = user_id
                except Exception as e:
                    logger.error(f"加载用户 {user_id} 失败: {e}")

            logger.info(f"已加载 {len(self._users)} 个用户")
        except Exception as e:
            logger.error(f"加载用户数据失败: {e}")

    def _save_users(self):
        """保存用户数据到文件"""
        try:
            import json
            os.makedirs(os.path.dirname(self._users_file), exist_ok=True)
            data = {user_id: user.to_dict() for user_id, user in self._users.items()}
            with open(self._users_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("用户数据已保存")
        except Exception as e:
            logger.error(f"保存用户数据失败: {e}")

    def get_user(self, user_id: str) -> Optional[User]:
        """获取用户"""
        return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> Optional[User]:
        """通过用户名获取用户"""
        user_id = self._username_index.get(username)
        if user_id:
            return self._users.get(user_id)
        return None

    def create_user(self, username: str, password: str, email: str = None) -> User:
        """创建新用户"""
        from uuid import uuid4

        if username in self._username_index:
            raise ValueError(f"用户名 {username} 已存在")

        user = User(
            user_id=str(uuid4()),
            username=username,
            password_hash=User.hash_password(password),
            email=email,
            membership_level=MembershipLevel.FREE,
        )

        self._users[user.user_id] = user
        self._username_index[username] = user.user_id
        self._save_users()

        logger.info(f"创建新用户: {username}")
        return user

    def update_user(self, user: User):
        """更新用户"""
        if user.user_id in self._users:
            self._save_users()
            logger.debug(f"更新用户: {user.username}")

    def delete_user(self, user_id: str):
        """删除用户"""
        if user_id in self._users:
            user = self._users[user_id]
            del self._username_index[user.username]
            del self._users[user_id]
            self._save_users()
            logger.info(f"删除用户: {user.username}")

    def list_users(self) -> List[User]:
        """列出所有用户"""
        return list(self._users.values())

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """验证用户登录"""
        user = self.get_user_by_username(username)
        if user and user.verify_password(password):
            user.last_login = datetime.now()
            user.reset_daily_quota_if_needed()
            self._save_users()
            logger.info(f"用户登录: {username}")
            return user
        return None
