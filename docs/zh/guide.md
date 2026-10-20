# Marathon 中文文档

怎么安装、怎么开始一个项目、中途怎么调整、它给你的信息怎么看。读完约十分钟，大多数人只需要看前三节。

## 安装

1. 下载 [marathon-skill.zip](/marathon-skill.zip) 并解压。
2. Windows：双击 `install.cmd`。macOS 或 Linux：在解压出来的文件夹里运行 `sh install.sh`。
3. 安装程序会把 skill 复制到 `~/.claude/skills/marathon`（装了 Claude Code 时）和 `~/.codex/skills/marathon`（装了 Codex CLI 时）。已有的旧版本会移到技能目录之外的 `~/.claude/marathon-backups/`（或 `~/.codex/marathon-backups/`）。安装时不动其他任何东西；项目运行期间，Marathon 会在 `~/.claude/settings.json` 里加一个自己的停止 hook，没有项目在跑时再删掉（卸载时也会删掉）。

需要 Python 3.10 或更新版本，以及 Claude Code：lead 和评审闸门都在 Claude 上运行。默认模式还需要登录了 ChatGPT 的 OpenAI Codex CLI，或者你自己的 OpenAI 兼容接口（见[模型和花费](#模型和花费)）。没有 Codex 的话，开工时选"全 Claude"模式即可。

卸载：再运行一次安装程序，Windows 加 `-Uninstall`，macOS/Linux 加 `--uninstall`。如果有备份，会恢复最近的一份。

## 开始一个项目

在 Claude Code 或 Codex 里描述项目，并说用 marathon：

```text
用 marathon 做一个丝绸之路题材的网页游戏：一个关卡、一个商店、
能存档读档、手机上能玩。预算 8 小时。
```

你正在对话的这个会话就成了 **lead**。它会在大约十分钟内读完你给的材料，检查能用哪些工具和登录，然后给你看：

- 运行配置（模式、worker、评审闸门、预算）；
- 你问到的问题的直接回答；
- 最多 5 个问题，每个都已经选好默认值。

点选后按确认，或者直接回文字（"同意"、"2B"）。10 分钟没回，普通问题就按默认值处理，项目开跑。只有你能回答的事（登录、付款、公开发布、删除东西、追加预算）永远不会自动选，会先放着，其他工作照常进行。

## 跑的过程中会发生什么

| 阶段 | lead 做什么 |
|---|---|
| 定章程 | 把对标对象、数字目标和及格线（例如 78/100 且没有严重问题）写进 `CHARTER.md` |
| 调研 | 派 worker 收集需要的东西：参考、数据、已有做法 |
| 一波一波干活 | 写几行任务说明，同时派多个 worker（默认 balanced 模式最多 4 个）；只读它们的简短总结（≤300 个英文单词） |
| 闸门 | 冻结一个版本，准备证据包，让两位评审独立打分 |
| 修改 | 按评审指出的最大短板安排下一波 |
| 交付 | 最终轮完整评审通过后：提交、上线、核对线上版本、写决策备忘 |

它会自己一直跑下去。每当 lead 要停下，停止 hook 就让它继续，直到满足某个停止条件：达标；连续三轮总共涨不到 3 分；预算用完；或者只有你能解决。

随时问一句"进度"（或 progress），就能看到一份简短汇报：状态面板、lead 自己的判断（包括达标的概率），以及几个需要你拿主意的问题。

## 两种模式

| | Codex worker 模式（默认） | 全 Claude |
|---|---|---|
| lead | 你对话的会话 | 你对话的会话 |
| worker | GPT-6.1-Sol high → GPT-6-Astra high → Claude Sonnet | Claude Sonnet → Claude Opus |
| 评审闸门 | 每轮 Claude Opus xhigh + GPT-6-Astra high | 每轮 Opus，最终轮再加 Astra |
| 额度 | worker 用你的 ChatGPT/Codex 订阅或 API；lead 和 Opus 用 Claude | 几乎全部用 Claude |

随时用一句话就能改："worker 换成 Astra"、"改成全 Claude"、"闸门用 Sonnet 加 Astra"。从下一个 worker 开始生效。实测把 worker 换成 Codex 后，每活跃小时的 Claude 花费少了 59–72%。

只有 worker 启动不了时（登录过期、额度用完、崩溃、还没开始干就超时）才按顺序换模型。结果不好不是换模型的理由：lead 会把任务说明写得更清楚，让 worker 返工。

## 评审闸门

每一轮由两位没有参与构建的评审，按章程给同一个冻结版本独立打分：Claude Opus 和 GPT-6-Astra。Astra 每轮都全面审。为了省钱，Opus 在第 1 轮、之后每 3 轮一次和最终轮全面审，其他轮只审改动的部分，其余项沿用上一次的分数。

两位分歧很大时（某一项差 3 分、总分差 10 分，或者严重问题只有一方报了），`marathon.py score` 会停在 **ADJUDICATE**。lead 必须逐条用证据（测试、复现的 bug、截图）裁决，这一轮才算数。最终轮一定要两个模型都完整审过。

## 项目会留下哪些文件

| 文件 | 内容 |
|---|---|
| `STATE.md` | 状态、阶段、进度、下一步和最近 5 条决定；新 lead 从这里接着做 |
| `DECISIONS.md` | 更早的决定和日志，自动从 STATE.md 移过来 |
| `CHARTER.md` | 对标对象、目标、及格线、假设 |
| `PROMPTS.md` | 你说过的话，一字不差，保证你提的要求不会丢 |
| `audits/scores.csv` | 每一轮闸门的分数 |
| `audits/workers.csv` | 每个 worker 一行：模型、用时、token、结果 |
| `.tmp/reports/` | worker 和评审的完整报告 |

## 命令

一般用不到，lead 会自己运行。想自己看一下项目时有用：

| 命令 | 作用 |
|---|---|
| `marathon.py status <dir>` | 简短状态；`--full` 看全部，`--report` 看完整报告；不带目录 = 它能找到的所有项目的总览（见 `status -h`） |
| `marathon.py config <dir>` | 当前模式、worker、闸门；`--models` 看 worker 顺序 |
| `marathon.py set <dir> workers=astra` | 改一项设置（也可以 `profile=claude`、`gate=sonnet+astra`） |
| `marathon.py set <dir> --status paused --reason "…"` | 暂停或结束 |
| `marathon.py usage <dir>` | 按部分统计的 Claude 花费 |
| `marathon.py worker list <dir>` | worker 质量表 |
| `marathon.py ask <dir> --status` | 有没有未回答的问题、离按默认处理还剩多久 |

脚本在 `~/.claude/skills/marathon/scripts/`（或 `~/.codex/skills/marathon/scripts/`）。

## 模型和花费

Codex worker 通过 Codex CLI 运行，默认用你登录的 ChatGPT 订阅。想改用 API，在开始前设置两个环境变量：

```text
MARATHON_API_BASE_URL = https://api.openai.com/v1   （或任何 OpenAI 兼容的 Responses 接口）
MARATHON_API_KEY      = 你的 key
```

两个都设了，worker 会先用 API，不行再用订阅。key 只传给 worker 进程，不会写进提示词、日志或文件。

`marathon.py usage <dir>` 按项目自己的对话记录计算 Claude 这边的花费，缓存读写分开算，可以看出钱主要花在 lead、评审还是 worker 上。

## 常见问题处理

| 现象 | 怎么办 |
|---|---|
| 项目停了，不再继续 | 看 `marathon.py status <dir>`：多半有一个放着的问题或必须你定的事在等你，回答它 |
| worker 每次都换成了 Claude | Codex CLI 没登录或找不到；运行一次 `codex` 登录，或者设置 API 变量 |
| 停在 "ADJUDICATE" 不动 | lead 欠一份裁决文件；让它对这一轮闸门做裁决 |
| 想马上停 | 说"暂停"或"停止 marathon"，它会保存状态后停下 |

Marathon 免费，MIT 许可。源代码和问题反馈在 [GitHub](https://github.com/washingtonshao-web/marathon)。
