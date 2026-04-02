#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
智能封面生成服务

提供基于解说文案生成封面的功能，支持多种封面模板样式和平台适配。
"""

import os
import json
import base64
import uuid
import asyncio
import re
from enum import Enum
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass, field
from io import BytesIO
from loguru import logger

import requests
from PIL import Image, ImageDraw, ImageFont

from app.services.llm.migration_adapter import _run_async_safely
from app.services.llm.unified_service import UnifiedLLMService
from app.services.prompts import PromptManager
from app.config import config
from app.utils import utils


class CoverStyle(str, Enum):
    """封面样式枚举"""
    CINEMATIC = "cinematic"       # 电影感
    COMEDIC = "comedic"          # 搞笑风格
    MYSTERIOUS = "mysterious"     # 悬疑风格
    DRAMATIC = "dramatic"         # 戏剧风格
    MINIMALIST = "minimalist"     # 简约风格
    VIBRANT = "vibrant"          # 活力风格


class CoverPlatform(str, Enum):
    """封面平台适配枚举"""
    DOUYIN = "douyin"            # 抖音
    BILIBILI = "bilibili"         # B站
    YOUTUBE = "youtube"           # YouTube
    WEIBO = "weibo"              # 微博
    XIAOHONGSHU = "xiaohongshu"  # 小红书
    UNIVERSAL = "universal"       # 通用


# 平台尺寸配置
PLATFORM_SIZES = {
    CoverPlatform.DOUYIN: (1080, 1920),      # 9:16 竖版
    CoverPlatform.BILIBILI: (1920, 1080),    # 16:9 横版
    CoverPlatform.YOUTUBE: (1280, 720),       # 16:9 横版
    CoverPlatform.WEIBO: (1080, 1080),        # 1:1 方形
    CoverPlatform.XIAOHONGSHU: (1242, 1660), # 3:4 竖版
    CoverPlatform.UNIVERSAL: (1080, 1920),    # 默认竖版
}


@dataclass
class CoverGenerationRequest:
    """封面生成请求"""
    narration_script: str = ""                    # 解说文案
    keywords: List[str] = field(default_factory=list)  # 关键词
    style: CoverStyle = CoverStyle.CINEMATIC      # 封面样式
    platform: CoverPlatform = CoverPlatform.DOUYIN  # 目标平台
    title_text: str = ""                          # 标题文字
    subtitle_text: str = ""                       # 副标题文字
    use_ai_generation: bool = True               # 是否使用AI生成


@dataclass
class CoverGenerationResult:
    """封面生成结果"""
    success: bool = False
    cover_description: str = ""                   # 封面描述
    cover_image_path: str = ""                    # 封面图片路径
    cover_image_base64: str = ""                  # 封面图片Base64
    error_message: str = ""


class CoverGenerator:
    """智能封面生成器"""

    # 样式提示词映射
    STYLE_PROMPTS = {
        CoverStyle.CINEMATIC: "电影感氛围，光影对比强烈，戏剧性构图，深邃的背景",
        CoverStyle.COMEDIC: "明亮活泼，夸张有趣，表情丰富，欢快轻松",
        CoverStyle.MYSTERIOUS: "神秘阴暗，光影交错，悬念感强，低饱和色调",
        CoverStyle.DRAMATIC: "强烈对比，大气磅礴，情绪饱满，张力十足",
        CoverStyle.MINIMALIST: "简洁大方，留白充足，主题突出，文艺清新",
        CoverStyle.VIBRANT: "色彩鲜艳，活力四射，青春时尚，视觉冲击",
    }

    # 平台适配提示
    PLATFORM_HINTS = {
        CoverPlatform.DOUYIN: "竖屏构图，适合手机全屏展示，前3秒必须抓住眼球",
        CoverPlatform.BILIBILI: "横屏构图，可添加B站风格装饰元素",
        CoverPlatform.YOUTUBE: "横屏构图，YouTube视频封面标准尺寸",
        CoverPlatform.WEIBO: "方形构图，微博分享适配",
        CoverPlatform.XIAOHONGSHU: "竖屏构图，小红书笔记风格",
        CoverPlatform.UNIVERSAL: "通用构图设计",
    }

    def __init__(self):
        """初始化封面生成器"""
        self.image_api_provider = config.llm.get("image_provider", "openai")
        self.image_api_key = config.llm.get("image_api_key", "")
        self.image_model = config.llm.get("image_model", "dall-e-3")
        self.image_base_url = config.llm.get("image_base_url", "")

    def extract_keywords_from_narration(self, narration_script: str) -> List[str]:
        """
        从解说文案中提取关键词

        Args:
            narration_script: 解说文案

        Returns:
            关键词列表
        """
        try:
            prompt = PromptManager.get_prompt(
                category="cover",
                name="keyword_extraction",
                parameters={"narration_script": narration_script}
            )

            result = _run_async_safely(
                UnifiedLLMService.generate_text,
                prompt=prompt,
                system_prompt="你是一个关键词提取专家。从给定的解说文案中提取5-8个最能代表视频主题的关键词，用于生成视频封面描述。",
                temperature=0.7,
                response_format="json"
            )

            parsed = json.loads(result)
            if isinstance(parsed, dict) and "keywords" in parsed:
                return parsed["keywords"]
            elif isinstance(parsed, list):
                return parsed[:8]
            else:
                return self._fallback_keyword_extraction(narration_script)

        except Exception as e:
            logger.warning(f"关键词提取失败: {str(e)}，使用备用方法")
            return self._fallback_keyword_extraction(narration_script)

    def _fallback_keyword_extraction(self, text: str) -> List[str]:
        """备用关键词提取方法"""
        # 移除标点符号
        text = re.sub(r'[^\w\s]', ' ', text)
        # 分词
        words = text.split()
        # 过滤停用词和短词
        stop_words = {'的', '了', '是', '在', '和', '与', '或', '等', '这', '那', '个', '我', '你', '他', '她', '它', '们'}
        keywords = [w for w in words if len(w) >= 2 and w not in stop_words]
        # 统计词频
        word_freq = {}
        for w in keywords:
            word_freq[w] = word_freq.get(w, 0) + 1
        # 按词频排序
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [w[0] for w in sorted_words[:8]]

    def generate_cover_description(
        self,
        keywords: List[str],
        style: CoverStyle = CoverStyle.CINEMATIC,
        platform: CoverPlatform = CoverPlatform.DOUYIN,
        title_text: str = ""
    ) -> str:
        """
        生成封面描述

        Args:
            keywords: 关键词列表
            style: 封面样式
            platform: 目标平台
            title_text: 标题文字

        Returns:
            封面描述
        """
        try:
            keywords_str = "、".join(keywords)
            style_hint = self.STYLE_PROMPTS.get(style, "")
            platform_hint = self.PLATFORM_HINTS.get(platform, "")

            prompt = PromptManager.get_prompt(
                category="cover",
                name="description_generation",
                parameters={
                    "keywords": keywords_str,
                    "style": style_hint,
                    "platform": platform_hint,
                    "title": title_text
                }
            )

            result = _run_async_safely(
                UnifiedLLMService.generate_text,
                prompt=prompt,
                system_prompt=f"你是一个专业的视频封面设计专家。根据提供的关键词和样式要求，生成一个详细的封面图像描述。{platform_hint}",
                temperature=1.0
            )

            return result.strip()

        except Exception as e:
            logger.error(f"封面描述生成失败: {str(e)}")
            return self._fallback_cover_description(keywords, style)

    def _fallback_cover_description(self, keywords: List[str], style: CoverStyle) -> str:
        """备用封面描述生成"""
        style_desc = {
            CoverStyle.CINEMATIC: "电影感封面，暗色调，光影对比",
            CoverStyle.COMEDIC: "搞笑风格，明亮色调",
            CoverStyle.MYSTERIOUS: "悬疑风格，低饱和度，神秘氛围",
            CoverStyle.DRAMATIC: "戏剧风格，强烈对比",
            CoverStyle.MINIMALIST: "简约风格，简洁大方",
            CoverStyle.VIBRANT: "活力风格，色彩鲜艳",
        }
        keyword_str = "、".join(keywords[:5])
        return f"视频封面，{style_desc.get(style, '电影感')}，主题关键词：{keyword_str}"

    async def generate_cover_image(
        self,
        description: str,
        size: tuple = (1080, 1920),
        quality: str = "hd"
    ) -> Optional[bytes]:
        """
        使用AI生成封面图片

        Args:
            description: 封面描述
            size: 图片尺寸 (width, height)
            quality: 图片质量 (hd, standard)

        Returns:
            图片字节数据，失败返回None
        """
        try:
            # 根据不同提供商调用对应的API
            if self.image_api_provider == "openai" or "dall" in self.image_model.lower():
                return await self._generate_dalle_image(description, size, quality)
            elif self.image_api_provider == "stability":
                return await self._generate_stability_image(description, size)
            else:
                # 默认使用 OpenAI DALL-E 格式
                return await self._generate_dalle_image(description, size, quality)

        except Exception as e:
            logger.error(f"AI封面图片生成失败: {str(e)}")
            return None

    async def _generate_dalle_image(
        self,
        description: str,
        size: tuple,
        quality: str
    ) -> Optional[bytes]:
        """使用 DALL-E 生成图片"""
        try:
            # DALL-E 3 支持的尺寸
            if size[0] > size[1]:
                dalle_size = "1024x1024" if abs(size[0] - size[1]) < 100 else "1792x1024"
            else:
                dalle_size = "1024x1024" if abs(size[0] - size[1]) < 100 else "1024x1792"

            # 构建API请求
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.image_api_key}"
            }

            payload = {
                "model": self.image_model,
                "prompt": description,
                "size": dalle_size,
                "quality": quality,
                "n": 1,
                "style": "vivid"  # vivid 或 natural
            }

            base_url = self.image_base_url or "https://api.openai.com/v1"
            response = requests.post(
                f"{base_url}/images/generations",
                headers=headers,
                json=payload,
                timeout=120
            )

            if response.status_code != 200:
                logger.error(f"DALL-E API 请求失败: {response.status_code} - {response.text}")
                return None

            result = response.json()
            image_url = result.get("data", [{}])[0].get("url", "")

            if not image_url:
                logger.error("DALL-E API 返回的图像URL为空")
                return None

            # 下载图片
            image_response = requests.get(image_url, timeout=60)
            if image_response.status_code == 200:
                return image_response.content

            return None

        except Exception as e:
            logger.error(f"DALL-E 图片生成异常: {str(e)}")
            return None

    async def _generate_stability_image(
        self,
        description: str,
        size: tuple
    ) -> Optional[bytes]:
        """使用 Stability AI 生成图片"""
        try:
            api_key = self.image_api_key
            engine_id = "stable-diffusion-xl-1024-v1-0"

            headers = {
                "Authorization": f"Bearer {api_key}"
            }

            payload = {
                "text_prompts": [{"text": description}],
                "cfg_scale": 7,
                "height": size[1],
                "width": size[0],
                "samples": 1,
                "steps": 30
            }

            base_url = self.image_base_url or "https://api.stability.ai/v1"
            response = requests.post(
                f"{base_url}/generation/{engine_id}/text-to-image",
                headers=headers,
                json=payload,
                timeout=120
            )

            if response.status_code != 200:
                logger.error(f"Stability AI API 请求失败: {response.status_code}")
                return None

            result = response.json()
            image_base64 = result.get("artifacts", [{}])[0].get("base64", "")

            if image_base64:
                return base64.b64decode(image_base64)

            return None

        except Exception as e:
            logger.error(f"Stability AI 图片生成异常: {str(e)}")
            return None

    def create_text_overlay(
        self,
        image_bytes: bytes,
        title_text: str,
        subtitle_text: str = "",
        position: str = "bottom"
    ) -> bytes:
        """
        在封面上添加文字叠加

        Args:
            image_bytes: 原始图片字节
            title_text: 标题文字
            subtitle_text: 副标题文字
            position: 文字位置 (top, center, bottom)

        Returns:
            处理后的图片字节
        """
        try:
            img = Image.open(BytesIO(image_bytes))
            draw = ImageDraw.Draw(img)

            # 获取图片尺寸
            width, height = img.size

            # 尝试加载字体
            try:
                # 尝试系统字体
                title_font = ImageFont.truetype("arial.ttf", int(height * 0.06))
                subtitle_font = ImageFont.truetype("arial.ttf", int(height * 0.04))
            except:
                # 使用默认字体
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()

            # 计算文字位置
            if position == "top":
                title_y = int(height * 0.08)
                subtitle_y = int(height * 0.16)
            elif position == "center":
                title_y = int(height * 0.45)
                subtitle_y = int(height * 0.55)
            else:  # bottom
                title_y = int(height * 0.82)
                subtitle_y = int(height * 0.90)

            # 绘制半透明背景条
            if title_text:
                # 估算文字宽度
                bbox = draw.textbbox((0, 0), title_text, font=title_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                bg_height = int(text_height * 1.5)
                bg_y = title_y - int(text_height * 0.2)

                # 绘制背景
                overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle(
                    [(width - text_width - 40, bg_y), (width + 10, bg_y + bg_height)],
                    fill=(0, 0, 0, 150)
                )
                img = Image.alpha_composite(img.convert('RGBA'), overlay)

                # 绘制标题文字
                draw = ImageDraw.Draw(img)
                draw.text(
                    ((width - text_width) // 2, title_y),
                    title_text,
                    font=title_font,
                    fill=(255, 255, 255, 255)
                )

            if subtitle_text:
                bbox = draw.textbbox((0, 0), subtitle_text, font=subtitle_font)
                text_width = bbox[2] - bbox[0]

                draw.text(
                    ((width - text_width) // 2, subtitle_y),
                    subtitle_text,
                    font=subtitle_font,
                    fill=(255, 255, 255, 200)
                )

            # 转换回 RGB 模式保存
            if img.mode == 'RGBA':
                img = img.convert('RGB')

            output = BytesIO()
            img.save(output, format='JPEG', quality=95)
            return output.getvalue()

        except Exception as e:
            logger.error(f"文字叠加失败: {str(e)}")
            return image_bytes

    def create_template_cover(
        self,
        keywords: List[str],
        style: CoverStyle,
        platform: CoverPlatform,
        title_text: str = "",
        subtitle_text: str = ""
    ) -> bytes:
        """
        使用模板创建封面（无AI生成时）

        Args:
            keywords: 关键词列表
            style: 封面样式
            platform: 目标平台
            title_text: 标题文字
            subtitle_text: 副标题文字

        Returns:
            封面图片字节
        """
        size = PLATFORM_SIZES.get(platform, (1080, 1920))

        # 根据样式选择背景色
        style_colors = {
            CoverStyle.CINEMATIC: (20, 20, 30),
            CoverStyle.COMEDIC: (255, 200, 100),
            CoverStyle.MYSTERIOUS: (30, 30, 50),
            CoverStyle.DRAMATIC: (50, 20, 20),
            CoverStyle.MINIMALIST: (250, 250, 250),
            CoverStyle.VIBRANT: (100, 50, 150),
        }

        bg_color = style_colors.get(style, (30, 30, 40))

        # 创建图片
        img = Image.new('RGB', size, bg_color)
        draw = ImageDraw.Draw(img)

        # 添加渐变效果
        for i in range(size[1] // 3):
            alpha = int(100 * (1 - i / (size[1] // 3)))
            overlay_color = (0, 0, 0, alpha)
            draw.rectangle(
                [(0, size[1] - i * 3), (size[0], size[1] - i * 3 + 3)],
                fill=(0, 0, 0)
            )

        # 尝试加载字体
        try:
            title_font = ImageFont.truetype("arial.ttf", int(size[1] * 0.05))
            keyword_font = ImageFont.truetype("arial.ttf", int(size[1] * 0.03))
        except:
            title_font = ImageFont.load_default()
            keyword_font = ImageFont.load_default()

        # 绘制标题
        if title_text:
            bbox = draw.textbbox((0, 0), title_text, font=title_font)
            text_width = bbox[2] - bbox[0]
            draw.text(
                ((size[0] - text_width) // 2, int(size[1] * 0.15)),
                title_text,
                font=title_font,
                fill=(255, 255, 255)
            )

        # 绘制关键词
        if keywords:
            keyword_text = " | ".join(keywords[:5])
            bbox = draw.textbbox((0, 0), keyword_text, font=keyword_font)
            text_width = bbox[2] - bbox[0]
            draw.text(
                ((size[0] - text_width) // 2, int(size[1] * 0.75)),
                keyword_text,
                font=keyword_font,
                fill=(200, 200, 200)
            )

        # 绘制副标题
        if subtitle_text:
            bbox = draw.textbbox((0, 0), subtitle_text, font=keyword_font)
            text_width = bbox[2] - bbox[0]
            draw.text(
                ((size[0] - text_width) // 2, int(size[1] * 0.85)),
                subtitle_text,
                font=keyword_font,
                fill=(180, 180, 180)
            )

        output = BytesIO()
        img.save(output, format='JPEG', quality=95)
        return output.getvalue()

    async def generate(
        self,
        request: CoverGenerationRequest
    ) -> CoverGenerationResult:
        """
        生成封面

        Args:
            request: 封面生成请求

        Returns:
            封面生成结果
        """
        result = CoverGenerationResult()

        try:
            # 1. 提取关键词
            if not request.keywords and request.narration_script:
                logger.info("从解说文案中提取关键词")
                request.keywords = self.extract_keywords_from_narration(request.narration_script)

            if not request.keywords:
                request.keywords = ["视频", "解说", "精彩"]

            logger.info(f"提取的关键词: {request.keywords}")

            # 2. 生成封面描述
            result.cover_description = self.generate_cover_description(
                keywords=request.keywords,
                style=request.style,
                platform=request.platform,
                title_text=request.title_text
            )
            logger.info(f"生成的封面描述: {result.cover_description}")

            # 3. 获取目标尺寸
            size = PLATFORM_SIZES.get(request.platform, (1080, 1920))

            # 4. 生成封面图片
            if request.use_ai_generation and self.image_api_key:
                logger.info("使用AI生成封面图片")
                image_bytes = await self.generate_cover_image(
                    description=result.cover_description,
                    size=size
                )

                if image_bytes:
                    # 添加文字叠加
                    if request.title_text or request.subtitle_text:
                        image_bytes = self.create_text_overlay(
                            image_bytes,
                            request.title_text,
                            request.subtitle_text
                        )
                else:
                    # AI生成失败，使用模板封面
                    logger.warning("AI封面生成失败，使用模板封面")
                    image_bytes = self.create_template_cover(
                        keywords=request.keywords,
                        style=request.style,
                        platform=request.platform,
                        title_text=request.title_text,
                        subtitle_text=request.subtitle_text
                    )
            else:
                # 不使用AI生成，使用模板封面
                logger.info("使用模板生成封面")
                image_bytes = self.create_template_cover(
                    keywords=request.keywords,
                    style=request.style,
                    platform=request.platform,
                    title_text=request.title_text,
                    subtitle_text=request.subtitle_text
                )

            # 5. 保存封面图片
            if image_bytes:
                # 转换为 base64
                result.cover_image_base64 = base64.b64encode(image_bytes).decode('utf-8')

                # 保存到文件
                cover_dir = utils.storage_dir("covers", create=True)
                filename = f"cover_{uuid.uuid4().hex[:8]}.jpg"
                cover_path = os.path.join(cover_dir, filename)

                with open(cover_path, 'wb') as f:
                    f.write(image_bytes)

                result.cover_image_path = cover_path
                result.success = True
                logger.info(f"封面已保存: {cover_path}")
            else:
                result.error_message = "封面图片生成失败"

        except Exception as e:
            logger.error(f"封面生成异常: {str(e)}")
            result.error_message = str(e)

        return result


# 全局实例
_cover_generator_instance: Optional[CoverGenerator] = None


def get_cover_generator() -> CoverGenerator:
    """获取封面生成器全局实例"""
    global _cover_generator_instance
    if _cover_generator_instance is None:
        _cover_generator_instance = CoverGenerator()
    return _cover_generator_instance


async def generate_cover_async(request: CoverGenerationRequest) -> CoverGenerationResult:
    """
    异步生成封面的便捷函数

    Args:
        request: 封面生成请求

    Returns:
        封面生成结果
    """
    generator = get_cover_generator()
    return await generator.generate(request)


def generate_cover(request: CoverGenerationRequest) -> CoverGenerationResult:
    """
    同步生成封面的便捷函数

    Args:
        request: 封面生成请求

    Returns:
        封面生成结果
    """
    generator = get_cover_generator()
    return asyncio.run(generator.generate(request))
