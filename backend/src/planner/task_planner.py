"""
任务分解器
使用 LLM 分析用户需求，生成结构化的执行计划
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.models.task import SubTask, TaskPlan, TaskStatus
from src.tools.filesystem import FileWorkspace

logger = logging.getLogger(__name__)

# 任务分解系统提示词
PLANNER_SYSTEM_PROMPT = """你是一个资深的软件项目规划师，擅长将复杂的开发需求分解为可执行的子任务。

你的职责：
1. 分析用户的开发需求
2. 结合工作区现有代码结构
3. 生成结构化的执行计划

分解原则：
- 每个子任务应该是**原子的**，可以独立完成
- 子任务之间通过**依赖关系**组织执行顺序
- 每个子任务的描述应该**具体明确**，包含：
  - 要做什么
  - 在哪个文件/目录
  - 预期产出是什么
- 合理控制子任务数量（建议 3-10 个）

输出格式（严格 JSON）：
{
  "analysis": "对需求的简要分析",
  "subtasks": [
    {
      "id": "task_1",
      "title": "任务标题",
      "description": "详细描述，包含具体要做的事情",
      "dependencies": []
    },
    {
      "id": "task_2",
      "title": "任务标题",
      "description": "详细描述",
      "dependencies": ["task_1"]
    }
  ]
}

注意：
- id 格式为 task_N，从 1 开始递增
- dependencies 是前置任务的 id 列表
- 第一个任务通常没有依赖
- 输出必须是合法的 JSON，不要包含其他内容"""


class TaskPlanner:
    """
    任务分解器
    
    使用 LLM 分析用户需求，生成结构化的执行计划
    """
    
    def __init__(
        self,
        llm: BaseChatModel,
        workspace: Optional[FileWorkspace] = None,
        max_subtasks: int = 10,
    ):
        """
        初始化分解器
        
        Args:
            llm: 语言模型
            workspace: 文件工作区（用于分析现有代码）
            max_subtasks: 最大子任务数
        """
        self.llm = llm
        self.workspace = workspace
        self.max_subtasks = max_subtasks
    
    def plan(self, requirement: str) -> TaskPlan:
        """
        分析需求并生成执行计划
        
        Args:
            requirement: 用户需求描述
            
        Returns:
            TaskPlan: 执行计划
        """
        logger.info(f"开始分析需求: {requirement[:50]}...")
        
        # 1. 收集工作区上下文
        workspace_context = self._get_workspace_context()
        
        # 2. 构建提示词
        user_message = self._build_user_message(requirement, workspace_context)
        
        # 3. 调用 LLM
        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]
        
        try:
            response = self.llm.invoke(messages)
            result = self._parse_response(response.content)
        except Exception as e:
            logger.error(f"任务分解失败: {e}")
            # 降级：创建单个任务
            result = self._fallback_plan(requirement)
        
        # 4. 构建 TaskPlan
        plan = TaskPlan(
            requirement=requirement,
            analysis=result.get("analysis", ""),
            subtasks=self._build_subtasks(result.get("subtasks", [])),
        )
        
        logger.info(f"任务分解完成: {len(plan.subtasks)} 个子任务")
        return plan
    
    def _get_workspace_context(self) -> str:
        """获取工作区上下文信息"""
        if not self.workspace:
            return "（无工作区信息）"
        
        try:
            # 列出根目录结构
            root_listing = self.workspace.list_directory(".")
            
            # 尝试读取关键文件
            context_parts = [f"工作区目录结构：\n{root_listing}"]
            
            # 读取 README（如果存在）
            try:
                readme = self.workspace.read_file("README.md")
                if len(readme) > 2000:
                    readme = readme[:2000] + "\n... (已截断)"
                context_parts.append(f"\nREADME.md:\n{readme}")
            except Exception:
                pass
            
            return "\n".join(context_parts)
        except Exception as e:
            logger.warning(f"获取工作区上下文失败: {e}")
            return "（无法读取工作区）"
    
    def _build_user_message(
        self,
        requirement: str,
        workspace_context: str
    ) -> str:
        """构建用户消息"""
        return f"""请将以下开发需求分解为可执行的子任务。

## 需求描述
{requirement}

## 工作区信息
{workspace_context}

## 要求
1. 分析需求，确定需要完成的工作
2. 结合工作区现有结构，合理规划子任务
3. 输出严格的 JSON 格式

请输出执行计划（JSON）："""
    
    def _parse_response(self, content: str) -> dict:
        """解析 LLM 响应"""
        # 尝试提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # 尝试解析代码块中的 JSON
        code_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass
        
        logger.warning("无法解析 LLM 响应为 JSON，使用降级方案")
        return {}
    
    def _build_subtasks(self, raw_subtasks: list) -> list[SubTask]:
        """构建子任务列表"""
        subtasks = []
        
        for i, raw in enumerate(raw_subtasks[:self.max_subtasks]):
            try:
                subtask = SubTask(
                    id=raw.get("id", f"task_{i+1}"),
                    title=raw.get("title", f"子任务 {i+1}"),
                    description=raw.get("description", ""),
                    dependencies=raw.get("dependencies", []),
                    status=TaskStatus.PENDING,
                )
                subtasks.append(subtask)
            except Exception as e:
                logger.warning(f"跳过无效子任务: {raw}, {e}")
        
        return subtasks
    
    def _fallback_plan(self, requirement: str) -> dict:
        """降级方案：创建单个任务"""
        return {
            "analysis": "需求分析失败，将作为单个任务执行",
            "subtasks": [
                {
                    "id": "task_1",
                    "title": "完成需求",
                    "description": requirement,
                    "dependencies": [],
                }
            ],
        }
