"""
Generator Agent 实现
负责根据任务和批判反馈生成/优化产出
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from langchain_core.language_models import BaseChatModel

from config.settings import get_config
from src.agents.base import BaseAgent
from src.models.schemas import AgentRole, CritiqueResult
from src.prompts.generator_prompt import (
    get_generator_prompt,
    build_generator_user_message,
)

logger = logging.getLogger(__name__)


class GeneratorAgent(BaseAgent):
    """
    生成者 Agent
    根据任务描述和 Critic 的反馈，不断优化产出内容
    """

    def __init__(
        self,
        domain: str = "general",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        llm: Optional[BaseChatModel] = None,
    ):
        """
        初始化 Generator Agent
        
        Args:
            domain: 任务领域，决定使用哪个系统提示词
            model: 模型名称，为 None 时从配置读取
            temperature: 温度参数，为 None 时从配置读取
            llm: 外部注入的 LLM 实例
        """
        self.domain = domain
        config = get_config()

        system_prompt = get_generator_prompt(domain)
        temp = temperature if temperature is not None else config.llm.generator_temperature

        super().__init__(
            role=AgentRole.GENERATOR,
            system_prompt=system_prompt,
            model=model,
            temperature=temp,
            llm=llm,
        )

    def _get_default_model(self) -> str:
        """获取默认模型名称"""
        return get_config().llm.generator_model

    def _build_user_message(
        self,
        task: str,
        draft: str = "",
        critique: Optional[CritiqueResult] = None,
    ) -> str:
        """
        构建发送给 Generator 的用户消息

        供 generate 与 generate_stream 共用，避免逻辑重复

        Args:
            task: 任务描述
            draft: 上一版产出（首次生成时为空）
            critique: 上一轮的批判结果（首次生成时为 None）

        Returns:
            格式化后的用户消息
        """
        is_first_turn = critique is None or draft == ""

        if is_first_turn:
            logger.info(f"[Generator] 首次生成，任务长度: {len(task)}")
            return build_generator_user_message(task=task, is_first_turn=True)

        # 格式化 issues 和 suggestions
        issues_str = "\n".join(
            f"{i+1}. {issue}"
            for i, issue in enumerate(critique.issues)
        ) if critique.issues else "无"

        suggestions_str = "\n".join(
            f"{i+1}. {sug}"
            for i, sug in enumerate(critique.suggestions)
        ) if critique.suggestions else "无"

        logger.info(
            f"[Generator] 迭代生成，上轮评分: {critique.score}, "
            f"问题数: {len(critique.issues)}"
        )
        return build_generator_user_message(
            task=task,
            draft=draft,
            is_first_turn=False,
            score=critique.score,
            issues=issues_str,
            suggestions=suggestions_str,
        )

    def generate(
        self,
        task: str,
        draft: str = "",
        critique: Optional[CritiqueResult] = None,
    ) -> str:
        """
        生成或优化产出（阻塞式，一次性返回完整结果）
        
        Args:
            task: 任务描述
            draft: 上一版产出（首次生成时为空）
            critique: 上一轮的批判结果（首次生成时为 None）
        
        Returns:
            生成的产出内容
        """
        user_message = self._build_user_message(task, draft, critique)
        result = self.call_llm_with_retry(user_message)
        return self._extract_final_output(result)

    def generate_stream(
        self,
        task: str,
        draft: str = "",
        critique: Optional[CritiqueResult] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        流式生成或优化产出，逐块返回生成内容

        与 generate 不同，此方法在模型生成过程中即可通过 on_token 回调
        拿到每一个文本增量，用于 Web 等实时展示场景。

        Args:
            task: 任务描述
            draft: 上一版产出（首次生成时为空）
            critique: 上一轮的批判结果（首次生成时为 None）
            on_token: 可选回调，每生成一段文本就调用一次，参数为文本增量

        Returns:
            生成完成后提取出的最终产出内容
        """
        user_message = self._build_user_message(task, draft, critique)

        parts: list[str] = []
        for piece in self.call_llm_stream(user_message):
            parts.append(piece)
            if on_token:
                on_token(piece)

        return self._extract_final_output("".join(parts))

    def _extract_final_output(self, response: str) -> str:
        """
        从 Generator 的回复中提取最终产出
        Generator 的输出格式为：
        【修改说明】...
        【最终产出】...
        
        如果没有明确的【最终产出】标记，则返回完整回复
        
        Args:
            response: LLM 的原始回复
        
        Returns:
            提取出的最终产出
        """
        # 尝试匹配【最终产出】标记
        pattern = r"【最终产出】\s*\n?(.*)"
        match = re.search(pattern, response, re.DOTALL)

        if match:
            output = match.group(1).strip()
            logger.debug(
                f"[Generator] 从回复中提取最终产出，长度: {len(output)}"
            )
            return output

        # 尝试匹配 "最终产出" 或 "完整代码" 等变体
        variants = [
            r"最终产出[：:]\s*\n?(.*)",
            r"完整代码[：:]\s*\n?(.*)",
            r"完整文案[：:]\s*\n?(.*)",
            r"完整方案[：:]\s*\n?(.*)",
        ]
        for variant in variants:
            match = re.search(variant, response, re.DOTALL)
            if match:
                output = match.group(1).strip()
                # 清理可能的代码块标记
                output = re.sub(r"^```\w*\n?", "", output)
                output = re.sub(r"\n?```$", "", output)
                return output.strip()

        # 没有找到标记，返回完整回复
        logger.debug(
            "[Generator] 未找到最终产出标记，返回完整回复"
        )
        return response.strip()
