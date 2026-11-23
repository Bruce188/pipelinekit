#!/usr/bin/env python3
"""Drive every docs-writer widget in headless Chromium and assert it reacts.

Renders a fixture that embeds every snippet (plus code, table, callout,
<details>), once in batch mode (2 pages + search.json) and once in single-page
mode, opens the output over file:// and uses each widget the way a reader
would: click, drag, type, keyboard. Any console error or uncaught page error
fails the check that caused it.

    python3 tests/test_interactive.py        # exit 0 = all pass, 1 = failures
Prints SKIP and exits 0 when playwright (or its Chromium) is not installed.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP  test_interactive: python playwright not installed (pip install playwright && playwright install chromium)")
    sys.exit(0)

SKILL_DIR = Path(__file__).resolve().parent.parent
RENDER = SKILL_DIR / "render.py"

INDEX_MD = """# Project docs

Start here: an index of every page with a cross-page search box.

<div data-snippet="search-widget"></div>

## Pages

See [widgets](widgets.html) for the interactive reference.
"""

TERM_STEPS = [
    {"type": "ps1", "text": "$ "},
    {"type": "cmd", "text": "deployctl push --env staging\n"},
    {"type": "out-info", "text": "Uploading 3 artefacts...\n"},
    {"type": "pause", "ms": 100},
    {"type": "out-success", "text": "Deployed build 42 to staging\n"},
    {"type": "ps1", "text": "$ "},
    {"type": "cmd", "text": "deployctl status\n"},
    {"type": "out-stdout", "text": "staging: healthy (build 42)\n"},
]
TERM_TRANSCRIPT = "".join(s.get("text", "") for s in TERM_STEPS)


# Kept out of the f-string below: Python < 3.12 forbids backslashes in f-string expressions.
LINTER = {"label": "Paste a release note title",
          "rules": [
              {"name": "Conventional type", "pattern": r"^(feat|fix|docs|chore)(\(.+\))?: ", "hint": "Start with feat:, fix:, ..."},
              {"name": "No trailing period", "pattern": r"\.$", "flags": "gm", "mode": "forbid", "level": "warn", "hint": "Drop the final period."}],
          "example": "fix: roll back build 42"}


def j(obj) -> str:
    return json.dumps(obj, indent=1)


WIDGETS_MD = f"""# Deployment reference

Rollback, promote and inspect deployments with deployctl.

<div data-snippet="tutorial-cards">
<script type="application/json">
{j([{"anchor": "rolling-back", "label": "HOW-TO 1", "title": "Roll back", "desc": "Return to the previous build.", "level": "easy", "badges": ["Easy", "~2 min"]},
    {"anchor": "command-reference", "label": "REFERENCE", "title": "Commands", "desc": "Every deployctl subcommand.", "badges": ["Lookup"]}])}
</script>
</div>

## Choosing a target

<div data-snippet="comparison-tabs" data-home-label="default">
<script type="application/json">
{j({"home": "vm", "items": {
    "vm": {"name": "Virtual machine", "icon": "V", "rows": {"Cold start": "none", "Cost": "fixed"}},
    "k8s": {"name": "Kubernetes", "icon": "K", "rows": {"Cold start": "seconds", "Cost": "per node"}},
    "fn": {"name": "Functions", "icon": "F", "rows": {"Cold start": "100 ms+", "Cost": "per call"}}}})}
</script>
</div>

<div data-snippet="chooser-quiz">
<script type="application/json">
{j({"title": "Which target fits?",
    "questions": [
      {"key": "traffic", "prompt": "Traffic pattern?", "options": [{"value": "steady", "label": "Steady"}, {"value": "spiky", "label": "Spiky", "hint": "bursts"}]},
      {"key": "ops", "prompt": "Ops team?", "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]}],
    "recommend": [
      {"match": {"traffic": "spiky", "ops": "no"}, "pick": "Functions", "why": "Scales to zero.", "runners": ["fn"]},
      {"match": {"traffic": "steady", "ops": "yes"}, "pick": "Kubernetes", "why": "Steady load, team to run it."},
      {"match": {}, "pick": "Virtual machine", "why": "Simplest default.", "link": "#choosing-a-target"}]})}
</script>
</div>

## Architecture

<div data-snippet="architecture-diagram">
<script type="application/json">
{j({"layers": [
    {"name": "Clients", "color": "#10b981", "count": "2 apps", "chips": [{"label": "web", "tip": "Single-page app"}, {"label": "cli", "tip": "deployctl binary"}]},
    {"name": "API", "color": "#3b82f6", "chips": [{"label": "gateway", "tip": "Auth and routing"}]},
    {"name": "Data", "color": "#f59e0b", "chips": [{"label": "postgres", "tip": "Build metadata"}]}]})}
</script>
</div>

## Rolling back

A rollback swaps the live build for the previous one.

<div data-snippet="before-after-slider">
<div data-bas-before><p>BEFORE-STATE build 42 live</p></div>
<div data-bas-after><p>AFTER-STATE build 41 live</p></div>
</div>

<div data-snippet="terminal-simulator" data-title="deploy session">
<script type="application/json">
{j(TERM_STEPS)}
</script>
</div>

```bash
deployctl rollback --to previous
```

> [TIP] Read the [status page](#command-reference) before rolling back.

<details>
<summary>Why not redeploy?</summary>
<p>HIDDEN-DETAIL a redeploy rebuilds from source.</p>
</details>

## Command reference

<div data-snippet="command-cheatsheet" data-label="deployctl commands">
<script type="application/json">
{j([{"name": "push", "args": "--env ENV", "description": "Upload and deploy a build."},
    {"name": "rollback", "args": "--to BUILD", "description": "Restore an earlier build."},
    {"name": "status", "args": "", "description": "Show live build health."},
    {"name": "promote", "args": "FROM TO", "description": "Copy a build between environments."}])}
</script>
</div>

| Flag | Default |
|------|---------|
| --env | staging |
| --dry-run | false |
| --apply | true |

### Commit messages

<div data-snippet="live-linter">
<script type="application/json">
{j(LINTER)}
</script>
</div>

### Config playground

<div data-snippet="playground-2col">
<script type="application/json">
{j({"title": "Config to plan", "left_label": "deploy.toml", "right_label": "Plan",
    "presets": [{"label": "staging", "left": "env = 'staging'", "right": "1 node", "note": "Staging uses <code>1</code> node."},
                {"label": "prod", "left": "env = 'prod'", "right": "3 nodes", "note": "PROD-NOTE three nodes."}]})}
</script>
</div>

### Search

<div data-snippet="search-widget"></div>

## Appendix

Closing words.
"""


def render(proj: Path) -> None:
    """Batch-render the 2-page project, then single-render widgets.md over it
    (SKILL.md step 3, then step 2)."""
    src = proj / "docs-source"
    src.mkdir(parents=True)
    (src / "index.md").write_text(INDEX_MD)
    (src / "widgets.md").write_text(WIDGETS_MD)
    subprocess.run([sys.executable, str(RENDER), "--root", str(proj)], check=True, capture_output=True)
    index = json.loads((proj / "documentation" / "search.json").read_text())
    assert {r["slug"] for r in index} == {"index", "widgets"}, index
    subprocess.run([sys.executable, str(RENDER), str(src / "widgets.md"), str(proj / "documentation" / "widgets.html")],
                   check=True, capture_output=True)


# ---------------------------------------------------------------- checks
# Each check gets a fresh page already at widgets.html (or index.html).

def check_tabs(page):
    tabs = page.locator(".pkit-cmp-tab")
    assert tabs.count() == 2
    right = page.locator(".pkit-cmp-col:not(.home) h4")
    assert "Kubernetes" in right.inner_text()
    tabs.nth(1).click()
    assert "Functions" in right.inner_text(), "click did not switch the panel"
    assert "per call" in page.locator(".pkit-cmp-col:not(.home)").inner_text()
    # Keyboard: focus first tab, Enter switches, focus stays on a tab so Tab/arrows keep working.
    tabs.nth(0).focus()
    page.keyboard.press("Enter")
    assert "Kubernetes" in right.inner_text(), "Enter did not switch the panel"
    focused = page.evaluate("document.activeElement.className")
    assert "pkit-cmp-tab" in focused, f"focus lost after activating a tab (now on {focused!r})"
    page.keyboard.press("ArrowRight")
    assert "Functions" in right.inner_text(), "ArrowRight did not move to the next tab"
    assert page.evaluate("document.activeElement.dataset.key") == "fn"
    assert page.locator('.pkit-cmp-tab[aria-selected="true"]').inner_text().strip().endswith("Functions")


def check_slider(page):
    root = page.locator(".pkit-bas")
    root.scroll_into_view_if_needed()
    assert "AFTER-STATE" in root.locator(".pkit-bas__layer--after").inner_text()
    assert "BEFORE-STATE" in root.locator(".pkit-bas__layer--before").inner_text()
    clip = lambda: page.evaluate("getComputedStyle(document.querySelector('.pkit-bas__layer--after')).clipPath")
    rng = root.locator(".pkit-bas__range")
    assert rng.input_value() == "50" and "50%" in clip()
    # Keyboard
    rng.focus()
    for _ in range(5):
        page.keyboard.press("ArrowRight")
    assert rng.input_value() == "55", rng.input_value()
    page.wait_for_function("getComputedStyle(document.querySelector('.pkit-bas__layer--after')).clipPath.includes('45%')")
    # Drag the range thumb
    box = rng.bounding_box()
    y = box["y"] + box["height"] / 2
    page.mouse.move(box["x"] + box["width"] * 0.55, y)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.85, y, steps=5)
    page.mouse.up()
    assert int(rng.input_value()) >= 80, f"thumb drag: value {rng.input_value()}"
    # Drag the handle on the picture itself
    vp = root.locator(".pkit-bas__viewport").bounding_box()
    hy = vp["y"] + vp["height"] / 2
    page.mouse.move(vp["x"] + vp["width"] * 0.85, hy)
    page.mouse.down()
    page.mouse.move(vp["x"] + vp["width"] * 0.2, hy, steps=5)
    page.mouse.up()
    v = int(rng.input_value())
    assert 15 <= v <= 25, f"dragging the handle in the picture did not move the slider (value {v})"
    left = page.evaluate("document.querySelector('.pkit-bas__handle').style.left")
    assert left == f"{v}%", left


def check_quiz(page):
    q = page.locator(".pkit-chooser")
    assert q.locator(".pkit-cq-title").inner_text() == "Which target fits?"
    assert "1 of 2" in q.locator("[data-cq-progress]").inner_text()
    q.locator(".pkit-cq-option", has_text="Spiky").click()
    assert "2 of 2" in q.locator("[data-cq-progress]").inner_text()
    q.locator('[data-act="back"]').click()
    assert "1 of 2" in q.locator("[data-cq-progress]").inner_text()
    q.locator(".pkit-cq-option", has_text="Spiky").click()
    q.locator(".pkit-cq-option", has_text="No").click()
    assert "Functions" in q.locator(".pkit-cq-r-pick").inner_text()
    assert "traffic=spiky" in q.locator(".pkit-cq-trail").inner_text()
    q.locator('[data-act="restart"]').click()
    q.locator(".pkit-cq-option", has_text="Steady").click()
    q.locator(".pkit-cq-option", has_text="No").click()
    assert "Virtual machine" in q.locator(".pkit-cq-r-pick").inner_text(), "fallback recommendation not shown"


def check_terminal(page):
    t = page.locator(".pkit-term")
    screen = t.locator("[data-tm-screen]")
    btn = lambda a: t.locator(f'[data-act="{a}"]')
    assert t.locator("[data-tm-title]").inner_text() == "deploy session"
    # Auto-plays once scrolled into view
    t.scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('[data-tm-screen]').textContent.length > 3", timeout=3000)
    # Restart, then step through prompt + command: the command must be typed out.
    btn("restart").click()
    assert screen.text_content() == ""
    btn("step").click()
    btn("step").click()
    page.wait_for_function(
        "document.querySelector('[data-tm-screen]').textContent === '$ deployctl push --env staging\\n'", timeout=5000)
    # Restart + immediate Play must not run two playbacks at once (duplicated output)
    btn("play").click()
    page.wait_for_timeout(150)
    btn("restart").click()
    btn("speed").click(); btn("speed").click()  # 4x
    assert btn("speed").inner_text() == "4×"
    btn("play").click()
    # Pause mid-way, then resume: no characters may be lost
    page.wait_for_timeout(120)
    btn("pause").click()
    assert btn("play").is_enabled() and btn("pause").is_disabled()
    # A pause in the middle of a command completes that line on the next typing
    # tick, so let it land before taking the reference text.
    page.wait_for_timeout(150)
    paused_at = screen.text_content()
    page.wait_for_timeout(200)
    assert screen.text_content() == paused_at, "output kept changing while paused"
    btn("play").click()
    page.wait_for_function("document.querySelector('[data-tm-progress]').style.width === '100%'", timeout=10000)
    page.wait_for_function("!document.querySelector('.pkit-term [data-act=\"play\"]').disabled", timeout=5000)
    page.wait_for_timeout(300)
    assert screen.text_content() == TERM_TRANSCRIPT, f"transcript mismatch:\n{screen.text_content()!r}"


def check_cheatsheet(page):
    c = page.locator(".pkit-cmd")
    assert c.locator("tbody tr").count() == 4
    assert c.locator("[data-cmd-count]").inner_text() == "4 / 4"
    c.locator(".pkit-cmd-filter").fill("rollback")
    page.wait_for_function("document.querySelector('[data-cmd-count]').textContent === '1 / 4'")
    assert c.locator("tbody tr:visible").count() == 1
    assert "rollback" in c.locator("tbody tr:visible").inner_text()
    c.locator(".pkit-cmd-filter").fill("zzzz")
    c.locator("[data-cmd-empty]").wait_for(state="visible")
    c.locator(".pkit-cmd-filter").fill("")
    page.wait_for_function("document.querySelector('[data-cmd-count]').textContent === '4 / 4'")
    assert c.locator("table").get_attribute("aria-label") == "deployctl commands"


def check_linter(page):
    lt = page.locator(".pkit-linter")
    ta = lt.locator("[data-ll-input]")
    grade = lt.locator("[data-ll-grade]")
    assert grade.text_content() == "no input"
    ta.fill("Updated stuff.")
    page.wait_for_function("document.querySelector('[data-ll-grade]').textContent === '1 failing'")
    assert lt.locator(".badge.fail").count() == 1 and lt.locator(".badge.warn").count() == 1
    assert "Start with feat:" in lt.locator("[data-ll-rows]").inner_text()
    # Same verdict on every keystroke, even with a /g rule (stateful lastIndex)
    for text in ["fix: a.", "fix: ab.", "fix: abc."]:
        ta.fill(text)
        page.wait_for_function(f"document.querySelector('[data-ll-input]').value === {text!r}")
        page.wait_for_timeout(200)
        assert grade.text_content() == "warnings only", f"{text!r}: {grade.text_content()}"
    lt.locator('[data-act="example"]').click()
    assert grade.text_content() == "all clear"
    lt.locator('[data-act="clear"]').click()
    assert ta.input_value() == "" and grade.text_content() == "no input"


def check_playground(page):
    pg = page.locator(".pkit-pg2")
    left, right = pg.locator("[data-p2-left]"), pg.locator("[data-p2-right]")
    assert left.input_value() == "env = 'staging'" and right.input_value() == "1 node"
    pg.locator(".pkit-p2-preset", has_text="prod").click()
    assert left.input_value() == "env = 'prod'" and right.input_value() == "3 nodes"
    assert "PROD-NOTE" in pg.locator("[data-p2-note]").inner_text()
    assert "active" in pg.locator(".pkit-p2-preset", has_text="prod").get_attribute("class")
    left.fill("env = 'mine'")
    assert left.input_value() == "env = 'mine'"


def heading_near_top(page, hid):
    return page.evaluate(f"(() => {{ const r = document.getElementById('{hid}').getBoundingClientRect(); return r.top >= 0 && r.top < 200; }})()")


def check_tutorial_cards(page):
    cards = page.locator(".pkit-tc-card")
    assert cards.count() == 2
    cards.nth(1).click()
    page.wait_for_function("location.hash === '#command-reference'")
    page.wait_for_function("(() => { const r = document.getElementById('command-reference').getBoundingClientRect(); return r.top >= 0 && r.top < 200; })()")
    cards.nth(0).scroll_into_view_if_needed()
    cards.nth(0).focus()
    page.keyboard.press("Enter")
    page.wait_for_function("location.hash === '#rolling-back'")


def check_diagram(page):
    d = page.locator(".pkit-arch-diagram")
    assert d.locator(".pkit-ad-layer").count() == 3
    d.locator(".pkit-ad-layer-btn", has_text="API").click()
    dimmed = d.locator(".pkit-ad-layer.dimmed")
    assert dimmed.count() == 2
    page.wait_for_function("parseFloat(getComputedStyle(document.querySelector('.pkit-ad-layer.dimmed')).opacity) < 0.6")
    d.locator(".pkit-ad-layer-btn", has_text="All").click()
    assert dimmed.count() == 0
    tip_opacity = "getComputedStyle(document.querySelectorAll('.pkit-ad-tooltip')[2]).opacity"
    page.wait_for_function(f"{tip_opacity} === '0'")
    d.locator(".pkit-ad-chip", has_text="gateway").hover()
    page.wait_for_function(f"{tip_opacity} === '1'")
    page.mouse.move(0, 0)
    d.locator(".pkit-ad-chip", has_text="postgres").focus()  # keyboard users
    page.wait_for_function("getComputedStyle(document.querySelectorAll('.pkit-ad-tooltip')[3]).opacity === '1'")


def check_toc(page):
    link = page.locator('.toc a[href="#command-reference"]')
    link.click()
    page.wait_for_function("location.hash === '#command-reference'")
    page.wait_for_function("(() => { const r = document.getElementById('command-reference').getBoundingClientRect(); return r.top >= 0 && r.top < 200; })()")
    page.wait_for_function("document.querySelector('.toc a.active') && document.querySelector('.toc a.active').getAttribute('href') === '#command-reference'",
                           timeout=3000)
    page.locator('.toc a[href="#architecture"]').click()
    page.wait_for_function("document.querySelector('.toc a.active').getAttribute('href') === '#architecture'", timeout=3000)
    # Heading permalink
    page.locator("#rolling-back a.anchor").click()
    page.wait_for_function("location.hash === '#rolling-back'")


def check_mobile_toc(page):
    page.set_viewport_size({"width": 600, "height": 800})
    toc = page.locator("#toc")
    assert not toc.is_visible()
    page.locator("#toc-toggle").click()
    assert toc.is_visible()
    toc.locator('a[href="#appendix"]').click()
    assert not toc.is_visible()
    page.wait_for_function("location.hash === '#appendix'")


def check_theme(page):
    bg = lambda: page.evaluate("getComputedStyle(document.body).backgroundColor")
    label = page.locator("#theme-label")
    assert label.inner_text() == "Auto"
    page.locator("#theme-toggle").click()
    assert label.inner_text() == "Light" and page.evaluate("document.documentElement.dataset.theme") == "light"
    light = bg()
    page.locator("#theme-toggle").click()
    assert label.inner_text() == "Dark" and page.evaluate("document.documentElement.dataset.theme") == "dark"
    page.wait_for_timeout(300)  # background may transition
    assert bg() != light, "dark theme did not change the background"
    page.reload()
    assert page.locator("#theme-label").inner_text() == "Dark", "theme not persisted across reload"
    page.locator("#theme-toggle").click()
    assert page.locator("#theme-label").inner_text() == "Auto"
    assert page.evaluate("document.documentElement.dataset.theme") is None


def check_copy_code(page):
    pre = page.locator("#page-content pre", has_text="deployctl rollback")
    pre.hover()
    btn = pre.locator(".copy-btn")
    btn.click()
    page.wait_for_function("document.querySelector('#page-content pre .copy-btn.copied') !== null")
    assert "Copied" in btn.inner_text()
    clip = page.evaluate("navigator.clipboard.readText()")
    assert clip.strip() == "deployctl rollback --to previous", repr(clip)


def check_sortable_table(page):
    table = page.locator("#page-content > .table-wrap table, #page-content table:not(.pkit-cmd-table)").first
    first_col = lambda: [c.strip() for c in table.locator("tbody tr td:first-child").all_inner_texts()]
    assert first_col() == ["--env", "--dry-run", "--apply"]
    table.locator("th", has_text="Flag").click()
    assert first_col() == ["--apply", "--dry-run", "--env"]
    table.locator("th", has_text="Flag").click()
    assert first_col() == ["--env", "--dry-run", "--apply"]


def check_page_search(page):
    content = page.locator("#page-content")
    before = content.text_content()
    page.keyboard.press("/")
    assert page.evaluate("document.activeElement.id") == "page-search", "/ did not focus the filter"
    page.keyboard.type("rollback")
    page.wait_for_function("document.querySelectorAll('#page-content .search-hit').length > 0")
    assert content.text_content() == before, "highlighting changed the page text"
    assert page.locator(".search-hit").first.inner_text().lower() == "rollback"
    assert page.locator("#page-content table:not(.pkit-cmd-table) tbody tr:visible").count() == 0  # flag table has no hit
    page.keyboard.press("Escape")
    page.wait_for_function("document.querySelectorAll('#page-content .search-hit').length === 0")
    assert content.text_content() == before
    page.locator("#page-search").fill("qqqxyz")
    page.locator("#no-results").wait_for(state="visible")


def check_details_and_callout(page):
    det = page.locator("#page-content details")
    hidden = det.locator("p", has_text="HIDDEN-DETAIL")
    assert not hidden.is_visible()
    det.locator("summary").click()
    assert hidden.is_visible()
    callout = page.locator(".callout")
    assert callout.count() == 1 and "Read the" in callout.inner_text()
    assert "[TIP]" not in callout.inner_text()
    link = callout.locator('a[href="#command-reference"]')
    assert link.count() == 1, "callout lost its inline link"
    link.click()
    page.wait_for_function("location.hash === '#command-reference'")


def check_search_widget(page):
    """index.html (batch mode): cross-page search over search.json."""
    inp = page.locator("#docs-search")
    inp.fill("rollback")
    hit = page.locator("#docs-search-results a", has_text="Deployment reference")
    hit.wait_for(timeout=3000)
    inp.fill("project")
    page.locator("#docs-search-results a", has_text="Project docs").wait_for(timeout=3000)
    inp.fill("roll")  # prefix match
    hit.wait_for(timeout=3000)
    hit.click()
    page.wait_for_url("**/widgets.html")
    assert page.locator(".page-header h1").inner_text() == "Deployment reference"


def check_search_widget_single(page):
    """widgets.html (single-page render next to search.json) can search too."""
    page.locator("#docs-search").fill("project")
    page.locator("#docs-search-results a", has_text="Project docs").wait_for(timeout=3000)


CHECKS = [
    ("comparison-tabs", "widgets", check_tabs),
    ("before-after-slider", "widgets", check_slider),
    ("chooser-quiz", "widgets", check_quiz),
    ("terminal-simulator", "widgets", check_terminal),
    ("command-cheatsheet", "widgets", check_cheatsheet),
    ("live-linter", "widgets", check_linter),
    ("playground-2col", "widgets", check_playground),
    ("tutorial-cards", "widgets", check_tutorial_cards),
    ("architecture-diagram", "widgets", check_diagram),
    ("search-widget (batch index)", "index", check_search_widget),
    ("search-widget (single render)", "widgets", check_search_widget_single),
    ("toc + scrollspy + permalinks", "widgets", check_toc),
    ("mobile toc drawer", "widgets", check_mobile_toc),
    ("theme toggle", "widgets", check_theme),
    ("copy-code button", "widgets", check_copy_code),
    ("sortable table", "widgets", check_sortable_table),
    ("in-page filter", "widgets", check_page_search),
    ("details + callout", "widgets", check_details_and_callout),
]


def launch(p):
    """Playwright's pinned Chromium, else any Chromium already in the playwright
    cache (the pip package and the downloaded browser often differ in version)."""
    try:
        return p.chromium.launch()
    except Exception as exc:
        first_err = str(exc).splitlines()[0]
    cache = Path.home() / ".cache" / "ms-playwright"
    for exe in sorted(cache.glob("chromium*/chrome*/chrome*"), reverse=True):
        if exe.name in ("chrome", "chrome-headless-shell", "headless_shell"):
            try:
                return p.chromium.launch(executable_path=str(exe))
            except Exception:
                continue
    print(f"SKIP  test_interactive: chromium not available ({first_err})")
    return None


def main() -> int:
    only = set(sys.argv[1:])
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp)
        render(proj)
        docs = proj / "documentation"
        with sync_playwright() as p:
            browser = launch(p)
            if browser is None:
                return 0
            failed = 0
            for name, pg, fn in CHECKS:
                if only and not any(o in name for o in only):
                    continue
                ctx = browser.new_context(viewport={"width": 1280, "height": 900})
                ctx.grant_permissions(["clipboard-read", "clipboard-write"])
                page = ctx.new_page()
                page.set_default_timeout(5000)
                errors: list[str] = []
                page.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))
                page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
                try:
                    page.goto((docs / f"{pg}.html").as_uri())
                    fn(page)
                    page.wait_for_timeout(50)
                    assert not errors, "; ".join(errors)
                    print(f"  PASS  {name}")
                except Exception as exc:
                    failed += 1
                    msg = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
                    if errors:
                        msg += " | " + "; ".join(errors)
                    print(f"  FAIL  {name}: {msg}")
                    if "-v" in only:
                        traceback.print_exc()
                finally:
                    ctx.close()
            browser.close()
    print(f"\ntest_interactive: {len(CHECKS) - failed if not only else '?'} pass, {failed} fail")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
