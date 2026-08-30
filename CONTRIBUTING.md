# 贡献指南（Contributing）

## 环境

- 运行与测试必须使用 agentchat 环境（base 环境的 pydantic_core 已损坏）：
  `D:\software\ProgramTool\Miniconda3\envs\agentchat\python.exe`
- 依赖：`pip install -r requirements.txt`

## 目录约定

- 后端核心逻辑在 `backend/src/`，按职责分层：`agents/`（Agent）、`orchestrator/`（编排）、`tools/`（工具）、`models/`（数据契约）、`prompts/`（提示词）
- Web 路由在 `backend/routers/`，入口 `backend/server.py`
- 前端源码在 `frontend/`，构建产物目标 `backend/static/dist`
- 纯函数/可复用逻辑优先抽取（如 `convergence.py` 共享收敛判定）

## 代码规范

- Python 遵循 PEP 8，类型注解用 `from __future__ import annotations` + `typing`
- 模块顶部写清职责 docstring（一句话定位 + 关键设计说明）
- 对 LLM 输出做防御性解析：永远不信任模型输出一定规范，层层降级兜底
- 文件操作走 `FileWorkspace` 沙箱，不直接 `open()` 用户路径

## 测试

- 测试必须能**完全离线**运行：用 Mock LLM 注入，不依赖真实 API Key
- 命令执行类测试用临时目录 + 脚本文件，避免 shell 引号跨平台问题
- 运行：`<exe> -m pytest tests/ -v`

## 提交约定

- 提交信息用**中文**
- Windows PowerShell 下 `git commit -m "中文"` 会乱码 → 将信息写入 UTF-8 临时文件后用 `git commit -F <file>`
- `git add` 显式列出文件，勿用 `-A`

## 新增功能 Checklist

1. 实现 + 必要的类型注解与 docstring
2. 补离线单元测试（Mock）
3. 若涉及新模块，更新 `README.md` 项目结构与 `docs/API.md`（若涉及接口）
4. 重要设计决策补一条 `docs/adr/`
