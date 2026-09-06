"""代码 Agent 单次运行的配置与验证结果契约。"""

from __future__ import annotations

import sys
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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

    def failure_summary(self, max_lines: int = 8, max_chars: int = 4000) -> str:
        """只提炼失败要点，供下一轮修复的 feedback 使用。

        与 evidence() 不同：丢弃成功输出与收集噪音，仅保留断言/异常/FAILED
        等关键行，避免多轮修复时失败日志线性撑爆任务文本（上下文管理的一环）。
        """
        if self.passed:
            return f"{self.label}：通过"
        lines = [f"{self.label}：失败"]
        if self.exit_code is not None:
            lines.append(f"退出码: {self.exit_code}")
        text = f"{self.stderr}\n{self.stdout}"

        def _is_key(line: str) -> bool:
            s = line.strip()
            if not s or s.startswith(("=", "-")):
                return False
            return s.startswith(
                ("FAILED", "ERROR", "assert", "E ", "Error", "Exception", "Traceback", "raise")
            ) or any(
                word in s for word in ("assert", "Error", "Exception", " failed", "FAILED")
            )

        key_lines = [line.strip() for line in text.splitlines() if _is_key(line)]
        if not key_lines:
            # 兜底：取前若干非空行
            key_lines = [
                line.strip() for line in text.splitlines() if line.strip()
            ][:max_lines]
        summary = "\n".join(key_lines[-max_lines:])
        lines.append(f"失败要点:\n{summary[:max_chars]}")
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
        """拼接失败证据，供下一轮修复使用。

        使用 failure_summary（失败要点）而非全量 stdout，控制回注文本体积。
        """
        failed = [result.failure_summary() for result in self.results if not result.passed]
        return "\n\n".join(failed) or "所有验证均通过"


class RunConfig(BaseModel):
    """编排器实例级配置，避免请求间修改全局配置。"""

    max_rounds: int = Field(default=3, ge=1, le=20)
    score_threshold: int = Field(default=85, ge=0, le=100)
    round_token_budget: int = Field(default=300000, ge=0)
    total_token_budget: int = Field(default=2000000, ge=0)
    verification_profile: VerificationProfile = "none"
    verification_steps: list[VerificationStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def migrate_windows_npm_command(self) -> "RunConfig":
        """Keep persisted tasks created before the Windows command fix runnable."""
        if sys.platform != "win32" or self.verification_profile != "node_build":
            return self
        for step in self.verification_steps:
            if step.id == "node_build" and step.args and step.args[0] == "npm":
                step.args[0] = "npm.cmd"
        return self

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
