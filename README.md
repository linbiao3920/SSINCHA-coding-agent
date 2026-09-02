# SSINCHA Coding Agent

> 一个 Coding Agent：使用 DeepSeek 官方 API，通过受限的 JSON 工具动作读取、修改并验证代码。

本项目演示一个可审计、可停止、受工作区约束的代码代理。模型不能直接执行任意 shell 命令，所有动作都经过结构化解析、安全检查和固定的循环控制。

---

## 评估合规与边界

本项目不是在现成 Agent 产品上套界面。DeepSeek/OpenAI 兼容客户端只负责发送消息、取得文本响应；以下关键逻辑均在本仓库本地实现：

| 评估项 | 本项目实现 |
| --- | --- |
| 对话与上下文 | `AgentState` 保存 system/user/assistant/tool 历史；`SessionStore` 原子化保存和恢复历史、验证状态、待验证文件。 |
| 模型输出解析 | 每轮只接受一个 JSON 对象，拒绝 prose、多个对象、未知动作、缺参和超长响应。 |
| 工具定义与本地执行 | `Toolbox` 自行实现文件读写和受限测试执行；未使用 Code Interpreter、Files API 或服务端文件工具。 |
| 循环控制 | `AgentLoop` 自行实现 30 步上限、重复动作阻止、连续错误熔断、验证驱动 Stop。 |
| 安全控制 | `Guardrail`、`Toolbox` 和 `TestTargetBinder` 分别处理路径、命令和测试关联性。 |
| 不使用的框架 | 未使用 LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen、CrewAI 或 Gradio。 |

模型仅能提出动作，不能拥有本机 shell、文件系统或测试进程的直接权限。

## 架构与执行流程

```text
CLI / Local Web UI
        |
        v
AgentState <-> SessionStore（本地历史、验证状态、待验证文件）
        |
        v
DeepSeek API -> 严格 JSON 解析 -> Action
                                  |
                                  v
              Guardrail + TestTargetBinder + CompletionGate
                                  |
                                  v
                  Toolbox（本地文件读写 / pytest 或 npm test）
                                  |
                                  v
             轨迹、结构化反馈、错误熔断 -> 下一轮或 Stop
```

典型的修复轨迹为 `Read_File -> Write_File -> Execute_Test -> Stop`。工具输出进入下一轮模型上下文，但模型输出的动作始终先经过本地校验。

---

## 功能概览

- **真实 LLM 客户端**：通过 DeepSeek 官方 API 获取下一步 JSON 动作，严格校验响应边界。
- **文件读写**：提供 `Read_File` 和 `Write_File`，路径只能位于指定 workspace 内。
- **受限测试执行**：仅允许 `pytest` 或 `npm test`；命令及其路径参数均不能越过 workspace，拒绝 shell 注入字符并有超时。
- **结构化反馈闭环**：从 pytest 输出提取错误类型、分类、文件位置、行号和摘要，将有限反馈回灌给下一轮模型。
- **测试目标绑定**：成功写入后要求测试命令明确覆盖对应测试文件，避免修改 `greet.py` 却只验证无关的 `test_blackjack.py`。
- **路径围栏**：阻止 `../`、绝对路径和符号链接造成的 workspace 越界访问。
- **验证驱动停止**：成功写入文件后，必须先有一次成功的 `Execute_Test` 才能 `Stop`；新的写入会使旧验证失效。
- **重复动作检测**：连续返回完全相同的动作时，不会重复执行该动作。
- **连续错误熔断**：同一错误连续出现三次后自动结束循环，避免死循环。
- **固定步数上限**：单次运行最多执行 30 步。
- **持久化会话**：使用 `--session` 保存对话历史、验证状态和待验证文件；后续命令仍须运行对应测试才能完成任务。
- **本地 Web UI**：使用 Python 标准库自建页面，支持密钥、workspace、指令输入，以及会话新建、继续和删除。
- **密钥管理**：支持环境变量、密钥文件和本地 `.env`；密钥不会写入 Git、Agent session 或 Web API 响应。
- **Docker 容器化**：非 root 镜像、最小构建上下文、显式 workspace 挂载和独立 session 卷，便于复现演示环境。

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

API Key 不写入源代码、session 文件或 Git 提交。为避免密钥出现在命令历史中，也可以保存为本地未跟踪文件并设置：

```powershell
$env:DEEPSEEK_API_KEY_FILE="C:\secure\deepseek.key"
```

客户端优先读取环境变量，其次读取密钥文件，最后读取仓库外/本地 `.env`；错误诊断会自动脱敏密钥。`.env`、密钥文件和 API Key 均不应提交到 Git。

加载优先级为：

```text
DEEPSEEK_API_KEY -> DEEPSEEK_API_KEY_FILE -> .env
```

密钥文件、`.env` 和 `sk-...` 风格令牌会受到 `.gitignore` 或脱敏逻辑保护；session 持久化前也会处理令牌，避免模型回显或异常信息把密钥写入本地会话文件。

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

命令仅在最终 `Stop` 成功时返回退出码 `0`；LLM 错误、熔断或达到步数上限而未完成时返回 `1`，启动配置错误返回 `2`，可直接用于脚本或 CI 判断任务状态。

如果模型在写入后直接请求停止，系统会返回：

```text
stop blocked: run tests after the latest successful write
```

模型需要根据反馈先运行测试，测试成功后才能停止。

### 本地 Web UI

```powershell
python -m agent.web
```

浏览器打开 `http://127.0.0.1:8765/`。页面提交的 API Key 会保存在当前浏览器标签页的 `sessionStorage`，因此运行后和刷新页面仍会保留；它不会写入 Agent session 或服务器文件。关闭标签页即可清除浏览器中的密钥；删除对话只删除 `.agent_sessions` 中对应的 JSON 文件。

Web 服务由 `agent/web.py` 通过 Python 标准库 `http.server` 提供，默认只监听 `127.0.0.1:8765`。前端为原生 HTML/CSS/JavaScript，不使用 Gradio 或 Web 框架。页面支持：

- 输入 API Key、workspace、任务指令和 session 名称；
- 新建、继续和删除 session；
- 显示动作摘要、pytest 通过数量、Stop 成功原因和历史警告数；
- 使用“清空反馈”只清除页面显示，不影响 API Key、任务输入、session 或 workspace；
- 对 Web 返回的任务、动作参数、观察和错误执行密钥脱敏。

### Docker Web UI

Docker Desktop 安装并启动后，在仓库根目录构建：

```powershell
docker build -t ssincha-coding-agent .
```

启动本地 Web UI，并将一个专用工作目录挂载到容器的 `/workspace`：

```powershell
docker run --rm -p 127.0.0.1:8765:8765 -v "D:\CodingAgent\myproject:/workspace" -v ssincha-agent-sessions:/data/sessions ssincha-coding-agent
```

浏览器打开 `http://127.0.0.1:8765/`，在页面的 workspace 输入 `/workspace`。API Key 仍从页面输入，不写入镜像、容器层或 Docker 命令行。

也可以使用 Compose。PowerShell 中先指定要挂载的工作目录：

```powershell
$env:SSINCHA_WORKSPACE="D:\CodingAgent\myproject"
docker compose up --build
```

Compose 默认只绑定 `127.0.0.1:8765`，并使用命名卷保存 session。不要挂载整个磁盘、用户目录或重要代码库；容器内 Agent 对 `/workspace` 的成功写入会同步到被挂载的宿主机目录。

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

会话保存在仓库根目录的 `.agent_sessions/`，并绑定首次使用的 workspace。会话文件不保存 API Key，也不应加入 Git。除消息历史外，会话还保存 `CompletionGate` 的验证状态和 `TestTargetBinder` 的待验证文件集合；因此跨命令继续 session 时，不能通过运行无关测试绕过最近一次写入后的验证。

会话写入使用临时文件加原子替换；读取时会拒绝符号链接、超大文件、损坏 JSON、不同 workspace、非规范路径和危险的待验证文件状态。删除会话只删除对应 JSON，绝不删除 workspace 文件。

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

测试失败时，反馈解析器会把原始输出转换为稳定的结构：

```text
category: assertion
error_type: AssertionError
location: tests/test_calculator.py:8
message: expected 5, got 2
```

该结构会作为独立消息回灌给 LLM；原始测试输出仍保留在执行轨迹中，便于审计。解析器和反馈闭环均可使用 mock LLM 脱机验证。

项目内的单元与集成测试覆盖路径围栏、重复动作、连续错误熔断、30 步上限、验证驱动停止、测试目标绑定、跨 session 恢复、密钥加载/脱敏及 Web UI 会话路由等场景。测试用确定性替身 LLM，不调用真实模型服务。

---

## 目录结构

```text
SSINCHA-coding-agent/
├── agent/
│   ├── action.py       # JSON 动作模型和参数校验
│   ├── cli.py          # 命令行入口和 session 编排
│   ├── completion.py   # 验证驱动停止门控
│   ├── feedback.py     # 结构化反馈和连续错误检测
│   ├── guardrail.py    # 动作执行前的安全检查
│   ├── llm.py          # DeepSeek 客户端和响应解析
│   ├── loop.py         # 最多 30 步的主循环
│   ├── secrets.py       # 密钥加载优先级与脱敏
│   ├── session.py      # 持久化会话
│   ├── state.py        # 消息、轨迹和错误状态
│   ├── test_target.py  # 修改文件与聚焦测试绑定
│   ├── tools.py        # 文件工具和受限测试执行
│   ├── web.py          # 本地 HTTP 服务
│   └── static/         # 原生 Web UI 页面
├── examples/
│   ├── demo_project/   # 计算器修复示例
│   └── mytest/         # 用户自定义 workspace
├── tests/              # Agent 单元测试
├── pyproject.toml
├── requirements.txt
├── Dockerfile           # 非 root Web UI 容器镜像
├── compose.yaml         # 本地端口、workspace 和 session 卷编排
├── .dockerignore        # 从镜像上下文排除密钥、session 和本地输出
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

当前完整测试套件为 **77 passed**。它覆盖 JSON 响应边界、本地工具与命令限制、测试路径围栏、循环终止、验证门控、测试绑定、session 安全、密钥脱敏、Web UI 会话操作，以及 Dockerfile、构建上下文和 Compose 的关键安全约束。

---

## 已知限制

- 当前工具集没有 `Delete_File` 动作，删除文件需要人工完成。
- 测试目标绑定要求测试命令显式指定与修改文件对应的测试路径；若项目没有对应测试，需先创建测试。
- 只有一个模型动作循环，没有 CI 自动化；Web UI 和 Docker 方案均为本地单用户演示，不是多用户服务。
- Docker 仅隔离运行环境；容器写入显式挂载的 `/workspace` 时，仍会修改对应宿主机目录。应只挂载专用测试项目。
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
