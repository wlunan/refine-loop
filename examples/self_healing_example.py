"""
代码自愈闭环示例

展示「生成 → 验证 → 失败定位 → 修复 → 复跑」的完整闭环：
让 Agent 在工作区中实现一个带单元测试的 Python 模块，
若测试失败则自动根据失败日志修复，直到测试通过。

与 quick_start.py（文本迭代）的区别：这里的「批判」不再是纯文本，
而是 pytest 的真实执行结果——批评的依据是事实，修复的目标是让测试通过。
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"
    ),
)

from config.settings import setup_logging
from src.orchestrator import SelfHealingOrchestrator


def on_event(event: dict):
    """实时打印自愈闭环的每个环节"""
    etype = event.get("type")

    if etype == "repair_round":
        print(f"\n{'=' * 50}")
        print(event.get("message"))
        print("=" * 50)

    elif etype == "tool_call":
        print(f"  [工具调用] {event.get('tool')}")

    elif etype == "verification_result":
        status = "通过" if event.get("success") else "失败"
        print(
            f"\n[验证] 第 {event.get('round')} 轮: {status} "
            f"(退出码 {event.get('exit_code')})"
        )
        if not event.get("success"):
            # 失败时打印关键报错（截断，避免刷屏）
            detail = event.get("detail", "")
            print(detail[:600])


def main():
    setup_logging()

    # 工作区目录：Agent 会在这里生成代码与测试
    workspace = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "_self_healing_demo"
    )

    orchestrator = SelfHealingOrchestrator(
        workspace_dir=workspace,
        verify_command="pytest",   # 用 pytest 作为客观验证信号
        max_repair_rounds=4,       # 最多修复 4 轮
        domain="code",
        on_event=on_event,
    )

    task = (
        "在工作区中实现一个 Python 模块 calculator.py，"
        "包含 add / sub / mul / div 四个函数，并编写对应的单元测试 "
        "test_calculator.py，确保所有测试都能通过。"
    )
    print(f"任务: {task}\n")

    result = orchestrator.run(task)

    print("\n" + result.summary())
    if result.final_verification:
        print("\n最终验证结果：")
        print(result.final_verification.to_str())


if __name__ == "__main__":
    main()
