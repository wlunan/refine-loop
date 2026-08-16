"""
Critic Agent 实现
负责审查 Generator 的产出，给出结构化的批判结果
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser

from config.settings import get_config
from src.agents.base import BaseAgent
from src.models.schemas import AgentRole, CritiqueResult
from src.prompts.critic_prompt import (
    get_critic_prompt,
    build_critic_user_message,
)

logger = logging.getLogger(__name__)


class CriticAgent(BaseAgent):
    """
    批判者 Agent
    审查 Generator 的产出，输出结构化的 CritiqueResult
    """

    def __init__(
        self,
        domain: str = "general",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        llm: Optional[BaseChatModel] = None,
    ):
        """
        初始化 Critic Agent
        
        Args:
            domain: 任务领域，决定使用哪个系统提示词
            model: 模型名称，为 None 时从配置读取
            temperature: 温度参数，为 None 时从配置读取
            llm: 外部注入的 LLM 实例
        """
        self.domain = domain
        config = get_config()

        system_prompt = get_critic_prompt(domain)
        temp = temperature if temperature is not None else config.llm.critic_temperature

        super().__init__(
            role=AgentRole.CRITIC,
            system_prompt=system_prompt,
            model=model,
            temperature=temp,
            llm=llm,
        )

        # 初始化 Pydantic 解析器
        self.parser = PydanticOutputParser(pydantic_object=CritiqueResult)

    def _get_default_model(self) -> str:
        """获取默认模型名称"""
        return get_config().llm.critic_model

    def critique(self, task: str, draft: str) -> CritiqueResult:
        """
        审查 Generator 的产出
        
        Args:
            task: 原始任务描述
            draft: Generator 的产出
        
        Returns:
            结构化的审查结果
        """
        user_message = build_critic_user_message(task=task, draft=draft)

        # 注入 Pydantic 输出的 JSON Schema，明确告知模型应输出的字段与类型，
        # 否则弱模型容易输出字段缺失/类型错误/夹带文字，导致解析降级
        format_instructions = self.parser.get_format_instructions()
        user_message = user_message + "\n\n" + format_instructions

        logger.info(
            f"[Critic] 开始审查，产出长度: {len(draft)}"
        )

        raw_response = self.call_llm_with_retry(user_message)
        result = self._parse_critique_response(raw_response)

        logger.info(
            f"[Critic] 审查完成，评分: {result.score}, "
            f"问题数: {len(result.issues)}, "
            f"可接受: {result.acceptable}"
        )
        return result

    def _parse_critique_response(self, response: str) -> CritiqueResult:
        """
        解析 Critic 的回复为结构化的 CritiqueResult
        
        Args:
            response: LLM 的原始回复
        
        Returns:
            解析后的 CritiqueResult，解析失败时返回降级结果
        """
        # 尝试直接用 Pydantic 解析
        try:
            return self.parser.parse(response)
        except Exception as e:
            logger.debug(f"[Critic] 直接解析失败: {e}，尝试提取 JSON")

        # 尝试从回复中提取 JSON 块
        json_str = self._extract_json(response)
        if json_str:
            try:
                data = json.loads(json_str)
                return self._coerce_critique(data)
            except Exception as e:
                logger.warning(f"[Critic] JSON 解析失败: {e}")

        # 降级：返回一个保守的审查结果，并把原始回复片段带出来方便定位
        snippet = response[:300].replace("\n", " ")
        logger.warning(
            "[Critic] 无法解析回复，返回降级结果（score=50, 不可接受）"
        )
        return CritiqueResult(
            score=50,
            issues=[
                "Critic 的回复格式无法解析，无法进行有效审查。"
                f"原始回复片段: {snippet}"
            ],
            suggestions=[
                "请确认 Critic 模型是否严格输出 JSON；"
                "或换用更强的模型（如 mimo-v2.5-pro / gpt-4o-mini）"
            ],
            acceptable=False,
            summary="解析降级",
        )

    def _coerce_critique(self, data) -> CritiqueResult:
        """
        对解析出的 JSON 做类型容错转换，再构造 CritiqueResult

        弱模型常输出 score 为字符串、issues 为字符串等类型偏差，
        直接 CritiqueResult(**data) 会因 Pydantic 严格校验而失败，
        这里统一清洗字段类型。

        Args:
            data: json.loads 得到的对象（期望是 dict）

        Returns:
            类型修正后的 CritiqueResult

        Raises:
            ValueError: data 不是 dict 等无法修复的情况
        """
        if not isinstance(data, dict):
            raise ValueError(f"审查 JSON 不是对象: {type(data)}")

        # score: 兼容字符串数字 / 浮点，并夹在 0-100
        raw_score = data.get("score", 0)
        try:
            score = int(round(float(raw_score)))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))

        # issues / suggestions: 统一转为字符串列表
        def _to_str_list(value):
            if value is None:
                return []
            if isinstance(value, str):
                return [value]
            if isinstance(value, list):
                return [str(item) for item in value]
            return [str(value)]

        issues = _to_str_list(data.get("issues"))
        suggestions = _to_str_list(data.get("suggestions"))

        # acceptable: 兼容 bool / 字符串布尔
        raw_acceptable = data.get("acceptable", False)
        if isinstance(raw_acceptable, str):
            acceptable = raw_acceptable.strip().lower() in (
                "true", "1", "yes", "是", "y"
            )
        else:
            acceptable = bool(raw_acceptable)

        summary = data.get("summary")

        try:
            return CritiqueResult(
                score=score,
                issues=issues,
                suggestions=suggestions,
                acceptable=acceptable,
                summary=summary,
            )
        except Exception:
            # 若 acceptable 与 score 一致性校验不通过（acceptable=True 但分过低），
            # 强制 acceptable=False 兜底
            return CritiqueResult(
                score=score,
                issues=issues,
                suggestions=suggestions,
                acceptable=False,
                summary=summary,
            )

    def _extract_json(self, text: str) -> Optional[str]:
        """
        从文本中提取 JSON 字符串
        处理 LLM 可能在 JSON 前后添加说明文字的情况
        
        Args:
            text: 原始文本
        
        Returns:
            提取出的 JSON 字符串，未找到时返回 None
        """
        # 方法1：匹配 ```json ... ``` 代码块
        json_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        match = re.search(json_block_pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 方法2：匹配第一个 { 到最后一个 }
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return text[first_brace:last_brace + 1]

        return None
