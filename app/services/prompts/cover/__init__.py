# -*- coding: UTF-8 -*-
"""
封面生成提示词模块
"""

from .keyword_extraction import CoverKeywordExtractionPrompt
from .description_generation import CoverDescriptionGenerationPrompt
from ..manager import PromptManager


def register_prompts():
    """注册封面生成相关的提示词"""

    # 注册关键词提取提示词
    keyword_prompt = CoverKeywordExtractionPrompt()
    PromptManager.register_prompt(keyword_prompt, is_default=True)

    # 注册描述生成提示词
    description_prompt = CoverDescriptionGenerationPrompt()
    PromptManager.register_prompt(description_prompt, is_default=True)


__all__ = [
    "CoverKeywordExtractionPrompt",
    "CoverDescriptionGenerationPrompt",
    "register_prompts"
]
