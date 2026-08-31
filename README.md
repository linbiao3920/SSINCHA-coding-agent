# SSINCHA Coding Agent

> 一个 Coding Agent：使用 DeepSeek 官方 API，通过受限的 JSON 工具动作读取、修改并验证代码。

本项目演示一个可审计、可停止、受工作区约束的代码代理。模型不能直接执行任意 shell 命令，所有动作都经过结构化解析、安全检查和固定的循环控制。

---

## 功能概览

- **真实 LLM 客户端**：通过 DeepSeek 官方 API 获取下一步 JSON 动作，严格校验响应边界。
- **文件读写**：提供 `Read_File` 和 `Write_File`，路径只能位于指定 workspace 内。
- **受限测试执行**：仅允许 `pytest` 或 `npm test`，拒绝 shell 注入字符，命令在 workspace 中执行并有超时。
- **路径围栏**：阻止 `../`、绝对路径和符号链接造成的 workspace 越界访问。
- **验证驱动停止**：成功写入文件后，必须先有一次成功的 `Execute_Test` 才能 `Stop`；新的写入会使旧验证失效。
- **重复动作检测**：连续返回完全相同的动作时，不会重复执行该动作。
- **连续错误熔断**：同一错误连续出现三次后自动结束循环，避免死循环。
- **固定步数上限**：单次运行最多执行 30 步。
- **持久化会话**：使用 `--session` 保存对话历史和验证状态，可在后续命令中继续任务。

---

## 环境要求

- Python 3.11 或更高版本
- DeepSeek API Key
- Windows、macOS 或 Linux

安装依赖：

```bash
python -m pip install -r requirements.txt
```

设置 API Key（PowerShell）：

```powershell
$env:DEEPSEEK_API_KEY="your-api-key"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
```

API Key 只从环境变量读取，不写入源代码、session 文件或 Git 提交。

---

## 快速开始

在仓库根目录运行：

```powershell
python -m agent --workspace examples\demo_project "Fix the failing calculator tests. Read the files first, update only the source code, run pytest, and stop when the tests pass."
```

典型动作顺序：

```text
Read_File -> Write_File -> Execute_Test -> Stop
```

如果模型在写入后直接请求停止，系统会返回：

```text
stop blocked: run tests after the latest successful write
```

模型需要根据反馈先运行测试，测试成功后才能停止。

---

## JSON 动作协议

模型每次只能返回一个 JSON 对象：

```json
{"type":"Read_File","params":{"path":"src/app.py"}}
```

支持的动作：

| 动作 | 用途 | 关键约束 |
|------|------|----------|
| `Read_File` | 读取文件 | 只能读取 workspace 内的文件 |
| `Write_File` | 创建或覆盖文件 | 路径必须位于 workspace 内 |
| `Execute_Test` | 执行测试 | 仅允许 `pytest` 或 `npm test` |
| `Stop` | 请求结束任务 | 写入后必须有成功测试证据 |

任意 prose、多个 JSON 对象、未知动作类型或缺少参数都会被拒绝。

---

## 持久化会话

会话名称由字母、数字、下划线和连字符组成，最长 64 个字符。

创建会话：

```powershell
python -m agent --session demo --workspace examples\mytest "Create unknown.py and wait for my next instruction."
```

继续会话：

```powershell
python -m agent --session demo --workspace examples\mytest "Make unknown.py print a."
```

重置会话：

```powershell
python -m agent --session demo --reset-session --workspace examples\mytest "Start a new task."
```

会话保存在仓库根目录的 `.agent_sessions/`，并绑定首次使用的 workspace。会话文件不保存 API Key，也不应加入 Git。

---

## 安全机制演示

路径越界会在工具执行前被拒绝：

```powershell
python -m agent --session path-demo --reset-session --workspace examples\mytest "Read ..\..\README.md, then stop."
```

受限命令会拒绝注入字符：

```powershell
python -c "from agent.tools import Toolbox; from agent.action import Action; print(Toolbox('examples/mytest').execute(Action('Execute_Test', {'cmd':'pytest && whoami'})))"
```

项目内的单元测试覆盖路径围栏、重复动作、连续错误熔断、30 步上限、验证驱动停止和 session 恢复等场景。

---

## 目录结构

```text
SSINCHA-coding-agent/
├── agent/
│   ├── action.py       # JSON 动作模型和参数校验
│   ├── cli.py          # 命令行入口和 session 编排
│   ├── completion.py   # 验证驱动停止门控
│   ├── feedback.py     # 连续错误检测
│   ├── guardrail.py    # 动作执行前的安全检查
│   ├── llm.py          # DeepSeek 客户端和响应解析
│   ├── loop.py         # 最多 30 步的主循环
│   ├── session.py      # 持久化会话
│   ├── state.py        # 消息、轨迹和错误状态
│   └── tools.py        # 文件工具和受限测试执行
├── examples/
│   ├── demo_project/   # 计算器修复示例
│   └── mytest/         # 用户自定义 workspace
├── tests/              # Agent 单元测试
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 测试

运行全部测试：

```powershell
python -m pytest -q
```

运行特定安全测试：

```powershell
python -m pytest tests\test_loop.py tests\test_tools.py tests\test_guardrail.py tests\test_completion.py tests\test_session.py -q
```

当前完整测试套件应全部通过。

---

## 已知限制

- 当前工具集没有 `Delete_File` 动作，删除文件需要人工完成。
- 验证门控判断测试命令是否成功，不会自动证明测试覆盖了最近修改的具体文件；建议在任务中明确指定测试路径。
- 只有一个模型动作循环，没有 Gradio WebUI、Docker 部署或 CI 自动化。
- 需要有效的 DeepSeek API Key 才能运行真实 Agent；单元测试使用本地确定性替身，不调用网络。
- 单次运行最多 30 步，单次测试命令默认超时 60 秒。

---

## 技术栈

- **语言**：Python 3.11+
- **模型接口**：OpenAI Python SDK，连接 DeepSeek 官方兼容 API
- **测试**：pytest
- **执行方式**：标准库文件和 subprocess 工具，workspace 级路径围栏

---

## 许可证

MIT
