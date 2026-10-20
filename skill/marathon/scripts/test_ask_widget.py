"""Offline ask-widget regression in installed headless Chrome; standard library only."""
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import marathon as m

ROOT = HERE.parents[2] / ".tmp"
ROOT.mkdir(exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="ask-widget-test-", dir=ROOT))
chrome = os.environ.get("MARATHON_TEST_CHROME") or next((str(p) for p in (
    Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe") if p.is_file()), None) or m.chrome_exe()
if not chrome:
    raise SystemExit("Chrome unavailable; set MARATHON_TEST_CHROME for the rendered widget regression")
cases = []
for count in (3, 4, 5, 8):
    questions = [{"id": f"q{i}", "text": ("Choose the next step for this project. " * 5)[:160],
                  "options": [f"Option {j}" for j in range(count)], "default": "Option 0", "must_decide": i == 4} for i in range(5)]
    data = {"id": f"widget{count}", "questions": questions}
    widget = m.ask_widget(data)
    script = re.search(r"<script>(.*?)</script>", widget, re.S)[1]
    markup = widget[:widget.index("<script>")]
    for width, height in ((375, 667), (1280, 900)):
        for moved in (False, True):
            cases.append(dict(count=count, width=width, height=height, moved=moved, markup=markup, script=script))
js = r'''
const results=[];
(async()=>{for(const c of CASES){
 const iframe=document.createElement('iframe');iframe.style.cssText=`width:${c.width}px;height:${c.height}px;border:0`;document.body.append(iframe);
 await new Promise(resolve=>{iframe.onload=resolve;iframe.srcdoc=c.markup});
 const w=iframe.contentWindow,d=w.document;let payload='',error='';w.sendPrompt=x=>payload=x;w.onerror=x=>error=String(x);
 if(c.moved){const unrelated=d.createElement('aside');unrelated.textContent='';d.body.append(unrelated)}
 const script=d.createElement('script');script.textContent=c.script;
 if(c.moved)d.body.append(script);else d.querySelector('form').after(script);
 const f=d.querySelector('form'),b=f.querySelector('button'),select=f.querySelector('select[name=q4]');
 const blocked=b.disabled;
 if(select){select.value='B';select.dispatchEvent(new w.Event('change',{bubbles:true}))}
 else{const radio=f.querySelector('input[name=q4][value=B]');radio.checked=true;radio.dispatchEvent(new w.Event('change',{bubbles:true}))}
 const enabled=!b.disabled;f.requestSubmit();
 results.push({count:c.count,width:c.width,moved:c.moved,blocked,enabled,payload,error,
   selectCount:f.querySelectorAll('select').length,bottom:b.getBoundingClientRect().bottom,
   height:d.documentElement.scrollHeight,overflow:d.documentElement.scrollWidth>c.width,
   minTarget:Math.min(...[...f.querySelectorAll('label,select,button')].map(e=>e.getBoundingClientRect().height))});
 iframe.remove();
}document.body.innerHTML='<pre id="results"></pre>';document.querySelector('pre').textContent=JSON.stringify(results)})().catch(e=>document.body.textContent=String(e));
'''.replace("CASES", json.dumps(cases))
page = TMP / "host.html"
page.write_text('<!doctype html><meta charset="utf-8"><script>' + js + '</script>', encoding="utf-8")
# An explicit body lets the script append test frames even when Chrome executes it immediately.
page.write_text(page.read_text(encoding="utf-8").replace('<script>', '<body><script>', 1), encoding="utf-8")
r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run", "--no-default-browser-check",
                    "--disable-background-networking", "--user-data-dir=" + str(TMP / "profile"), "--dump-dom", "--virtual-time-budget=3000", page.as_uri()],
                   capture_output=True, timeout=45, stdin=subprocess.DEVNULL)
(TMP / "dom.html").write_bytes(r.stdout)
match = re.search(r'<pre id="results">(.*?)</pre>', r.stdout.decode("utf-8", "replace"), re.S)
assert r.returncode == 0 and match, (r.returncode, r.stderr[-1000:])
results = json.loads(html.unescape(match[1]))
assert len(results) == len(cases), results
for result in results:
    assert result["blocked"] and result["enabled"] and not result["error"], result
    assert result["payload"] == f'ASK widget{result["count"]}: q0=A q1=A q2=A q3=A q4=B', result
    assert result["selectCount"] == (5 if result["count"] > 4 else 0), result
    assert not result["overflow"] and result["bottom"] <= (667 if result["width"] == 375 else 900), result
    assert result["minTarget"] >= 44, result
    print("ok   widget", json.dumps(result))
(TMP / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"{len(results)} passed; artifacts: {TMP}")
