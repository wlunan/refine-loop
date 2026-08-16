"""
Agent 单元测试
测试 Generator 的输出提取和 Critic 的响应解析
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

import pytest

from src.agents.critic import CriticAgent
from src.agents.generator import GeneratorAgent
from src.models.schemas import CritiqueResult


class TestGeneratorAgent:
    """GeneratorAgent 测试"""

    def test_extract_final_output_with_marker(self):
        """测试从带【最终产出】标记的回复中提取"""
        generator = GeneratorAgent.__new__(GeneratorAgent)
        response = "【修改说明】\n修复了bug\n\n【最终产出】\ndef foo():\n    return 1"

        result = generator._extract_final_output(response)
        assert "def foo()" in result
        assert "修改说明" not in result

    def test_extract_final_output_with_code_marker(self):
        """测试从带完整代码标记的回复中提取"""
        generator = GeneratorAgent.__new__(GeneratorAgent)
        response = "修改了以下内容...\n\n完整代码：\n```python\ndef foo():\n    pass\n```"

        result = generator._extract_final_output(response)
        assert "def foo()" in result
        assert "```" not in result

    def test_extract_final_output_no_marker(self):
        """测试无标记时返回完整回复"""
        generator = GeneratorAgent.__new__(GeneratorAgent)
        response = "这是完整的产出内容，没有任何标记"

        result = generator._extract_final_output(response)
        assert result == response

    def test_extract_final_output_empty(self):
        """测试空回复"""
        generator = GeneratorAgent.__new__(GeneratorAgent)
        result = generator._extract_final_output("")
        assert result == ""


class TestCriticAgent:
    """CriticAgent 测试"""

    def test_extract_json_from_code_block(self):
        """测试从 ```json 代码块中提取 JSON"""
        critic = CriticAgent.__new__(CriticAgent)
        text = '这里是说明文字\n```json\n{"score": 85, "issues": [], "suggestions": [], "acceptable": true}\n```'

        json_str = critic._extract_json(text)
        assert '"score"' in json_str
        assert "85" in json_str

    def test_extract_json_from_braces(self):
        """测试从花括号中提取 JSON"""
        critic = CriticAgent.__new__(CriticAgent)
        text = '结果如下：{"score": 90, "issues": [], "suggestions": [], "acceptable": true}'

        json_str = critic._extract_json(text)
        assert json_str.startswith("{")
        assert json_str.endswith("}")

    def test_extract_json_none(self):
        """测试无 JSON 时返回 None"""
        critic = CriticAgent.__new__(CriticAgent)
        text = "这段文字中没有 JSON"

        result = critic._extract_json(text)
        assert result is None

    def test_parse_valid_json_response(self):
        """测试解析合法的 JSON 回复"""
        critic = CriticAgent.__new__(CriticAgent)
        response = '{"score": 85, "issues": ["问题1"], "suggestions": ["建议1"], "acceptable": true}'

        result = critic._parse_critique_response(response)
        assert isinstance(result, CritiqueResult)
        assert result.score == 85
        assert len(result.issues) == 1
        assert result.acceptable is True

    def test_parse_invalid_response_fallback(self):
        """测试解析失败时的降级处理"""
        critic = CriticAgent.__new__(CriticAgent)
        response = "这不是合法的 JSON，也没有花括号"

        result = critic._parse_critique_response(response)
        assert isinstance(result, CritiqueResult)
        assert result.score == 50  # 降级默认分数
        assert result.acceptable is False
        assert len(result.issues) > 0

    def test_parse_json_with_extra_text(self):
        """测试解析前后有额外文字的 JSON"""
        critic = CriticAgent.__new__(CriticAgent)
        response = '好的，这是我的审查结果：\n{"score": 70, "issues": ["bug"], "suggestions": ["fix"], "acceptable": false}\n希望对你有帮助'

        result = critic._parse_critique_response(response)
        assert result.score == 70
        assert len(result.issues) == 1
