"""
长时间运行任务示例
演示如何使用 TaskManager 创建和管理长时间运行的代码开发任务
"""

import sys
import os
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import setup_logging
from src.manager.task_manager import TaskManager
from src.models.task import TaskStatus


def on_task_event(event_type: str, data: dict):
    """任务事件回调"""
    task_id = data.get("task_id", "")
    
    if event_type == "task_created":
        print(f"[创建] 任务 {task_id} 已创建")
    elif event_type == "task_planning":
        print(f"[规划] 正在分析需求...")
    elif event_type == "task_planned":
        print(f"[规划] 分解完成: {data.get('subtask_count', 0)} 个子任务")
    elif event_type == "task_started":
        print(f"[启动] 任务开始执行")
    elif event_type == "subtask_started":
        print(f"[执行] 子任务开始: {data.get('title', '')}")
    elif event_type == "subtask_progress":
        print(f"[进度] 第 {data.get('round', 0)} 轮完成，评分: {data.get('score', 0)}")
    elif event_type == "subtask_completed":
        print(f"[完成] 子任务完成，评分: {data.get('score', 0)}")
    elif event_type == "task_completed":
        print(f"[完成] 任务已完成！")
    elif event_type == "task_failed":
        print(f"[失败] 任务失败: {data.get('error', '')}")


def main():
    setup_logging()
    
    print("=" * 60)
    print("长时间运行任务示例")
    print("=" * 60)
    
    # 创建任务管理器
    manager = TaskManager(on_task_event=on_task_event)
    
    # 创建任务
    task = manager.create_task(
        requirement="创建一个简单的 Python 计算器模块，支持加减乘除运算，包含单元测试",
        workspace_dir=".",
        domain="code",
    )
    
    print(f"\n任务已创建: {task.id}")
    print(f"标题: {task.title}")
    
    # 分解任务
    print("\n正在分解任务...")
    task = manager.plan_task(task.id)
    
    print(f"\n执行计划:")
    print(f"  分析: {task.plan.analysis}")
    print(f"  子任务数: {len(task.plan.subtasks)}")
    
    for i, st in enumerate(task.plan.subtasks, 1):
        deps = f" (依赖: {', '.join(st.dependencies)})" if st.dependencies else ""
        print(f"  {i}. {st.title}{deps}")
    
    # 启动任务
    print("\n启动任务执行...")
    manager.start_task(task.id)
    
    # 等待任务完成
    while True:
        progress = manager.get_progress(task.id)
        print(f"\r进度: {progress.progress_percent:.1f}% - {progress.message}", end="", flush=True)
        
        if progress.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ):
            break
        
        time.sleep(1)
    
    # 获取最终结果
    final_task = manager.get_task(task.id)
    print(f"\n\n{'=' * 60}")
    print(f"任务状态: {final_task.status.value}")
    print(f"总 Token 消耗: {final_task.total_tokens}")
    
    if final_task.plan:
        print(f"\n子任务结果:")
        for st in final_task.plan.subtasks:
            status_icon = "✓" if st.status == TaskStatus.COMPLETED else "✗"
            print(f"  {status_icon} {st.title}: {st.status.value}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
