"""
会员服务模块
提供会员等级管理、配额检查、权益验证等功能
"""
from typing import Dict, List, Optional, Any
from loguru import logger

from app.models.user import (
    MembershipLevel,
    MEMBERSHIP_CONFIG,
    QuotaType,
    QuotaInfo,
    User,
    UserStore,
)


class MembershipService:
    """会员服务类"""

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

    def get_all_membership_levels(self) -> List[Dict[str, Any]]:
        """获取所有会员等级信息"""
        levels = []
        for level in MembershipLevel:
            config = MEMBERSHIP_CONFIG[level]
            levels.append({
                "level": level.value,
                "name": config["name"],
                "name_en": config["name_en"],
                "price": config["price"],
                "features": config["features"],
                "daily_generations": config["daily_generations"],
                "video_duration_limit": config["video_duration_limit"],
                "project_count": config["project_count"],
                "storage_limit": config["storage_limit"],
            })
        return levels

    def get_membership_details(self, level: MembershipLevel) -> Dict[str, Any]:
        """获取指定会员等级的详细信息"""
        config = MEMBERSHIP_CONFIG.get(level, MEMBERSHIP_CONFIG[MembershipLevel.FREE])
        return {
            "level": level.value,
            "name": config["name"],
            "name_en": config["name_en"],
            "price": config["price"],
            "features": config["features"],
            "daily_generations": config["daily_generations"],
            "video_duration_limit": config["video_duration_limit"],
            "project_count": config["project_count"],
            "storage_limit": config["storage_limit"],
        }

    def get_user_membership(self, user: User) -> Dict[str, Any]:
        """获取用户的会员信息"""
        level = MembershipLevel(user.membership_level)
        config = MEMBERSHIP_CONFIG[level]

        return {
            "level": level.value,
            "name": config["name"],
            "name_en": config["name_en"],
            "features": config["features"],
            "daily_generations_info": {
                "used": user.daily_generations_used,
                "limit": config["daily_generations"],
                "remaining": user.get_quota_info(QuotaType.DAILY_GENERATIONS).remaining,
                "reset_at": user.daily_generations_reset.isoformat() if user.daily_generations_reset else None,
            },
            "video_duration_info": {
                "total": user.total_video_duration,
                "limit": config["video_duration_limit"],
                "remaining": config["video_duration_limit"] - user.total_video_duration
                    if config["video_duration_limit"] > 0 else -1,
            },
            "project_count_info": {
                "used": len(user.project_ids),
                "limit": config["project_count"],
            },
            "storage_limit": config["storage_limit"],
        }

    def check_quota(self, user: User, quota_type: QuotaType, amount: int = 1) -> tuple[bool, str]:
        """
        检查用户配额是否足够

        Args:
            user: 用户对象
            quota_type: 配额类型
            amount: 需要消耗的数量

        Returns:
            (can_use, message)
        """
        config = MEMBERSHIP_CONFIG[MembershipLevel(user.membership_level)]
        quota_info = user.get_quota_info(quota_type)

        if quota_info.is_exhausted:
            if quota_type == QuotaType.DAILY_GENERATIONS:
                reset_time = user.daily_generations_reset.strftime("%H:%M") if user.daily_generations_reset else "次日0点"
                return False, f"今日生成次数已用完，将在{reset_time}重置"
            elif quota_type == QuotaType.VIDEO_DURATION:
                return False, f"视频时长配额已用完（累计{quota_info.limit}秒）"
            elif quota_type == QuotaType.PROJECT_COUNT:
                return False, f"项目数量已达上限（{quota_info.limit}个）"

        return True, "配额充足"

    def consume_quota(self, user: User, quota_type: QuotaType, amount: int = 1) -> tuple[bool, str]:
        """
        消耗用户配额

        Args:
            user: 用户对象
            quota_type: 配额类型
            amount: 消耗数量

        Returns:
            (success, message)
        """
        can_use, msg = self.check_quota(user, quota_type, amount)
        if not can_use:
            return False, msg

        # 更新用户配额
        user.consume_quota(quota_type, amount)
        self._user_store.update_user(user)

        quota_info = user.get_quota_info(quota_type)
        remaining = quota_info.remaining if quota_info.remaining >= 0 else "无限"

        if quota_type == QuotaType.DAILY_GENERATIONS:
            return True, f"已消耗1次生成配额，剩余{remaining}次"
        elif quota_type == QuotaType.VIDEO_DURATION:
            return True, f"已消耗{amount}秒视频时长配额"

        return True, "配额已消耗"

    def check_feature_access(self, user: User, feature: str) -> tuple[bool, str]:
        """
        检查用户是否有权使用某个功能

        Args:
            user: 用户对象
            feature: 功能标识

        Returns:
            (has_access, message)
        """
        level = MembershipLevel(user.membership_level)
        config = MEMBERSHIP_CONFIG[level]

        features = config.get("features", [])

        if feature in features:
            return True, "可以使用此功能"

        # 获取需要此功能的最少会员等级
        required_level = None
        for lvl in MembershipLevel:
            if feature in MEMBERSHIP_CONFIG[lvl].get("features", []):
                required_level = lvl
                break

        if required_level:
            req_config = MEMBERSHIP_CONFIG[required_level]
            return False, f"此功能需要{req_config['name']}会员，当前为{config['name']}会员"

        return False, "此功能不可用"

    def get_available_features(self, user: User) -> Dict[str, List[str]]:
        """获取用户可用的功能列表"""
        level = MembershipLevel(user.membership_level)
        config = MEMBERSHIP_CONFIG[level]

        all_features = {
            "basic_script_generation": "基础脚本生成",
            "advanced_script_generation": "高级脚本生成",
            "unlimited_script_generation": "无限脚本生成",
            "basic_video_generation": "基础视频生成",
            "advanced_video_generation": "高级视频生成",
            "unlimited_video_generation": "无限视频生成",
            "community_support": "社区支持",
            "priority_support": "优先支持",
            "draft_save": "草稿保存",
            "project_template": "项目模板",
            "analytics_dashboard": "数据统计面板",
            "api_access": "API访问",
            "batch_processing": "批量处理",
            "custom_branding": "自定义品牌",
        }

        user_features = config.get("features", [])
        available = []
        unavailable = []

        for feature_key, feature_name in all_features.items():
            if feature_key in user_features:
                available.append(f"{feature_name} ({feature_key})")
            else:
                unavailable.append(f"{feature_name} ({feature_key})")

        return {
            "available": available,
            "unavailable": unavailable,
        }

    def format_duration(self, seconds: float) -> str:
        """格式化时长显示"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}分{secs}秒" if secs > 0 else f"{minutes}分钟"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}小时{minutes}分钟" if minutes > 0 else f"{hours}小时"

    def format_size(self, bytes_size: int) -> str:
        """格式化文件大小显示"""
        if bytes_size < 0:
            return "无限制"

        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(bytes_size)
        unit_idx = 0

        while size >= 1024 and unit_idx < len(units) - 1:
            size /= 1024
            unit_idx += 1

        return f"{size:.2f} {units[unit_idx]}"

    def get_upgrade_suggestions(self, user: User) -> List[Dict[str, Any]]:
        """获取升级建议"""
        level = MembershipLevel(user.membership_level)
        levels = list(MembershipLevel)

        # 检查哪些配额即将用完
        suggestions = []

        quota_info = user.get_quota_info(QuotaType.DAILY_GENERATIONS)
        if quota_info.usage_percent > 80 and level != MembershipLevel.PRO:
            suggestions.append({
                "type": "quota",
                "message": f"每日生成次数使用率已达 {quota_info.usage_percent:.0f}%",
                "suggested_level": "PREMIUM",
            })

        if level == MembershipLevel.FREE and len(user.project_ids) >= 3:
            suggestions.append({
                "type": "quota",
                "message": "项目数量已达免费用户上限",
                "suggested_level": "BASIC",
            })

        return suggestions


# 全局会员服务实例
_membership_service: Optional[MembershipService] = None


def get_membership_service() -> MembershipService:
    """获取会员服务单例"""
    global _membership_service
    if _membership_service is None:
        _membership_service = MembershipService()
    return _membership_service
