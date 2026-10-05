"""Build the one-page, tabbed artifact from the five design docs plus a hand-written overview.

    <scratch venv with `markdown`>/bin/python site/build.py   → grid_simulator_design.html
"""

import html
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SITE = Path(__file__).resolve().parent

TABS = [  # id, file, tab label, number
    ("landscape", "01_landscape_and_literature.md", "Landscape", "01"),
    ("simulator", "02_simulator_v2_design.md", "Simulator v2", "02"),
    ("goals", "03_goals_macro_micro.md", "Goals", "03"),
    ("experiments", "04_experiment_protocol.md", "Experiments", "04"),
    ("compiler", "05_compiler_and_verifier.md", "Compiler", "05"),
]
FILE_TO_TAB = {f: t for t, f, _, _ in TABS}
FILE_TO_TAB["README.md"] = "overview"

# Extra diagrams placed after a given heading line in a doc (in memory only; the .md files are unchanged).
EXTRA = {
    "landscape": [("## 5. Design rules collected", """
```mermaid
flowchart LR
  subgraph EV["Evidence"]
    B["Blake et al.<br/>brand ads ≈ 0 lift"]
    S["Simonov et al.<br/>stealing depends on presence"]
    L["Logit choice models<br/>nested substitution"]
    Q["Quick-commerce practice<br/>festive CPM +30–50%, stock-outs"]
    A["AuctionNet / AdCraft<br/>strategic, drifting markets"]
    C["COMPASS, MoHOLLM code<br/>LLMs weak on hard constraints"]
  end
  subgraph DR["Design rules"]
    D1["D1 nested-logit shelf"]
    D2["D2 intent mix"]
    D4["D4 conditional stealing"]
    D5["D5 calendar"]
    D6["D6 competitor agents"]
    D7["D7 finite stock"]
    D8["D8 counterfactual scorer"]
  end
  L --> D1
  B --> D2
  S --> D4
  Q --> D5
  Q --> D7
  A --> D6
  B --> D8
  C --> CMP["Compiler (tab 05)"]
```
""")],
    "simulator": [("## 1. Today's response model, and the one line we replace", """
```mermaid
flowchart LR
  SE["Searches<br/>city × keyword × daypart"] --> AU["Auction<br/>slot shares 1/5/9/13"]
  AU --> IM["Impressions<br/>× on-shelf availability"]
  IM --> BU["Budget pacing"]
  BU --> SH["Shelf choice<br/>NEW: nested logit + intent mix"]
  SH --> OR["Orders: ad-attributed + organic<br/>for own and competitor SKUs"]
  CAL["NEW: calendar<br/>seasons, festive, ephemeral"] -.-> SE
  CAL -.-> SH
  COMP["NEW: competitor agents"] -.-> AU
  STK["NEW: finite stock"] -.-> IM
  OR --> SC["NEW: Scorer v2<br/>counterfactual, ads off"]
```
"""), ("### 2.4 The 4-way decomposition of every ad order", """
```mermaid
flowchart TD
  AO["One ad-attributed order of S1 on 'soap'"] --> Q{"Without the ad, the shopper would have…"}
  Q -->|"bought S1 organically"| SELF["self<br/>not incremental"]
  Q -->|"bought S3 or S5"| SIB["sibling<br/>not incremental for the brand"]
  Q -->|"bought Velora or Nimbus"| CO["competitor<br/>stolen: incremental"]
  Q -->|"not bought in the category"| EXP["expansion<br/>incremental"]
```
""")],
    "goals": [("### 3.1 The hierarchy", """
```mermaid
flowchart TD
  subgraph MACRO["Macro: aggregates over weeks, in ₹ or share"]
    L0["L0 Portfolio: all Aurel"] --> L1["L1 Nest: bar soap · liquid"]
    L1 --> L2["L2 SKU or region: S5 · North"]
  end
  subgraph MICRO["Micro: cells over days, in delivery terms"]
    L3["L3 SKU × city"] --> L4["L4 cell: SKU × city × keyword"]
    L4 --> L5["L5 cell × daypart"]
    L5 --> L6["L6 bid / budget value"]
  end
  L2 --> L3
  L0 -. "prices λ (budget), μ (floor)" .-> L4
  L4 -. "ν: what each micro goal costs" .-> L0
```
""")],
    "experiments": [("## 1. Two tracks", """
```mermaid
flowchart LR
  E1["E1 · G-0<br/>max brand IncRev at budget B"] --> E2["E2 · G-1<br/>+ S5 North SOV, S6 sell-through<br/>(Pareto, hypervolume)"]
  E2 --> E3["E3 · G-2<br/>+ 9 typed constraints"]
  E3 --> ARMS["prompt-only · penalty · reject ·<br/>compiler-repair · compiler-box"]
  O["Oracles O1 (in-space), O2 (full-space)"] -.-> E1
  O -.-> E2
  O -.-> E3
```
""")],
}


def protect(text: str):
    """Pull out mermaid blocks and math so the markdown converter leaves them alone."""
    store = []

    def keep(s):
        store.append(s)
        return f"\x00{len(store) - 1}\x00"

    text = re.sub(r"```mermaid\n(.*?)```",
                  lambda m: "\n\n" + keep(f'<div class="diagram"><pre class="mmd">{html.escape(m.group(1))}</pre></div>') + "\n\n",
                  text, flags=re.S)
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: keep(r"\[" + html.escape(m.group(1)) + r"\]"), text, flags=re.S)
    text = re.sub(r"\$([^\s$\d][^$\n]*?)\$", lambda m: keep(r"\(" + html.escape(m.group(1)) + r"\)"), text)
    return text, store


def restore(h: str, store) -> str:
    for _ in range(2):
        h = re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], h)
    h = re.sub(r"<p>\s*(<div class=\"diagram\">.*?</div>)\s*</p>", r"\1", h, flags=re.S)
    return h


def blank_before_blocks(text: str) -> str:
    """python-markdown needs a blank line before lists and tables that follow a paragraph line."""
    out, prev, fence = [], "", False
    for line in text.split("\n"):
        if line.startswith("```"):
            fence = not fence
        starts_block = re.match(r"^(\s*[-*] |\s*\d+\. |\|)", line)
        prev_block = re.match(r"^(\s*[-*] |\s*\d+\. |\||#)", prev) or prev.strip() == ""
        if not fence and starts_block and not prev_block:
            out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


def fix_links(h: str) -> str:
    def rel(m):
        target = m.group(1)
        f = target.split("#")[0]
        if f in FILE_TO_TAB:
            return f'href="#{FILE_TO_TAB[f]}" data-tab="{FILE_TO_TAB[f]}"'
        if target.startswith("http"):
            return f'href="{target}" target="_blank" rel="noopener"'
        return f'href="{target}"'
    return re.sub(r'href="([^"]+)"', rel, h)


def convert(tab: str, path: Path) -> tuple[str, str]:
    text = path.read_text()
    for after, block in EXTRA.get(tab, []):
        assert after in text, (tab, after)
        text = text.replace(after, after + "\n" + block, 1)
    title = re.match(r"# (.+)", text).group(1)
    text = re.sub(r"^# .+\n", "", text, count=1)
    text, store = protect(text)
    text = blank_before_blocks(text)
    h = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    h = restore(h, store)
    h = re.sub(r"<table>", '<div class="tablewrap"><table>', h)
    h = h.replace("</table>", "</table></div>")
    h = re.sub(r"<h2>(Assumptions and caveats)</h2>", r'<h2 class="caveats">\1</h2>', h)
    h = fix_links(h)
    return title.split(" · ", 1)[-1], h


def main():
    sections, buttons = [], []
    overview = (SITE / "overview.html").read_text()
    buttons.append('<button role="tab" id="t-overview" aria-controls="overview" data-tab="overview" aria-selected="true">'
                   '<span class="n">00</span>Overview</button>')
    sections.append(f'<section id="overview" role="tabpanel" aria-labelledby="t-overview">{fix_links(overview)}</section>')
    for tab, f, label, n in TABS:
        title, body = convert(tab, ROOT / f)
        buttons.append(f'<button role="tab" id="t-{tab}" aria-controls="{tab}" data-tab="{tab}" aria-selected="false">'
                       f'<span class="n">{n}</span>{label}</button>')
        sections.append(f'<section id="{tab}" role="tabpanel" aria-labelledby="t-{tab}" hidden>'
                        f'<p class="eyebrow">Doc {n} · {f}</p><h1>{html.escape(title)}</h1>{body}</section>')
    page = (SITE / "shell.html").read_text()
    page = page.replace("{{TABS}}", "\n".join(buttons)).replace("{{SECTIONS}}", "\n".join(sections))
    out = ROOT / "grid_simulator_design.html"
    out.write_text(page)
    print(out, len(page) // 1024, "KB")


if __name__ == "__main__":
    main()
