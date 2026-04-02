"""
预览管理器
提供文案、字幕、配音、视频片段的预览功能
"""

import base64
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from loguru import logger

from app.config import config
from app.utils import utils


@dataclass
class ScriptPreviewItem:
    """脚本预览项"""
    id: int
    timestamp: str
    picture: str
    narration: str
    ost: int = 0


@dataclass
class SubtitlePreviewItem:
    """字幕预览项"""
    index: int
    start_time: float
    end_time: float
    text: str
    style: Dict[str, Any] = None


@dataclass
class AudioPreviewItem:
    """音频预览项"""
    id: str
    text: str
    duration: float
    audio_path: Optional[str] = None
    waveform_data: Optional[List[float]] = None


@dataclass
class VideoPreviewItem:
    """视频片段预览项"""
    id: str
    start_time: float
    end_time: float
    duration: float
    thumbnail_path: Optional[str] = None
    description: str = ""


class PreviewManager:
    """预览管理器"""

    def __init__(self):
        self.temp_dir = utils.storage_dir("temp/preview", create=True)
        self.waveform_cache = {}

    # ==================== 文案预览 ====================

    @staticmethod
    def parse_script_json(script_json: Union[str, list]) -> List[ScriptPreviewItem]:
        """解析脚本JSON为预览项列表"""
        try:
            if isinstance(script_json, str):
                data = json.loads(script_json)
            else:
                data = script_json

            items = []
            for idx, item in enumerate(data):
                items.append(ScriptPreviewItem(
                    id=item.get('_id', idx + 1),
                    timestamp=item.get('timestamp', ''),
                    picture=item.get('picture', ''),
                    narration=item.get('narration', ''),
                    ost=item.get('OST', 0)
                ))
            return items
        except Exception as e:
            logger.error(f"解析脚本JSON失败: {e}")
            return []

    @staticmethod
    def format_script_for_display(script_json: Union[str, list]) -> str:
        """格式化脚本用于显示（带语法高亮标记）"""
        items = PreviewManager.parse_script_json(script_json)
        if not items:
            return ""

        formatted_lines = []
        for item in items:
            # 使用特殊标记以便前端进行语法高亮
            formatted_lines.append(f"### 片段 {item.id}")
            formatted_lines.append(f"**时间戳:** {item.timestamp}")
            formatted_lines.append(f"**画面:** {item.picture}")
            formatted_lines.append(f"**解说:** {item.narration}")
            if item.ost:
                formatted_lines.append(f"**音效:** {'是' if item.ost else '否'}")
            formatted_lines.append("")
            formatted_lines.append("---")
            formatted_lines.append("")

        return "\n".join(formatted_lines)

    @staticmethod
    def highlight_script_syntax(script_text: str) -> Dict[str, Any]:
        """
        为脚本文本添加语法高亮信息
        返回高亮后的 tokens 列表
        """
        tokens = []
        lines = script_text.split('\n')

        for line in lines:
            if line.startswith('###'):
                tokens.append({"type": "header", "text": line})
            elif line.startswith('**时间戳:**'):
                tokens.append({"type": "timestamp", "text": line})
            elif line.startswith('**画面:**'):
                tokens.append({"type": "picture", "text": line})
            elif line.startswith('**解说:**'):
                tokens.append({"type": "narration", "text": line})
            elif line.startswith('**音效:**'):
                tokens.append({"type": "ost", "text": line})
            elif line == '---':
                tokens.append({"type": "divider", "text": line})
            else:
                tokens.append({"type": "text", "text": line})

        return {"tokens": tokens, "html": PreviewManager._generate_highlighted_html(tokens)}

    @staticmethod
    def _generate_highlighted_html(tokens: List[Dict[str, str]]) -> str:
        """生成带语法高亮的HTML"""
        type_colors = {
            "header": "#FFD700",      # 金色
            "timestamp": "#00CED1",    # 青色
            "picture": "#98FB98",      # 浅绿色
            "narration": "#87CEEB",    # 天蓝色
            "ost": "#DDA0DD",          # 梅红色
            "divider": "#808080",      # 灰色
            "text": "#FFFFFF",          # 白色
        }

        html_parts = ['<div class="script-preview">']
        for token in tokens:
            color = type_colors.get(token["type"], "#FFFFFF")
            text = token["text"].replace("<", "&lt;").replace(">", "&gt;")
            html_parts.append(f'<span style="color: {color}">{text}</span>')
        html_parts.append('</div>')

        return "\n".join(html_parts)

    # ==================== 字幕预览 ====================

    @staticmethod
    def parse_srt_content(srt_content: str) -> List[SubtitlePreviewItem]:
        """解析SRT字幕内容"""
        items = []
        pattern = r'(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n(.+?)(?=\n\n\d+\s*\n|\n*$)'

        matches = re.findall(pattern, srt_content, re.DOTALL)
        for match in matches:
            index = int(match[0])
            start_str = match[1]
            end_str = match[2]
            text = match[3].strip()

            # 转换时间
            start_time = PreviewManager._srt_time_to_seconds(start_str)
            end_time = PreviewManager._srt_time_to_seconds(end_str)

            items.append(SubtitlePreviewItem(
                index=index,
                start_time=start_time,
                end_time=end_time,
                text=text
            ))

        return items

    @staticmethod
    def _srt_time_to_seconds(time_str: str) -> float:
        """将SRT时间格式转换为秒"""
        parts = time_str.replace(',', '.').split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def _seconds_to_srt_time(seconds: float) -> str:
        """将秒转换为SRT时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')

    @staticmethod
    def generate_subtitle_preview_image(
        text: str,
        font_name: str = "SimHei",
        font_size: int = 36,
        text_color: str = "#FFFFFF",
        stroke_color: str = "#000000",
        stroke_width: float = 1.5,
        position: str = "bottom",
        custom_position: float = 70.0,
        image_width: int = 720,
        image_height: int = 1280,
        background_color: str = "#1a1a1a"
    ) -> str:
        """
        生成字幕预览图片
        返回图片的base64编码或文件路径
        """
        try:
            # 创建背景图
            img = Image.new('RGB', (image_width, image_height), background_color)
            draw = ImageDraw.Draw(img)

            # 加载字体
            try:
                font_path = PreviewManager._find_font_file(font_name)
                if font_path:
                    font = ImageFont.truetype(font_path, font_size)
                else:
                    font = ImageFont.load_default()
            except Exception as e:
                logger.warning(f"加载字体失败: {e}, 使用默认字体")
                font = ImageFont.load_default()

            # 计算文字位置
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # 根据位置计算y坐标
            if position == "top":
                y = int(image_height * 0.05)
            elif position == "center":
                y = int(image_height * 0.45)
            elif position == "bottom":
                y = int(image_height * 0.85)
            elif position == "custom":
                y = int(image_height * (custom_position / 100))
            else:
                y = int(image_height * 0.85)

            x = (image_width - text_width) // 2

            # 绘制描边
            if stroke_width > 0:
                for adj in range(int(stroke_width)):
                    draw.text((x - adj, y), text, font=font, fill=stroke_color)
                    draw.text((x + adj, y), text, font=font, fill=stroke_color)
                    draw.text((x, y - adj), text, font=font, fill=stroke_color)
                    draw.text((x, y + adj), text, font=font, fill=stroke_color)

            # 绘制文字
            draw.text((x, y), text, font=font, fill=text_color)

            # 保存图片
            temp_dir = utils.storage_dir("temp/preview", create=True)
            filename = f"subtitle_preview_{uuid.uuid4().hex[:8]}.png"
            filepath = os.path.join(temp_dir, filename)
            img.save(filepath)

            return filepath

        except Exception as e:
            logger.error(f"生成字幕预览图片失败: {e}")
            return ""

    @staticmethod
    def _find_font_file(font_name: str) -> Optional[str]:
        """查找字体文件"""
        font_dirs = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "resource", "fonts"),
            "C:/Windows/Fonts",
            "/usr/share/fonts",
            "/System/Library/Fonts"
        ]

        # 尝试不同的字体扩展名
        extensions = ['.ttf', '.ttc', '.otf']

        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue
            for ext in extensions:
                font_path = os.path.join(font_dir, font_name + ext)
                if os.path.exists(font_path):
                    return font_path
                # 也尝试直接匹配
                for file in os.listdir(font_dir):
                    if font_name.lower() in file.lower():
                        return os.path.join(font_dir, file)

        return None

    @staticmethod
    def get_subtitle_style_preview_html(
        text: str,
        font_size: int = 36,
        text_color: str = "#FFFFFF",
        stroke_color: str = "#000000",
        stroke_width: float = 1.5,
        position: str = "bottom"
    ) -> str:
        """
        生成字幕样式的HTML预览
        """
        # 位置映射
        position_styles = {
            "top": "top: 5%;",
            "center": "top: 45%;",
            "bottom": "top: 85%;",
            "custom": f"top: var(--custom-position, 70%);"
        }

        position_style = position_styles.get(position, position_styles["bottom"])

        html = f"""
        <style>
        .subtitle-preview-container {{
            width: 100%;
            max-width: 720px;
            aspect-ratio: 9/16;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 12px;
            position: relative;
            overflow: hidden;
            margin: 10px auto;
        }}
        .subtitle-text {{
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
            {position_style}
            font-size: {font_size}px;
            color: {text_color};
            text-shadow:
                -{stroke_width}px -{stroke_width}px 0 {stroke_color},
                {stroke_width}px -{stroke_width}px 0 {stroke_color},
                -{stroke_width}px {stroke_width}px 0 {stroke_color},
                {stroke_width}px {stroke_width}px 0 {stroke_color},
                0 0 10px rgba(0,0,0,0.5);
            text-align: center;
            padding: 10px 20px;
            max-width: 90%;
            word-wrap: break-word;
            font-family: "Microsoft YaHei", "SimHei", sans-serif;
        }}
        </style>
        <div class="subtitle-preview-container">
            <div class="subtitle-text">{text}</div>
        </div>
        """
        return html

    # ==================== 配音预览 ====================

    @staticmethod
    def generate_waveform_data(audio_path: str, num_samples: int = 100) -> List[float]:
        """
        生成音频波形数据
        基于音频文件分析并返回归一化的振幅样本
        """
        try:
            import struct

            if not os.path.exists(audio_path):
                return [0.0] * num_samples

            with open(audio_path, 'rb') as f:
                # 读取WAV文件头
                chunk_id = f.read(4)
                if chunk_id != b'RIFF':
                    return [0.0] * num_samples

                f.read(4)  # chunk_size
                format_tag = f.read(4)
                if format_tag != b'WAVE':
                    return [0.0] * num_samples

                # 查找data块
                while True:
                    sub_chunk_id = f.read(4)
                    if not sub_chunk_id:
                        break
                    sub_chunk_size = struct.unpack('<I', f.read(4))[0]

                    if sub_chunk_id == b'data':
                        # 读取音频数据
                        audio_data = f.read(sub_chunk_size)
                        # 转换为numpy数组
                        samples = np.frombuffer(audio_data, dtype=np.int16)
                        # 转换为浮点数并归一化
                        samples = samples.astype(np.float32) / 32768.0
                        # 计算每段的平均振幅
                        chunk_size = len(samples) // num_samples
                        if chunk_size > 0:
                            chunks = samples[:chunk_size * num_samples].reshape(num_samples, chunk_size)
                            waveform = np.mean(np.abs(chunks), axis=1)
                        else:
                            waveform = np.zeros(num_samples)
                        return waveform.tolist()

                    # 跳过当前块
                    f.seek(sub_chunk_size, 1)

            return [0.0] * num_samples

        except Exception as e:
            logger.error(f"生成波形数据失败: {e}")
            return [0.0] * num_samples

    @staticmethod
    def generate_waveform_image(
        waveform_data: List[float],
        width: int = 600,
        height: int = 100,
        bar_color: str = "#00CED1",
        background_color: str = "transparent"
    ) -> str:
        """
        生成波形图像
        返回图片的base64编码
        """
        try:
            img = Image.new('RGBA', (width, height), background_color)
            draw = ImageDraw.Draw(img)

            if not waveform_data:
                return ""

            num_bars = len(waveform_data)
            bar_width = width / num_bars
            center_y = height / 2

            for i, amplitude in enumerate(waveform_data):
                bar_height = max(2, amplitude * height * 0.8)
                x = i * bar_width
                y_top = center_y - bar_height / 2

                draw.rectangle(
                    [x, y_top, x + bar_width - 1, y_top + bar_height],
                    fill=bar_color
                )

            # 保存
            temp_dir = utils.storage_dir("temp/preview", create=True)
            filename = f"waveform_{uuid.uuid4().hex[:8]}.png"
            filepath = os.path.join(temp_dir, filename)
            img.save(filepath)

            return filepath

        except Exception as e:
            logger.error(f"生成波形图像失败: {e}")
            return ""

    @staticmethod
    def get_waveform_html(
        waveform_data: List[float],
        duration: float = 5.0,
        bar_color: str = "#00CED1"
    ) -> str:
        """
        生成波形的HTML预览
        """
        # 归一化数据
        max_val = max(waveform_data) if waveform_data and max(waveform_data) > 0 else 1
        normalized = [v / max_val for v in waveform_data]

        bars_json = json.dumps(normalized)
        duration_str = f"{duration:.1f}"

        html = f"""
        <style>
        .waveform-container {{
            width: 100%;
            max-width: 600px;
            height: 100px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 10px auto;
            cursor: pointer;
        }}
        .waveform-bars {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 2px;
            height: 60%;
            width: 90%;
        }}
        .waveform-bar {{
            flex: 1;
            max-width: 4px;
            background: {bar_color};
            border-radius: 2px;
            transition: height 0.1s ease;
        }}
        .waveform-time {{
            position: absolute;
            bottom: 5px;
            right: 10px;
            font-size: 12px;
            color: #888;
        }}
        .waveform-play-icon {{
            position: absolute;
            width: 40px;
            height: 40px;
            background: rgba(255, 255, 255, 0.9);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transition: opacity 0.2s;
        }}
        .waveform-container:hover .waveform-play-icon {{
            opacity: 1;
        }}
        </style>
        <div class="waveform-container" onclick="this.querySelector('audio')?.play()">
            <div class="waveform-bars" id="waveform-bars"></div>
            <span class="waveform-time">{duration_str}s</span>
            <div class="waveform-play-icon">▶</div>
        </div>
        <script>
        (function() {{
            const bars = {bars_json};
            const container = document.getElementById('waveform-bars');
            if (container) {{
                bars.forEach(amplitude => {{
                    const bar = document.createElement('div');
                    bar.className = 'waveform-bar';
                    bar.style.height = (amplitude * 100).toFixed(1) + '%';
                    container.appendChild(bar);
                }});
            }}
        }})();
        </script>
        """
        return html

    # ==================== 视频片段预览 ====================

    @staticmethod
    def generate_video_thumbnail(
        video_path: str,
        timestamp: float = 0.0,
        size: Tuple[int, int] = (320, 180)
    ) -> Optional[str]:
        """
        生成视频缩略图
        """
        try:
            import subprocess

            if not os.path.exists(video_path):
                return None

            temp_dir = utils.storage_dir("temp/preview", create=True)
            output_path = os.path.join(temp_dir, f"thumb_{uuid.uuid4().hex[:8]}.jpg")

            # 使用ffmpeg提取帧
            cmd = [
                config.app.get("ffmpeg_path", "ffmpeg"),
                "-ss", str(timestamp),
                "-i", video_path,
                "-vframes", "1",
                "-s", f"{size[0]}x{size[1]}",
                "-y",
                output_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0 and os.path.exists(output_path):
                return output_path

            return None

        except Exception as e:
            logger.error(f"生成视频缩略图失败: {e}")
            return None

    @staticmethod
    def get_video_preview_html(
        thumbnail_path: str = None,
        duration: float = 5.0,
        timestamp: str = "00:00:00",
        description: str = ""
    ) -> str:
        """
        生成视频片段预览的HTML
        """
        thumb_src = ""
        if thumbnail_path and os.path.exists(thumbnail_path):
            with open(thumbnail_path, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode()
                thumb_src = f"data:image/jpeg;base64,{img_data}"
        else:
            # 使用占位图
            thumb_src = "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='320' height='180' viewBox='0 0 320 180'><rect fill='%231a1a2e' width='320' height='180'/><text x='160' y='90' text-anchor='middle' fill='%23888' font-size='14'>无预览图</text></svg>"

        html = f"""
        <style>
        .video-preview-item {{
            display: inline-block;
            width: 320px;
            margin: 10px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            overflow: hidden;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .video-preview-item:hover {{
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(0, 206, 209, 0.3);
        }}
        .video-thumbnail {{
            width: 100%;
            height: 180px;
            object-fit: cover;
            background: #1a1a2e;
        }}
        .video-info {{
            padding: 10px;
            font-size: 12px;
            color: #aaa;
        }}
        .video-timestamp {{
            color: #00CED1;
            font-weight: bold;
        }}
        .video-duration {{
            float: right;
        }}
        .video-description {{
            margin-top: 5px;
            color: #888;
            font-size: 11px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        </style>
        <div class="video-preview-item">
            <img class="video-thumbnail" src="{thumb_src}" alt="视频预览">
            <div class="video-info">
                <span class="video-timestamp">{timestamp}</span>
                <span class="video-duration">{duration:.1f}s</span>
            </div>
            <div class="video-description">{description}</div>
        </div>
        """
        return html

    # ==================== 工具方法 ====================

    @staticmethod
    def create_preview_from_timestamp(
        video_path: str,
        timestamp: str,
        duration: float = 5.0
    ) -> VideoPreviewItem:
        """
        根据时间戳创建视频预览项
        timestamp格式: "00:00:00,600-00:00:07,559"
        """
        try:
            # 解析时间戳
            start_str, end_str = timestamp.split('-')
            start_seconds = PreviewManager._srt_time_to_seconds(start_str.replace(',', '.'))
            end_seconds = PreviewManager._srt_time_to_seconds(end_str.replace(',', '.'))

            # 生成缩略图
            thumbnail = PreviewManager.generate_video_thumbnail(video_path, start_seconds)

            return VideoPreviewItem(
                id=uuid.uuid4().hex[:8],
                start_time=start_seconds,
                end_time=end_seconds,
                duration=end_seconds - start_seconds,
                thumbnail_path=thumbnail
            )
        except Exception as e:
            logger.error(f"创建视频预览项失败: {e}")
            return VideoPreviewItem(
                id=uuid.uuid4().hex[:8],
                start_time=0,
                end_time=duration,
                duration=duration
            )

    @staticmethod
    def get_preview_data_url(file_path: str) -> str:
        """
        获取文件的data URL
        """
        if not os.path.exists(file_path):
            return ""

        try:
            with open(file_path, 'rb') as f:
                data = f.read()

            # 判断文件类型
            if file_path.endswith('.png'):
                mime_type = 'image/png'
            elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                mime_type = 'image/jpeg'
            elif file_path.endswith('.gif'):
                mime_type = 'image/gif'
            elif file_path.endswith('.mp3'):
                mime_type = 'audio/mpeg'
            elif file_path.endswith('.wav'):
                mime_type = 'audio/wav'
            else:
                mime_type = 'application/octet-stream'

            return f"data:{mime_type};base64,{base64.b64encode(data).decode()}"
        except Exception as e:
            logger.error(f"生成data URL失败: {e}")
            return ""

    @staticmethod
    def cleanup_temp_previews():
        """清理临时预览文件"""
        try:
            temp_dir = utils.storage_dir("temp/preview", create=False)
            if os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    filepath = os.path.join(temp_dir, file)
                    try:
                        # 只删除超过1小时的预览文件
                        if os.path.getmtime(filepath) < time.time() - 3600:
                            os.remove(filepath)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"清理临时预览文件失败: {e}")


# 预览管理器单例
preview_manager = PreviewManager()
