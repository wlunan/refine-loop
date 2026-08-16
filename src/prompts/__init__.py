"""Prompt 模板模块"""
from .generator_prompt import (
    get_generator_prompt,
    build_generator_user_message,
    GENERATOR_PROMPTS,
)
from .critic_prompt import (
    get_critic_prompt,
    build_critic_user_message,
    CRITIC_PROMPTS,
)

__all__ = [
    "get_generator_prompt",
    "build_generator_user_message",
    "GENERATOR_PROMPTS",
    "get_critic_prompt",
    "build_critic_user_message",
    "CRITIC_PROMPTS",
]
