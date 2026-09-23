"""Create a clean, disposable Git repository for the RefineLoop demo."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = PROJECT_ROOT / "demo" / "buggy-calculator"
DEMO_ROOT = (PROJECT_ROOT / ".refineloop-demo").resolve()
TARGET_DIR = DEMO_ROOT / "buggy-calculator"


def run_git(*args: str) -> None:
    """Run one Git command inside the disposable demo repository."""
    subprocess.run(["git", *args], cwd=TARGET_DIR, check=True)


def main() -> None:
    """Reset the demo directory, initialize Git, and commit the broken baseline."""
    if TARGET_DIR.parent != DEMO_ROOT:
        raise RuntimeError(f"Unexpected demo target: {TARGET_DIR}")
    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)

    DEMO_ROOT.mkdir(exist_ok=True)
    shutil.copytree(TEMPLATE_DIR, TARGET_DIR)
    run_git("init")
    run_git("config", "user.name", "RefineLoop Demo")
    run_git("config", "user.email", "demo@refineloop.local")
    run_git("add", ".")
    run_git("commit", "-m", "demo: add failing calculator baseline")

    print(f"Demo workspace: {TARGET_DIR}")
    print("Task: 修复 src/cart.py 的价格计算与输入校验问题，使全部测试通过。保持函数签名不变，不要修改测试。")


if __name__ == "__main__":
    main()
