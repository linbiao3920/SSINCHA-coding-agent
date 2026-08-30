SSINCHA Coding Agent

使用 DeepSeek 官方 API 的最小 Coding Agent。

运行前先设置环境变量：

- `DEEPSEEK_API_KEY`
- 可选：`DEEPSEEK_MODEL=deepseek-v4-pro`

测试：

1. `python -m pytest -q`
2. `python -m agent --workspace examples\\demo_project "Fix the failing calculator tests. Read the files first, update only the source code, run pytest, and stop when the tests pass."`
