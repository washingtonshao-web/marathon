# 去 AI 味：模式清单

Read the sections the script flagged (A for tallies/meta/notes/openers/repeats, B for sentence tells, C when the shape is wrong, D for narration). Sources: blader/humanizer (Wikipedia "Signs of AI writing"), op7418/Humanizer-zh (31 patterns), hardikpandya/stop-slop, plus section A, which those miss.


## A. The report machine (deliverable level; check these first)
| Pattern | Looks like | Do instead |
|---|---|---|
| Tally sentences | "12 条判断：6 条倾向发生，4 条倾向不发生"; "五个信号"; "三大趋势" | Say the most important judgment itself. Counts belong in a table header, if anywhere |
| Talking about the document | "判断按照到期、事件复核和非新闻热度写"; "本页/本节/本站编码"; "口径"; "下文将" | Delete. The reader wants the subject, not the method. Method goes on the method page |
| Annotation everywhere | "截至 2026-11-03" on every card; "来源：…" under every chart; [S299] in running text | One as-of date per page (footer). Sources in a drawer, footnote or method page. Body text: ≤1 note per 150 characters |
| Internal labels shown to readers | J1, X3, Ex14, pipeline names, file names, "Exhibit" | Use the plain name ("中国新药出海"), number charts only when presenting |
| Format borrowed from the wrong genre | Executive summary, numbered Exhibits and rating cards for what is a talk to colleagues | Match the occasion (below) |
| Hedge stacks | "概率为主观估计，不是统计置信度，事件定义见判断卡" on each item | Say it once, where it first matters |
| Everything qualified, nothing said | Five caveats per number; no sentence that takes a side | Lead with the view; give the one caveat that would change it |
| One stock frame on repeat | "不等于" ×13, "两件事 / 三件事 / 五句话" ×12, "对我们意味着" ×17 across one talk | Fine once; from the third use it reads as a template. Vary it or just say the thing (`ai_tells.py` counts repeats site-wide) |

## B. Sentence patterns (Chinese)
| # | Pattern | Example | Fix |
|---|---|---|---|
| 1 | 不是 X，而是 Y / 并非…而是 / …，而非… | "下一步不是取消分型，而是验证一线" | State Y: "下一步要验证一线、耐药谱和治疗窗" |
| 2 | Signposts and wrap-ups | 首先/其次/最后；值得注意的是；总的来说；综上 | Cut; let order carry the logic |
| 3 | Inflated words | 赋能、闭环、抓手、底层逻辑、重塑、里程碑式、标志着、彰显、全景、深度洞察 | The concrete verb or number |
| 4 | Forced threes and four-character runs | "安全可控、精准高效、全面覆盖" | Two specifics beat three slogans |
| 5 | 进行 + verb, stacked 的, 被 chains | "进行了分析"; "公司的产品的检测的灵敏度" | "分析了"; break the noun chain |
| 6 | Aphorism endings | "这才是真正的护城河。" | End on the fact or the next step |
| 7 | Colon-label sentences everywhere | "判断：…" "含义：…" "风险：…" on every line | Use labels in tables, sentences in prose |
| 8 | Dashes as all-purpose glue | "——" several times a paragraph | Comma, full stop or a new sentence |
| 9 | Vague attribution | "业内普遍认为"; "有观点指出" | Name who, or drop it |
| 10 | Opening that repeats the title; customer-service tone | "关于 ADC，以下是…"; "希望对你有帮助" | Start with the point |

English text: no "delve, pivotal, underscore, landscape, seamless, leverage, testament, navigate the", no "not just X but Y", no em-dash chains, no paragraph ending in a punchy one-liner, vary sentence length.

## C. Format must fit the occasion
Decide the format from what the user will do with it, in their words, before the look. A style reference ("像券商报告那样精致") sets polish, not genre.
| Occasion | Shape | Voice |
|---|---|---|
| Internal talk / 内部分享 / 讲课 / 演讲 | A story in 15–30 slides-worth of sections: why it matters to us → what happened (headline studies, plenary first) → what it means → what to watch; a primer for any technology the audience may not know (e.g. ADC, mRNA vaccines, MRD) | First person plural, spoken: "我们看到…", "这意味着我们…"; short sentences; one idea per screen; speaker notes carry detail |
| Report to read / 报告 | Answer first, sections by question, evidence under each | Plain, precise, still human |
| Tool / atlas / database | Search and filters first, prose minimal | Labels and help text only |
Missing sections the audience expects (the plenary studies at a congress talk; a primer before jargon) are content gaps, not style issues.

## D. Narration and voice (films, TTS)
- Write for the ear: ≤25 characters per spoken clause; one number per sentence, two at most; round numbers ("约七成") unless the exact value is the point; never read a list of values ("零点二七、零点二九、零点四一") or letters ("P D L 一": say "PD-L1" as people say it).
- The voice is chosen by listening, not by a reviewer reading a transcript: make 2–4 samples of the same paragraph (compare at least two voices of the kind the film needs), and pick the most natural one yourself (name it in the report). It is scored with the narration like any other item; no sign-off from the user is needed.
- Subtitles follow the spoken words, not the written page.

