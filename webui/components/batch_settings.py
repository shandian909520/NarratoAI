#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
批量处理和进度可视化组件 - NarratoAI WebUI
提供视频队列管理、拖拽排序和实时进度展示功能
"""

import json
import streamlit as st
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from app.services.batch_processor import (
    QueueItem,
    QueueManager,
    BatchProcessor,
    ProcessingMode,
    TaskStatus,
    get_batch_processor,
    get_queue_status,
    add_to_queue,
)


def render_batch_settings(tr) -> None:
    """渲染批量处理设置面板"""
    with st.expander(tr("Batch Processing"), expanded=False):
        col1, col2 = st.columns([3, 1])

        with col1:
            render_queue_panel(tr)

        with col2:
            render_batch_controls(tr)


def render_queue_panel(tr) -> None:
    """渲染队列面板"""
    st.subheader(tr("Video Queue"))

    # 获取队列状态
    queue_status = get_queue_status()

    # 显示队列统计
    stats_cols = st.columns(5)
    stats = [
        ("Total", queue_status["total"], "total"),
        ("Pending", queue_status["pending"], "pending"),
        ("Processing", queue_status["processing"], "processing"),
        ("Completed", queue_status["completed"], "completed"),
        ("Failed", queue_status["failed"], "failed"),
    ]
    for col, (label, count, key) in zip(stats_cols, stats):
        with col:
            color = {
                "total": "blue",
                "pending": "gray",
                "processing": "orange",
                "completed": "green",
                "failed": "red",
            }.get(key, "blue")
            st.metric(label=f"{tr(label)}", value=count)

    st.divider()

    # 渲染队列列表
    items = queue_status.get("items", [])
    if not items:
        st.info(tr("Queue is empty. Add videos to start batch processing."))
        return

    # 队列操作按钮
    action_cols = st.columns([1, 1, 1, 1, 1])
    with action_cols[0]:
        if st.button(tr("Clear Completed"), use_container_width=True):
            QueueManager.get_instance().clear_completed()
            st.rerun()

    with action_cols[1]:
        if st.button(tr("Clear All"), use_container_width=True):
            QueueManager.get_instance().clear_all()
            st.rerun()

    # 显示每个队列项
    for item in items:
        render_queue_item(tr, item)


def render_queue_item(tr, item: Dict[str, Any]) -> None:
    """渲染单个队列项

    Args:
        tr: 翻译函数
        item: 队列项数据
    """
    status = item.get("status", "pending")
    status_color = {
        "pending": "gray",
        "processing": "orange",
        "complete": "green",
        "failed": "red",
        "paused": "blue",
        "cancelled": "gray",
    }.get(status, "gray")

    # 使用 expander 显示队列项详情
    with st.container():
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            status_icon = {
                "pending": "⏳",
                "processing": "🔄",
                "complete": "✅",
                "failed": "❌",
                "paused": "⏸️",
                "cancelled": "🚫",
            }.get(status, "❓")
            st.markdown(f"**{status_icon} {item.get('name', 'Untitled')}**")
            if item.get("error_message"):
                st.caption(f"⚠️ {item.get('error_message')[:50]}...")

        with col2:
            # 进度条
            progress = item.get("progress", 0)
            st.progress(progress / 100, text=f"{progress:.0f}%")

        with col3:
            # 删除按钮
            if st.button(tr("Delete"), key=f"del_{item['id']}", use_container_width=True):
                QueueManager.get_instance().remove_item(item["id"])
                st.rerun()

        # 显示各阶段进度详情
        stage_progress = item.get("stage_progress", {})
        if stage_progress and status == "processing":
            render_stage_progress(tr, stage_progress)

        st.divider()


def render_stage_progress(tr, stage_progress: Dict[str, Any]) -> None:
    """渲染各阶段进度详情

    Args:
        tr: 翻译函数
        stage_progress: 各阶段进度数据
    """
    # 阶段名称映射
    stage_names = {
        "script": tr("Script Generation"),
        "tts": tr("TTS Generation"),
        "clip": tr("Video Clipping"),
        "subtitle": tr("Subtitle Generation"),
        "merge": tr("Video Merging"),
    }

    # 阶段进度条
    stage_cols = st.columns(5)
    for idx, (stage, steps) in enumerate(stage_progress.items()):
        with stage_cols[idx]:
            st.caption(f"**{stage_names.get(stage, stage)}**")
            if isinstance(steps, dict):
                for step_name, step_data in steps.items():
                    step_p = step_data.get("progress", 0)
                    st.progress(step_p / 100, text=f"{step_name}: {step_p:.0f}%")


def render_batch_controls(tr) -> None:
    """渲染批量控制按钮"""
    st.subheader(tr("Batch Controls"))

    # 处理模式选择
    mode = st.selectbox(
        tr("Processing Mode"),
        options=[(ProcessingMode.SERIAL.value, tr("Serial")), (ProcessingMode.PARALLEL.value, tr("Parallel"))],
        format_func=lambda x: x[1],
        index=0,
        key="batch_mode"
    )

    # 最大并行数
    max_workers = st.number_input(
        tr("Max Parallel Workers"),
        min_value=1,
        max_value=8,
        value=2,
        key="max_workers"
    )

    # 控制按钮
    processor = get_batch_processor()

    col1, col2 = st.columns(2)
    with col1:
        if not processor.is_running():
            if st.button(tr("Start"), use_container_width=True, type="primary"):
                processor.mode = ProcessingMode(mode[0])
                processor.max_workers = max_workers
                processor.process_all()
                st.rerun()
        else:
            if st.button(tr("Stop"), use_container_width=True):
                processor.stop()
                st.rerun()

    with col2:
        if processor.is_paused():
            if st.button(tr("Resume"), use_container_width=True):
                processor.resume()
                st.rerun()
        else:
            if processor.is_running():
                if st.button(tr("Pause"), use_container_width=True):
                    processor.pause()
                    st.rerun()


def render_add_to_queue(tr) -> None:
    """渲染添加到队列的表单"""
    with st.expander(tr("Add to Queue"), expanded=False):
        # 视频文件
        video_path = st.text_input(
            tr("Video File Path"),
            key="queue_video_path"
        )

        # 脚本文件
        script_path = st.text_input(
            tr("Script File Path"),
            key="queue_script_path"
        )

        # 任务名称
        task_name = st.text_input(
            tr("Task Name"),
            key="queue_task_name",
            value=""
        )

        # 添加按钮
        if st.button(tr("Add to Queue"), use_container_width=True):
            if not video_path:
                st.error(tr("Video file path is required"))
            elif not script_path:
                st.error(tr("Script file path is required"))
            else:
                name = task_name if task_name else f"Task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                add_to_queue(
                    name=name,
                    video_path=video_path,
                    script_path=script_path
                )
                st.success(tr("Added to queue"))
                st.rerun()


def render_progress_visualization(tr, item_id: str) -> None:
    """渲染单个任务的进度可视化

    Args:
        tr: 翻译函数
        item_id: 任务ID
    """
    queue = QueueManager.get_instance()
    item = queue.get_item(item_id)

    if not item:
        st.warning(tr("Task not found"))
        return

    # 任务状态头部
    status = item.status.value if isinstance(item.status, Enum) else item.status
    status_icons = {
        "pending": "⏳",
        "processing": "🔄",
        "complete": "✅",
        "failed": "❌",
        "paused": "⏸️",
        "cancelled": "🚫",
    }

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(f"### {status_icons.get(status, '❓')} {item.name}")
    with col2:
        st.metric(tr("Progress"), f"{item.progress:.1f}%")
    with col3:
        if item.processing_time:
            st.metric(tr("Time"), f"{item.processing_time:.1f}s")

    # 主进度条
    st.progress(item.progress / 100)

    # 各阶段进度
    if item.stage_progress:
        render_stage_progress(tr, item.stage_progress)

    # 错误信息
    if item.error_message:
        st.error(f"**{tr('Error')}:** {item.error_message}")

    # 时间信息
    time_cols = st.columns(3)
    with time_cols[0]:
        if item.created_at:
            st.caption(f"🕐 {tr('Created')}: {item.created_at[:19]}")
    with time_cols[1]:
        if item.started_at:
            st.caption(f"🚀 {tr('Started')}: {item.started_at[:19]}")
    with time_cols[2]:
        if item.completed_at:
            st.caption(f"🏁 {tr('Completed')}: {item.completed_at[:19]}")

    # 结果视频
    if item.result_video and item.status == TaskStatus.COMPLETE:
        st.success(tr("Processing completed successfully!"))
        try:
            st.video(item.result_video)
        except Exception as e:
            logger.error(f"播放视频失败: {e}")
            st.download_button(
                label=tr("Download Result"),
                data=open(item.result_video, "rb"),
                file_name=item.result_video.split("/")[-1],
                mime="video/mp4"
            )


def render_realtime_progress(tr, item_id: str, poll_interval: float = 0.5) -> None:
    """渲染实时进度（自动刷新）

    Args:
        tr: 翻译函数
        item_id: 任务ID
        poll_interval: 轮询间隔(秒)
    """
    import time

    placeholder = st.empty()

    while True:
        queue = QueueManager.get_instance()
        item = queue.get_item(item_id)

        if not item:
            placeholder.warning(tr("Task not found"))
            break

        status = item.status.value if isinstance(item.status, Enum) else item.status

        # 如果任务完成或失败，停止轮询
        if status in [TaskStatus.COMPLETE.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
            with placeholder.container():
                render_progress_visualization(tr, item_id)
            break

        with placeholder.container():
            render_progress_visualization(tr, item_id)

        time.sleep(poll_interval)


def render_queue_drag_sort(tr) -> None:
    """渲染可拖拽排序的队列列表"""
    st.subheader(tr("Queue (Drag to Sort)"))

    items = QueueManager.get_instance().get_queue()
    if not items:
        st.info(tr("Queue is empty"))
        return

    # 使用编号实现简单排序
    item_names = [f"{i+1}. {item.name} ({item.status.value if isinstance(item.status, Enum) else item.status})" for i, item in enumerate(items)]
    selected = st.selectbox(tr("Select item to move"), options=item_names)

    if selected:
        idx = item_names.index(selected)
        move_col1, move_col2 = st.columns(2)

        with move_col1:
            if st.button(tr("Move Up") and idx > 0, use_container_width=True):
                items[idx], items[idx-1] = items[idx-1], items[idx]
                item_ids = [item.id for item in items]
                QueueManager.get_instance().reorder(item_ids)
                st.rerun()

        with move_col2:
            if st.button(tr("Move Down") and idx < len(items)-1, use_container_width=True):
                items[idx], items[idx+1] = items[idx+1], items[idx]
                item_ids = [item.id for item in items]
                QueueManager.get_instance().reorder(item_ids)
                st.rerun()


def init_batch_session_state() -> None:
    """初始化批量处理的 session state"""
    if "batch_processor" not in st.session_state:
        st.session_state.batch_processor = get_batch_processor()

    if "queue_refresh_key" not in st.session_state:
        st.session_state.queue_refresh_key = 0
