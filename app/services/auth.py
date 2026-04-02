"""
认证服务模块
提供用户认证相关功能：注册、登录、登出、会话管理等
"""
from typing import Optional
from loguru import logger

from app.models.user import User, UserStore, MembershipLevel


class AuthService:
    """认证服务类"""

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
        self._user_store = UserStore()
        self._current_user: Optional[User] = None
        self._session_id: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        """检查是否已登录"""
        return self._current_user is not None

    @property
    def current_user(self) -> Optional[User]:
        """获取当前登录用户"""
        return self._current_user

    def register(self, username: str, password: str, email: str = None) -> tuple[bool, str, Optional[User]]:
        """
        注册新用户

        Args:
            username: 用户名
            password: 密码
            email: 邮箱（可选）

        Returns:
            (success, message, user)
        """
        # 验证用户名
        if not username or len(username) < 3:
            return False, "用户名长度至少3个字符", None

        if len(username) > 50:
            return False, "用户名长度不能超过50个字符", None

        # 验证密码
        if not password or len(password) < 6:
            return False, "密码长度至少6个字符", None

        # 验证邮箱格式（如果提供）
        if email:
            import re
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                return False, "邮箱格式不正确", None

        try:
            user = self._user_store.create_user(username, password, email)
            logger.info(f"用户注册成功: {username}")
            return True, "注册成功", user
        except ValueError as e:
            return False, str(e), None
        except Exception as e:
            logger.error(f"注册失败: {e}")
            return False, f"注册失败: {str(e)}", None

    def login(self, username: str, password: str) -> tuple[bool, str, Optional[User]]:
        """
        用户登录

        Args:
            username: 用户名
            password: 密码

        Returns:
            (success, message, user)
        """
        if not username or not password:
            return False, "用户名和密码不能为空", None

        try:
            user = self._user_store.authenticate(username, password)
            if user:
                self._current_user = user
                self._session_id = user.user_id
                logger.info(f"用户登录成功: {username}")
                return True, "登录成功", user
            else:
                logger.warning(f"用户登录失败: {username}")
                return False, "用户名或密码错误", None
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return False, f"登录失败: {str(e)}", None

    def logout(self):
        """用户登出"""
        if self._current_user:
            logger.info(f"用户登出: {self._current_user.username}")
        self._current_user = None
        self._session_id = None

    def change_password(self, old_password: str, new_password: str) -> tuple[bool, str]:
        """
        修改密码

        Args:
            old_password: 旧密码
            new_password: 新密码

        Returns:
            (success, message)
        """
        if not self._current_user:
            return False, "用户未登录"

        if not self._current_user.verify_password(old_password):
            return False, "旧密码不正确"

        if not new_password or len(new_password) < 6:
            return False, "新密码长度至少6个字符"

        try:
            self._current_user.password_hash = User.hash_password(new_password)
            self._user_store.update_user(self._current_user)
            logger.info(f"用户修改密码: {self._current_user.username}")
            return True, "密码修改成功"
        except Exception as e:
            logger.error(f"修改密码失败: {e}")
            return False, f"修改密码失败: {str(e)}"

    def update_profile(self, email: str = None, **kwargs) -> tuple[bool, str]:
        """
        更新用户资料

        Args:
            email: 新邮箱（可选）
            **kwargs: 其他可更新的字段

        Returns:
            (success, message)
        """
        if not self._current_user:
            return False, "用户未登录"

        try:
            if email is not None:
                import re
                if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    return False, "邮箱格式不正确"
                self._current_user.email = email

            self._user_store.update_user(self._current_user)
            return True, "资料更新成功"
        except Exception as e:
            logger.error(f"更新资料失败: {e}")
            return False, f"更新资料失败: {str(e)}"

    def upgrade_membership(self, target_level: MembershipLevel) -> tuple[bool, str]:
        """
        升级会员等级（本地版本暂不支持实际支付）

        Args:
            target_level: 目标会员等级

        Returns:
            (success, message)
        """
        if not self._current_user:
            return False, "用户未登录"

        current_level = MembershipLevel(self._current_user.membership_level)
        levels = list(MembershipLevel)

        if levels.index(target_level) <= levels.index(current_level):
            return False, "只能升级到更高级别"

        # 本地版本直接升级（实际应该集成支付系统）
        self._current_user.membership_level = target_level
        self._user_store.update_user(self._current_user)
        logger.info(f"用户升级会员: {self._current_user.username} -> {target_level}")
        return True, f"已升级到{MembershipLevel(target_level).value}"

    def get_user_stats(self) -> dict:
        """获取当前用户统计数据"""
        if not self._current_user:
            return {}

        user = self._current_user
        config = user.get_membership_config()

        return {
            "username": user.username,
            "membership_level": user.membership_level,
            "membership_name": config.get("name", "未知"),
            "daily_generations": {
                "used": user.daily_generations_used,
                "limit": config.get("daily_generations", 0),
                "remaining": user.get_quota_info("daily_generations").remaining,
            },
            "video_duration": {
                "total": user.total_video_duration,
                "limit": config.get("video_duration_limit", 0),
            },
            "total_token_usage": user.total_token_usage,
            "project_count": len(user.project_ids),
            "member_since": user.created_at.strftime("%Y-%m-%d"),
        }

    def set_current_user(self, user: User):
        """设置当前用户（用于会话恢复）"""
        self._current_user = user
        self._session_id = user.user_id if user else None

    def clear_session(self):
        """清除会话"""
        self.logout()


# 全局认证服务实例
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """获取认证服务单例"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
