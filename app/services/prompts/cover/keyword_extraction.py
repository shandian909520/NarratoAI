#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : keyword_extraction.py
@Description: 封面关键词提取提示词
"""

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class CoverKeywordExtractionPrompt(TextPrompt):
    """封面关键词提取提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="keyword_extraction",
            category="cover",
            version="v1.0",
            description="从解说文案中提取用于生成视频封面的关键词",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["封面", "关键词提取", "视频生成"],
            parameters=["narration_script"]
        )
        super().__init__(metadata)

        self._system_prompt = "你是一个专业的视频内容分析专家，擅长提取最能代表视频主题的关键词。"

    def get_template(self) -> str:
        return """请分析以下解说文案，提取5-8个最能代表视频主题和吸引力的关键词。

<narration_script>
${narration_script}
</narration_script>

关键词选择原则：
1. 选择最能吸引观众点击的词汇
2. 优先选择具有视觉表现力的词语
3. 突出视频的核心亮点或悬念
4. 考虑目标平台（抖音、B站等）的用户喜好

请使用以下 JSON 格式输出：

<output>
{
  "keywords": ["关键词1", "关键词2", "关键词3", ...]
}
</output>

<restriction>
1. 只输出 JSON 内容，不要输出其他任何说明性文字
2. 关键词数量控制在5-8个
3. 每个关键词不超过6个字
4. 关键词应该具有视觉表现力和吸引力
5. 使用简体中文
"""