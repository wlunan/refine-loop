"""Regression tests for Critic structured-output recovery."""

import os
import sys
from unittest.mock import MagicMock

from langchain_core.output_parsers import PydanticOutputParser

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from src.agents.critic import CriticAgent
from src.models.schemas import CritiqueResult


def make_critic() -> CriticAgent:
    """Build a Critic without configuration or network access."""
    critic = CriticAgent.__new__(CriticAgent)
    critic.parser = PydanticOutputParser(pydantic_object=CritiqueResult)
    return critic


def test_parse_uses_later_valid_json_object():
    """Ignore unrelated JSON before the actual Critic result."""
    critic = make_critic()
    response = (
        'debug: {"request_id": "abc"}\n'
        '{"score": 88, "issues": [], "suggestions": [], "acceptable": true}'
    )

    result = critic._try_parse_critique_response(response)

    assert result is not None
    assert result.score == 88
    assert result.acceptable is True


def test_critique_repairs_non_json_response_once():
    """A non-JSON first reply gets one bounded format-repair attempt."""
    critic = make_critic()
    critic.call_llm_with_retry = MagicMock(side_effect=[
        "score: 85\nissues: none\nsuggestion: merge it",
        '{"score": 85, "issues": [], "suggestions": [], "acceptable": true}',
    ])

    result = critic.critique("review login", "def login(): pass")

    assert result.score == 85
    assert result.acceptable is True
    assert critic.call_llm_with_retry.call_count == 2
    repair_prompt = critic.call_llm_with_retry.call_args_list[1].args[0]
    assert "only one JSON object" in repair_prompt
