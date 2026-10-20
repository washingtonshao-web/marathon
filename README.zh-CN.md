# Marathon

**把要做几个小时的项目交给 AI，Marathon 一直做到达标为止。**

Marathon 是一个免费的 skill，**Claude Code** 和 **OpenAI Codex CLI** 都能用。你描述一个要花几个小时的项目（网页应用、网页游戏、数据网站、带出处的研究报告），你正在对话的会话就成了它的 lead。它先和你定好数字目标，派多个 worker 并行去做，**每一轮由两个不同的模型打分**，一直做到达标、分数不再上涨或预算用完，然后交付，并给你一份决策备忘。整个过程不用你说"继续"。

[**下载一键安装包**](https://marathon.falconshire.com/marathon-skill.zip) · [网站](https://marathon.falconshire.com/zh/) · [中文文档](https://marathon.falconshire.com/zh/docs/) · [English](README.md)

```text
● running · build wave 9 · 47.9 / 57 h
Progress ████████████░░░░░░░░ 58%
Targets  14 / 22 met
Score    73.5 → 76.5 → 77.0   pass 75
Workers  3 running · GPT-6.1-Sol high
Gate     Opus 5.5 xhigh + GPT-6-Astra high
```
<sub>根据一次真实业务系统项目的状态面板简化（预算 57 小时，已用 47.9 小时）。</sub>

## 在真实项目上量出来的

| | 结果 |
|---|---|
| 把 worker 换成 Codex 后，每活跃小时的 Claude 花费 | 业务系统项目 **−72%**，网页游戏 **−59%** |
| 一个停在 65.5–67.5 分的项目 | 切换后三轮内达标（76.5，最终 **77.0**；及格线 75） |
| 盲测重做 6 个已完成任务：GPT-6-Astra worker 对 Claude Opus worker | Codex 一次通过 **5/6**（Opus 3/6）；严重问题 **2 对 8** |

花费按项目自己的对话记录、分 token 类型计价；Codex 用的是订阅，不在数字里。

## 它能做什么

- **只问一次，然后开干。** 开工最多 5 个问题，默认值已选好，点一次确认；你不在时，10 分钟后按默认开跑。
- **目标可以检验。** 开工前就定好对标对象、数字目标和及格线。
- **并行 worker。** 同时派多个 worker（默认 balanced 模式最多 4 个）写代码、做研究、测试、打磨；每个交回一段简短总结（≤300 个英文单词），完整报告存成文件。
- **双模型评审闸门。** Claude Opus 和 GPT-6-Astra 独立给同一个冻结版本打分；分歧大时按证据裁决。
- **不用说"继续"。** 停止 hook 让它一直跑，直到满足停止条件。
- **不怕上下文变长。** 状态存在 `STATE.md`；上下文超过 150k 时，在空档换新 lead 接班。
- **花费算得清。** 每个 worker 一行账，Claude 花费按 token 类型计价。
- **交付后再汇报。** 提交、上线、核对线上版本，最后给一份写明局限和选项的备忘。
- **危险的事从不替你决定。** 登录、付款、公开发布、删除和追加预算，一定等你回答。

## 两种模式

| | Codex worker 模式（默认） | 全 Claude |
|---|---|---|
| worker | GPT-6.1-Sol high → GPT-6-Astra high → Claude Sonnet | Claude Sonnet → Claude Opus |
| 评审闸门 | 每轮 Opus xhigh + Astra high | 每轮 Opus，最终轮加 Astra |
| 额度 | worker 用你的 ChatGPT/Codex 订阅或自己的 API；lead 和 Opus 用 Claude | 几乎全部用 Claude |

随时一句话就能换（"worker 换成 Astra"、"改成全 Claude"）。

## 安装

1. 下载 [marathon-skill.zip](https://marathon.falconshire.com/marathon-skill.zip)（或最新的 [release](https://github.com/washingtonshao-web/marathon/releases/latest)）并解压。
2. Windows：双击 `install.cmd`。macOS / Linux：`sh install.sh`。
3. 在 Claude Code 或 Codex 里说："用 marathon 做……"

需要 Python 3.10+ 和 Claude Code（lead 和评审闸门都在 Claude 上运行）；默认的 Codex worker 模式还需要 Codex CLI。如果 Codex worker 想用 API 而不是 ChatGPT 登录，设置 `MARATHON_API_BASE_URL` 和 `MARATHON_API_KEY`（任何 OpenAI 兼容的 Responses 接口）。卸载：加 `-Uninstall` / `--uninstall` 再运行一次安装程序。

## 仓库结构

| 路径 | 内容 |
|---|---|
| `skill/marathon/` | skill 本体：`SKILL.md`、流程文档、模式说明卡、`scripts/marathon.py`、`scripts/codex_worker.py`、测试 |
| `install/` | `install.cmd` + `install.ps1`（Windows）、`install.sh`（macOS/Linux） |
| `docs/` | 中英文文档 |
| `site/` | marathon.falconshire.com 的源码（构建时用到一套不在本仓库里的设计组件；发布出去的网页是自包含的） |
| `tools/make_zip.py` | 生成安装包 |

## 许可

MIT。Marathon 适用于 Claude Code 和 OpenAI Codex CLI，并非 Anthropic 或 OpenAI 的产品，与它们没有隶属关系。
