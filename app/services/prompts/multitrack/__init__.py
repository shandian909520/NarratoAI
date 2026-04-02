# -*- coding: UTF-8 -*-
"""
多音轨解说提示词模块
"""

from .role_detection import MultitrackRoleDetectionPrompt
from .dialogue_parsing import MultitrackDialogueParsingPrompt
from ..manager import PromptManager


def register_prompts():
    """注册多音轨解说相关的提示词"""

    # 注册角色检测提示词
    role_prompt = MultitrackRoleDetectionPrompt()
    PromptManager.register_prompt(role_prompt, is_default=True)

    # 注册对话解析提示词
    dialogue_prompt = MultitrackDialogueParsingPrompt()
    PromptManager.register_prompt(dialogue_prompt, is_default=True)


__all__ = [
    "MultitrackRoleDetectionPrompt",
    "MultitrackDialogueParsingPrompt",
    "register_prompts"
]
