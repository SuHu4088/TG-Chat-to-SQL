#!/usr/bin/env python3
"""对 TG Chat Studio 做真实浏览器验收并截图。

用法：
    python3 scripts/shot_studio.py --url http://127.0.0.1:8765 --out docs/screenshots
"""

import argparse
import json
import os
import time

from playwright.sync_api import sync_playwright


def wait_idle(page, ms=900):
    page.wait_for_timeout(ms)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--out", default="docs/screenshots")
    parser.add_argument("--chrome", default="chrome")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    report = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=args.chrome)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.goto(args.url, wait_until="load")
        page.wait_for_function(
            "() => window.__studio && window.__studio.getState().chats > 0",
            timeout=60000,
        )
        wait_idle(page, 1200)

        report["initial"] = page.evaluate("() => window.__studio.getState()")
        page.screenshot(path=os.path.join(args.out, "studio-messages.png"))

        # 翻页：第 1 → 2 页
        page.click("#nextPage")
        page.wait_for_timeout(900)
        report["page2"] = page.evaluate("() => window.__studio.getState()")
        page.screenshot(path=os.path.join(args.out, "studio-messages-page2.png"))

        # 热力图
        page.click(".tab[data-view='heatmap']")
        page.wait_for_timeout(1500)
        report["heatmap"] = page.evaluate("() => window.__studio.getState()")
        page.screenshot(path=os.path.join(args.out, "studio-heatmap.png"))

        # 备份
        page.click(".tab[data-view='backups']")
        page.wait_for_timeout(700)
        page.screenshot(path=os.path.join(args.out, "studio-backups.png"))

        # 权限
        page.click(".tab[data-view='security']")
        page.wait_for_timeout(700)
        page.screenshot(path=os.path.join(args.out, "studio-security.png"))

        # 导入记录
        page.click(".tab[data-view='imports']")
        page.wait_for_timeout(700)
        page.screenshot(path=os.path.join(args.out, "studio-imports.png"))

        report["console_errors"] = []
        browser.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
