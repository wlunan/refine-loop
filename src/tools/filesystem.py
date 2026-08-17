"""
文件系统工具集（带安全沙箱）

为 Generator Agent 提供在用户选定项目文件夹内操作文件的能力，
支持创建 / 读取 / 修改 / 删除 / 搜索文件。

安全设计：
- 所有路径都相对 FileWorkspace 根目录解析，并通过 _resolve_safe 校验，
  禁止通过 ../ 或绝对路径逃逸出根目录（目录穿越防护）。
- read_file 限制单次读取大小，避免超大文件撑爆上下文。
- 提供 build_file_tools 生成 LangChain StructuredTool 列表，供原生
  tool calling 使用；同名文本描述用于 JSON 文本协议降级。
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import List, Optional

from langchain_core.tools import tool

# 单次读取文件的最大字符数（超出则截断并提示）
MAX_READ_CHARS = 100_000

# 默认忽略的目录（保护敏感目录，避免误操作）
PROTECTED_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__"}


class FileWorkspaceError(Exception):
    """文件操作错误（含路径越界、文件不存在等）"""
    pass


@dataclass
class FileWorkspace:
    """
    文件沙箱：把 Agent 的所有文件操作限制在指定根目录内

    Args:
        root: 工作区根目录（绝对路径）
    """

    root: str
    # 操作日志：记录每次写/删操作，便于审计与回滚展示
    _operations: List[dict] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        root = os.path.abspath(os.path.expanduser(self.root))
        if not os.path.isdir(root):
            raise FileWorkspaceError(f"工作区目录不存在: {root}")
        self.root = root
        self._operations = []

    # ------------------------------------------------------------------
    # 路径安全
    # ------------------------------------------------------------------
    def _resolve_safe(self, path: str) -> str:
        """
        把相对路径解析为绝对路径，并确保其位于根目录内

        Args:
            path: 相对或绝对路径

        Returns:
            位于根目录内的绝对路径

        Raises:
            FileWorkspaceError: 路径越界或非法
        """
        if not path or path.strip() == "":
            raise FileWorkspaceError("路径不能为空")

        # 绝对路径：直接解析后校验是否在根目录内
        candidate = os.path.abspath(os.path.join(self.root, path))

        root_norm = os.path.normcase(self.root)
        cand_norm = os.path.normcase(candidate)

        # 必须等于根目录，或以根目录 + 分隔符开头（避免 /root_evil 被误判）
        if cand_norm != root_norm and not cand_norm.startswith(root_norm + os.sep):
            raise FileWorkspaceError(
                f"路径越界，禁止访问工作区之外的位置: {path}"
            )
        return candidate

    def _rel(self, path: str) -> str:
        """返回相对根目录的路径（用于日志与展示）"""
        return os.path.relpath(path, self.root)

    # ------------------------------------------------------------------
    # 文件操作（供工具调用）
    # ------------------------------------------------------------------
    def list_directory(self, path: str = ".") -> str:
        """列出目录内容"""
        target = self._resolve_safe(path)
        if not os.path.isdir(target):
            raise FileWorkspaceError(f"不是目录: {path}")

        entries = []
        for name in sorted(os.listdir(target)):
            full = os.path.join(target, name)
            rel = os.path.relpath(full, self.root)
            if os.path.isdir(full):
                entries.append(f"[目录] {rel}/")
            else:
                try:
                    size = os.path.getsize(full)
                    entries.append(f"[文件] {rel}  ({size} 字节)")
                except OSError:
                    entries.append(f"[文件] {rel}")

        if not entries:
            return f"目录为空: {self._rel(target) or '.'}"
        header = f"目录 {self._rel(target) or '.'} 共 {len(entries)} 项：\n"
        return header + "\n".join(entries)

    def read_file(self, path: str) -> str:
        """读取文件内容（文本）"""
        target = self._resolve_safe(path)
        if not os.path.isfile(target):
            raise FileWorkspaceError(f"文件不存在: {path}")

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            raise FileWorkspaceError(f"读取失败: {path}，{e}")

        if len(content) > MAX_READ_CHARS:
            truncated = content[:MAX_READ_CHARS]
            return (
                f"（文件过大，已截断，仅显示前 {MAX_READ_CHARS} 字符）\n"
                f"{truncated}\n... [已截断，总长度 {len(content)} 字符]"
            )
        return content

    def write_file(self, path: str, content: str) -> str:
        """创建或覆盖写入文件（自动创建父目录）"""
        target = self._resolve_safe(path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            raise FileWorkspaceError(f"写入失败: {path}，{e}")

        self._operations.append({"op": "write", "path": self._rel(target)})
        return f"已写入文件: {self._rel(target)}（{len(content)} 字符）"

    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        """
        精准替换：将文件中首次出现的 old_text 替换为 new_text

        old_text 必须唯一匹配，否则报错（避免误改）。
        """
        target = self._resolve_safe(path)
        if not os.path.isfile(target):
            raise FileWorkspaceError(f"文件不存在: {path}")

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            raise FileWorkspaceError(f"读取失败: {path}，{e}")

        count = content.count(old_text)
        if count == 0:
            raise FileWorkspaceError(
                f"未找到要替换的内容（old_text 不存在）: {old_text[:60]}"
            )
        if count > 1:
            raise FileWorkspaceError(
                f"old_text 出现 {count} 次，不够唯一，请提供更长的上下文使其唯一"
            )

        new_content = content.replace(old_text, new_text, 1)
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(new_content)
        except OSError as e:
            raise FileWorkspaceError(f"写入失败: {path}，{e}")

        self._operations.append({"op": "edit", "path": self._rel(target)})
        return f"已修改文件: {self._rel(target)}"

    def delete_file(self, path: str) -> str:
        """删除文件（仅允许删除文件，禁止删除目录）"""
        target = self._resolve_safe(path)

        # 保护敏感目录
        for part in self._rel(target).split(os.sep):
            if part in PROTECTED_DIRS:
                raise FileWorkspaceError(f"禁止删除受保护目录下的内容: {part}")

        if not os.path.exists(target):
            raise FileWorkspaceError(f"路径不存在: {path}")
        if os.path.isdir(target):
            raise FileWorkspaceError(f"禁止删除目录（仅支持删除文件）: {path}")

        try:
            os.remove(target)
        except OSError as e:
            raise FileWorkspaceError(f"删除失败: {path}，{e}")

        self._operations.append({"op": "delete", "path": self._rel(target)})
        return f"已删除文件: {self._rel(target)}"

    def search_files(self, pattern: str, path: str = ".") -> str:
        """按文件名通配符搜索（如 *.py、test_*）"""
        target = self._resolve_safe(path)
        pattern = os.path.basename(pattern)  # 仅允许文件名匹配，防路径注入

        matches = []
        for dirpath, dirnames, filenames in os.walk(target):
            # 跳过受保护目录
            dirnames[:] = [d for d in dirnames if d not in PROTECTED_DIRS]
            for name in filenames:
                if glob.fnmatch.fnmatch(name, pattern):
                    full = os.path.join(dirpath, name)
                    matches.append(os.path.relpath(full, self.root))

        if not matches:
            return f"未找到匹配 {pattern} 的文件"
        return f"匹配 {pattern} 的文件（{len(matches)} 个）：\n" + "\n".join(matches)

    # ------------------------------------------------------------------
    # 快照：把工作区内容打包成文本（供 Critic 审查）
    # ------------------------------------------------------------------
    def snapshot(self, path: str = ".", max_files: int = 50) -> str:
        """
        将工作区（或子目录）的文本文件内容打包成一段文本，
        用于交给 Critic 审查真实落盘的文件。

        Args:
            path: 相对根目录的路径，默认整个工作区
            max_files: 最多纳入快照的文件数

        Returns:
            形如 "== 文件: xxx ==\\n内容\\n..." 的文本
        """
        target = self._resolve_safe(path)
        parts: List[str] = []
        count = 0

        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [d for d in dirnames if d not in PROTECTED_DIRS]
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self.root)
                # 跳过二进制/超大文件
                if os.path.getsize(full) > MAX_READ_CHARS * 2:
                    continue
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except OSError:
                    continue
                parts.append(f"===== 文件: {rel} =====\n{content}\n")
                count += 1
                if count >= max_files:
                    parts.append(f"... [已达 {max_files} 个文件上限，其余省略]")
                    return "\n".join(parts)

        if not parts:
            return "（工作区为空，尚无文件）"
        return "\n".join(parts)


def build_file_tools(workspace: FileWorkspace) -> list:
    """
    基于一个 FileWorkspace 实例生成 LangChain 工具列表

    这些工具既可用于原生 tool calling（llm.bind_tools），
    也可通过 name 手动分派（JSON 文本协议降级）。

    Args:
        workspace: 文件沙箱实例

    Returns:
        LangChain StructuredTool 列表
    """

    @tool
    def list_directory(path: str = ".") -> str:
        """列出工作区内某个目录的内容（文件与子目录）。path 为相对工作区根目录的路径，如 "." 表示根目录。"""
        return workspace.list_directory(path)

    @tool
    def read_file(path: str) -> str:
        """读取工作区内某个文本文件的内容。path 为相对工作区根目录的路径。"""
        return workspace.read_file(path)

    @tool
    def write_file(path: str, content: str) -> str:
        """创建或覆盖写入一个文件。path 为相对路径（可含子目录，会自动创建），content 为完整文件内容。"""
        return workspace.write_file(path, content)

    @tool
    def edit_file(path: str, old_text: str, new_text: str) -> str:
        """精准修改文件：把文件中唯一出现的 old_text 替换为 new_text。old_text 必须唯一，否则会报错。"""
        return workspace.edit_file(path, old_text, new_text)

    @tool
    def delete_file(path: str) -> str:
        """删除工作区内的一个文件（只能删除文件，不能删除目录）。path 为相对路径。"""
        return workspace.delete_file(path)

    @tool
    def search_files(pattern: str, path: str = ".") -> str:
        """按文件名通配符搜索文件（如 *.py、test_*）。pattern 为文件名匹配模式，path 为搜索起点目录。"""
        return workspace.search_files(pattern, path)

    return [
        list_directory,
        read_file,
        write_file,
        edit_file,
        delete_file,
        search_files,
    ]
