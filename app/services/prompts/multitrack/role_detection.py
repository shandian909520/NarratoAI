#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : role_detection.py
@Description: 多音轨角色检测提示词
"""

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class MultitrackRoleDetectionPrompt(TextPrompt):
    """多音轨角色检测提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="role_detection",
            category="multitrack",
            version="v1.0",
            description="从解说文案中自动识别不同的角色对话",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["多音轨", "角色识别", "对话分析"],
            parameters=["narration_script"]
        )
        super().__init__(metadata)

        self._system_prompt = "你是一个专业的角色识别专家，能够准确识别解说文案中的不同角色对话。"

    def get_template(self) -> str:
        return """请分析以下解说文案，识别出不同的角色对话。

<narration_script>
${narration_script}
</narration_script>

角色识别规则：
1. 旁白（narrator）：叙述性、说明性、总结性的文字
2. 男性角色（male）：明显的男性对话或发言
3. 女性角色（female）：明显的女性对话或发言
4. 老年男性（elderly_male）：老年男性的对话
5. 老年女性（elderly_female）：老年女性的对话
6. 儿童（child）：儿童或稚嫩的声音

识别要求：
1. 仔细分析文案的对话格式和语气
2. 根据说话内容判断角色类型
3. 如果有明确的角色名称标注（如"旁白："、"角色A："），按标注识别
4. 提供每个角色的代表性台词样本

请使用以下 JSON 格式输出：

<output>
[
  {
    "role_id": "narrator",
    "role_name": "旁白",
    "role_type": "narrator",
    "sample_text": "旁白的一句代表性台词"
  },
  {
    "role_id": "role_1",
    "role_name": "角色A",
    "role_type": "male",
    "sample_text": "角色A的一句代表性台词"
  }
]
</output>

<restriction>
1. 只输出 JSON 数组内容，不要输出其他任何说明性文字
2. 确保每个识别的角色都有代表性台词
3. role_type 必须是指定的值之一：narrator, male, female, elderly_male, elderly_female, child
4. 使用简体中文输出
5. 如果没有明确的角色对话，至少应该包含一个旁白
"""