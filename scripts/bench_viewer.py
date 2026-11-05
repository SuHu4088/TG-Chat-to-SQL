#!/usr/bin/env python3
"""用 Playwright + Chromium 实测聊天查看器的大数据性能。

指标：
- first_render_ms：从页面导航开始到首批消息进入 DOM 的耗时
- fps_avg / fps_p95 / frame_p95_ms：持续滚动期间的帧率
- heap_mb：JS 堆占用（Chrome 限定）
- rendered_nodes：虚拟滚动实际渲染的节点数

用法：
    python3 scripts/bench_viewer.py --url http://127.0.0.1:8099/ --json
"""

import argparse
import json
import statistics
import time

from playwright.sync_api import sync_playwright


def measure(url: str, scroll_seconds: float, duration_ms: int, channel: str = "chrome"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=channel)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        start = time.perf_counter()
        page.goto(url, wait_until="load")
        # 等待查看器真正把消息渲染出来
        page.wait_for_function(
            "() => window.__viewer && window.__viewer.getState().renderedNodes > 0",
            timeout=180000,
        )
        first_render_ms = (time.perf_counter() - start) * 1000

        state = page.evaluate("() => window.__viewer.getState()")
        heap = page.evaluate(
            "() => (performance.memory ? performance.memory.usedJSHeapSize / 1048576 : null)"
        )

        # 采样滚动帧率：固定速度向下滚动，记录每帧间隔
        result = page.evaluate(
            """(opts) => new Promise((resolve) => {
                const container = document.getElementById('chatMessages');
                const frames = [];
                let last = performance.now();
                const started = last;
                const step = opts.step;
                function tick(now) {
                    frames.push(now - last);
                    last = now;
                    container.scrollTop += step;
                    if (now - started < opts.duration) {
                        requestAnimationFrame(tick);
                    } else {
                        resolve({
                            frames,
                            scrollTop: container.scrollTop,
                            renderedNodes: window.__viewer.getState().renderedNodes
                        });
                    }
                }
                requestAnimationFrame(tick);
            })""",
            {"duration": duration_ms, "step": 600},
        )

        frames = [f for f in result["frames"] if f > 0]
        total = sum(frames) / 1000.0
        fps_avg = len(frames) / total if total else 0
        sorted_frames = sorted(frames)
        p95 = sorted_frames[int(len(sorted_frames) * 0.95) - 1] if sorted_frames else 0
        fps_p95 = 1000.0 / p95 if p95 else 0

        browser.close()

    return {
        "first_render_ms": round(first_render_ms, 1),
        "fps_avg": round(fps_avg, 1),
        "fps_p95": round(fps_p95, 1),
        "frame_p95_ms": round(p95, 2),
        "frames": len(frames),
        "heap_mb": round(heap, 1) if heap else None,
        "rendered_nodes": result["renderedNodes"],
        "scrolled_px": result["scrollTop"],
        "viewer_state": state,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8099/")
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--channel", default="chrome", help="Playwright 浏览器通道，默认系统 Chrome")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    stats = measure(args.url, args.seconds, int(args.seconds * 1000), args.channel)
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(f"首屏渲染: {stats['first_render_ms']} ms")
        print(f"滚动平均帧率: {stats['fps_avg']} FPS，P95 帧率: {stats['fps_p95']} FPS")
        print(f"P95 帧耗时: {stats['frame_p95_ms']} ms，采样帧数: {stats['frames']}")
        print(f"JS 堆: {stats['heap_mb']} MB，渲染节点: {stats['rendered_nodes']}")


if __name__ == "__main__":
    main()
