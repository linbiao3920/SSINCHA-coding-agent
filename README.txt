SSINCHA Coding Agent
Git 仓库：https://github.com/linbiao3920/SSINCHA-coding-agent.git

一、运行
环境 Python3.11+、DeepSeek Key。
1. 安装：python -m pip install -r requirements.txt
2. 设置：$env:DEEPSEEK_API_KEY="你的API Key"
3. CLI：python -m agent --workspace examples\demo_project "修复测试"
4. Web：python -m agent.web，打开 http://127.0.0.1:8765/
5. Docker：docker compose up --build，workspace 填 /workspace
6. 测试：python -m pytest -q

二、特色
1. 自研上下文、JSON动作协议/解析和循环；动作仅 Read_File、Write_File、Execute_Test、Stop。
2. 本地文件和 pytest/npm test 工具；不用 Agent 框架/SDK、Code Interpreter、Files API。单文件读写上限 1 MiB（UTF-8 字节），超限拒绝。
3. workspace 路径围栏拦截越界路径、链接和测试路径；命令白名单、注入拦截、超时。
4. 最多30步、重复动作检测、连续同错3次熔断；写后测试成功才可 Stop，退出码反映状态。
5. 测试目标绑定：Python 用聚焦 pytest，JS/TS/package.json 用 npm test；校验 npm runner，pytest 失败反馈结构化。
6. session 保存历史、验证状态和待验证文件，支持继续、重置、删除；密钥支持环境变量、文件和 .env，并脱敏。
7. Web 支持输入 Key/workspace/指令、新建/继续/删除 session、清空反馈、步骤摘要和 Stop 原因。
8. Docker 使用非 root、显式 workspace 挂载、独立 session 卷和本机端口绑定。

三、其它
未使用 Agent 框架；删除对话不删除 workspace。89项测试通过。
