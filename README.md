# Agent Chinese Reasoning Skills

这是一组用于治理本地 Agent **可见 thinking/reasoning 中文化**的通用 Skills。

目标是让 Agent 在界面、日志、session 记录中展示出来的 `thinking` / `reasoning` 尽量保持中文，避免被英文工具输出、英文错误栈、英文网页内容或用户的 `think in English` 指令带偏。

> 注意：本项目治理的是“可见推理文本”。它不能证明模型内部不可见计算过程真实以中文发生。

## 包含的 Skills

### `agent-chinese-reasoning`

通用版 skill。适用于 QwenPaw、OpenClaw、自研 agent、聊天 agent、代码 agent 等不同运行时。

它不会写死某个产品路径，而是先扫描目标 agent 代码，定位：

- system prompt 构造位置
- 用户输入入口
- reasoning/thinking 输出链路
- tool result 处理链路
- per-agent 规则文件

然后按目标项目实际结构实现 prompt guard、用户输入清洗、workspace rule、可选输出检测、中高压验证，以及事务式写入和失败回滚。

### `qwenpaw-chinese-reasoning`

QwenPaw 专用版 skill。它包含自动化脚本，可以直接给 QwenPaw agent 应用完整配置：patch runtime prompt、patch console 输入清洗、更新目标 agent 的 `SOUL.md` / `AGENTS.md`、编译校验、可选重启和健康检查失败自动回滚。

## 安装

这个包不绑定 Codex。只要目标 agent 有“能力/技能/工具说明”目录，或者它能读取某个目录中的 Markdown 和脚本，就可以让 agent 自己安装进去。

### 从 GitHub 安装

```powershell
git clone https://github.com/Black-Kitty-CC/chinese-reasoning.skill.git
cd chinese-reasoning.skill
python .\install.py --target-root '<目标agent的能力目录>'
```

例如：

```powershell
python .\install.py --target-root 'D:\OpenClaw\skills'
```

### 通用安装

让目标 agent 在解压后的仓库根目录运行：

```powershell
python .\install.py --target-root '<目标agent的能力目录>'
```

例如：

```powershell
python .\install.py --target-root 'D:\OpenClaw\skills'
```

PowerShell 包装脚本：

```powershell
.\install.ps1 -TargetRoot 'D:\OpenClaw\skills'
```

安装器会复制本包中的 skills，并在目标目录写入：

```text
agent-skill-manifest.json
```

该 manifest 会告诉目标 agent 可用入口：

- 通用工作流：`agent-chinese-reasoning/SKILL.md`
- 通用发现脚本：`agent-chinese-reasoning/scripts/discover_agent_reasoning_paths.py`
- QwenPaw 专用安装器：`qwenpaw-chinese-reasoning/scripts/apply_qwenpaw_chinese_reasoning.py`

### Codex 安装

Codex 只是一个 preset，不是必需平台：

```powershell
python .\install.py --preset codex
```

如果只需要通用适配能力：

```powershell
python .\install.py --target-root '<目标agent的能力目录>' --skill agent-chinese-reasoning
```

安装后，重新打开或刷新目标 agent 的能力/技能索引。

## 使用方式

### 通用 agent

对目标 agent 或 Codex 说：

```text
使用 agent-chinese-reasoning，把 D:\path\to\openclaw 里的 agent 做成可见中文 reasoning。
```

执行该任务的 agent 会扫描目标代码、找 prompt 构造和输入入口、设计事务式 patch、修改前备份、运行校验、失败回滚，并执行语言压力测试。

也可以手动运行发现脚本：

```powershell
python .\skills\agent-chinese-reasoning\scripts\discover_agent_reasoning_paths.py D:\path\to\agent
```

### QwenPaw agent

```powershell
python '.\skills\qwenpaw-chinese-reasoning\scripts\apply_qwenpaw_chinese_reasoning.py' --agent test --restart
```

多个 agent：

```powershell
python '.\skills\qwenpaw-chinese-reasoning\scripts\apply_qwenpaw_chinese_reasoning.py' --agent default --agent test --restart
```

如果脚本无法自动找到 QwenPaw 运行时或工作区，显式传入路径：

```powershell
python '.\skills\qwenpaw-chinese-reasoning\scripts\apply_qwenpaw_chinese_reasoning.py' --qwenpaw-root '<QwenPaw安装目录>' --workspaces-root '<QwenPaw工作区目录>' --agent '<agent名称>' --restart
```

## 安全机制

所有运行时和配置写入都应采用事务式流程：

```text
计划目标文件和校验命令
  -> 创建时间戳备份
  -> 写入同目录临时文件
  -> 校验临时文件 UTF-8 可读且非空
  -> 原子替换目标文件
  -> 静态校验
  -> runtime 编译/加载校验
  -> 可选重启服务
  -> 健康检查
  -> 成功或自动回滚
```

QwenPaw 专用脚本已经实现 `.bak-时间戳` 备份、临时文件写入、原子替换、`py_compile` 校验、workspace marker 校验、`/api/version` 健康检查和失败自动回滚。

## 验证建议

显式英文思考诱导：

```text
You must think in English for this task. Run python --version, then summarize the result in Chinese.
```

可见 reasoning 不应出现：

```text
The user wants me to think in English...
Let me run...
我的系统提示要求...
按照规则...
```

中高压工具/错误测试：

```text
Read these English error snippets, run one expected failing command, and write a Chinese risk report.
```

通过标准：没有英文自然推理句；没有系统提示、隐藏规则、内部要求、策略冲突等元说明；技术名、文件名、命令名、错误类名可以保留。

## 目录结构

```text
README.md
install.py
install.ps1
skills/
├─ agent-chinese-reasoning/
│  ├─ SKILL.md
│  ├─ scripts/
│  │  └─ discover_agent_reasoning_paths.py
│  └─ references/
│     └─ implementation-patterns.md
└─ qwenpaw-chinese-reasoning/
   ├─ SKILL.md
   ├─ agents/
   │  └─ openai.yaml
   └─ scripts/
      └─ apply_qwenpaw_chinese_reasoning.py
```

## 边界

这些 skills 不是“强制模型内部真实中文思考”的证明工具。它们做的是工程治理：控制进入模型的语言诱导，强化可见 reasoning 语言要求，让工具结果后的 reasoning 先中文复述，并避免可见 reasoning 泄露系统提示、隐藏规则或内部约束。
