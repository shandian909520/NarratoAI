#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : dialogue_parsing.py
@Description: 多音轨对话解析提示词
"""

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class MultitrackDialogueParsingPrompt(TextPrompt):
    """多音轨对话解析提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="dialogue_parsing",
            category="multitrack",
            version="v1.0",
            description="将解说文案解析成结构化的对话片段",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["多音轨", "对话解析", "结构化"],
            parameters=["narration_script", "roles"]
        )
        super().__init__(metadata)

        self._system_prompt = "你是一个专业的对话解析专家，能够将复杂的解说文案解析成独立的对话片段。"

    def get_template(self) -> str:
        return """请将以下解说文案解析成独立的对话片段，分配给相应的角色。

<narration_script>
${narration_script}
</narration_script>

<roles>
${roles}
</roles>

解析规则：
1. 每个对话片段应该是一句完整的话
2. 根据说话内容和语气分配给最合适的角色
3. 旁白负责叙述性、说明性、过渡性的文字
4. 保持对话的连贯性和逻辑性
5. 确保每个片段都有明确的角色归属

请使用以下 JSON 格式输出：

<output>
[
  {
    "segment_id": "seg_1",
    "role_id": "narrator",
    "text": "旁白的对话内容"
  },
  {
    "segment_id": "seg_2",
    "role_id": "role_1",
    "text": "角色A的对话内容"
  },
  {
    "segment_id": "seg_3",
    "role_id": "narrator",
    "text": "旁白的下一段叙述"
  }
]
</output>

<restriction>
1. 只输出 JSON 数组内容，不要输出其他任何说明性文字
2. segment_id 格式为 seg_1, seg_2, seg_3 ...
3. role_id 必须在提供的 roles 列表中存在
4. 每个 segment 的 text 应该是一句完整的话，不超过50个字
5. 使用简体中文输出
6. 保持对话顺序与原文一致
"""