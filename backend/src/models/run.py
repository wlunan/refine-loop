"""代码 Agent 单次运行的配置与验证结果契约。"""

from __future__ import annotations

import sys
from typing import Literal

from pydantic import BaseModel, Field


VerificationProfile = Literal["none", "python_pytest", "python_lint", "node_build"]
VerificationRequestProfile = Literal[
    "auto", "none", "python_pytest", "python_lint", "node_build"
]


class VerificationStep(BaseModel):
    """一次确定性验证的声明。"""

    id: str
    label: str
    command: str
    args: list[str] | None = None
    required: bool = True
    timeout_seconds: int = Field(default=120, ge=1, le=3600)


class VerificationResult(BaseModel):
    """一次验证执行后的可持久化结果。"""

    step_id: str
    label: str
    required: bool = True
    passed: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_seconds: float = Field(default=0.0, ge=0)

    def evidence(self) -> str:
        """返回适合回注给 Agent 的简短证据文本。"""
        lines = [f"{self.label}：{'通过' if self.passed else '失败'}"]
        if self.exit_code is not None:
            lines.append(f"退出码: {self.exit_code}")
        if self.stdout:
            lines.append(f"标准输出:\n{self.stdout}")
        if self.stderr:
            lines.append(f"标准错误:\n{self.stderr}")
        return "\n".join(lines)


class VerificationSummary(BaseModel):
    """一轮中所有验证步骤的汇总。"""

    profile: VerificationProfile = "none"
    results: list[VerificationResult] = Field(default_factory=list)

    @property
    def has_required_steps(self) -> bool:
        return any(result.required for result in self.results)

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results if result.required)

    def evidence(self) -> str:
        """拼接失败证据，供下一轮修复使用。"""
        failed = [result.evidence() for result in self.results if not result.passed]
        return "\n\n".join(failed) or "所有验证均通过"


class RunConfig(BaseModel):
    """编排器实例级配置，避免请求间修改全局配置。"""

    max_rounds: int = Field(default=3, ge=1, le=20)
    score_threshold: int = Field(default=85, ge=0, le=100)
    round_token_budget: int = Field(default=300000, ge=0)
    total_token_budget: int = Field(default=2000000, ge=0)
    verification_profile: VerificationProfile = "none"
    verification_steps: list[VerificationStep] = Field(default_factory=list)

    @classmethod
    def from_profile(
        cls,
        profile: VerificationProfile,
        *,
        max_rounds: int,
        score_threshold: int,
        round_token_budget: int,
        total_token_budget: int,
    ) -> "RunConfig":
        """按内置 profile 构建受控验证步骤。"""
        profiles: dict[VerificationProfile, list[VerificationStep]] = {
            "none": [],
            "python_pytest": [
                VerificationStep(
                    id="pytest",
                    label="pytest",
                    command=f'"{sys.executable}" -m pytest -q',
                    args=[sys.executable, "-m", "pytest", "-q"],
                )
            ],
            "python_lint": [
                VerificationStep(
                    id="ruff",
                    label="ruff",
                    command=f'"{sys.executable}" -m ruff check .',
                    args=[sys.executable, "-m", "ruff", "check", "."],
                )
            ],
            "node_build": [
                VerificationStep(
                    id="node_build",
                    label="npm run build",
                    command="npm run build",
                    # Windows resolves npm through its .cmd shim when
                    # subprocess runs without a shell.
                    args=["npm.cmd" if sys.platform == "win32" else "npm", "run", "build"],
                )
            ],
        }
        return cls(
            max_rounds=max_rounds,
            score_threshold=score_threshold,
            round_token_budget=round_token_budget,
            total_token_budget=total_token_budget,
            verification_profile=profile,
            verification_steps=profiles[profile],
        )
