#!/usr/bin/env python3
"""Count machine-sounding writing patterns ("AI 味") in Chinese or English text, per page and per site.

Usage:
    python ai_tells.py <file.html | file.md | file.txt | folder> [--json] [--examples N] [--skip method,sources]
    python ai_tells.py narration.txt --spoken      # a TTS script or subtitle text, written for the ear

Measures what the de-ai skill (patterns.md) defines:
  tells       sentence-level patterns (document tallies, meta narration, not-X-but-Y, signposts, inflated
              words, 进行+verb, stacked 的, four-character runs, English slop words), per 1,000 characters
  notes       annotation load in body text: 来源/出处/截至/截止/数据：/as of/[S12]-style refs, per 1,000 characters
  openers     tallies or meta lines inside the first 600 characters of a page (the first screen)
  repeats     stock frames (不等于, N 件事, 下一轮, 真正的…, 对我们意味着, 关键在于) used 3+ times: on a page and across
              the whole site, every use from the third counts as a tell
Characters = CJK characters, or words/2 for mostly-English text. nav, buttons, form controls, scripts,
styles, SVG, footer, aside and <details> drawers are skipped (drawers and footers are where sources belong).
In a folder, pages under 600 characters are ignored. Pages whose path contains a --skip word (default: method, source,
references, glossary) are listed but left out of the site verdict, since method talk belongs there.

The site verdict is character-weighted over the counted pages and gives a SUGGESTED cap for the `voice`
rubric key (10 = no cap):
  tells > 6/1k, or openers on >= 1/3 of pages -> 4;  tells > 3/1k, openers on any page, or notes > 7/1k -> 6;
  tells > 1.5/1k -> 8.
It is advisory evidence, not a verdict: a reviewer applies it unless they quote the hits and show they are
false positives, and a clean count with a dull voice still fails the read-aloud test. Thresholds were set on
one case (a talk site, owner score 60-65) and must be recalibrated as more user scores arrive.
--spoken adds two ear checks per sentence: number runs (3+ numbers read aloud in one sentence, e.g.
"百分之八十四、六十九、八十五", Chinese integers included) and long sentences (over 40 CJK characters), plus the
structure of a script (patterns.md D): route signs (先说…再说…最后说, 2+), attribution chains ("作者认为 / 专家提醒",
from the third), no view of our own (3+ attributions, no 我们认为/觉得/判断), footnotes read aloud (数的是, 说的是,
分母, 口径), closing hedges (不能代表, 仅供参考), unnamed drugs (一个新的 ADC) and an ending that restates the opening.
Exit code 0 always.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

SKIP_TAGS = r"script|style|svg|nav|button|select|option|template|noscript|textarea|label|footer|aside|details"
MIN_CHARS = 600
CJK = re.compile(r"[一-鿿]")
NUM = r"(?:\d+|[一二两三四五六七八九十]+)"
DOC_NOUN = r"(?:判断|信号|趋势|主题|看点|结论|倾向|要点|发现|启示|关键词|观察)"
TELLS = {
    # 12 条判断 / 五个信号 / 三大趋势 / 6 条倾向发生、4 条倾向不发生 (counts of the document's own claims)
    "tally": rf"{NUM}\s*(?:条|个|大|项)\s*{DOC_NOUN}|{NUM}\s*条[^。；\n]{{0,8}}[，,、]\s*{NUM}\s*条",
    # narration about the document instead of the subject
    "meta": r"本页|本节|本站|本报告|本文将|如下所示|以下将|口径|按照?[^。，；\n]{1,12}写",
    "not_but": r"(?:不是|并非|不只是|不仅仅是)[^。；\n]{1,30}(?:而是|更是)|，而非",
    "signpost": r"首先[^。]{1,80}其次|值得注意的是|需要指出的是|总的来说|综上所述?|总而言之|换句话说|一方面[^。]{1,40}另一方面",
    "inflated": r"赋能|闭环|抓手|底层逻辑|范式转移|全景|深度洞察|重塑|颠覆|里程碑式|标志着|彰显|见证了|助力|引领|生态位|新纪元|关键一步",
    "jinxing": r"进行了?(?:分析|评估|研究|讨论|比较|验证|优化|探索|布局|梳理)",
    "de_stack": r"[^，。；：、\n]{0,30}的[^，。；：、\n]{1,12}的[^，。；：、\n]{1,12}的",
    "four_run": r"(?:[一-鿿]{4}[、，]){2,}[一-鿿]{4}(?=[，。；])",
    "en_slop": r"(?i)\b(?:delve|tapestry|testament to|pivotal|underscores?|navigat(?:e|ing) the|landscape of|seamless(?:ly)?|"
               r"leverag(?:e|ing)|in conclusion|it'?s worth noting|not just [^.]{1,40} but)\b",
}
NUMBER = (r"\d+(?:\.\d+)?%?|百分之[零一二两三四五六七八九十百点]+|[零一二两三四五六七八九十百]+点[零一二三四五六七八九]+"
          r"|[零一二两三四五六七八九十百千万]{2,}")
SPOKEN = {"number_run": lambda s: len(re.findall(NUMBER, s)) >= 3, "long_sentence": lambda s: len(CJK.findall(s)) > 40}
# Spoken structure (--spoken): what makes a cleanly worded script still sound machine-made aloud (the films of one
# talk: 0 sentence tells, yet the user heard "非常 AI 化").
ROUTE = r"(?:先|再|接着|然后|最后)来?(?:说|讲|看)"  # 先说…再说…最后说: a table of contents read aloud
ATTRIB = (r"作者(?:认为|据此|指出|表示|提出)|研究者(?:认为|指出)"
          r"|(?:专家|嘉宾|讨论者|点评人)[^，。；\n]{0,6}?(?:认为|指出|提醒|建议|强调|说)")
VIEW = r"我们(?:认为|觉得|判断|看好|的判断|的看法)|我认为|我觉得|在我们看来"
SPOKEN_TELLS = {
    "footnote_read": r"(?:数|算|统计|指|说)的是|分母|口径",  # a denominator note or definition read out
    "hedge_close": r"不能代表|仅供参考|并不意味着|有待(?:进一步)?验证|还需要?更多",
    "vague_name": r"一[个款种](?:新的?)?[^，。；、\d]{0,6}?(?:组合|新药|ADC|疗法|方案)",  # name the drug or trial
}
STOP_BIGRAMS = {"我们", "这个", "一个", "不是", "就是", "这些", "他们", "可以", "没有", "什么", "如果", "因为", "所以",
                "还是", "已经", "自己", "以及", "能不", "不能", "这次", "会上"}
# Stock frames that are fine once and read as a template when repeated (one talk site: 不等于 ×11, N 件事 ×5).
REPEATS = {
    "不等于": r"不等于",
    "N 件事 / N 句话": rf"{NUM}\s*(?:件事|句话|样东西|个关键)",
    "下一轮 / 下一步": r"下一[轮步]",
    "真正的…": r"真正的(?:问题|门槛|关键|变化|分水岭|难点)",
    "对我们意味着 / 对我们来说": r"对我们(?:意味着|来说)",
    "关键是 / 关键在于": r"关键(?:是|在于)",
}
NOTES = r"来源|出处|截至|截止|(?:数据|资料)[：:]|[Aa]s of\b|\[\s*S?\d{1,4}\s*\]"


def visible_text(raw: str, is_html: bool) -> str:
    if is_html:
        raw = re.sub(rf"(?is)<({SKIP_TAGS})\b[^>]*>.*?</\1\s*>", " ", raw)
        main = re.search(r"(?is)<(main|article)\b[^>]*>(.*)</\1\s*>", raw)
        raw = main.group(2) if main else raw
        raw = re.sub(r"(?is)<br\s*/?>|</(p|li|h\d|div|tr|figcaption|header)>", "。\n", raw)
        raw = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    else:
        raw = re.sub(r"(?m)^\s*[#>|*-]+\s*", "", raw)
    return re.sub(r"[ \t\r\f\v]+", " ", raw)


def size(text: str) -> float:
    cjk = len(CJK.findall(text))
    words = len(re.findall(r"[A-Za-z]{2,}", text))
    return float(cjk) if cjk >= words / 2 else words / 2


def cap(tells_k: float, notes_k: float, opener_share: float) -> int:
    if tells_k > 6 or opener_share >= 1 / 3:
        return 4
    if tells_k > 3 or opener_share > 0 or notes_k > 7:
        return 6
    return 8 if tells_k > 1.5 else 10


class Hit:
    def __init__(self, start, end):
        self.start, self.end = (lambda: start), (lambda: end)


def spoken_hits(text: str) -> dict:
    found = {k: [] for k in SPOKEN}
    pos = 0
    for sent in re.split(r"(?<=[。！？!?\n])", text):
        for k, test in SPOKEN.items():
            if sent.strip() and test(sent):
                found[k].append(Hit(pos, pos + len(sent)))
        pos += len(sent)
    route = list(re.finditer(ROUTE, text))
    found["route_signs"] = route if len(route) >= 2 else []
    attrib = list(re.finditer(ATTRIB, text))
    found["attribution_chain"] = attrib[2:]  # one or two "作者认为" are fine; every one from the third is a tell
    found["no_own_view"] = attrib[:1] if len(attrib) >= 3 and not re.search(VIEW, text) else []
    for k, p in SPOKEN_TELLS.items():
        found[k] = list(re.finditer(p, text))
    found["echo_close"] = echo_close(text)
    return found


def echo_close(text: str) -> list:
    """The last two sentences restate the opening: 6+ shared content bigrams with the first 30% of the script."""
    sents = [s for s in re.split(r"(?<=[。！？!?])", text) if CJK.search(s)]
    if len(sents) < 8:
        return []
    def grams(s):
        return {a + b for a, b in zip(s, s[1:]) if CJK.match(a) and CJK.match(b)} - STOP_BIGRAMS
    head = text[:int(len(text) * 0.3)]
    tail = "".join(sents[-2:])
    if len(grams(head) & grams(tail)) < 6:
        return []
    start = text.rfind(sents[-2].strip())
    return [Hit(start, start + len(sents[-2].strip()))]


def scan(path: Path, root: Path, skip: list, n_ex: int, spoken: bool = False) -> dict:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = visible_text(raw, path.suffix.lower() in (".html", ".htm"))
    chars = max(size(text), 1.0)
    hits = {k: [m for m in re.finditer(p, text)] for k, p in TELLS.items()}
    if spoken:
        hits |= spoken_hits(text)
    repeats = {name: len(re.findall(pat, text)) for name, pat in REPEATS.items()}
    base = sum(len(v) for v in hits.values())
    for name, pat in REPEATS.items():  # a stock frame used 3+ times on one page: every use from the third counts
        ms = list(re.finditer(pat, text))
        if len(ms) >= 3:
            hits["repeat " + name] = ms[2:]
    notes = len(re.findall(NOTES, text))
    head = text.lstrip()[:600]
    openers = len(re.findall(TELLS["tally"], head)) + len(re.findall(TELLS["meta"], head))
    total = sum(len(v) for v in hits.values())
    rel = str(path.relative_to(root)) if path != root else path.name
    counted = not any(w in rel.lower() for w in skip)
    examples = []
    for k, ms in hits.items():
        for m in ms[:n_ex]:
            examples.append(f"{k}: …{text[max(0, m.start() - 20):m.end() + 20].strip()}…")
    return {"page": rel, "chars": int(chars), "tells": total, "tells_per_1k": round(total / chars * 1000, 1),
            "by_kind": {k: len(v) for k, v in hits.items() if v}, "notes": notes,
            "notes_per_1k": round(notes / chars * 1000, 1), "counted": counted, "openers": openers,
            "tells_base": base, "repeats": repeats,
            "voice_cap": cap(total / chars * 1000, notes / chars * 1000, 1.0 if openers else 0.0), "examples": examples}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--examples", type=int, default=2)
    ap.add_argument("--skip", default="method,source,references,glossary")
    ap.add_argument("--spoken", action="store_true", help="narration/subtitle script: add the ear checks")
    a = ap.parse_args()
    root = Path(a.target)
    files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.suffix.lower() in (".html", ".htm", ".md", ".txt"))
    skip = [w for w in a.skip.split(",") if w]
    floor = MIN_CHARS if root.is_dir() else 100  # folders: ignore stub pages; a single file is always scanned
    pages = [p for p in (scan(f, root, skip, a.examples, a.spoken) for f in files) if p["chars"] >= floor]
    counted = [p for p in pages if p["counted"]] or pages
    if not pages:
        sys.exit(f"no page with {floor}+ characters of text found")
    chars = sum(p["chars"] for p in counted)
    # Site verdict: page tells without the per-page repeat counts, plus stock frames repeated across the whole site.
    site_repeats = {name: sum(p["repeats"][name] for p in counted) for name in REPEATS}
    repeat_excess = sum(max(0, n - 2) for n in site_repeats.values())
    tells_k = (sum(p["tells_base"] for p in counted) + repeat_excess) / chars * 1000
    notes_k = sum(p["notes"] for p in counted) / chars * 1000
    opened = sum(1 for p in counted if p["openers"])
    summary = {"pages": len(counted), "chars": chars, "tells_per_1k": round(tells_k, 1), "notes_per_1k": round(notes_k, 1),
               "pages_with_openers": opened, "repeated_frames": {k: v for k, v in site_repeats.items() if v >= 3},
               "suggested_voice_cap": cap(tells_k, notes_k, opened / len(counted))}
    if a.json:
        print(json.dumps({"summary": summary, "pages": pages}, ensure_ascii=False, indent=1))
        return
    out = [f"{'page':40} {'chars':>6} {'tells/1k':>8} {'notes/1k':>8} {'open':>4} cap"]
    for p in pages:
        out.append(f"{p['page'][:40]:40} {p['chars']:6d} {p['tells_per_1k']:8.1f} {p['notes_per_1k']:8.1f}"
                   f"{'' if p['counted'] else '*':1} {p['openers']:3d} {p['voice_cap']:3d}")
    out.append(f"ALL: {summary['pages']} counted pages, {chars} chars, tells {summary['tells_per_1k']}/1k, notes "
               f"{summary['notes_per_1k']}/1k, first-screen tallies/meta on {opened} pages → suggested voice cap "
               f"{summary['suggested_voice_cap']}   (* not counted in the site verdict)")
    if summary["repeated_frames"]:
        out.append("repeated stock frames across the site (3+ uses; each use from the third is a tell): "
                   + ", ".join(f"{k} ×{v}" for k, v in summary["repeated_frames"].items()))
    for p in pages:
        for e in p["examples"]:
            out.append(f"  {p['page'][:30]} {e}")
    sys.stdout.buffer.write(("\n".join(out) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
