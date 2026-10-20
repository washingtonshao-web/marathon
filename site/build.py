"""Build marathon.falconshire.com into site/out/: landing pages (EN, 中文), guides from docs/*.md, the installer zip.

    SITE_KIT_APPLY=<path to the design kit's apply_kit.py> python site/build.py
"""
import os, re, shutil, subprocess, sys
from pathlib import Path
import markdown
from markdown.extensions.toc import slugify_unicode

SITE = Path(__file__).resolve().parent
REPO = SITE.parent
OUT = SITE / "out"
KIT = Path(os.environ.get("SITE_KIT_APPLY", "apply_kit.py"))  # the design kit's inliner (inlines CSS/JS into each page)
GITHUB = "https://github.com/washingtonshao-web/marathon"
ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%23b4531f'/%3E"
        "%3Ctext x='16' y='23' font-family='Segoe UI,Arial' font-size='20' font-weight='700' fill='white' text-anchor='middle'%3EM%3C/text%3E%3C/svg%3E")

NAV = {
    "en": [("/#how", "How it works"), ("/#results", "Results"), ("/#install", "Install"), ("/docs/", "Guide"), ("/zh/", "中文")],
    "zh": [("/zh/#how", "怎么运作"), ("/zh/#results", "实测"), ("/zh/#install", "安装"), ("/zh/docs/", "中文文档"), ("/", "English")],
}
FOOT = {
    "en": f'<a href="{GITHUB}">GitHub</a> · <a href="/docs/">Guide</a> · <a href="/zh/">中文</a> · MIT licence · Marathon works with Claude Code and the OpenAI Codex CLI; it is not made by Anthropic or OpenAI.',
    "zh": f'<a href="{GITHUB}">GitHub</a> · <a href="/zh/docs/">中文文档</a> · <a href="/">English</a> · MIT 许可 · Marathon 适用于 Claude Code 和 OpenAI Codex CLI，并非 Anthropic 或 OpenAI 的官方产品。',
}


def header(lang):
    home = "/" if lang == "en" else "/zh/"
    links = "".join(f'<a href="{h}"{" class=\"m-lang\" lang=\"zh-CN\"" if t == "中文" else (" class=\"m-lang\" lang=\"en\"" if t == "English" else (" class=\"m-guide\"" if h.endswith("docs/") else ""))}>{t}</a>' for h, t in NAV[lang])
    return (f'<header class="k-header"><div class="k-page k-header__in">'
            f'<a class="k-brand" href="{home}"><span class="k-brand__mark">M</span><span class="k-brand__name">Marathon</span></a>'
            f'<nav class="k-nav">{links}</nav></div></header>')


def footer(lang):
    return f'<footer class="k-footer"><div class="k-page">{FOOT[lang]}</div></footer>'


def page(src: Path, lang: str) -> str:
    html = src.read_text(encoding="utf-8")
    css = (SITE / "src" / "site.css").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="site.css">', f"<style>\n{css}</style>")
    return html.replace("<!--HEADER-->", header(lang)).replace("<!--FOOTER-->", footer(lang))


DOC_SHELL = """<!doctype html>
<html lang="{lang_attr}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="icon" href="ICON">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<link rel="stylesheet" href="kit/v1.css">
<link rel="stylesheet" href="kit/styles/editorial.css">
<link rel="stylesheet" href="site.css">
<script src="kit/v1.js"></script>
</head>
<body class="k">
<!--HEADER-->
<main id="top">
  <section class="k-hero"><div class="k-page">
    <h1>{h1}</h1>
    <p class="k-hero__lede">{lede}</p>
    <div class="m-cta"><a class="k-btn k-btn--primary m-btn-big" href="/marathon-skill.zip" download>{dl}</a></div>
  </div></section>
  <div class="k-page k-with-toc">
    <nav class="k-toc">{toc}</nav>
    <div class="k-prose m-doc">{body}
      <div class="m-final-cta"><a class="k-btn k-btn--primary m-btn-big" href="/marathon-skill.zip" download>{dl}</a></div>
    </div>
  </div>
</main>
<!--FOOTER-->
</body>
</html>
"""


def label_cells(body: str) -> str:
    """Give each cell after the first its column header as data-label (shown above it on phones)."""
    def one(m):
        heads = [re.sub("<[^>]+>", "", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", m.group(0), re.S)]
        out = []
        for part in re.split(r"(<tr>.*?</tr>)", m.group(0), flags=re.S):
            if part.startswith("<tr>") and "<td" in part:
                i = [0]
                def cell(c):
                    lab = heads[i[0]] if i[0] < len(heads) else ""
                    i[0] += 1
                    return f'<td{c.group(1)} data-label="{lab}">' if i[0] > 1 and lab else f"<td{c.group(1)}>"
                part = re.sub(r"<td([^>]*)>", cell, part)
            out.append(part)
        return "".join(out)
    return re.sub(r"<table>.*?</table>", one, body, flags=re.S)


def doc_page(md_path: Path, lang: str) -> str:
    text = md_path.read_text(encoding="utf-8")
    first, rest = text.split("\n", 1)
    h1 = first.lstrip("# ").strip()
    lede_m = re.match(r"\s*(.+?)\n\n(.*)", rest, re.S)
    lede, rest = (lede_m.group(1).strip(), lede_m.group(2)) if lede_m else ("", rest)
    body = markdown.markdown(rest, extensions=["tables", "fenced_code", "toc"], extension_configs={"toc": {"toc_depth": "2", "slugify": slugify_unicode}})
    body = label_cells(body)
    body = re.sub(r"<table>", '<div class="m-tablewrap"><table>', body).replace("</table>", "</table></div>")
    toc = "".join(f'<a href="#{i}">{re.sub("<[^>]+>", "", t)}</a>' for i, t in re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', body))
    zh = lang == "zh"
    html = DOC_SHELL.format(lang_attr="zh-CN" if zh else "en", title=f"{h1} — Marathon", desc=lede.replace('"', "'"), h1=h1, lede=lede,
                            dl="下载一键安装包" if zh else "Download the installer", toc=toc, body=body)
    css = (SITE / "src" / "site.css").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="site.css">', f"<style>\n{css}</style>").replace("ICON", ICON)
    return html.replace("<!--HEADER-->", header(lang)).replace("<!--FOOTER-->", footer(lang))


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "zh" / "docs").mkdir(parents=True)
    (OUT / "docs").mkdir()
    (OUT / "index.html").write_text(page(SITE / "src" / "index.html", "en"), encoding="utf-8")
    (OUT / "zh" / "index.html").write_text(page(SITE / "src" / "zh" / "index.html", "zh"), encoding="utf-8")
    (OUT / "docs" / "index.html").write_text(doc_page(REPO / "docs" / "guide.md", "en"), encoding="utf-8")
    (OUT / "zh" / "docs" / "index.html").write_text(doc_page(REPO / "docs" / "zh" / "guide.md", "zh"), encoding="utf-8")
    z = REPO / "dist" / "marathon-skill.zip"
    if not z.exists():
        sys.exit("dist/marathon-skill.zip missing: run tools/make_zip.py first")
    shutil.copy2(z, OUT / "marathon-skill.zip")
    r = subprocess.run([sys.executable, str(KIT), str(OUT)], capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL)
    print(r.stdout.strip()[-400:], r.stderr.strip()[-400:])
    leftovers = [str(p) for p in OUT.rglob("*.html") if 'href="kit/' in p.read_text(encoding="utf-8")]
    if leftovers:
        sys.exit(f"kit not inlined in: {leftovers}")
    print("built", sorted(str(p.relative_to(OUT)) for p in OUT.rglob("*") if p.is_file()))


if __name__ == "__main__":
    main()
