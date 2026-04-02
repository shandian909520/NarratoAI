"""
模板数据模型
提供解说风格模板的数据结构和验证
"""

import json
import os
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import pydantic
from loguru import logger
from pydantic import BaseModel, Field


class TemplateStyle(str, Enum):
    """模板风格枚举"""
    HUMOROUS = "humorous"  # 搞笑
    EMOTIONAL = "emotional"  # 感人
    MYSTERIOUS = "mysterious"  # 悬疑
    EDUCATIONAL = "educational"  # 科普
    INSPIRATIONAL = "inspirational"  # 励志
    CUSTOM = "custom"  # 自定义


class NarrationStyle(BaseModel):
    """解说风格配置"""
    style: TemplateStyle = TemplateStyle.EDUCATIONAL
    description: str = ""
    # 语气词使用频率 (0-1)
    emotion_word_frequency: float = 0.3
    # 句子平均长度
    avg_sentence_length: int = 25
    # 感叹句比例 (0-1)
    exclamation_ratio: float = 0.1
    # 问句比例 (0-1)
    question_ratio: float = 0.05
    # 悬念设置
    suspense_enabled: bool = True
    suspense_frequency: float = 0.2
    # 专业术语使用 (0-1)
    technical_term_usage: float = 0.2
    # 是否使用流行语
    trending_word_usage: float = 0.1
    # 背景音乐风格
    bgm_style: str = "auto"
    # 语速基准
    base_rate: float = 1.0


class SubtitleStyle(BaseModel):
    """字幕样式配置"""
    enabled: bool = True
    font_name: str = "SimHei"
    font_size: int = 36
    text_color: str = "#FFFFFF"
    background_color: Optional[str] = None
    stroke_color: str = "#000000"
    stroke_width: float = 1.5
    position: str = "bottom"  # top, center, bottom, custom
    custom_position: float = 70.0


class VoiceStyle(BaseModel):
    """语音样式配置"""
    engine: str = "edge_tts"
    voice_name: str = "zh-CN-XiaoxiaoNeural-Female"
    volume: float = 1.0
    rate: float = 1.0
    pitch: float = 1.0


class VideoStyle(BaseModel):
    """视频样式配置"""
    aspect: str = "9:16"  # 16:9, 9:16, 1:1, 4:3
    transition_effect: str = "fade"  # fade, slide, none
    clip_duration: int = 5
    concat_mode: str = "random"


class TemplateMetadata(BaseModel):
    """模板元数据"""
    id: str = Field(default="", description="模板唯一ID")
    name: str = Field(default="", description="模板名称")
    description: str = Field(default="", description="模板描述")
    author: str = Field(default="", description="作者")
    created_at: str = Field(default="", description="创建时间")
    updated_at: str = Field(default="", description="更新时间")
    tags: List[str] = Field(default_factory=list, description="标签")
    is_builtin: bool = Field(default=False, description="是否内置模板")
    is_editable: bool = Field(default=True, description="是否可编辑")
    version: str = Field(default="1.0.0", description="模板版本")
    thumbnail: Optional[str] = Field(default=None, description="缩略图路径")


class VideoTemplate(BaseModel):
    """完整视频模板"""
    metadata: TemplateMetadata = Field(default_factory=TemplateMetadata)
    narration: NarrationStyle = Field(default_factory=NarrationStyle)
    subtitle: SubtitleStyle = Field(default_factory=SubtitleStyle)
    voice: VoiceStyle = Field(default_factory=VoiceStyle)
    video: VideoStyle = Field(default_factory=VideoStyle)

    class Config:
        use_enum_values = True


class TemplateManager:
    """模板管理器"""

    TEMPLATES_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))),
        "resource", "templates"
    )

    BUILTIN_TEMPLATES = {
        "humorous": {
            "metadata": {
                "id": "builtin_humorous",
                "name": "搞笑风格",
                "description": "轻松幽默的解说风格，适合娱乐类视频",
                "author": "NarratoAI",
                "tags": ["搞笑", "幽默", "娱乐"],
                "is_builtin": True,
                "is_editable": False,
            },
            "narration": {
                "style": "humorous",
                "description": "轻松幽默的解说风格",
                "emotion_word_frequency": 0.6,
                "avg_sentence_length": 20,
                "exclamation_ratio": 0.25,
                "question_ratio": 0.1,
                "suspense_enabled": False,
                "suspense_frequency": 0.1,
                "technical_term_usage": 0.05,
                "trending_word_usage": 0.4,
                "bgm_style": "comedy",
                "base_rate": 1.15,
            },
            "subtitle": {
                "enabled": True,
                "font_size": 40,
                "text_color": "#FFD700",
                "stroke_color": "#000000",
                "stroke_width": 2.0,
            },
            "voice": {
                "engine": "edge_tts",
                "voice_name": "zh-CN-XiaoyiNeural-Female",
                "rate": 1.15,
            },
            "video": {
                "transition_effect": "slide",
                "clip_duration": 4,
            }
        },
        "emotional": {
            "metadata": {
                "id": "builtin_emotional",
                "name": "感人风格",
                "description": "深情厚意的解说风格，适合情感类视频",
                "author": "NarratoAI",
                "tags": ["感人", "情感", "深情"],
                "is_builtin": True,
                "is_editable": False,
            },
            "narration": {
                "style": "emotional",
                "description": "深情厚意的解说风格",
                "emotion_word_frequency": 0.7,
                "avg_sentence_length": 30,
                "exclamation_ratio": 0.05,
                "question_ratio": 0.02,
                "suspense_enabled": False,
                "suspense_frequency": 0.05,
                "technical_term_usage": 0.02,
                "trending_word_usage": 0.05,
                "bgm_style": "emotional",
                "base_rate": 0.9,
            },
            "subtitle": {
                "enabled": True,
                "font_size": 38,
                "text_color": "#FFFFFF",
                "stroke_color": "#333333",
                "stroke_width": 1.5,
            },
            "voice": {
                "engine": "edge_tts",
                "voice_name": "zh-CN-YunxiNeural-Male",
                "rate": 0.9,
                "pitch": 0.95,
            },
            "video": {
                "transition_effect": "fade",
                "clip_duration": 6,
            }
        },
        "mysterious": {
            "metadata": {
                "id": "builtin_mysterious",
                "name": "悬疑风格",
                "description": "紧张刺激的悬疑解说风格，适合推理类视频",
                "author": "NarratoAI",
                "tags": ["悬疑", "紧张", "推理"],
                "is_builtin": True,
                "is_editable": False,
            },
            "narration": {
                "style": "mysterious",
                "description": "紧张刺激的悬疑解说风格",
                "emotion_word_frequency": 0.3,
                "avg_sentence_length": 22,
                "exclamation_ratio": 0.15,
                "question_ratio": 0.15,
                "suspense_enabled": True,
                "suspense_frequency": 0.5,
                "technical_term_usage": 0.25,
                "trending_word_usage": 0.05,
                "bgm_style": "tension",
                "base_rate": 1.0,
            },
            "subtitle": {
                "enabled": True,
                "font_size": 36,
                "text_color": "#8B0000",
                "stroke_color": "#000000",
                "stroke_width": 2.5,
            },
            "voice": {
                "engine": "edge_tts",
                "voice_name": "zh-CN-YunyangNeural-Male",
                "rate": 1.0,
                "pitch": 0.9,
            },
            "video": {
                "transition_effect": "fade",
                "clip_duration": 5,
            }
        },
        "educational": {
            "metadata": {
                "id": "builtin_educational",
                "name": "科普风格",
                "description": "严谨专业的科普解说风格，适合知识类视频",
                "author": "NarratoAI",
                "tags": ["科普", "专业", "知识"],
                "is_builtin": True,
                "is_editable": False,
            },
            "narration": {
                "style": "educational",
                "description": "严谨专业的科普解说风格",
                "emotion_word_frequency": 0.15,
                "avg_sentence_length": 35,
                "exclamation_ratio": 0.03,
                "question_ratio": 0.1,
                "suspense_enabled": True,
                "suspense_frequency": 0.2,
                "technical_term_usage": 0.4,
                "trending_word_usage": 0.05,
                "bgm_style": "calm",
                "base_rate": 1.0,
            },
            "subtitle": {
                "enabled": True,
                "font_size": 34,
                "text_color": "#00CED1",
                "stroke_color": "#000000",
                "stroke_width": 1.5,
            },
            "voice": {
                "engine": "edge_tts",
                "voice_name": "zh-CN-XiaoxiaoNeural-Female",
                "rate": 1.0,
            },
            "video": {
                "transition_effect": "none",
                "clip_duration": 5,
            }
        },
        "inspirational": {
            "metadata": {
                "id": "builtin_inspirational",
                "name": "励志风格",
                "description": "激昂奋进的励志解说风格，适合激励类视频",
                "author": "NarratoAI",
                "tags": ["励志", "激励", "正能量"],
                "is_builtin": True,
                "is_editable": False,
            },
            "narration": {
                "style": "inspirational",
                "description": "激昂奋进的励志解说风格",
                "emotion_word_frequency": 0.5,
                "avg_sentence_length": 25,
                "exclamation_ratio": 0.3,
                "question_ratio": 0.05,
                "suspense_enabled": True,
                "suspense_frequency": 0.25,
                "technical_term_usage": 0.1,
                "trending_word_usage": 0.15,
                "bgm_style": "epic",
                "base_rate": 1.1,
            },
            "subtitle": {
                "enabled": True,
                "font_size": 42,
                "text_color": "#FFD700",
                "stroke_color": "#000000",
                "stroke_width": 2.0,
            },
            "voice": {
                "engine": "edge_tts",
                "voice_name": "zh-CN-YunjianNeural-Male",
                "rate": 1.1,
                "pitch": 1.05,
            },
            "video": {
                "transition_effect": "fade",
                "clip_duration": 4,
            }
        },
    }

    @classmethod
    def ensure_templates_dir(cls) -> None:
        """确保模板目录存在"""
        os.makedirs(cls.TEMPLATES_DIR, exist_ok=True)

    @classmethod
    def get_builtin_template(cls, style: str) -> Optional[VideoTemplate]:
        """获取内置模板"""
        template_data = cls.BUILTIN_TEMPLATES.get(style)
        if template_data:
            return VideoTemplate(**template_data)
        return None

    @classmethod
    def get_all_builtin_templates(cls) -> Dict[str, VideoTemplate]:
        """获取所有内置模板"""
        return {
            style: VideoTemplate(**data)
            for style, data in cls.BUILTIN_TEMPLATES.items()
        }

    @classmethod
    def list_user_templates(cls) -> List[TemplateMetadata]:
        """列出用户自定义模板"""
        cls.ensure_templates_dir()
        templates = []
        for filename in os.listdir(cls.TEMPLATES_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(cls.TEMPLATES_DIR, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        templates.append(TemplateMetadata(**data.get('metadata', {})))
                except Exception as e:
                    logger.error(f"加载模板失败 {filename}: {e}")
        return templates

    @classmethod
    def load_template(cls, template_id: str) -> Optional[VideoTemplate]:
        """加载指定模板"""
        # 先检查内置模板
        style = template_id.replace("builtin_", "")
        if template_id.startswith("builtin_") and style in cls.BUILTIN_TEMPLATES:
            return cls.get_builtin_template(style)

        # 检查用户模板
        cls.ensure_templates_dir()
        filepath = os.path.join(cls.TEMPLATES_DIR, f"{template_id}.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return VideoTemplate(**data)
            except Exception as e:
                logger.error(f"加载模板失败 {template_id}: {e}")
        return None

    @classmethod
    def save_template(cls, template: VideoTemplate) -> bool:
        """保存模板到文件"""
        cls.ensure_templates_dir()

        # 设置元数据
        if not template.metadata.id:
            template.metadata.id = f"custom_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if not template.metadata.created_at:
            template.metadata.created_at = datetime.now().isoformat()
        template.metadata.updated_at = datetime.now().isoformat()
        template.metadata.is_builtin = False
        template.metadata.is_editable = True

        filepath = os.path.join(cls.TEMPLATES_DIR, f"{template.metadata.id}.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(template.model_dump(mode='json'), f, ensure_ascii=False, indent=2)
            logger.info(f"模板已保存: {filepath}")
            return True
        except Exception as e:
            logger.error(f"保存模板失败: {e}")
            return False

    @classmethod
    def delete_template(cls, template_id: str) -> bool:
        """删除用户模板"""
        if template_id.startswith("builtin_"):
            logger.warning("无法删除内置模板")
            return False

        cls.ensure_templates_dir()
        filepath = os.path.join(cls.TEMPLATES_DIR, f"{template_id}.json")
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                logger.info(f"模板已删除: {filepath}")
                return True
            except Exception as e:
                logger.error(f"删除模板失败: {e}")
        return False

    @classmethod
    def export_template(cls, template_id: str, export_path: str) -> bool:
        """导出模板到指定路径"""
        template = cls.load_template(template_id)
        if not template:
            logger.error(f"模板不存在: {template_id}")
            return False

        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(template.model_dump(mode='json'), f, ensure_ascii=False, indent=2)
            logger.info(f"模板已导出: {export_path}")
            return True
        except Exception as e:
            logger.error(f"导出模板失败: {e}")
            return False

    @classmethod
    def import_template(cls, import_path: str) -> Optional[VideoTemplate]:
        """从指定路径导入模板"""
        if not os.path.exists(import_path):
            logger.error(f"导入文件不存在: {import_path}")
            return None

        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                template = VideoTemplate(**data)
                # 生成新ID避免冲突
                template.metadata.id = f"imported_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                template.metadata.is_builtin = False
                template.metadata.is_editable = True
                # 保存到模板目录
                if cls.save_template(template):
                    return template
        except Exception as e:
            logger.error(f"导入模板失败: {e}")
        return None

    @classmethod
    def get_template_as_dict(cls, template_id: str) -> Optional[Dict[str, Any]]:
        """获取模板数据字典"""
        template = cls.load_template(template_id)
        if template:
            return template.model_dump(mode='json')
        return None

    @classmethod
    def apply_template_params(cls, template_id: str) -> Dict[str, Any]:
        """应用模板参数到当前配置"""
        template = cls.load_template(template_id)
        if not template:
            return {}

        return {
            # 字幕设置
            "subtitle_enabled": template.subtitle.enabled,
            "font_name": template.subtitle.font_name,
            "font_size": template.subtitle.font_size,
            "text_fore_color": template.subtitle.text_color,
            "stroke_color": template.subtitle.stroke_color,
            "stroke_width": template.subtitle.stroke_width,
            "subtitle_position": template.subtitle.position,
            "custom_position": template.subtitle.custom_position,
            # 语音设置
            "tts_engine": template.voice.engine,
            "voice_name": template.voice.voice_name,
            "voice_volume": template.voice.volume,
            "voice_rate": template.voice.rate,
            "voice_pitch": template.voice.pitch,
            # 视频设置
            "video_aspect": template.video.aspect,
            "video_clip_duration": template.video.clip_duration,
            # 解说风格
            "narration_style": template.narration.style,
            "emotion_word_frequency": template.narration.emotion_word_frequency,
            "exclamation_ratio": template.narration.exclamation_ratio,
            "question_ratio": template.narration.question_ratio,
            "suspense_enabled": template.narration.suspense_enabled,
            "technical_term_usage": template.narration.technical_term_usage,
            "trending_word_usage": template.narration.trending_word_usage,
            "base_rate": template.narration.base_rate,
        }
