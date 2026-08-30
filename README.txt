SSINCHA Coding Agent

使用 DeepSeek 官方 API 的最小 Coding Agent。

运行前先设置环境变量：

- `DEEPSEEK_API_KEY`
- 可选：`DEEPSEEK_MODEL=deepseek-v4-pro`

测试：

1. `python -m pytest -q`
2. `python -m agent --workspace examples\\demo_project "Fix the failing calculator tests. Read the files first, update only the source code, run pytest, and stop when the tests pass."`

持久化会话：

1. 创建：`python -m agent --session demo --workspace examples\\mytest "Create unknown.py and wait for my next instruction."`
2. 继续：`python -m agent --session demo --workspace examples\\mytest "Make unknown.py print a."`
3. 重置：`python -m agent --session demo --reset-session --workspace examples\\mytest "Start a new task."`

会话保存在本地 `.agent_sessions/`，绑定首次使用的 workspace，不保存 API Key，也不会加入 Git。
