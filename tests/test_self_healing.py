"""
代码自愈闭环（Self-Healing）单元测试

使用 Mock Generator + 可控验证命令，离线测试闭环逻辑：
成功收敛、达到上限、失败日志反馈注入。
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"
    ),
)

from src.orchestrator.self_healing import SelfHealingOrchestrator


def make_mock_generator():
    """创建一个 mock Generator，不真正调用 LLM"""
    gen = MagicMock()
    gen.generate_with_files = MagicMock(return_value="done")
    return gen


def _write_script(directory: str, name: str, content: str) -> str:
    """在目录下写一个脚本文件，返回其绝对路径"""
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestSelfHealing:
    def test_success_on_first_round(self):
        d = tempfile.mkdtemp()
        gen = make_mock_generator()
        orch = SelfHealingOrchestrator(
            generator=gen,
            workspace_dir=d,
            verify_command=f'"{sys.executable}" --version',  # 总是成功
            max_repair_rounds=3,
        )
        result = orch.run("实现一个函数")
        assert result.success is True
        assert result.repair_rounds == 1
        assert gen.generate_with_files.call_count == 1

    def test_fail_all_rounds(self):
        d = tempfile.mkdtemp()
        fail_script = _write_script(d, "verify_fail.py", "import sys\nsys.exit(1)\n")
        gen = make_mock_generator()
        orch = SelfHealingOrchestrator(
            generator=gen,
            workspace_dir=d,
            verify_command=f'"{sys.executable}" "{fail_script}"',  # 总是失败
            max_repair_rounds=3,
        )
        result = orch.run("写一个 LRU 缓存")
        assert result.success is False
        assert result.repair_rounds == 3
        assert gen.generate_with_files.call_count == 3

    def test_feedback_contains_failure_log(self):
        d = tempfile.mkdtemp()
        fail_script = _write_script(
            d, "verify_fail.py", "import sys\nprint('boom')\nsys.exit(1)\n"
        )
        gen = make_mock_generator()
        orch = SelfHealingOrchestrator(
            generator=gen,
            workspace_dir=d,
            verify_command=f'"{sys.executable}" "{fail_script}"',
            max_repair_rounds=2,
        )
        orch.run("写一个 LRU 缓存")
        # 第二轮（修复轮）的 task 应包含失败反馈与失败日志
        second_task = gen.generate_with_files.call_args_list[1].kwargs["task"]
        assert "验证未通过" in second_task
        assert "boom" in second_task

    def test_workspace_created_if_missing(self):
        base = tempfile.mkdtemp()
        workspace = os.path.join(base, "not_exists_yet")
        gen = make_mock_generator()
        orch = SelfHealingOrchestrator(
            generator=gen,
            workspace_dir=workspace,
            verify_command=f'"{sys.executable}" --version',
            max_repair_rounds=1,
        )
        orch.run("任务")
        assert os.path.isdir(workspace)
