import streamlit as st
import os
import shutil
import json
from loguru import logger

from app.utils.utils import storage_dir
from app.models.template import TemplateManager, VideoTemplate, TemplateStyle
from app.models.user import UserStore, MembershipLevel
from app.services.auth import get_auth_service
from app.services.membership import get_membership_service
from app.services.project_manager import get_project_manager, ProjectStatus
from app.services.stats_collector import get_stats_collector
from app.services.draft_manager import get_draft_manager


def clear_directory(dir_path, tr):
    """清理指定目录"""
    if os.path.exists(dir_path):
        try:
            for item in os.listdir(dir_path):
                item_path = os.path.join(dir_path, item)
                try:
                    if os.path.isfile(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    logger.error(f"Failed to delete {item_path}: {e}")
            st.success(tr("Directory cleared"))
            logger.info(f"Cleared directory: {dir_path}")
        except Exception as e:
            st.error(f"{tr('Failed to clear directory')}: {str(e)}")
            logger.error(f"Failed to clear directory {dir_path}: {e}")
    else:
        st.warning(tr("Directory does not exist"))

def render_system_panel(tr):
    """渲染系统设置面板"""
    # 系统设置使用 container 而非 expander，避免与内部 expander 冲突
    with st.container(border=True):
        st.write(tr("System settings"))
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(tr("Clear frames"), use_container_width=True):
                clear_directory(os.path.join(storage_dir(), "temp/keyframes"), tr)

        with col2:
            if st.button(tr("Clear clip videos"), use_container_width=True):
                clear_directory(os.path.join(storage_dir(), "temp/clip_video"), tr)

        with col3:
            if st.button(tr("Clear tasks"), use_container_width=True):
                clear_directory(os.path.join(storage_dir(), "tasks"), tr)

    # 模板管理（在 container 外部避免 expander 嵌套问题）
    st.divider()
    render_template_panel(tr)

    # 用户中心和项目管理
    render_user_and_project_panels(tr)


def render_template_panel(tr):
    """渲染模板管理面板"""
    st.subheader(tr("Template Management"))

    # 确保模板目录存在
    TemplateManager.ensure_templates_dir()

    # 标签页：内置模板 / 用户模板
    tab1, tab2, tab3 = st.tabs([
        tr("Built-in Templates"),
        tr("User Templates"),
        tr("Create/Edit Template")
    ])

    with tab1:
        render_builtin_templates(tr)

    with tab2:
        render_user_templates(tr)

    with tab3:
        render_template_editor(tr)


def render_builtin_templates(tr):
    """渲染内置模板列表"""
    st.write(tr("Built-in Templates Description"))
    st.info(tr("Built-in templates cannot be modified but can be applied or exported"))

    builtin_templates = TemplateManager.get_all_builtin_templates()

    for style_id, template in builtin_templates.items():
        with st.expander(f"{template.metadata.name}", expanded=False):
            st.markdown(f"**{tr('Description')}**: {template.metadata.description}")
            st.markdown(f"**{tr('Tags')}**: {', '.join(template.metadata.tags)}")

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button(tr("Apply"), key=f"apply_builtin_{style_id}", use_container_width=True):
                    apply_template_params(template)
                    st.success(tr("Template applied successfully"))

            with col2:
                if st.button(tr("Preview"), key=f"preview_builtin_{style_id}", use_container_width=True):
                    st.session_state['preview_template_id'] = f"builtin_{style_id}"

            with col3:
                # 导出内置模板（保存为副本）
                export_path = os.path.join(TemplateManager.TEMPLATES_DIR, f"{template.metadata.id}_export.json")
                if st.button(tr("Export"), key=f"export_builtin_{style_id}", use_container_width=True):
                    if TemplateManager.export_template(f"builtin_{style_id}", export_path):
                        st.success(f"{tr('Template exported to')}: {export_path}")


def render_user_templates(tr):
    """渲染用户自定义模板列表"""
    user_templates = TemplateManager.list_user_templates()

    if not user_templates:
        st.info(tr("No user templates yet. Create one in the 'Create/Edit Template' tab."))
        return

    for tmpl in user_templates:
        with st.expander(f"{tmpl.name}", expanded=False):
            st.markdown(f"**{tr('Description')}**: {tmpl.description}")
            st.markdown(f"**{tr('Author')}**: {tmpl.author}")
            st.markdown(f"**{tr('Created')}**: {tmpl.created_at}")
            st.markdown(f"**{tr('Tags')}**: {', '.join(tmpl.tags) if tmpl.tags else '-'}")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if st.button(tr("Apply"), key=f"apply_user_{tmpl.id}", use_container_width=True):
                    template = TemplateManager.load_template(tmpl.id)
                    if template:
                        apply_template_params(template)
                        st.success(tr("Template applied successfully"))

            with col2:
                if st.button(tr("Edit"), key=f"edit_user_{tmpl.id}", use_container_width=True):
                    st.session_state['edit_template_id'] = tmpl.id

            with col3:
                export_path = st.text_input(tr("Export Path"), value=f"{tmpl.name}.json", key=f"export_path_{tmpl.id}")
                if st.button(tr("Export"), key=f"export_user_{tmpl.id}", use_container_width=True):
                    if TemplateManager.export_template(tmpl.id, export_path):
                        st.success(f"{tr('Template exported')}")

            with col4:
                if st.button(tr("Delete"), key=f"delete_user_{tmpl.id}", use_container_width=True, type="primary"):
                    if TemplateManager.delete_template(tmpl.id):
                        st.success(tr("Template deleted"))
                        st.rerun()


def render_template_editor(tr):
    """渲染模板编辑器"""
    edit_template_id = st.session_state.get('edit_template_id', None)

    # 创建新模板或编辑现有模板
    if edit_template_id:
        template = TemplateManager.load_template(edit_template_id)
        if not template:
            st.error(tr("Template not found"))
            return
        st.subheader(tr("Edit Template"))
    else:
        template = VideoTemplate()
        st.subheader(tr("Create New Template"))

    # 基本信息
    st.markdown("### " + tr("Basic Information"))
    col1, col2 = st.columns(2)
    with col1:
        template.metadata.name = st.text_input(
            tr("Template Name"),
            value=template.metadata.name,
            key="template_name"
        )
        template.metadata.description = st.text_area(
            tr("Description"),
            value=template.metadata.description,
            key="template_description"
        )
    with col2:
        template.metadata.author = st.text_input(
            tr("Author"),
            value=template.metadata.author,
            key="template_author"
        )
        tags_input = st.text_input(
            tr("Tags (comma separated)"),
            value=', '.join(template.metadata.tags),
            key="template_tags"
        )
        template.metadata.tags = [t.strip() for t in tags_input.split(',') if t.strip()]

    # 解说风格
    st.markdown("### " + tr("Narration Style"))
    narration_styles = {
        "humorous": tr("Humorous"),
        "emotional": tr("Emotional"),
        "mysterious": tr("Mysterious"),
        "educational": tr("Educational"),
        "inspirational": tr("Inspirational"),
        "custom": tr("Custom")
    }

    col1, col2 = st.columns(2)
    with col1:
        style_key = st.selectbox(
            tr("Style"),
            options=list(narration_styles.keys()),
            format_func=lambda x: narration_styles[x],
            index=list(narration_styles.keys()).index(template.narration.style) if template.narration.style in narration_styles else 5,
            key="narration_style"
        )
        template.narration.style = style_key

        template.narration.emotion_word_frequency = st.slider(
            tr("Emotion Word Frequency"),
            0.0, 1.0,
            value=template.narration.emotion_word_frequency,
            key="emotion_freq"
        )

        template.narration.exclamation_ratio = st.slider(
            tr("Exclamation Ratio"),
            0.0, 1.0,
            value=template.narration.exclamation_ratio,
            key="excl_ratio"
        )

    with col2:
        template.narration.avg_sentence_length = st.slider(
            tr("Average Sentence Length"),
            10, 50,
            value=template.narration.avg_sentence_length,
            key="avg_sentence"
        )

        template.narration.question_ratio = st.slider(
            tr("Question Ratio"),
            0.0, 1.0,
            value=template.narration.question_ratio,
            key="quest_ratio"
        )

        template.narration.suspense_enabled = st.checkbox(
            tr("Enable Suspense"),
            value=template.narration.suspense_enabled,
            key="suspense_enabled"
        )

    # 字幕样式
    st.markdown("### " + tr("Subtitle Style"))
    col1, col2 = st.columns(2)
    with col1:
        template.subtitle.enabled = st.checkbox(
            tr("Enable Subtitles"),
            value=template.subtitle.enabled,
            key="subtitle_enabled"
        )
        template.subtitle.font_size = st.slider(
            tr("Font Size"),
            20, 80,
            value=template.subtitle.font_size,
            key="subtitle_font_size"
        )
        template.subtitle.text_color = st.color_picker(
            tr("Text Color"),
            value=template.subtitle.text_color,
            key="subtitle_color"
        )
    with col2:
        template.subtitle.position = st.selectbox(
            tr("Position"),
            options=["top", "center", "bottom", "custom"],
            index=["top", "center", "bottom", "custom"].index(template.subtitle.position) if template.subtitle.position in ["top", "center", "bottom", "custom"] else 2,
            key="subtitle_position"
        )
        template.subtitle.stroke_color = st.color_picker(
            tr("Stroke Color"),
            value=template.subtitle.stroke_color,
            key="subtitle_stroke_color"
        )
        template.subtitle.stroke_width = st.slider(
            tr("Stroke Width"),
            0.0, 5.0,
            value=template.subtitle.stroke_width,
            key="subtitle_stroke_width"
        )

    # 语音设置
    st.markdown("### " + tr("Voice Settings"))
    col1, col2 = st.columns(2)
    with col1:
        template.voice.engine = st.selectbox(
            tr("TTS Engine"),
            options=["edge_tts", "azure_speech", "tencent_tts", "qwen3_tts"],
            index=["edge_tts", "azure_speech", "tencent_tts", "qwen3_tts"].index(template.voice.engine) if template.voice.engine in ["edge_tts", "azure_speech", "tencent_tts", "qwen3_tts"] else 0,
            key="voice_engine"
        )
        template.voice.rate = st.slider(
            tr("Rate"),
            0.5, 2.0,
            value=template.voice.rate,
            step=0.1,
            key="voice_rate"
        )
    with col2:
        template.voice.voice_name = st.text_input(
            tr("Voice Name"),
            value=template.voice.voice_name,
            key="voice_name"
        )
        template.voice.pitch = st.slider(
            tr("Pitch"),
            0.5, 2.0,
            value=template.voice.pitch,
            step=0.1,
            key="voice_pitch"
        )

    # 视频设置
    st.markdown("### " + tr("Video Settings"))
    col1, col2 = st.columns(2)
    with col1:
        template.video.aspect = st.selectbox(
            tr("Aspect Ratio"),
            options=["16:9", "9:16", "1:1", "4:3"],
            index=["16:9", "9:16", "1:1", "4:3"].index(template.video.aspect) if template.video.aspect in ["16:9", "9:16", "1:1", "4:3"] else 1,
            key="video_aspect"
        )
        template.video.clip_duration = st.slider(
            tr("Clip Duration (seconds)"),
            2, 15,
            value=template.video.clip_duration,
            key="clip_duration"
        )
    with col2:
        template.video.transition_effect = st.selectbox(
            tr("Transition Effect"),
            options=["fade", "slide", "none"],
            index=["fade", "slide", "none"].index(template.video.transition_effect) if template.video.transition_effect in ["fade", "slide", "none"] else 0,
            key="transition_effect"
        )

    # 保存/取消按钮
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button(tr("Save Template"), use_container_width=True, type="primary"):
            if not template.metadata.name:
                st.error(tr("Please enter template name"))
            else:
                if TemplateManager.save_template(template):
                    st.success(tr("Template saved successfully"))
                    st.session_state.pop('edit_template_id', None)
                    st.rerun()

    with col2:
        if st.button(tr("Preview Template"), use_container_width=True):
            preview_template_in_ui(template)

    with col3:
        if st.button(tr("Cancel"), use_container_width=True):
            st.session_state.pop('edit_template_id', None)
            st.rerun()

    # 模板导入/导出
    st.divider()
    st.markdown("### " + tr("Import/Export"))
    col1, col2 = st.columns(2)
    with col1:
        uploaded_file = st.file_uploader(
            tr("Import Template"),
            type=["json"],
            key="import_template_file"
        )
        if uploaded_file:
            import_template_from_upload(uploaded_file, tr)

    with col2:
        if edit_template_id:
            export_json = json.dumps(template.model_dump(mode='json'), ensure_ascii=False, indent=2)
            st.download_button(
                tr("Download Template"),
                data=export_json,
                file_name=f"{template.metadata.name}.json",
                mime="application/json",
                use_container_width=True
            )


def apply_template_params(template: VideoTemplate):
    """应用模板参数到当前配置"""
    try:
        # 字幕设置
        config.ui["subtitle_enabled"] = template.subtitle.enabled
        config.ui["font_name"] = template.subtitle.font_name
        config.ui["font_size"] = template.subtitle.font_size
        config.ui["text_fore_color"] = template.subtitle.text_color
        config.ui["stroke_color"] = template.subtitle.stroke_color
        config.ui["stroke_width"] = template.subtitle.stroke_width
        config.ui["subtitle_position"] = template.subtitle.position

        # 语音设置
        config.ui["tts_engine"] = template.voice.engine
        config.ui["voice_name"] = template.voice.voice_name
        config.ui["voice_volume"] = template.voice.volume
        config.ui["voice_rate"] = template.voice.rate
        config.ui["voice_pitch"] = template.voice.pitch

        # 视频设置
        config.app["video_aspect"] = template.video.aspect
        config.app["video_clip_duration"] = template.video.clip_duration

        # 更新session state
        st.session_state['font_name'] = template.subtitle.font_name
        st.session_state['font_size'] = template.subtitle.font_size
        st.session_state['text_fore_color'] = template.subtitle.text_color
        st.session_state['stroke_color'] = template.subtitle.stroke_color
        st.session_state['stroke_width'] = template.subtitle.stroke_width
        st.session_state['subtitle_position'] = template.subtitle.position
        st.session_state['tts_engine'] = template.voice.engine
        st.session_state['voice_name'] = template.voice.voice_name
        st.session_state['voice_rate'] = template.voice.rate
        st.session_state['voice_pitch'] = template.voice.pitch

    except Exception as e:
        logger.error(f"应用模板参数失败: {e}")


def preview_template_in_ui(template: VideoTemplate):
    """在UI中预览模板"""
    st.info(f"{tr('Template Name')}: {template.metadata.name}")
    st.info(f"{tr('Style')}: {template.narration.style}")
    st.info(f"{tr('Emotion Word Frequency')}: {template.narration.emotion_word_frequency}")
    st.info(f"{tr('Font Size')}: {template.subtitle.font_size}")
    st.info(f"{tr('Position')}: {template.subtitle.position}")


def import_template_from_upload(uploaded_file, tr):
    """从上传的文件导入模板"""
    try:
        template = TemplateManager.import_template(uploaded_file.name)
        if template:
            st.success(f"{tr('Template imported successfully')}: {template.metadata.name}")
            st.rerun()
        else:
            st.error(tr("Failed to import template"))
    except Exception as e:
        st.error(f"{tr('Import error')}: {str(e)}")


def render_user_center_panel(tr):
    """渲染用户中心面板"""
    st.divider()
    st.subheader(tr("User Center"))

    auth_service = get_auth_service()
    membership_service = get_membership_service()

    # 用户登录状态
    if not auth_service.is_authenticated:
        # 未登录，显示登录/注册表单
        tab1, tab2 = st.tabs([tr("Login"), tr("Register")])

        with tab1:
            login_username = st.text_input(tr("Username"), key="login_username")
            login_password = st.text_input(tr("Password"), type="password", key="login_password")
            if st.button(tr("Login"), use_container_width=True, type="primary"):
                success, msg, user = auth_service.login(login_username, login_password)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        with tab2:
            reg_username = st.text_input(tr("Username"), key="reg_username")
            reg_password = st.text_input(tr("Password"), type="password", key="reg_password")
            reg_email = st.text_input(tr("Email (optional)"), key="reg_email")
            if st.button(tr("Register"), use_container_width=True, type="primary"):
                success, msg, user = auth_service.register(reg_username, reg_password, reg_email if reg_email else None)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    else:
        # 已登录，显示用户信息
        user = auth_service.current_user
        membership_info = membership_service.get_user_membership(user)

        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown(f"**{tr('Username')}**: {user.username}")
            st.markdown(f"**{tr('Membership Level')}**: {membership_info['name']}")

            # 配额信息
            st.markdown(f"**{tr('Daily Generations')}**: {membership_info['daily_generations_info']['used']} / {membership_info['daily_generations_info']['limit']}")
            progress = membership_info['daily_generations_info']['used'] / max(1, membership_info['daily_generations_info']['limit'])
            st.progress(min(1.0, progress), text=tr("Daily quota used"))

            st.markdown(f"**{tr('Video Duration')}**: {membership_service.format_duration(user.total_video_duration)}")

            # 可用功能
            features = membership_service.get_available_features(user)
            st.markdown(f"**{tr('Available Features')}**: {len(features['available'])}")

        with col2:
            if st.button(tr("Logout"), use_container_width=True):
                auth_service.logout()
                st.rerun()

        # 升级建议
        suggestions = membership_service.get_upgrade_suggestions(user)
        if suggestions:
            st.divider()
            st.markdown(f"**{tr('Upgrade Suggestions')}**")
            for suggestion in suggestions:
                st.info(suggestion['message'])
                if st.button(f"{tr('Upgrade to')} {suggestion['suggested_level']}", key=f"upgrade_{suggestion['suggested_level']}"):
                    target_level = MembershipLevel(suggestion['suggested_level'])
                    success, msg = auth_service.upgrade_membership(target_level)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)


def render_project_panel(tr):
    """渲染项目管理面板"""
    st.divider()
    st.subheader(tr("Project Management"))

    project_manager = get_project_manager()

    # 创建新项目
    with st.expander(tr("Create New Project"), expanded=False):
        new_project_name = st.text_input(tr("Project Name"), key="new_project_name")
        new_project_desc = st.text_area(tr("Description"), key="new_project_desc")
        new_project_tags = st.text_input(tr("Tags (comma separated)"), key="new_project_tags")

        if st.button(tr("Create Project"), use_container_width=True, type="primary"):
            if new_project_name:
                tags = [t.strip() for t in new_project_tags.split(',') if t.strip()]
                project = project_manager.create_project(
                    name=new_project_name,
                    description=new_project_desc,
                    tags=tags,
                )
                st.success(f"{tr('Project created')}: {project.name}")
                st.rerun()
            else:
                st.error(tr("Please enter project name"))

    # 项目列表
    st.divider()
    tab1, tab2, tab3 = st.tabs([tr("Active Projects"), tr("Templates"), tr("Statistics")])

    with tab1:
        projects = project_manager.list_projects(status=ProjectStatus.ACTIVE)
        if not projects:
            st.info(tr("No active projects"))
        else:
            for project in projects[:10]:  # 只显示前10个
                with st.expander(f"{project.name} ({project.status.value})", expanded=False):
                    st.markdown(f"**{tr('Description')}**: {project.description or '-'}")
                    st.markdown(f"**{tr('Created')}**: {project.created_at}")
                    st.markdown(f"**{tr('Updated')}**: {project.updated_at}")
                    st.markdown(f"**{tr('Tags')}**: {', '.join(project.tags) if project.tags else '-'}")

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        if st.button(tr("Open"), key=f"open_{project.project_id}", use_container_width=True):
                            st.session_state['current_project_id'] = project.project_id
                            st.rerun()
                    with col2:
                        if st.button(tr("Archive"), key=f"archive_{project.project_id}", use_container_width=True):
                            project_manager.archive_project(project.project_id)
                            st.rerun()
                    with col3:
                        if st.button(tr("Duplicate"), key=f"dup_{project.project_id}", use_container_width=True):
                            new_proj = project_manager.duplicate_project(project.project_id)
                            if new_proj:
                                st.success(f"{tr('Project duplicated')}: {new_proj.name}")
                                st.rerun()
                    with col4:
                        if st.button(tr("Delete"), key=f"del_{project.project_id}", use_container_width=True, type="primary"):
                            project_manager.delete_project(project.project_id)
                            st.rerun()

    with tab2:
        templates = project_manager.list_templates()
        if not templates:
            st.info(tr("No templates yet. Create one from an existing project."))
        else:
            for template in templates:
                with st.expander(f"{template.name}", expanded=False):
                    st.markdown(f"**{tr('Description')}**: {template.description or '-'}")
                    st.markdown(f"**{tr('Created')}**: {template.created_at}")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button(tr("Apply"), key=f"apply_tmpl_{template.template_id}", use_container_width=True):
                            project = project_manager.apply_template(template.template_id)
                            if project:
                                st.success(f"{tr('Project created from template')}: {project.name}")
                                st.rerun()
                    with col2:
                        if st.button(tr("Create Project"), key=f"new_proj_{template.template_id}", use_container_width=True):
                            project = project_manager.apply_template(template.template_id)
                            if project:
                                st.success(f"{tr('Project created')}: {project.name}")
                                st.rerun()
                    with col3:
                        if st.button(tr("Delete"), key=f"del_tmpl_{template.template_id}", use_container_width=True, type="primary"):
                            project_manager.delete_template(template.template_id)
                            st.rerun()

        # 从项目创建模板
        st.divider()
        st.markdown(f"**{tr('Create Template from Project')}**")
        active_projects = project_manager.list_projects(status=ProjectStatus.ACTIVE)
        if active_projects:
            project_options = {p.project_id: p.name for p in active_projects}
            selected_project = st.selectbox(tr("Select Project"), options=list(project_options.keys()), format_func=lambda x: project_options[x])
            template_name = st.text_input(tr("Template Name"))
            template_desc = st.text_area(tr("Description"))

            if st.button(tr("Create Template"), use_container_width=True):
                if template_name and selected_project:
                    template = project_manager.create_template(
                        name=template_name,
                        description=template_desc,
                        from_project_id=selected_project,
                    )
                    st.success(f"{tr('Template created')}: {template.name}")
                    st.rerun()
        else:
            st.info(tr("No active projects available"))

    with tab3:
        stats_collector = get_stats_collector()
        dashboard = stats_collector.get_dashboard_summary()

        # 今日统计
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(tr("Today's Generations"), dashboard['today']['total_actions'])
        with col2:
            st.metric(tr("This Week"), dashboard['this_week']['total_actions'])
        with col3:
            st.metric(tr("This Month"), dashboard['this_month']['total_actions'])

        # 累计统计
        st.divider()
        st.markdown(f"**{tr('All Time Statistics')}**")
        all_time = dashboard['all_time']
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(tr("Total Actions"), all_time['total_actions'])
        with col2:
            st.metric(tr("Total Tokens"), all_time['total_tokens'])
        with col3:
            st.metric(tr("Total Video Duration"), stats_collector.format_duration(all_time['total_video_duration']))

        # 功能使用统计
        st.divider()
        st.markdown(f"**{tr('Feature Usage')}**")
        feature_usage = dashboard['feature_usage']
        if feature_usage:
            for action, stats in feature_usage.items():
                st.markdown(f"- **{action}**: {stats['count']} {tr('times')} ({stats['success_rate']:.1f}% {tr('success')})")
        else:
            st.info(tr("No usage data yet"))


def render_draft_panel(tr):
    """渲染草稿管理面板"""
    st.divider()
    st.subheader(tr("Draft Management"))

    draft_manager = get_draft_manager()

    # 草稿列表
    drafts = draft_manager.list_drafts()
    if not drafts:
        st.info(tr("No drafts"))
    else:
        for draft in drafts[:10]:
            with st.expander(f"{draft.name} ({draft.status.value})", expanded=False):
                st.markdown(f"**{tr('Created')}**: {draft.created_at}")
                st.markdown(f"**{tr('Updated')}**: {draft.updated_at}")
                st.markdown(f"**{tr('Steps')}**: {len(draft.step_results)}")

                if draft.can_resume():
                    resume_info = draft_manager.get_resume_info(draft.draft_id)
                    st.markdown(f"**{tr('Last Step')}**: {resume_info.get('last_successful_step', '-')}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    if draft.can_resume():
                        if st.button(tr("Resume"), key=f"resume_{draft.draft_id}", use_container_width=True):
                            success, msg, _ = draft_manager.resume_draft(draft.draft_id)
                            if success:
                                st.success(msg)
                            else:
                                st.error(msg)
                with col2:
                    if st.button(tr("Delete"), key=f"del_draft_{draft.draft_id}", use_container_width=True, type="primary"):
                        draft_manager.delete_draft(draft.draft_id)
                        st.rerun()
                with col3:
                    if st.button(tr("Abandon"), key=f"abandon_{draft.draft_id}", use_container_width=True):
                        draft_manager.abandon_draft(draft.draft_id)
                        st.rerun()


def render_user_and_project_panels(tr):
    """渲染用户中心和项目管理面板（整合版）"""
    # 用户中心
    render_user_center_panel(tr)

    # 项目管理
    render_project_panel(tr)

    # 草稿管理
    render_draft_panel(tr)


def init_user_session():
    """初始化用户会话"""
    if 'auth_service' not in st.session_state:
        auth_service = get_auth_service()
        st.session_state['auth_service'] = auth_service
