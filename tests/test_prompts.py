"""
Prompt 模板单元测试
测试 prompt 构建和领域选择逻辑
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prompts import (
    get_generator_prompt,
    build_generator_user_message,
    get_critic_prompt,
    build_critic_user_message,
    GENERATOR_PROMPTS,
    CRITIC_PROMPTS,
)


class TestGeneratorPrompt:
    """Generator Prompt 测试"""

    def test_get_prompt_all_domains(self):
        """测试所有领域都能获取到 prompt"""
        for domain in ["general", "code", "writing", "design"]:
            prompt = get_generator_prompt(domain)
            assert prompt is not None
            assert len(prompt) > 0

    def test_get_prompt_unknown_domain_fallback(self):
        """测试未知领域回退到 general"""
        prompt = get_generator_prompt("unknown_domain")
        assert prompt == GENERATOR_PROMPTS["general"]

    def test_first_turn_message(self):
        """测试首次生成的用户消息"""
        msg = build_generator_user_message(
            task="写一个函数",
            is_first_turn=True,
        )
        assert "写一个函数" in msg
        assert "初始方案" in msg

    def test_iterate_message(self):
        """测试迭代生成的用户消息"""
        msg = build_generator_user_message(
            task="写一个函数",
            draft="旧版本",
            is_first_turn=False,
            score=60,
            issues="1. 问题A\n2. 问题B",
            suggestions="1. 建议A",
        )
        assert "旧版本" in msg
        assert "60" in msg
        assert "问题A" in msg
        assert "建议A" in msg


class TestCriticPrompt:
    """Critic Prompt 测试"""

    def test_get_prompt_all_domains(self):
        """测试所有领域都能获取到 prompt"""
        for domain in ["general", "code", "writing", "design"]:
            prompt = get_critic_prompt(domain)
            assert prompt is not None
            assert len(prompt) > 0

    def test_get_prompt_unknown_domain_fallback(self):
        """测试未知领域回退到 general"""
        prompt = get_critic_prompt("unknown_domain")
        assert prompt == CRITIC_PROMPTS["general"]

    def test_build_user_message(self):
        """测试构建 Critic 用户消息"""
        msg = build_critic_user_message(
            task="审查代码",
            draft="def foo(): pass",
        )
        assert "审查代码" in msg
        assert "def foo()" in msg

    def test_code_prompt_contains_code_dimensions(self):
        """测试代码领域 prompt 包含代码审查维度"""
        prompt = get_critic_prompt("code")
        assert "正确性" in prompt
        assert "性能" in prompt
        assert "安全性" in prompt

    def test_writing_prompt_contains_writing_dimensions(self):
        """测试文案领域 prompt 包含文案审查维度"""
        prompt = get_critic_prompt("writing")
        assert "逻辑" in prompt
        assert "表达" in prompt
        assert "受众" in prompt
