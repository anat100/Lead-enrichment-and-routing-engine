"""Render the README images from the HTML templates in assets/src/.

Data comes from the repo itself: the workflow export and the generated examples,
so the images always match the code. Run after scripts/generate_examples.js.

Usage: python3 scripts/render_assets.py [name ...]   (needs Playwright + Chromium; demo GIF needs ffmpeg)
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "src"
OUT = ROOT / "assets"

STILLS = ["banner", "workflow-canvas", "score-breakdown", "slack-alert", "hubspot-note"]


def page_data():
    examples = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "examples").glob("*.json")}
    return {
        "ICONS": json.loads((SRC / "icons.json").read_text()),
        "WORKFLOW": json.loads((ROOT / "workflow" / "inbound-lead-engine-mvp.json").read_text(encoding="utf-8")),
        "EXAMPLES": examples,
    }


def open_page(browser, name, data):
    page = browser.new_page(device_scale_factor=2, viewport={"width": 1600, "height": 1000})
    page.add_init_script("".join(f"window.{k} = {json.dumps(v)};" for k, v in data.items()))
    page.goto((SRC / f"{name}.html").as_uri())
    page.evaluate("document.fonts.ready")
    return page


def render_still(browser, name, data):
    page = open_page(browser, name, data)
    page.locator("#frame").screenshot(path=str(OUT / f"{name}.png"))
    page.close()
    print("wrote", f"assets/{name}.png")


def render_demo(browser, data):
    if not shutil.which("ffmpeg"):
        print("skip demo.gif (ffmpeg not found)")
        return
    page = open_page(browser, "demo", data)
    steps = page.evaluate("window.STEPS.length")
    holds = page.evaluate("window.STEPS.map(s => s.hold)")
    with tempfile.TemporaryDirectory() as tmp:
        lines = []
        for i in range(steps):
            page.evaluate(f"window.setStep({i})")
            page.wait_for_timeout(50)
            frame = Path(tmp) / f"f{i:02d}.png"
            page.locator("#frame").screenshot(path=str(frame), scale="css")
            lines += [f"file '{frame}'", f"duration {holds[i]}"]
        lines.append(f"file '{frame}'")  # ffmpeg concat needs the last frame twice
        listing = Path(tmp) / "frames.txt"
        listing.write_text("\n".join(lines))
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-vf", "fps=10,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=none",
             "-loop", "0", str(OUT / "demo.gif")],
            check=True,
        )
    page.close()
    print("wrote assets/demo.gif")


def main():
    wanted = sys.argv[1:] or STILLS + ["demo"]
    data = page_data()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in wanted:
            render_demo(browser, data) if name == "demo" else render_still(browser, name, data)
        browser.close()


if __name__ == "__main__":
    main()
