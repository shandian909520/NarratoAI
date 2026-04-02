"""
数据统计服务模块
提供使用统计、Token消耗、视频时长等数据收集功能
"""
import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from loguru import logger

from app.utils.utils import storage_dir


class ActionType(str):
    """操作类型"""
    SCRIPT_GENERATION = "script_generation"
    VIDEO_GENERATION = "video_generation"
    TTS_GENERATION = "tts_generation"
    SUBTITLE_GENERATION = "subtitle_generation"
    PROJECT_CREATED = "project_created"
    PROJECT_DELETED = "project_deleted"
    DRAFT_SAVED = "draft_saved"
    DRAFT_RESTORED = "draft_restored"
    TEMPLATE_USED = "template_used"


class StatsRecord:
    """统计记录"""

    def __init__(
        self,
        record_id: str,
        user_id: str = None,
        action_type: str = None,
        timestamp: str = None,
        details: Dict[str, Any] = None,
        token_count: int = 0,
        video_duration: float = 0.0,
        project_id: str = None,
        success: bool = True,
    ):
        self.record_id = record_id
        self.user_id = user_id
        self.action_type = action_type
        self.timestamp = timestamp or datetime.now().isoformat()
        self.details = details or {}
        self.token_count = token_count
        self.video_duration = video_duration
        self.project_id = project_id
        self.success = success

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "timestamp": self.timestamp,
            "details": self.details,
            "token_count": self.token_count,
            "video_duration": self.video_duration,
            "project_id": self.project_id,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StatsRecord":
        return cls(**data)


class StatsCollector:
    """数据统计收集器"""

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
        self._stats_dir = os.path.join(storage_dir(create=True), "stats")
        self._records_file = os.path.join(self._stats_dir, "records.json")
        self._daily_file = os.path.join(self._stats_dir, "daily_stats.json")
        self._records: List[StatsRecord] = []
        self._daily_stats: Dict[str, Dict[str, int]] = {}  # date -> {action_type: count}
        self._load_stats()

    def _load_stats(self):
        """加载统计数据"""
        # 加载记录
        if os.path.exists(self._records_file):
            try:
                with open(self._records_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._records = [StatsRecord.from_dict(r) for r in data]
                logger.info(f"已加载 {len(self._records)} 条统计记录")
            except Exception as e:
                logger.error(f"加载统计记录失败: {e}")

        # 加载每日统计
        if os.path.exists(self._daily_file):
            try:
                with open(self._daily_file, "r", encoding="utf-8") as f:
                    self._daily_stats = json.load(f)
            except Exception as e:
                logger.error(f"加载每日统计失败: {e}")

    def _save_stats(self):
        """保存统计数据"""
        try:
            os.makedirs(self._stats_dir, exist_ok=True)

            # 保存记录（只保留最近10000条）
            if len(self._records) > 10000:
                self._records = self._records[-10000:]

            with open(self._records_file, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in self._records], f, ensure_ascii=False, indent=2)

            # 保存每日统计
            with open(self._daily_file, "w", encoding="utf-8") as f:
                json.dump(self._daily_stats, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"保存统计数据失败: {e}")

    def _update_daily_stats(self, action_type: str, amount: int = 1):
        """更新每日统计"""
        today = datetime.now().strftime("%Y-%m-%d")

        if today not in self._daily_stats:
            self._daily_stats[today] = {}

        if action_type not in self._daily_stats[today]:
            self._daily_stats[today][action_type] = 0

        self._daily_stats[today][action_type] += amount

    def record_action(
        self,
        action_type: str,
        user_id: str = None,
        details: Dict[str, Any] = None,
        token_count: int = 0,
        video_duration: float = 0.0,
        project_id: str = None,
        success: bool = True,
    ) -> StatsRecord:
        """
        记录操作

        Args:
            action_type: 操作类型
            user_id: 用户ID
            details: 详细信息
            token_count: Token消耗数量
            video_duration: 视频时长（秒）
            project_id: 项目ID
            success: 是否成功

        Returns:
            StatsRecord: 创建的记录对象
        """
        from uuid import uuid4

        record = StatsRecord(
            record_id=str(uuid4()),
            user_id=user_id,
            action_type=action_type,
            details=details or {},
            token_count=token_count,
            video_duration=video_duration,
            project_id=project_id,
            success=success,
        )

        self._records.append(record)
        self._update_daily_stats(action_type)
        self._save_stats()

        logger.debug(f"记录操作: {action_type}")
        return record

    def get_user_stats(
        self,
        user_id: str,
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> Dict[str, Any]:
        """
        获取用户统计数据

        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            dict: 用户统计数据
        """
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        # 筛选该用户的记录
        user_records = [
            r for r in self._records
            if r.user_id == user_id
            and start_date <= datetime.fromisoformat(r.timestamp) <= end_date
        ]

        stats = {
            "user_id": user_id,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "total_actions": len(user_records),
            "successful_actions": len([r for r in user_records if r.success]),
            "failed_actions": len([r for r in user_records if not r.success]),
            "total_tokens": sum(r.token_count for r in user_records),
            "total_video_duration": sum(r.video_duration for r in user_records),
            "action_breakdown": {},
        }

        # 统计各操作类型数量
        for record in user_records:
            action = record.action_type
            if action not in stats["action_breakdown"]:
                stats["action_breakdown"][action] = {
                    "count": 0,
                    "tokens": 0,
                    "duration": 0.0,
                }
            stats["action_breakdown"][action]["count"] += 1
            stats["action_breakdown"][action]["tokens"] += record.token_count
            stats["action_breakdown"][action]["duration"] += record.video_duration

        return stats

    def get_daily_stats(self, date: datetime = None) -> Dict[str, Any]:
        """
        获取每日统计数据

        Args:
            date: 日期，默认为今天

        Returns:
            dict: 每日统计数据
        """
        if date is None:
            date = datetime.now()

        date_str = date.strftime("%Y-%m-%d")
        daily_data = self._daily_stats.get(date_str, {})

        total_count = sum(daily_data.values())

        return {
            "date": date_str,
            "total_actions": total_count,
            "actions": daily_data,
        }

    def get_weekly_stats(self, week_start: datetime = None) -> Dict[str, Any]:
        """
        获取本周统计数据

        Args:
            week_start: 周开始日期，默认为本周一

        Returns:
            dict: 周统计数据
        """
        if week_start is None:
            # 计算本周一
            today = datetime.now()
            week_start = today - timedelta(days=today.weekday())

        week_end = week_start + timedelta(days=7)
        daily_data = {}

        for i in range(7):
            date = (week_start + timedelta(days=i)).strftime("%Y-%m-%d")
            if date in self._daily_stats:
                daily_data[date] = self._daily_stats[date]

        total_count = sum(sum(d.values()) for d in daily_data.values())

        return {
            "week_start": week_start.strftime("%Y-%m-%d"),
            "week_end": (week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
            "total_actions": total_count,
            "daily_breakdown": daily_data,
        }

    def get_monthly_stats(self, year: int = None, month: int = None) -> Dict[str, Any]:
        """
        获取月度统计数据

        Args:
            year: 年份，默认为今年
            month: 月份，默认为本月

        Returns:
            dict: 月度统计数据
        """
        now = datetime.now()
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        prefix = f"{year}-{month:02d}"
        monthly_data = {
            date: data
            for date, data in self._daily_stats.items()
            if date.startswith(prefix)
        }

        total_count = sum(sum(d.values()) for d in monthly_data.values())

        # 统计各操作类型
        action_totals = {}
        for data in monthly_data.values():
            for action, count in data.items():
                action_totals[action] = action_totals.get(action, 0) + count

        return {
            "year": year,
            "month": month,
            "total_actions": total_count,
            "daily_breakdown": monthly_data,
            "action_totals": action_totals,
        }

    def get_all_time_stats(self) -> Dict[str, Any]:
        """
        获取累计统计数据

        Returns:
            dict: 累计统计数据
        """
        if not self._records:
            return {
                "total_actions": 0,
                "total_tokens": 0,
                "total_video_duration": 0.0,
                "first_record_date": None,
                "last_record_date": None,
            }

        total_tokens = sum(r.token_count for r in self._records)
        total_duration = sum(r.video_duration for r in self._records)

        return {
            "total_actions": len(self._records),
            "total_tokens": total_tokens,
            "total_video_duration": total_duration,
            "first_record_date": self._records[0].timestamp if self._records else None,
            "last_record_date": self._records[-1].timestamp if self._records else None,
        }

    def get_feature_usage_stats(self, user_id: str = None) -> Dict[str, Any]:
        """
        获取功能使用频率统计

        Args:
            user_id: 用户ID，不提供则统计所有用户

        Returns:
            dict: 功能使用统计
        """
        records = self._records
        if user_id:
            records = [r for r in records if r.user_id == user_id]

        feature_usage = {}

        for record in records:
            action = record.action_type
            if action not in feature_usage:
                feature_usage[action] = {
                    "count": 0,
                    "success_count": 0,
                    "fail_count": 0,
                    "total_tokens": 0,
                    "total_duration": 0.0,
                }

            feature_usage[action]["count"] += 1
            if record.success:
                feature_usage[action]["success_count"] += 1
            else:
                feature_usage[action]["fail_count"] += 1
            feature_usage[action]["total_tokens"] += record.token_count
            feature_usage[action]["total_duration"] += record.video_duration

        # 计算成功率
        for action, stats in feature_usage.items():
            if stats["count"] > 0:
                stats["success_rate"] = stats["success_count"] / stats["count"] * 100
            else:
                stats["success_rate"] = 0

        return feature_usage

    def get_dashboard_summary(self, user_id: str = None) -> Dict[str, Any]:
        """
        获取仪表盘摘要数据

        Args:
            user_id: 用户ID，不提供则统计全局

        Returns:
            dict: 仪表盘摘要
        """
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        # 今日统计
        today_stats = self.get_daily_stats(today)

        # 本周统计
        week_stats = self.get_weekly_stats(week_start)

        # 本月统计
        month_stats = self.get_monthly_stats()

        # 累计统计
        all_time = self.get_all_time_stats()

        # 功能使用统计
        feature_usage = self.get_feature_usage_stats(user_id)

        return {
            "today": today_stats,
            "this_week": week_stats,
            "this_month": month_stats,
            "all_time": all_time,
            "feature_usage": feature_usage,
        }

    def format_duration(self, seconds: float) -> str:
        """格式化时长"""
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

    def format_number(self, num: int) -> str:
        """格式化数字"""
        if num < 1000:
            return str(num)
        elif num < 10000:
            return f"{num/1000:.1f}K"
        elif num < 1000000:
            return f"{num/1000:.0f}K"
        else:
            return f"{num/1000000:.1f}M"

    def cleanup_old_stats(self, days: int = 180):
        """清理旧统计数据"""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        # 清理旧记录
        self._records = [r for r in self._records if r.timestamp >= cutoff_str]

        # 清理旧每日统计
        dates_to_delete = [
            date for date in self._daily_stats.keys()
            if datetime.fromisoformat(date) < cutoff
        ]
        for date in dates_to_delete:
            del self._daily_stats[date]

        self._save_stats()
        logger.info(f"清理了 {len(dates_to_delete)} 天的旧统计数据")


# 全局统计收集器实例
_stats_collector: Optional[StatsCollector] = None


def get_stats_collector() -> StatsCollector:
    """获取统计收集器单例"""
    global _stats_collector
    if _stats_collector is None:
        _stats_collector = StatsCollector()
    return _stats_collector
