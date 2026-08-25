"""
混合模式工具调用执行器（Tool Agent Loop）

把「LLM + 工具集」组合成一个可以自主决策、执行工具、观察结果、
反复迭代直到给出最终答案的 agent 循环。

混合模式策略：
1. 优先使用原生 Function Calling（llm.bind_tools），最可靠；
2. 若模型不支持原生 tool call（调用抛异常），自动永久降级到
   「JSON 命令文本协议」：在 prompt 中注入工具清单，要求模型输出
   形如 {"tool": "...", "arguments": {...}} 的 JSON 命令，解析后执行；
3. 即使原生调用成功，若模型返回空 tool_calls 且内容是 JSON 命令，
   也会按文本协议兜底解析（兼容"忽略 tools 参数"的模型）。

本模块独立于 BaseAgent，接收外部 LLM 与工具，便于测试与复用。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# 工具调用事件回调签名：on_event(dict) -> None
EventCallback = Callable[[Dict[str, Any]], None]


class ToolAgent:
    """
    混合模式工具调用 agent 循环

    Args:
        llm: 底层语言模型
        tools: LangChain StructuredTool 列表
        system_prompt: 系统提示词（不含工具清单，清单由本类按需注入）
        on_event: 可选事件回调，用于推送工具调用/结果等过程信息
        max_steps: 最大工具调用步数，防止死循环
        usage_callback: 可选，每次 LLM 调用后回调 usage_metadata 用于累计 token
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list,
        system_prompt: str,
        on_event: Optional[EventCallback] = None,
        max_steps: int = 20,
        usage_callback: Optional[Callable[[Optional[dict]], None]] = None,
    ):
        self.llm = llm
        self.tools = tools
        self.tool_map: Dict[str, Any] = {t.name: t for t in tools}
        self.system_prompt = system_prompt
        self.on_event = on_event
        self.max_steps = max_steps
        self.usage_callback = usage_callback

        # 原生 tool call 是否已确认失败（失败后永久走文本协议）
        self._native_failed = False

    # ------------------------------------------------------------------
    # 事件推送
    # ------------------------------------------------------------------
    def _emit(self, event: Dict[str, Any]) -> None:
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"工具事件回调失败: {e}")

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def run(
        self,
        user_message: str,
        conversation_history: Optional[list] = None,
    ) -> str:
        """
        执行工具调用循环，返回最终答案文本

        Args:
            user_message: 用户消息
            conversation_history: 可选历史消息

        Returns:
            最终答案文本
        """
        messages: list = [SystemMessage(content=self.system_prompt)]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append(HumanMessage(content=user_message))

        for step in range(self.max_steps):
            response = self._invoke_once(messages)

            # 累计 token
            if self.usage_callback:
                self.usage_callback(getattr(response, "usage_metadata", None))

            tool_calls = getattr(response, "tool_calls", None) or []
            content = (response.content or "").strip()

            # 1) 原生 tool call 命中
            if tool_calls:
                self._execute_native_tool_calls(messages, response, tool_calls)
                continue

            # 2) 无 tool call：尝试把 content 解析为 JSON 文本命令
            command = self._try_parse_command(content)
            if command is not None:
                observation = self._execute_command(command)
                messages.append(AIMessage(content=json.dumps(observation, ensure_ascii=False)))
                continue

            # 3) 纯文本：视为最终答案
            return content or "（Agent 未返回内容）"

        # 达到最大步数仍未收敛：返回最后一步的文本作为兜底
        logger.warning(f"达到最大工具调用步数 {self.max_steps}，强制结束")
        return content if "content" in dir() and content else "（达到最大操作步数，任务未完成）"

    # ------------------------------------------------------------------
    # LLM 调用（原生 / 文本协议）
    # ------------------------------------------------------------------
    def _invoke_once(self, messages: list):
        """调用一次 LLM，按需走原生或文本协议"""
        if not self._native_failed:
            try:
                llm_with_tools = self.llm.bind_tools(self.tools)
                return llm_with_tools.invoke(messages)
            except Exception as e:  # noqa: BLE001
                # 原生 tool call 失败（模型不支持 tools 参数等），永久降级
                self._native_failed = True
                logger.warning(
                    f"原生 Function Calling 不可用，降级为 JSON 文本协议: {e}"
                )

        # 文本协议：注入工具清单
        text_messages = [self._build_text_system_message()] + messages[1:]
        return self.llm.invoke(text_messages)

    def _build_text_system_message(self) -> SystemMessage:
        """构建带工具清单与命令格式说明的 system 消息（文本协议用）"""
        manifest = self._tool_manifest_text()
        prompt = (
            f"{self.system_prompt}\n\n"
            "【可用工具】你只能通过以下工具操作文件系统：\n"
            f"{manifest}\n\n"
            "【操作规则】\n"
            "1. 当你需要读写文件时，必须只输出一个 JSON 命令，格式：\n"
            '   {"tool": "<工具名>", "arguments": {<参数>}}\n'
            "2. 每次只输出一个命令，我会执行它并把结果返回给你；\n"
            "3. 当所有文件操作完成后，直接输出最终总结文本（不要再输出 JSON）；\n"
            "4. 所有路径都是相对工作区根目录的路径。"
        )
        return SystemMessage(content=prompt)

    def _tool_manifest_text(self) -> str:
        """生成工具清单文本"""
        lines = []
        for t in self.tools:
            args_desc = ""
            try:
                if t.args and hasattr(t.args, "model_fields"):
                    fields = []
                    for name, f in t.args.model_fields.items():
                        req = "" if f.is_required() else "?"
                        fields.append(f"{name}{req}: {f.annotation.__name__ if hasattr(f.annotation, '__name__') else str(f.annotation)}")
                    args_desc = "{" + ", ".join(fields) + "}"
            except Exception:  # noqa: BLE001
                args_desc = ""
            lines.append(f"- {t.name}{args_desc}: {t.description}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------
    def _execute_native_tool_calls(
        self, messages: list, response: AIMessage, tool_calls: list
    ) -> None:
        """执行原生 tool_calls 并把结果追加回消息列表"""
        messages.append(response)
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {}) or {}
            self._emit({"type": "tool_call", "tool": name, "arguments": args})

            observation = self._run_tool(name, args)
            self._emit({"type": "tool_result", "tool": name, "result": observation})

            # 追加 ToolMessage
            try:
                from langchain_core.messages import ToolMessage

                messages.append(
                    ToolMessage(content=observation, tool_call_id=tc.get("id", ""))
                )
            except ImportError:  # 极端兜底：用 HumanMessage
                messages.append(HumanMessage(content=f"工具 {name} 结果：\n{observation}"))

    def _execute_command(self, command: dict) -> str:
        """执行 JSON 文本协议命令，返回观察结果"""
        name = command.get("tool", "")
        args = command.get("arguments", {}) or {}
        self._emit({"type": "tool_call", "tool": name, "arguments": args})
        observation = self._run_tool(name, args)
        self._emit({"type": "tool_result", "tool": name, "result": observation})
        return f"工具 {name} 执行结果：\n{observation}"

    def _run_tool(self, name: str, args: dict) -> str:
        """执行单个工具，返回结果文本（出错时返回错误文本，不中断循环）"""
        tool = self.tool_map.get(name)
        if tool is None:
            return f"错误：未知工具 {name}，可用工具：{', '.join(self.tool_map.keys())}"
        try:
            result = tool.invoke(args)
            return str(result)
        except Exception as e:  # noqa: BLE001
            return f"错误：工具 {name} 执行失败：{e}"

    # ------------------------------------------------------------------
    # JSON 命令解析（文本协议 / 兜底）
    # ------------------------------------------------------------------
    @staticmethod
    def _try_parse_command(text: str) -> Optional[dict]:
        """
        尝试把文本解析为工具命令 JSON

        支持：```json ... ``` 代码块、裸 JSON 对象。
        仅当解析结果含 "tool" 字段时视为命令，否则返回 None。
        """
        if not text:
            return None

        # 提取 ```json ... ``` 代码块
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        candidate = m.group(1).strip() if m else text.strip()

        # 尝试整体解析
        try:
            data = json.loads(candidate)
        except Exception:  # noqa: BLE001
            # 尝试提取首个 {...}
            m2 = re.search(r"\{.*\}", candidate, re.DOTALL)
            if not m2:
                return None
            try:
                data = json.loads(m2.group(0))
            except Exception:  # noqa: BLE001
                return None

        if isinstance(data, dict) and "tool" in data:
            return data
        return None
