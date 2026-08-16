"""
配置管理模块
统一管理系统配置，支持环境变量覆盖
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

# 加载 .env 文件
# override=True 确保 .env 中的配置优先于系统环境变量，
# 避免系统里残留的旧 OPENAI_API_KEY 覆盖 .env 中的有效 Key
load_dotenv(override=True)


@dataclass
class LLMConfig:
    """LLM 模型配置"""
    # Generator 使用的模型（建议用较强模型）
    generator_model: str = field(
        default_factory=lambda: os.getenv("GENERATOR_MODEL", "gpt-4o")
    )
    # Critic 使用的模型（可用稍弱模型降低成本）
    critic_model: str = field(
        default_factory=lambda: os.getenv("CRITIC_MODEL", "gpt-4o-mini")
    )
    # API 基础地址（支持兼容 OpenAI 协议的其他模型）
    api_base: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENAI_API_BASE")
    )
    # API Key
    api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    # Generator 温度（较高以激发创意）
    generator_temperature: float = 0.7
    # Critic 温度（较低以保证审查稳定性）
    critic_temperature: float = 0.1
    # 最大 token 数
    max_tokens: int = 4096
    # 超时时间（秒）
    request_timeout: int = 120


@dataclass
class OrchestratorConfig:
    """编排器配置"""
    # 默认最大迭代轮数
    default_max_rounds: int = 5
    # 收敛评分阈值
    convergence_score_threshold: int = 85
    # 连续无新反馈轮数阈值
    no_progress_rounds: int = 2
    # 单轮最大 token 预算
    round_token_budget: int = 8000
    # 总 token 预算
    total_token_budget: int = 50000


@dataclass
class SystemConfig:
    """系统总配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    # 日志级别
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )
    # 是否开启调试模式（打印每轮详细信息）
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )

    def validate(self) -> None:
        """校验配置合法性"""
        if not self.llm.api_key:
            raise ValueError(
                "未配置 OPENAI_API_KEY，请设置环境变量或在 .env 文件中配置"
            )
        if self.orchestrator.default_max_rounds < 1:
            raise ValueError("default_max_rounds 必须 >= 1")
        if not (0 <= self.orchestrator.convergence_score_threshold <= 100):
            raise ValueError("convergence_score_threshold 必须在 0-100 之间")


# 全局配置单例
_config: Optional[SystemConfig] = None


def get_config() -> SystemConfig:
    """获取全局配置单例"""
    global _config
    if _config is None:
        _config = SystemConfig()
    return _config


def reload_config() -> SystemConfig:
    """重新加载配置（修改环境变量后调用）"""
    global _config
    load_dotenv(override=True)
    _config = SystemConfig()
    return _config
