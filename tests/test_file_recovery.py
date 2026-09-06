"""FileWorkspace 幂等恢复判定测试。"""

from __future__ import annotations

import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"),
)

from src.tools.filesystem import FileWorkspace


def test_write_file_recovery_states(tmp_path):
    workspace = FileWorkspace(str(tmp_path))
    target = "app.py"

    # 文件不存在 → 可以重放
    assert workspace.write_file_recovery(target, "value = 2\n") == "replay"

    # 文件已写入目标内容 → 已完成
    workspace.write_file(target, "value = 2\n")
    assert workspace.write_file_recovery(target, "value = 2\n") == "completed"

    # 文件内容与目标、旧状态都不匹配 → 冲突
    workspace.write_file(target, "value = 999\n")
    assert workspace.write_file_recovery(target, "value = 2\n") == "conflict"


def test_edit_file_recovery_states(tmp_path):
    workspace = FileWorkspace(str(tmp_path))
    workspace.write_file("app.py", "value = 1\n")

    # 旧文本唯一存在 → 可以重放
    assert workspace.edit_file_recovery("app.py", "value = 1", "value = 2") == "replay"

    # 新文本已存在 → 已完成
    workspace.write_file("app.py", "value = 2\n")
    assert workspace.edit_file_recovery("app.py", "value = 1", "value = 2") == "completed"

    # 旧文本不存在且新文本不存在 → 冲突
    workspace.write_file("app.py", "value = 999\n")
    assert workspace.edit_file_recovery("app.py", "value = 1", "value = 2") == "conflict"


def test_delete_file_recovery_states(tmp_path):
    workspace = FileWorkspace(str(tmp_path))
    workspace.write_file("app.py", "value = 1\n")

    # 文件仍存在 → 可以重放
    assert workspace.delete_file_recovery("app.py") == "replay"

    # 文件已不存在 → 已完成
    workspace.delete_file("app.py")
    assert workspace.delete_file_recovery("app.py") == "completed"
