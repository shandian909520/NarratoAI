#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : description_generation.py
@Description: 封面描述生成提示词
"""

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class CoverDescriptionGenerationPrompt(TextPrompt):
    """封面描述生成提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="description_generation",
            category="cover",
            version="v1.0",
            description="根据关键词和样式要求生成详细的封面图像描述",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.TEXT,
            tags=["封面", "图像描述", "AI生成"],
            parameters=["keywords", "style", "platform", "title"]
        )
        super().__init__(metadata)

        self._system_prompt = "你是一个专业的视频封面设计专家，擅长创作具有视觉冲击力和吸引力的封面图像描述。"

    def get_template(self) -> str:
        return """请根据以下信息生成一个详细的封面图像描述，用于AI图像生成。

<keywords>
${keywords}
</keywords>

<style>
${style}
</style>

<platform>
${platform}
</platform>

<title>
${title}
</title>

封面描述要求：
1. 详细描述画面的主体、背景、光影效果
2. 强调视觉冲击力和吸引力
3. 突出关键词代表的元素
4. 符合指定样式的氛围
5. 适合在指定平台展示
6. 如果有标题，确保文字与整体设计协调

请直接输出封面描述，不要使用引号或任何格式标记。描述应该详细、具体，便于AI图像生成模型理解。"""