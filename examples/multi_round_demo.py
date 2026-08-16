"""
多轮迭代演示示例
通过「复杂任务 + 提高收敛阈值」，观察 Generator 与 Critic 的多轮对话过程

为什么 quick_start.py 只跑一轮？
- 任务太简单，Generator 第一轮就产出合格内容
- Critic 第一轮就打 >=85 分且 acceptable=True，满足收敛条件立即停止

本示例：
1. 把收敛阈值从默认 85 提高到 95，让模型更难一次达标
2. 用 design 领域 + 复杂技术方案任务，Critic 会持续挑出改进点
3. 注册 on_round_complete 回调，实时打印每一轮的完整对话内容
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import get_config
from src.orchestrator import Orchestrator
from src.models.schemas import CritiqueResult


def on_round_complete(round_num: int, draft: str, critique: CritiqueResult):
    """每轮迭代完成时，实时打印 Generator 产出与 Critic 审查内容"""
    print(f"\n{'=' * 60}")
    print(f"第 {round_num} 轮迭代")
    print(f"{'=' * 60}")

    print("\n【Generator 产出】")
    print(draft)

    print("\n【Critic 审查】")
    print(f"评分: {critique.score} / 100  可接受: {'是' if critique.acceptable else '否'}")

    if critique.issues:
        print("问题:")
        for i, issue in enumerate(critique.issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("问题: 无")

    if critique.suggestions:
        print("建议:")
        for i, sug in enumerate(critique.suggestions, 1):
            print(f"  {i}. {sug}")

    if critique.summary:
        print(f"总结: {critique.summary}")
    print()


def main():
    # 1. 提高收敛阈值：默认 85 分就达标，简单任务第一轮就能收敛。
    #    这里调到 95，让模型更难一次达标，从而触发多轮迭代。
    #    （get_config() 返回全局单例，在创建 Orchestrator 之前修改即可生效）
    config = get_config()
    config.orchestrator.convergence_score_threshold = 95

    # 2. 定义一个较难的复杂任务（方案设计，Critic 会持续挑出改进点）
    task = """
设计一个支持百万级日活用户的短视频 App 后端架构方案，要求：
1. 给出完整的系统分层架构（接入层 / 业务层 / 数据层）
2. 视频存储与 CDN 分发方案
3. 推荐系统的实时与离线计算链路
4. 数据库选型与分库分表策略
5. 缓存设计（热点视频、用户 feed 流）
6. 高可用与容灾方案
7. 核心接口的性能指标（QPS、延迟）
    """.strip()

    # 3. 创建编排器：design 领域、最多 5 轮、注册逐轮回调
    orchestrator = Orchestrator(
        domain="design",
        max_rounds=5,
        on_round_complete=on_round_complete,
    )

    print(f"任务:\n{task}\n")
    print("=" * 60)
    print("开始 Generator-Critic 多轮迭代...")
    print("=" * 60)

    result = orchestrator.run(task)

    # 4. 打印评分趋势
    print("\n" + "=" * 60)
    print("评分趋势:")
    for i, score in enumerate(result.score_trend, 1):
        print(f"  第 {i} 轮: {score} 分")

    # 5. 打印最终产出与摘要
    print("\n" + "=" * 60)
    print("最终产出:")
    print("=" * 60)
    print(result.final_output)

    print("\n" + result.summary())


if __name__ == "__main__":
    main()
