import streamlit as st
from app.models.schema import (
    VideoClipParams, VideoAspect, AudioVolumeDefaults,
    CoverStyle, CoverPlatform, CoverSettings
)


def render_video_panel(tr):
    """渲染视频配置面板"""
    with st.container(border=True):
        st.write(tr("Video Settings"))
        params = VideoClipParams()
        render_video_config(tr, params)


def render_video_config(tr, params):
    """渲染视频配置"""
    # 视频比例
    video_aspect_ratios = [
        (tr("Portrait"), VideoAspect.portrait.value),
        (tr("Landscape"), VideoAspect.landscape.value),
    ]
    selected_index = st.selectbox(
        tr("Video Ratio"),
        options=range(len(video_aspect_ratios)),
        format_func=lambda x: video_aspect_ratios[x][0],
    )
    params.video_aspect = VideoAspect(video_aspect_ratios[selected_index][1])
    st.session_state['video_aspect'] = params.video_aspect.value

    # 视频画质
    video_qualities = [
        ("4K (2160p)", "2160p"),
        ("2K (1440p)", "1440p"),
        ("Full HD (1080p)", "1080p"),
        ("HD (720p)", "720p"),
        ("SD (480p)", "480p"),
    ]
    quality_index = st.selectbox(
        tr("Video Quality"),
        options=range(len(video_qualities)),
        format_func=lambda x: video_qualities[x][0],
        index=2  # 默认选择 1080p
    )
    st.session_state['video_quality'] = video_qualities[quality_index][1]

    # 原声音量 - 使用统一的默认值
    params.original_volume = st.slider(
        tr("Original Volume"),
        min_value=AudioVolumeDefaults.MIN_VOLUME,
        max_value=AudioVolumeDefaults.MAX_VOLUME,
        value=AudioVolumeDefaults.ORIGINAL_VOLUME,
        step=0.01,
        help=tr("Adjust the volume of the original audio")
    )
    st.session_state['original_volume'] = params.original_volume


def get_video_params():
    """获取视频参数"""
    return {
        'video_aspect': st.session_state.get('video_aspect', VideoAspect.portrait.value),
        'video_quality': st.session_state.get('video_quality', '1080p'),
        'original_volume': st.session_state.get('original_volume', AudioVolumeDefaults.ORIGINAL_VOLUME)
    }


def render_cover_panel(tr):
    """渲染封面设置面板"""
    with st.container(border=True):
        st.write(tr("Cover Settings"))

        # 封面生成开关
        cover_enabled = st.checkbox(
            tr("Enable Cover Generation"),
            value=False,
            help=tr("Generate an AI-powered cover image based on narration script")
        )
        st.session_state['cover_enabled'] = cover_enabled

        if cover_enabled:
            render_cover_settings(tr)


def render_cover_settings(tr):
    """渲染封面设置选项"""
    # 封面样式选择
    style_options = [
        (tr("Cinematic"), CoverStyle.CINEMATIC.value),
        (tr("Comedic"), CoverStyle.COMEDIC.value),
        (tr("Mysterious"), CoverStyle.MYSTERIOUS.value),
        (tr("Dramatic"), CoverStyle.DRAMATIC.value),
        (tr("Minimalist"), CoverStyle.MINIMALIST.value),
        (tr("Vibrant"), CoverStyle.VIBRANT.value),
    ]

    style_labels = [opt[0] for opt in style_options]
    style_values = [opt[1] for opt in style_options]

    saved_style = st.session_state.get('cover_style', CoverStyle.CINEMATIC.value)
    if saved_style in style_values:
        default_style_idx = style_values.index(saved_style)
    else:
        default_style_idx = 0

    selected_style_idx = st.selectbox(
        tr("Cover Style"),
        options=range(len(style_options)),
        format_func=lambda x: style_options[x][0],
        index=default_style_idx
    )
    selected_style = style_options[selected_style_idx][1]
    st.session_state['cover_style'] = selected_style

    # 平台适配选择
    platform_options = [
        (tr("Douyin (Vertical 9:16)"), CoverPlatform.DOUYIN.value),
        (tr("Bilibili (Horizontal 16:9)"), CoverPlatform.BILIBILI.value),
        (tr("YouTube (Horizontal 16:9)"), CoverPlatform.YOUTUBE.value),
        (tr("Weibo (Square 1:1)"), CoverPlatform.WEIBO.value),
        (tr("Xiaohongshu (Vertical 3:4)"), CoverPlatform.XIAOHONGSHU.value),
        (tr("Universal"), CoverPlatform.UNIVERSAL.value),
    ]

    platform_labels = [opt[0] for opt in platform_options]
    platform_values = [opt[1] for opt in platform_options]

    saved_platform = st.session_state.get('cover_platform', CoverPlatform.DOUYIN.value)
    if saved_platform in platform_values:
        default_platform_idx = platform_values.index(saved_platform)
    else:
        default_platform_idx = 0

    selected_platform_idx = st.selectbox(
        tr("Target Platform"),
        options=range(len(platform_options)),
        format_func=lambda x: platform_options[x][0],
        index=default_platform_idx
    )
    selected_platform = platform_options[selected_platform_idx][1]
    st.session_state['cover_platform'] = selected_platform

    # 标题文字
    title_text = st.text_input(
        tr("Cover Title"),
        value=st.session_state.get('cover_title', ''),
        help=tr("Text to overlay on the cover (optional)")
    )
    st.session_state['cover_title'] = title_text

    # 副标题文字
    subtitle_text = st.text_input(
        tr("Cover Subtitle"),
        value=st.session_state.get('cover_subtitle', ''),
        help=tr("Subtitle text to overlay on the cover (optional)")
    )
    st.session_state['cover_subtitle'] = subtitle_text

    # AI生成开关
    use_ai = st.checkbox(
        tr("Use AI Image Generation"),
        value=st.session_state.get('cover_use_ai', True),
        help=tr("Use AI to generate cover image (requires API key)")
    )
    st.session_state['cover_use_ai'] = use_ai

    # 显示样式预览说明
    with st.expander(tr("Cover Style Preview"), expanded=False):
        style_descriptions = {
            CoverStyle.CINEMATIC.value: tr("Cinematic: Strong contrast, dramatic lighting, cinematic feel"),
            CoverStyle.COMEDIC.value: tr("Comedic: Bright colors, lively atmosphere, fun elements"),
            CoverStyle.MYSTERIOUS.value: tr("Mysterious: Dark tones, suspenseful mood, mysterious atmosphere"),
            CoverStyle.DRAMATIC.value: tr("Dramatic: Strong contrast, emotional, powerful visual impact"),
            CoverStyle.MINIMALIST.value: tr("Minimalist: Clean design, ample white space, simple and elegant"),
            CoverStyle.VIBRANT.value: tr("Vibrant: Vivid colors, energetic, youthful and fresh"),
        }
        st.info(style_descriptions.get(selected_style, ""))


def get_cover_settings() -> CoverSettings:
    """获取封面设置"""
    return CoverSettings(
        enabled=st.session_state.get('cover_enabled', False),
        style=CoverStyle(st.session_state.get('cover_style', CoverStyle.CINEMATIC.value)),
        platform=CoverPlatform(st.session_state.get('cover_platform', CoverPlatform.DOUYIN.value)),
        title_text=st.session_state.get('cover_title', ''),
        subtitle_text=st.session_state.get('cover_subtitle', ''),
        use_ai_generation=st.session_state.get('cover_use_ai', True),
        cover_image_path=st.session_state.get('cover_image_path', '')
    )
