"""Write templates/scoring/<format>.json from the profiles the user saved on the review-standards page.

Usage: export the page database first (ArtifactData list, collection "profiles", out_dir=<dir>), then
    python scoring_profiles.py <dir>/profiles
The page: your review-standards settings (references/review-principles.md).
"""
import json, pathlib, sys
SRC = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(__file__).resolve().parent.parent / "templates" / "scoring"
OUT.mkdir(parents=True, exist_ok=True)

LABELS = {  # (label, what full marks look like), as shown on the page
    "talk": {"share_ready": ("愿意拿给同事看", "评审以同事身份看完：用户会不会明天就拿去讲，不用改"),
             "accuracy": ("准确", "抽查的数字、结论和来源一致；没有夸大"),
             "voice": ("口语化", "能直接照着讲：短句，“我们”的口吻；注释少，没有 AI 腔"),
             "story": ("讲述线", "一条线讲下来，听的人跟得上"),
             "slides": ("页面", "一页一个意思，大字，图比字多"),
             "narration": ("讲稿与配音", "逐页讲稿，能照着讲；配音由执行者试样本后选定，听起来自然")},
    "report": {"share_ready": ("愿意拿给同事看", "评审以同事身份读完：用户会不会直接转给同事，不用改"),
               "correctness": ("正确性", "抽查的数字和结论与一手来源一致"),
               "answers_questions": ("回答了问题", "用户问的每个问题都有直接答案"),
               "decision_value": ("有看法", "给出明确看法和理由；概率、到期日只在年终报告这类场合用"),
               "depth": ("深度", "读过该读的文献，用行业标准术语"),
               "presentation": ("版面", "结论先行，图表清楚，手机可读")},
    "site": {"share_ready": ("愿意拿给同事用", "评审以同事身份用一遍：用户会不会把链接发给同事"),
             "accuracy": ("准确", "抽查记录与一手来源一致"),
             "coverage": ("覆盖", "该有的条目都有，没有占位符"),
             "visual_design": ("视觉", "设计评分卡达标"),
             "map_dataviz": ("地图与图表", "符合地图和图表规则"),
             "phone": ("手机", "iPhone 上好用，无溢出"),
             "voice": ("文字", "说明文字短而具体，注释少"),
             "speed": ("速度", "首屏快，包体小"),
             "interaction": ("交互", "点击不跳，返回好用，没有白屏")},
    "film": {"share_ready": ("愿意拿给同事看", "评审看完：用户会不会直接发给同事看"),
             "visuals": ("画面", "风格统一、清楚，字幕手机上看得清"),
             "accuracy": ("准确", "画面和旁白里的事实与来源一致"),
             "story": ("故事", "开头点题，一条主线，结尾落到“所以呢”"),
             "voice": ("旁白与配音", "为耳朵写的短句；配音由执行者试样本后选定，听起来自然"),
             "pacing": ("节奏", "每分钟不超过 3 个数字，不念列表")},
    "game": {"share_ready": ("愿意给朋友玩", "评审玩 10 分钟：用户会不会把它发给朋友"),
             "core_loop": ("核心玩法", "30 秒上手，有想继续玩的理由"),
             "visual_art": ("美术", "风格统一，近看不穿帮"),
             "ui_ux": ("界面", "目标清楚，操作顺手"),
             "feel": ("手感", "反馈及时，有分量"),
             "content": ("内容", "关卡和文本有料"),
             "performance": ("性能", "帧率稳，加载快"),
             "stability": ("稳定", "不崩，存档可靠")},
}
CAPS = {  # order = importance; notes first. Caps are ceilings: the lowest one that applies wins, never added up.
    "notes": ("注释过多", "正文每千字超过 7 处“来源 / 截至 / [S12]”；来源放抽屉、脚注或方法页"),
    "judgment": ("判断格式本身", "概率表、到期日、复核日、“倾向发生 / 不发生”、“判断按……写”；年终报告这类需要时除外"),
    "opener": ("首屏计数句或讲文档自己的话", "如“12 条判断：6 条倾向发生，4 条……”“本页口径”"),
    "tells": ("去 AI 味脚本给出的上限", "de-ai scripts/ai_tells.py 的建议（含同一句式重复 3 次以上）；评审证明是误报才可不封顶"),
    "talkreport": ("该讲的做成了报告", "执行摘要 + 编号图表 + 评级卡，没有讲述线"),
    "missing": ("缺了同事一定会问的重要内容", "评审要说出具体缺什么；不按固定板块清单查"),
    "evidence": ("只列证据，没有自己的建议", "每一节要落到“我建议……因为……”；免责只说一次（2026-11-05）"),
    "reason": ("用户上次提的理由还没解决", "对应的评分项（不含 share_ready）"),
    "playtest": ("人物试玩卡在核心玩法上", "3 分钟内不知道要做什么"),
}
# Which item each cap limits, per type. share_ready is the reviewer's overall judgment and is never capped (2026-11-05).
TARGETS = {
    "talk": {"notes": "voice", "judgment": "voice", "opener": "voice", "tells": "voice", "talkreport": "story", "missing": "story"},
    "report": {"notes": "presentation", "judgment": "decision_value", "opener": "presentation", "tells": "presentation",
               "missing": "answers_questions", "evidence": "decision_value"},
    "site": {"notes": "voice", "judgment": "voice", "opener": "voice", "tells": "voice", "missing": "coverage"},
    "film": {"judgment": "voice", "tells": "voice", "missing": "story"},
    "game": {"playtest": "core_loop"},
}
STEPS = {
    "passA": "评审先冷读：只看用户的原话，以同事身份打开作品，先给 share_ready（愿意拿给同事）打分，再看其他材料",
    "quotes": "评审引用 5 句最像机器写的话",
    "tells": "执行者交付前、评审打分时都跑 de-ai scripts/ai_tells.py（旁白加 --spoken），引用结果",
    "listen": "执行者自己试 2–4 个配音样本，挑最自然的；配音好坏算在讲稿 / 旁白的分里",
    "ask": "做到 15–20% 时把预览发给用户看方向（不问分数，默认继续）",
    "hold": "用户的分数低于及格线时，评审通过也不上线：继续干活，发预览只问能不能上线",
}
FORMAT = {"talk": "talk", "report": "report", "site": "tool", "film": "film", "game": "game"}
# Caps added after the page data was last saved: used until the page saves its own value.
NEW_CAPS = {"report": {"evidence": {"on": True, "cap": 50}}}

for page_id, labels in LABELS.items():
    d = json.loads((SRC / f"{page_id}.json").read_text(encoding="utf-8"))
    d = d.get("data", d)
    keys = []
    for k in d["keys"]:
        if not k["on"] or k["weight"] <= 0:
            continue
        label, desc = labels[k["id"]]
        keys.append({"id": k["id"], "label": label, "full_marks": desc, "weight": k["weight"], "floor_pct": k["pct"]})
    ids = {k["id"] for k in keys}
    assert sum(k["weight"] for k in keys) == 100, page_id
    caps = []
    for c, (text, note) in CAPS.items():
        v = d["caps"].get(c) or NEW_CAPS.get(page_id, {}).get(c)
        if not v or not v["on"]:
            continue
        target = "*" if c == "reason" else TARGETS[page_id].get(c)
        if target is None:
            continue  # this cap has no item to limit in this type
        assert target == "*" or target in ids, (page_id, c, target)
        caps.append({"id": c, "text": text, "note": note, "key": target,
                     "max_pct": v["cap"] if isinstance(v["cap"], int) else "ai_tells"})
    steps = [STEPS[s] for s in STEPS if d["steps"].get(s)]
    fmt = FORMAT[page_id]
    out = {"format": fmt, "pass_total": d["pass"], "keys": keys, "caps": caps, "steps": steps,
           "source": "your review-standards settings", "saved": d.get("savedAt")}
    (OUT / f"{fmt}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(fmt, [(k["id"], k["weight"], k["floor_pct"]) for k in keys], [c["id"] + "->" + c["key"] for c in caps])
