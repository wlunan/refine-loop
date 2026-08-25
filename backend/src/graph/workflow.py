"""
LangGraph 工作流模块
提供基于图状态机的 Generator-Critic 迭代流程实现
与 Orchestrator 的命令式实现互为补充
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.critic import CriticAgent
from src.agents.generator import GeneratorAgent
from src.convergence import evaluate_convergence
from src.models.schemas import CritiqueResult, IterationRecord

logger = logging.getLogger(__name__)


class GraphState(TypedDict, total=False):
    """
    LangGraph 中的共享状态类型
    使用 TypedDict 以兼容 LangGraph 的状态更新机制
    """
    task: str
    domain: str
    draft: str
    critique: CritiqueResult
    current_round: int
    max_rounds: int
    history: List[IterationRecord]
    converged: bool
    convergence_reason: str
    score_threshold: int
    no_progress_rounds: int


class GeneratorCriticGraph:
    """
    基于 LangGraph 的 Generator-Critic 工作流
    
    图结构：
    generate → critique → (条件判断) → generate / END
    
    使用场景：
    - 需要可视化工作流时
    - 需要与其他 LangGraph 节点组合时
    - 需要更灵活的状态管理时
    """

    def __init__(
        self,
        domain: str = "general",
        max_rounds: int = 5,
        score_threshold: int = 85,
        no_progress_rounds: int = 2,
        generator: Optional[GeneratorAgent] = None,
        critic: Optional[CriticAgent] = None,
    ):
        """
        初始化工作流
        
        Args:
            domain: 任务领域
            max_rounds: 最大迭代轮数
            score_threshold: 收敛评分阈值
            no_progress_rounds: 无新反馈收敛轮数
            generator: 外部注入的 Generator
            critic: 外部注入的 Critic
        """
        self.domain = domain
        self.max_rounds = max_rounds
        self.score_threshold = score_threshold
        self.no_progress_rounds = no_progress_rounds

        self.generator = generator or GeneratorAgent(domain=domain)
        self.critic = critic or CriticAgent(domain=domain)

        # 构建图
        self.workflow = self._build_graph()
        self.app = self.workflow.compile()

        logger.info(
            f"GeneratorCriticGraph 初始化完成: domain={domain}, "
            f"max_rounds={max_rounds}"
        )

    def _build_graph(self) -> StateGraph:
        """
        构建 LangGraph 状态图
        
        Returns:
            编译前的 StateGraph
        """
        workflow = StateGraph(GraphState)

        # 添加节点
        workflow.add_node("generate", self._generate_node)
        workflow.add_node("critique", self._critique_node)

        # 设置入口
        workflow.set_entry_point("generate")

        # 生成后进入审查
        workflow.add_edge("generate", "critique")

        # 审查后条件判断：继续生成 or 结束
        workflow.add_conditional_edges(
            "critique",
            self._should_continue,
            {
                "continue": "generate",
                "end": END,
            },
        )

        return workflow

    def _generate_node(self, state: GraphState) -> GraphState:
        """
        Generator 节点：生成或修改产出
        
        Args:
            state: 当前图状态
        
        Returns:
            更新后的状态
        """
        task = state["task"]
        draft = state.get("draft", "")
        critique = state.get("critique")
        current_round = state.get("current_round", 0)

        logger.info(f"[Graph] 生成节点执行，第 {current_round + 1} 轮")

        new_draft = self.generator.generate(
            task=task,
            draft=draft,
            critique=critique,
        )

        return {
            "draft": new_draft,
            "current_round": current_round + 1,
        }

    def _critique_node(self, state: GraphState) -> GraphState:
        """
        Critic 节点：审查产出
        
        Args:
            state: 当前图状态
        
        Returns:
            更新后的状态
        """
        task = state["task"]
        draft = state["draft"]
        current_round = state["current_round"]

        logger.info(f"[Graph] 审查节点执行，第 {current_round} 轮")

        critique = self.critic.critique(task=task, draft=draft)

        # 记录历史
        history = state.get("history", [])
        record = IterationRecord(
            round=current_round,
            draft=draft,
            critique=critique,
            duration_seconds=0,  # Graph 模式下暂不精确计时
        )
        history.append(record)

        # 收敛判定必须在节点内完成：只有节点返回的 dict 才会被 LangGraph
        # 持久化到最终 state，条件边函数（_should_continue）对 state 的
        # 修改不会生效。
        decision = evaluate_convergence(
            critique=critique,
            current_round=current_round,
            max_rounds=state.get("max_rounds", self.max_rounds),
            score_threshold=self.score_threshold,
            no_progress_rounds=self.no_progress_rounds,
            history=history,
        )

        return {
            "critique": critique,
            "history": history,
            "converged": decision.converged,
            "convergence_reason": decision.reason,
        }

    def _should_continue(self, state: GraphState) -> str:
        """
        条件判断节点：决定继续迭代还是终止

        收敛结果已在 _critique_node 中写入 state，
        这里仅依据 convergence_reason 是否非空来决定路由。

        Args:
            state: 当前图状态

        Returns:
            "continue" 或 "end"
        """
        reason = state.get("convergence_reason", "")
        if reason:
            logger.info(f"[Graph] 终止：{reason}")
            return "end"

        logger.info(
            f"[Graph] 继续迭代，当前第 {state.get('current_round', 0)} 轮"
        )
        return "continue"

    def run(self, task: str, initial_draft: str = "") -> Dict:
        """
        执行工作流
        
        Args:
            task: 任务描述
            initial_draft: 初始草稿（可选）
        
        Returns:
            最终状态字典
        """
        logger.info(f"[Graph] 开始执行任务: {task[:80]}...")

        initial_state: GraphState = {
            "task": task,
            "domain": self.domain,
            "draft": initial_draft,
            "current_round": 0,
            "max_rounds": self.max_rounds,
            "history": [],
            "converged": False,
            "convergence_reason": "",
        }

        final_state = self.app.invoke(initial_state)
        logger.info(
            f"[Graph] 执行完成，迭代 {final_state.get('current_round', 0)} 轮, "
            f"收敛: {final_state.get('converged', False)}"
        )
        return final_state

    def get_best_draft(self, state: Dict) -> str:
        """
        从状态中获取评分最高的产出
        
        Args:
            state: 最终状态
        
        Returns:
            最优产出文本
        """
        history = state.get("history", [])
        if not history:
            return state.get("draft", "")

        best = max(history, key=lambda r: r.critique.score)
        return best.draft

    def visualize(self, output_path: str = "workflow.png") -> None:
        """
        可视化工作流图（需要安装 graphviz）
        
        Args:
            output_path: 输出图片路径
        """
        try:
            graph = self.app.get_graph()
            graph.draw_mermaid_png(output_file_path=output_path)
            logger.info(f"工作流图已保存到: {output_path}")
        except Exception as e:
            logger.warning(f"可视化失败（可能未安装 graphviz）: {e}")
            logger.info("可通过以下命令安装: pip install graphviz")
