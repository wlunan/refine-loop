"""
Agent 基类模块
定义所有 Agent 的公共接口和基础功能
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config.settings import get_config
from src.models.schemas import AgentRole

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Agent 基类
    所有具体 Agent（Generator、Critic）都继承自此类
    封装了 LLM 调用、日志记录、token 统计等公共能力
    """

    def __init__(
        self,
        role: AgentRole,
        system_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        llm: Optional[BaseChatModel] = None,
    ):
        """
        初始化 Agent
        
        Args:
            role: Agent 角色
            system_prompt: 系统提示词
            model: 模型名称，为 None 时从配置读取
            temperature: 温度参数
            llm: 外部注入的 LLM 实例（用于测试或自定义）
        """
        self.role = role
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.total_tokens_used = 0

        # 支持外部注入 LLM（便于测试和自定义）
        if llm is not None:
            self.llm = llm
        else:
            config = get_config()
            self.llm = ChatOpenAI(
                model=model or self._get_default_model(),
                temperature=temperature,
                api_key=config.llm.api_key,
                base_url=config.llm.api_base,
                max_tokens=config.llm.max_tokens,
                timeout=config.llm.request_timeout,
            )

        logger.info(
            f"Agent 初始化完成: role={role.value}, "
            f"model={self.llm.model_name}, temperature={temperature}"
        )

    @abstractmethod
    def _get_default_model(self) -> str:
        """获取默认模型名称（由子类实现）"""
        pass

    def _build_messages(
        self,
        user_message: str,
        conversation_history: Optional[list] = None,
    ) -> list:
        """
        构建发送给 LLM 的消息列表
        
        Args:
            user_message: 当前用户消息
            conversation_history: 历史对话（可选）
        
        Returns:
            消息列表
        """
        messages = [SystemMessage(content=self.system_prompt)]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append(HumanMessage(content=user_message))
        return messages

    def call_llm(
        self,
        user_message: str,
        conversation_history: Optional[list] = None,
        **kwargs: Any,
    ) -> str:
        """
        调用 LLM 并返回文本内容
        
        Args:
            user_message: 用户消息内容
            conversation_history: 历史对话
            **kwargs: 额外参数传递给 LLM
        
        Returns:
            LLM 返回的文本内容
        
        Raises:
            Exception: LLM 调用失败时抛出
        """
        messages = self._build_messages(user_message, conversation_history)

        start_time = time.time()
        try:
            logger.debug(
                f"[{self.role.value}] 调用 LLM，消息长度: {len(user_message)}"
            )
            response = self.llm.invoke(messages, **kwargs)

            # 统计 token 使用量
            self._accumulate_usage(
                getattr(response, "usage_metadata", None)
            )

            content = response.content
            duration = time.time() - start_time
            logger.info(
                f"[{self.role.value}] LLM 调用完成，耗时: {duration:.2f}s, "
                f"返回长度: {len(content)}"
            )
            return content

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"[{self.role.value}] LLM 调用失败，耗时: {duration:.2f}s, "
                f"错误: {str(e)}"
            )
            raise

    def call_llm_stream(
        self,
        user_message: str,
        conversation_history: Optional[list] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """
        流式调用 LLM，逐块返回生成的文本内容

        与 call_llm 不同，此方法在模型生成过程中就逐个返回文本增量，
        适合 Web 等需要实时展示生成过程的场景（前端逐字/逐句显示）。

        Args:
            user_message: 用户消息内容
            conversation_history: 历史对话
            **kwargs: 额外参数传递给 LLM

        Yields:
            每次生成的一小段文本（str）

        Raises:
            Exception: LLM 调用失败时抛出
        """
        messages = self._build_messages(user_message, conversation_history)

        start_time = time.time()
        try:
            logger.debug(
                f"[{self.role.value}] 流式调用 LLM，消息长度: {len(user_message)}"
            )
            for chunk in self.llm.stream(messages, **kwargs):
                # 统计 token：多数模型在最后一个 chunk 才返回 usage_metadata
                self._accumulate_usage(
                    getattr(chunk, "usage_metadata", None)
                )
                piece = chunk.content if hasattr(chunk, "content") else str(chunk)
                if piece:
                    yield piece

            duration = time.time() - start_time
            logger.info(
                f"[{self.role.value}] 流式调用完成，耗时: {duration:.2f}s"
            )
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"[{self.role.value}] 流式调用失败，耗时: {duration:.2f}s, "
                f"错误: {str(e)}"
            )
            raise

    def call_llm_with_retry(
        self,
        user_message: str,
        conversation_history: Optional[list] = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        **kwargs: Any,
    ) -> str:
        """
        带重试机制的 LLM 调用
        
        Args:
            user_message: 用户消息内容
            conversation_history: 历史对话
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            **kwargs: 额外参数
        
        Returns:
            LLM 返回的文本内容
        """
        last_exception = None
        for attempt in range(1, max_retries + 1):
            try:
                return self.call_llm(
                    user_message, conversation_history, **kwargs
                )
            except Exception as e:
                last_exception = e
                # 不可重试的错误（如 401 鉴权失败、400 参数错误）立即抛出，
                # 避免无意义的等待
                if not self._is_retryable(e):
                    logger.error(
                        f"[{self.role.value}] 不可重试错误，立即放弃: {str(e)}"
                    )
                    raise
                if attempt < max_retries:
                    logger.warning(
                        f"[{self.role.value}] 第 {attempt} 次调用失败，"
                        f"{retry_delay}s 后重试: {str(e)}"
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        f"[{self.role.value}] 已达到最大重试次数 "
                        f"{max_retries}，放弃调用"
                    )

        raise last_exception  # type: ignore

    def _accumulate_usage(self, usage: Optional[dict]) -> None:
        """
        累计一次 LLM 调用的 token 使用量

        兼容不同模型返回 usage_metadata 的时机：
        - invoke：直接在响应对象上
        - stream：通常在最后一个 chunk 上

        Args:
            usage: 模型的 usage_metadata 字典，可能为 None
        """
        if not usage:
            return
        tokens = usage.get("total_tokens", 0)
        if not tokens:
            return
        self.total_tokens_used += tokens
        logger.debug(
            f"[{self.role.value}] 本轮 token: {tokens}, "
            f"累计: {self.total_tokens_used}"
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """
        判断某个异常是否值得重试

        规则：
        - 429（限流）：可重试
        - 4xx（除 429，如 401 鉴权失败、400 参数错误）：不可重试
        - 5xx（服务端错误）：可重试
        - 无法判断时：默认可重试（保守，保持原有行为）

        Args:
            exc: 捕获到的异常

        Returns:
            是否可重试
        """
        status = getattr(exc, "status_code", None)
        if status is None:
            return True
        if status == 429:
            return True
        if 400 <= status < 500:
            return False
        return True

    def reset_token_counter(self) -> None:
        """重置 token 计数器"""
        self.total_tokens_used = 0
        logger.info(f"[{self.role.value}] Token 计数器已重置")
