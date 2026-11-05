#!/usr/bin/env python3
"""实测 TG Chat Studio（新 UI）在 20 万+ 消息下的渲染与滚动性能。

指标：
- first_render_ms：导航开始 → 首批虚拟节点进入 DOM
- deep_page_ms：跳到第 201 页（服务端 OFFSET 100000）并完成首批渲染的耗时
- fps_avg / fps_p95 / frame_p95_ms：持续滚动期间的帧率
- heap_mb：JS 堆占用（Chrome 限定）
- rendered_nodes：虚拟滚动窗口内实际节点数

用法：
    python3 scripts/bench_studio.py --url http://127.0.0.1:8765 --json
"""

import argparse
import json
import time

from playwright.sync_api import sync_playwright


def measure(url: str, scroll_ms: int, channel: str = "chrome"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=channel)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        start = time.perf_counter()
        page.goto(url, wait_until="load")
        page.wait_for_function(
            "() => window.__studio && window.__studio.getState().renderedNodes > 0",
            timeout=180000,
        )
        first_render_ms = (time.perf_counter() - start) * 1000

        state = page.evaluate("() => window.__studio.getState()")
        heap = page.evaluate(
            "() => (performance.memory ? performance.memory.usedJSHeapSize / 1048576 : null)"
        )

        # 深分页：跳到一个 OFFSET 很大的页。必须等待对应的 API 请求完成，
        # 否则 renderedNodes 仍是上一页的，会得到失真的耗时。
        jump_start = time.perf_counter()
        with page.expect_response(
            lambda r: "/api/messages" in r.url and "offset=100000" in r.url,
            timeout=60000,
        ):
            page.evaluate("() => window.__studio.goToPage(201)")
        page.wait_for_function(
            "() => window.__studio.getState().page === 201 && window.__studio.getState().renderedNodes > 0",
            timeout=60000,
        )
        deep_page_ms = (time.perf_counter() - jump_start) * 1000
        deep_state = page.evaluate("() => window.__studio.getState()")

        # 回到第 1 页，测量持续滚动帧率
        page.evaluate("() => window.__studio.goToPage(1)")
        page.wait_for_timeout(1200)

        result = page.evaluate(
            """(opts) => new Promise((resolve) => {
                const canvas = document.getElementById('chatCanvas');
                const frames = [];
                let last = performance.now();
                const started = last;
                const step = opts.step;
                function tick(now) {
                    frames.push(now - last);
                    last = now;
                    canvas.scrollTop += step;
                    if (now - started < opts.duration) {
                        requestAnimationFrame(tick);
                    } else {
                        resolve({
                            frames,
                            scrollTop: canvas.scrollTop,
                            nodes: window.__studio.getState().renderedNodes
                        });
                    }
                }
                requestAnimationFrame(tick);
            })""",
            {"duration": scroll_ms, "step": 500},
        )

        frames = [f for f in result["frames"] if f > 0]
        total = sum(frames) / 1000.0
        fps_avg = len(frames) / total if total else 0
        ordered = sorted(frames)
        p95 = ordered[int(len(ordered) * 0.95) - 1] if ordered else 0
        fps_p95 = 1000.0 / p95 if p95 else 0

        heap_after = page.evaluate(
            "() => (performance.memory ? performance.memory.usedJSHeapSize / 1048576 : null)"
        )

        browser.close()

    return {
        "first_render_ms": round(first_render_ms, 1),
        "deep_page_ms": round(deep_page_ms, 1),
        "fps_avg": round(fps_avg, 1),
        "fps_p95": round(fps_p95, 1),
        "frame_p95_ms": round(p95, 2),
        "frames": len(frames),
        "heap_mb_before_scroll": round(heap, 1) if heap else None,
        "heap_mb_after_scroll": round(heap_after, 1) if heap_after else None,
        "rendered_nodes": result["nodes"],
        "scrolled_px": result["scrollTop"],
        "total_messages": state.get("total"),
        "page2_state": deep_state,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--channel", default="chrome")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    stats = measure(args.url, int(args.seconds * 1000), args.channel)
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(f"首屏渲染: {stats['first_render_ms']} ms")
        print(f"深分页（OFFSET 100000）: {stats['deep_page_ms']} ms")
        print(f"滚动平均帧率: {stats['fps_avg']} FPS，P95 帧率: {stats['fps_p95']} FPS")
        print(f"P95 帧耗时: {stats['frame_p95_ms']} ms，采样帧数: {stats['frames']}")
        print(f"JS 堆: {stats['heap_mb_before_scroll']} → {stats['heap_mb_after_scroll']} MB")
        print(f"渲染节点: {stats['rendered_nodes']}，总消息: {stats['total_messages']}")


if __name__ == "__main__":
    main()
