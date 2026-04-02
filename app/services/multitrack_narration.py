#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
多音轨解说服务

提供多角色解说功能，支持角色识别、音色分配、多轨音频生成和混音控制。
"""

import os
import json
import uuid
import asyncio
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from dataclasses import dataclass
from loguru import logger

from app.services.voice import tts, get_audio_duration_from_file, SubMaker
from app.services.prompts import PromptManager
from app.services.llm.migration_adapter import _run_async_safely
from app.services.llm.unified_service import UnifiedLLMService
from app.config import config
from app.utils import utils


class DialogueRole(str, Enum):
    """对话角色类型"""
    NARRATOR = "narrator"      # 旁白
    MALE = "male"              # 男性角色
    FEMALE = "female"          # 女性角色
    ELDERLY_MALE = "elderly_male"    # 老年男性
    ELDERLY_FEMALE = "elderly_female"  # 老年女性
    CHILD = "child"            # 儿童
    CUSTOM = "custom"          # 自定义角色


@dataclass
class RoleVoiceConfig:
    """角色音色配置"""
    role_id: str = ""                    # 角色ID
    role_name: str = ""                  # 角色名称
    role_type: DialogueRole = DialogueRole.NARRATOR  # 角色类型
    voice_name: str = ""                 # 音色名称
    voice_rate: float = 1.0              # 语速
    voice_pitch: float = 1.0            # 音调
    volume: float = 1.0                 # 音量
    pan_position: float = 0.0            # 声像位置 (-1.0 左 到 1.0 右)


@dataclass
class DialogueSegment:
    """对话片段"""
    segment_id: str = ""                 # 片段ID
    role_id: str = ""                   # 角色ID
    text: str = ""                       # 对话文本
    timestamp: Tuple[float, float] = field(default_factory=(0.0, 0.0))  # 开始、结束时间
    audio_file: str = ""                 # 生成的音频文件路径
    duration: float = 0.0                # 音频时长


@dataclass
class MultiTrackNarrationRequest:
    """多音轨解说请求"""
    task_id: str = ""                    # 任务ID
    narration_script: str = ""            # 解说文案
    role_configs: List[RoleVoiceConfig] = field(default_factory=list)  # 角色配置列表
    default_narrator_voice: str = "zh-CN-XiaoxiaoNeural"  # 默认旁白音色
    use_ai_role_detection: bool = True   # 是否使用AI进行角色识别
    enable_mixing: bool = True           # 是否启用混音


@dataclass
class MultiTrackNarrationResult:
    """多音轨解说结果"""
    success: bool = False
    dialogue_segments: List[DialogueSegment] = field(default_factory=list)  # 对话片段列表
    role_configs: List[RoleVoiceConfig] = field(default_factory=list)       # 角色配置列表
    total_duration: float = 0.0           # 总时长
    mixed_audio_path: str = ""           # 混音后音频路径
    track_audio_paths: Dict[str, str] = field(default_factory=dict)  # 各音轨音频路径
    error_message: str = ""


class MultiTrackNarrationService:
    """多音轨解说服务"""

    # 角色默认音色映射
    DEFAULT_ROLE_VOICES = {
        DialogueRole.NARRATOR: "zh-CN-XiaoxiaoNeural",
        DialogueRole.MALE: "zh-CN-YunxiNeural",
        DialogueRole.FEMALE: "zh-CN-XiaoyiNeural",
        DialogueRole.ELDERLY_MALE: "zh-CN-YunyangNeural",
        DialogueRole.ELDERLY_FEMALE: "zh-CN-liaoning-XiaobeiNeural",
        DialogueRole.CHILD: "zh-CN-XiaoyiNeural",
    }

    # 声像位置预设
    PAN_POSITIONS = {
        DialogueRole.NARRATOR: 0.0,        # 中央
        DialogueRole.MALE: -0.3,            # 偏左
        DialogueRole.FEMALE: 0.3,           # 偏右
        DialogueRole.ELDERLY_MALE: -0.5,     # 偏左
        DialogueRole.ELDERLY_FEMALE: 0.5,   # 偏右
        DialogueRole.CHILD: 0.2,             # 偏右
    }

    def __init__(self):
        """初始化多音轨解说服务"""
        self.tts_engine = config.ui.get("tts_engine", "edge_tts")

    def detect_roles_from_script(
        self,
        narration_script: str
    ) -> List[Dict[str, Any]]:
        """
        使用AI从解说文案中识别角色

        Args:
            narration_script: 解说文案

        Returns:
            角色列表
        """
        try:
            prompt = PromptManager.get_prompt(
                category="multitrack",
                name="role_detection",
                parameters={"narration_script": narration_script}
            )

            result = _run_async_safely(
                UnifiedLLMService.generate_text,
                prompt=prompt,
                system_prompt="""你是一个专业的角色识别专家。从给定的解说文案中识别出不同的角色对话。

请分析文案中的对话和叙述，识别出：
1. 旁白（叙述性文字）
2. 不同角色的对话

输出格式为JSON数组，每个元素包含：
- role_id: 角色唯一标识
- role_name: 角色名称（如：旁白、角色A、角色B等）
- role_type: 角色类型（narrator, male, female, elderly_male, elderly_female, child）
- sample_text: 该角色的一句代表性台词

只输出JSON数组，不要有其他文字。""",
                temperature=0.5,
                response_format="json"
            )

            parsed = json.loads(result)
            if isinstance(parsed, list):
                return parsed
            else:
                logger.warning(f"角色检测返回格式异常: {type(parsed)}")
                return self._fallback_role_detection(narration_script)

        except Exception as e:
            logger.error(f"角色检测失败: {str(e)}，使用备用方法")
            return self._fallback_role_detection(narration_script)

    def _fallback_role_detection(self, text: str) -> List[Dict[str, Any]]:
        """备用角色检测方法 - 检测对话格式"""
        roles = []
        role_map = {}

        # 简单检测"旁白："、"角色A："等格式
        import re
        pattern = r'([^\s：]+)[:：]([^\n]+)'

        for match in re.finditer(pattern, text):
            role_name = match.group(1).strip()
            if role_name not in role_map:
                role_id = f"role_{len(role_map) + 1}"
                role_map[role_name] = role_id

                # 根据名称判断角色类型
                role_type = DialogueRole.NARRATOR
                if any(kw in role_name for kw in ['旁白', '解说', '叙述']):
                    role_type = DialogueRole.NARRATOR
                elif any(kw in role_name for kw in ['男', '老', '爷', '叔', '公']):
                    role_type = DialogueRole.MALE
                elif any(kw in role_name for kw in ['女', '妈', '奶', '婆', '姨']):
                    role_type = DialogueRole.FEMALE

                roles.append({
                    "role_id": role_id,
                    "role_name": role_name,
                    "role_type": role_type.value,
                    "sample_text": match.group(2).strip()[:50]
                })

        if not roles:
            # 如果没有检测到对话格式，默认是旁白
            roles.append({
                "role_id": "narrator",
                "role_name": "旁白",
                "role_type": DialogueRole.NARRATOR.value,
                "sample_text": text[:50] if text else ""
            })

        return roles

    def parse_dialogue_segments(
        self,
        narration_script: str,
        role_configs: List[RoleVoiceConfig]
    ) -> List[DialogueSegment]:
        """
        解析对话片段

        Args:
            narration_script: 解说文案
            role_configs: 角色配置列表

        Returns:
            对话片段列表
        """
        try:
            # 构建角色配置JSON
            roles_json = json.dumps([
                {
                    "role_id": rc.role_id,
                    "role_name": rc.role_name,
                    "role_type": rc.role_type.value
                }
                for rc in role_configs
            ], ensure_ascii=False)

            prompt = PromptManager.get_prompt(
                category="multitrack",
                name="dialogue_parsing",
                parameters={
                    "narration_script": narration_script,
                    "roles": roles_json
                }
            )

            result = _run_async_safely(
                UnifiedLLMService.generate_text,
                prompt=prompt,
                system_prompt="""你是一个专业的对话解析专家。将解说文案解析成结构化的对话片段。

根据提供的角色列表，将解说文案解析成独立的对话片段。每个片段包含：
- segment_id: 片段唯一ID
- role_id: 对应的角色ID
- text: 该角色的对话内容

输出格式为JSON数组。只输出JSON数组，不要有其他文字。""",
                temperature=0.3,
                response_format="json"
            )

            parsed = json.loads(result)
            if isinstance(parsed, list):
                segments = []
                for item in parsed:
                    segment = DialogueSegment(
                        segment_id=item.get("segment_id", f"seg_{len(segments)}"),
                        role_id=item.get("role_id", ""),
                        text=item.get("text", ""),
                        timestamp=(0.0, 0.0)
                    )
                    segments.append(segment)
                return segments
            else:
                return self._fallback_parse_dialogue(narration_script, role_configs)

        except Exception as e:
            logger.error(f"对话解析失败: {str(e)}，使用备用方法")
            return self._fallback_parse_dialogue(narration_script, role_configs)

    def _fallback_parse_dialogue(
        self,
        text: str,
        role_configs: List[RoleVoiceConfig]
    ) -> List[DialogueSegment]:
        """备用对话解析方法"""
        segments = []

        # 如果没有角色配置，默认是旁白
        if not role_configs:
            role_configs = [RoleVoiceConfig(
                role_id="narrator",
                role_name="旁白",
                role_type=DialogueRole.NARRATOR
            )]

        import re
        pattern = r'([^\s：]+)[:：]([^\n]+)'

        role_map = {rc.role_name: rc.role_id for rc in role_configs}

        for match in re.finditer(pattern, text):
            role_name = match.group(1).strip()
            role_id = role_map.get(role_name, role_configs[0].role_id)

            segments.append(DialogueSegment(
                segment_id=f"seg_{len(segments)}",
                role_id=role_id,
                text=match.group(2).strip()
            ))

        if not segments:
            # 如果没有解析到对话，整体作为一个旁白片段
            role_id = role_configs[0].role_id if role_configs else "narrator"
            # 按句子分割
            sentences = re.split(r'[。！？\n]', text)
            for i, sent in enumerate(sentences):
                sent = sent.strip()
                if sent:
                    segments.append(DialogueSegment(
                        segment_id=f"seg_{i}",
                        role_id=role_id,
                        text=sent
                    ))

        return segments

    async def generate_single_track(
        self,
        segment: DialogueSegment,
        role_config: RoleVoiceConfig,
        output_dir: str,
        tts_engine: str
    ) -> DialogueSegment:
        """
        生成单个角色的音频

        Args:
            segment: 对话片段
            role_config: 角色配置
            output_dir: 输出目录
            tts_engine: TTS引擎

        Returns:
            更新后的对话片段
        """
        try:
            # 生成音频文件路径
            timestamp_str = f"{int(segment.timestamp[0] * 1000)}_{int(segment.timestamp[1] * 1000)}"
            audio_file = os.path.join(
                output_dir,
                f"track_{role_config.role_id}_{segment.segment_id}_{timestamp_str}.mp3"
            )

            # 调用TTS生成音频
            sub_maker = tts(
                text=segment.text,
                voice_name=role_config.voice_name,
                voice_rate=role_config.voice_rate,
                voice_pitch=role_config.voice_pitch,
                voice_file=audio_file,
                tts_engine=tts_engine
            )

            if sub_maker and os.path.exists(audio_file):
                # 获取音频时长
                duration = get_audio_duration_from_file(audio_file)
                if duration <= 0:
                    duration = max(1.0, len(segment.text) / 3.0)

                segment.audio_file = audio_file
                segment.duration = duration
                logger.info(f"已生成角色 {role_config.role_name} 的音频: {audio_file}")
            else:
                logger.error(f"角色 {role_config.role_name} 的音频生成失败")

        except Exception as e:
            logger.error(f"生成音频片段失败: {str(e)}")

        return segment

    def mix_audio_tracks(
        self,
        segments: List[DialogueSegment],
        output_path: str,
        sample_rate: int = 48000
    ) -> bool:
        """
        混音多个音轨

        Args:
            segments: 对话片段列表
            output_path: 输出路径
            sample_rate: 采样率

        Returns:
            是否成功
        """
        try:
            # 尝试使用 moviepy 进行混音
            try:
                from moviepy import AudioFileClip
                import numpy as np
            except ImportError:
                logger.warning("moviepy 未安装，无法进行专业混音")
                return False

            if not segments:
                return False

            # 找出总时长
            max_duration = max(
                (seg.timestamp[1] for seg in segments if seg.timestamp[1] > 0),
                default=sum(seg.duration for seg in segments)
            )

            # 创建混合音频
            mixed_audio = np.zeros(int(max_duration * sample_rate))

            for seg in segments:
                if not seg.audio_file or not os.path.exists(seg.audio_file):
                    continue

                try:
                    clip = AudioFileClip(seg.audio_file)
                    audio_data = clip.to_soundarray(fps=sample_rate)

                    # 获取音量和声像
                    role_config = next(
                        (rc for rc in self.role_configs if rc.role_id == seg.role_id),
                        None
                    )
                    volume = role_config.volume if role_config else 1.0
                    pan = role_config.pan_position if role_config else 0.0

                    # 计算左右声道音量
                    left_vol = volume * (1 - pan) / 2
                    right_vol = volume * (1 + pan) / 2

                    # 确保音频数据是立体声
                    if len(audio_data.shape) == 1:
                        audio_data = np.column_stack([audio_data, audio_data])

                    # 应用音量和声像
                    audio_data[:, 0] *= left_vol
                    audio_data[:, 1] *= right_vol

                    # 计算放置位置
                    start_sample = int(seg.timestamp[0] * sample_rate)
                    end_sample = min(start_sample + len(audio_data), len(mixed_audio))

                    if start_sample < len(mixed_audio):
                        # 添加音频数据
                        actual_len = end_sample - start_sample
                        mixed_audio[start_sample:end_sample] += audio_data[:actual_len]

                    clip.close()

                except Exception as e:
                    logger.warning(f"处理音频片段 {seg.segment_id} 失败: {str(e)}")
                    continue

            # 归一化
            max_val = np.max(np.abs(mixed_audio))
            if max_val > 1.0:
                mixed_audio = mixed_audio / max_val * 0.95

            # 保存混音结果
            import soundfile as sf
            sf.write(output_path, mixed_audio, sample_rate)

            logger.info(f"混音完成: {output_path}")
            return True

        except ImportError:
            logger.warning("soundfile 未安装，无法保存混音")
            return False
        except Exception as e:
            logger.error(f"混音失败: {str(e)}")
            return False

    def calculate_timestamps(
        self,
        segments: List[DialogueSegment]
    ) -> List[DialogueSegment]:
        """
        计算每个片段的时间戳

        Args:
            segments: 对话片段列表

        Returns:
            更新后的对话片段列表
        """
        current_time = 0.0
        gap_between_segments = 0.2  # 片段间隔

        for seg in segments:
            seg.timestamp = (current_time, current_time + seg.duration)
            current_time += seg.duration + gap_between_segments

        return segments

    async def generate(
        self,
        request: MultiTrackNarrationRequest
    ) -> MultiTrackNarrationResult:
        """
        生成多音轨解说

        Args:
            request: 多音轨解说请求

        Returns:
            多音轨解说结果
        """
        result = MultiTrackNarrationResult()
        self.role_configs = request.role_configs

        try:
            # 1. 角色检测和配置
            if request.use_ai_role_detection:
                logger.info("使用AI检测角色")
                detected_roles = self.detect_roles_from_script(request.narration_script)

                # 更新角色配置
                for detected in detected_roles:
                    role_id = detected["role_id"]
                    role_type = DialogueRole(detected.get("role_type", "narrator"))

                    # 检查是否已存在该角色配置
                    existing = next(
                        (rc for rc in request.role_configs if rc.role_id == role_id),
                        None
                    )

                    if existing:
                        # 更新已有配置
                        existing.role_name = detected.get("role_name", existing.role_name)
                        existing.role_type = role_type
                        if not existing.voice_name:
                            existing.voice_name = self.DEFAULT_ROLE_VOICES.get(
                                role_type,
                                request.default_narrator_voice
                            )
                    else:
                        # 添加新角色配置
                        new_config = RoleVoiceConfig(
                            role_id=role_id,
                            role_name=detected.get("role_name", f"角色{len(request.role_configs)}"),
                            role_type=role_type,
                            voice_name=self.DEFAULT_ROLE_VOICES.get(
                                role_type,
                                request.default_narrator_voice
                            ),
                            pan_position=self.PAN_POSITIONS.get(role_type, 0.0)
                        )
                        request.role_configs.append(new_config)

            # 确保有默认旁白配置
            if not any(rc.role_type == DialogueRole.NARRATOR for rc in request.role_configs):
                request.role_configs.insert(0, RoleVoiceConfig(
                    role_id="narrator",
                    role_name="旁白",
                    role_type=DialogueRole.NARRATOR,
                    voice_name=request.default_narrator_voice,
                    volume=1.0,
                    pan_position=0.0
                ))

            result.role_configs = request.role_configs
            logger.info(f"角色配置: {[rc.role_name for rc in result.role_configs]}")

            # 2. 解析对话片段
            logger.info("解析对话片段")
            segments = self.parse_dialogue_segments(
                request.narration_script,
                request.role_configs
            )
            result.dialogue_segments = segments
            logger.info(f"解析到 {len(segments)} 个对话片段")

            # 3. 生成各角色音频
            logger.info("生成各角色音频")
            output_dir = utils.task_dir(request.task_id)

            # 按角色分组生成
            for role_config in request.role_configs:
                role_segments = [
                    seg for seg in segments
                    if seg.role_id == role_config.role_id
                ]

                for seg in role_segments:
                    updated_seg = await self.generate_single_track(
                        seg, role_config, output_dir, request.tts_engine or self.tts_engine
                    )
                    # 更新原始片段
                    for original in result.dialogue_segments:
                        if original.segment_id == seg.segment_id:
                            original.audio_file = updated_seg.audio_file
                            original.duration = updated_seg.duration
                            break

            # 4. 计算时间戳
            result.dialogue_segments = self.calculate_timestamps(result.dialogue_segments)

            # 5. 计算总时长
            result.total_duration = max(
                (seg.timestamp[1] for seg in result.dialogue_segments),
                default=0.0
            )

            # 6. 混音
            if request.enable_mixing:
                logger.info("开始混音")
                mixed_path = os.path.join(output_dir, f"mixed_audio_{uuid.uuid4().hex[:8]}.wav")

                if self.mix_audio_tracks(result.dialogue_segments, mixed_path):
                    result.mixed_audio_path = mixed_path

            # 7. 收集各音轨路径
            result.track_audio_paths = {
                seg.role_id: seg.audio_file
                for seg in result.dialogue_segments
                if seg.audio_file
            }

            result.success = True
            logger.info(f"多音轨解说生成完成，总时长: {result.total_duration:.2f}秒")

        except Exception as e:
            logger.error(f"多音轨解说生成失败: {str(e)}")
            result.error_message = str(e)

        return result


# 全局实例
_multitrack_service_instance: Optional[MultiTrackNarrationService] = None


def get_multitrack_service() -> MultiTrackNarrationService:
    """获取多音轨解说服务全局实例"""
    global _multitrack_service_instance
    if _multitrack_service_instance is None:
        _multitrack_service_instance = MultiTrackNarrationService()
    return _multitrack_service_instance


async def generate_multitrack_narration_async(
    request: MultiTrackNarrationRequest
) -> MultiTrackNarrationResult:
    """
    异步生成多音轨解说的便捷函数

    Args:
        request: 多音轨解说请求

    Returns:
        多音轨解说结果
    """
    service = get_multitrack_service()
    return await service.generate(request)


def generate_multitrack_narration(
    request: MultiTrackNarrationRequest
) -> MultiTrackNarrationResult:
    """
    同步生成多音轨解说的便捷函数

    Args:
        request: 多音轨解说请求

    Returns:
        多音轨解说结果
    """
    service = get_multitrack_service()
    return asyncio.run(service.generate(request))
