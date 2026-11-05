#!/usr/bin/env python3
"""TG Chat Studio 的 macOS 原生外壳（PyObjC + AppKit + WebKit）。

选型理由见 docs/SystemDesign.md「桌面外壳选型」一节，摘要：

- 需求要求「真实系统毛玻璃」，只有原生 NSVisualEffectView 能做到
  `behindWindow` 采样桌面内容；CSS 的 `backdrop-filter` 只能模糊应用自身
  已绘制的内容，在纯色窗口上就是「假玻璃」。
- 界面仍是 HTML/CSS/JS，用 WKWebView 承载，因此可以继续复用
  ECharts、虚拟滚动、Playwright 自动化验收这一整套已验证的资产。
- 数据与逻辑全在 core（Python），Web 层通过本地 127.0.0.1 HTTP API 访问，
  与浏览器调试模式共用同一套接口，避免出现两套实现。

启动流程：
    1. 启动本地 API 服务（随机端口，仅绑定 127.0.0.1）；
    2. 创建 NSWindow，内容视图自下而上为 NSVisualEffectView → 透明 WKWebView；
    3. 注入 `tgchat` 消息桥，用于原生文件选择；
    4. 深色外观（NSAppearanceNameDarkAqua）强制生效，不跟随系统浅色。
"""

import json
import os
import sys
import threading
import traceback

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSColor,
    NSMenu,
    NSMenuItem,
    NSOpenPanel,
    NSScreen,
    NSViewHeightSizable,
    NSViewMaxYMargin,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialUnderWindowBackground,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject, NSURL, NSURLRequest
from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController

from core import __version__
from core.logging_setup import get_logger, setup_logging
from core.paths import default_db_path

log = get_logger("app")

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 840


# ----------------------------------------------------------------------
# 资源定位：源码运行 / PyInstaller 打包 都可用
# ----------------------------------------------------------------------
def _find_web_root():
    candidates = []

    env_root = os.environ.get("TGCHAT_WEB_ROOT")
    if env_root:
        candidates.append(env_root)

    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "web"))

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "app", "web"))
        candidates.append(os.path.join(meipass, "web"))

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "..", "Resources", "app", "web"))
        candidates.append(os.path.join(exe_dir, "..", "Resources", "web"))

    for path in candidates:
        if path and os.path.exists(os.path.join(path, "index.html")):
            return os.path.abspath(path)
    raise RuntimeError("找不到 Web 资源目录，已尝试: " + repr(candidates))


# ----------------------------------------------------------------------
# 原生桥：JS -> AppKit
# ----------------------------------------------------------------------
class MessageBridge(NSObject):
    """接收 WKWebView 的脚本消息，处理文件选择等需要原生能力的事情。"""

    def initWithWindow_(self, window):
        self = objc.super(MessageBridge, self).init()
        if self is None:
            return None
        self._window = window
        self._webview = None
        return self

    def setWebView_(self, webview):
        self._webview = webview

    def userContentController_didReceiveScriptMessage_(self, controller, message):
        try:
            body = message.body()
            action = body.get("action") if hasattr(body, "get") else None
            if action == "pick_json":
                self.pickJson()
            elif action == "log":
                log.info("前端: %s", body.get("message"))
        except Exception:
            log.error("处理脚本消息失败:\n%s", traceback.format_exc())

    def pickJson(self):
        panel = NSOpenPanel.openPanel()
        panel.setTitle_("选择 Telegram 导出的 result.json")
        panel.setMessage_("选择一个或多个 result.json（可多选，用于批量导入不同群组）")
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(True)
        panel.setAllowedFileTypes_(["json"])
        panel.setAllowsOtherFileTypes_(False)

        if panel.runModal() != 1:  # NSModalResponseOK
            return

        urls = panel.URLs()
        paths = [str(url.path()) for url in urls]
        if not paths:
            return
        log.info("用户选择文件: %s", paths)
        payload = json.dumps(paths, ensure_ascii=False)
        if self._webview is not None:
            js = f"window.__native && window.__native.pickedJson({payload});"
            self._webview.evaluateJavaScript_completionHandler_(js, None)


# ----------------------------------------------------------------------
# 应用委托
# ----------------------------------------------------------------------
class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        try:
            self._boot()
        except Exception:
            log.error("启动失败:\n%s", traceback.format_exc())
            raise

    def applicationShouldTerminateAfterLastWindowClosed_(self, sender):
        return True

    def _boot(self):
        web_root = _find_web_root()
        os.environ["TGCHAT_WEB_ROOT"] = web_root

        # core.server 在模块导入时解析 Web 资源路径，必须等环境变量就绪后再导入
        from core.server import create_server

        db_path = default_db_path()
        server, state = create_server(db_path=db_path, host="127.0.0.1", port=0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, name="api-server", daemon=True)
        thread.start()
        self._server = server
        self._state = state
        log.info("API 服务 http://127.0.0.1:%d （数据库 %s）", port, db_path)

        # ---- 窗口 ----
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskFullSizeContentView
        )
        rect = ((0, 0), (WINDOW_WIDTH, WINDOW_HEIGHT))
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        window.setTitle_("TG Chat Studio")
        window.setTitlebarAppearsTransparent_(True)
        window.setTitleVisibility_(1)  # NSWindowTitleHidden
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setMovableByWindowBackground_(True)
        window.setReleasedWhenClosed_(False)
        window.center()

        # 深色外观：强制 Dark Aqua，不跟随系统浅色设置
        appearance = NSAppearanceNamedDarkAqua()
        if appearance is not None:
            window.setAppearance_(appearance)

        content = window.contentView()

        # ---- 真实系统毛玻璃层 ----
        effect = NSVisualEffectView.alloc().initWithFrame_(content.bounds())
        effect.setAutoresizingMask_(
            NSViewWidthSizable | NSViewHeightSizable | NSViewMinYMargin | NSViewMaxYMargin
        )
        effect.setMaterial_(NSVisualEffectMaterialUnderWindowBackground)
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(NSVisualEffectStateActive)
        effect.setWantsLayer_(True)
        content.addSubview_(effect)
        self._effect = effect

        # ---- 透明 WKWebView ----
        config = WKWebViewConfiguration.alloc().init()
        controller = WKUserContentController.alloc().init()
        self._bridge = MessageBridge.alloc().initWithWindow_(window)
        controller.addScriptMessageHandler_name_(self._bridge, "tgchat")
        config.setUserContentController_(controller)

        webview = WKWebView.alloc().initWithFrame_configuration_(content.bounds(), config)
        webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        webview.setValue_forKey_(False, "drawsBackground")
        webview.setValue_forKey_(False, "opaque")
        content.addSubview_(webview)
        self._bridge.setWebView_(webview)
        self._webview = webview

        url = NSURL.URLWithString_(f"http://127.0.0.1:{port}/")
        webview.loadRequest_(NSURLRequest.requestWithURL_(url))

        window.makeKeyAndOrderFront_(None)
        window.makeFirstResponder_(webview)
        NSApp.activateIgnoringOtherApps_(True)

        self._window = window
        self._content = content

    def applicationWillTerminate_(self, notification):
        try:
            if getattr(self, "_server", None) is not None:
                self._server.shutdown()
            if getattr(self, "_state", None) is not None:
                self._state.db.close()
            log.info("已退出")
        except Exception:
            log.error("退出清理失败:\n%s", traceback.format_exc())


def NSAppearanceNamedDarkAqua():
    from AppKit import NSAppearance

    return NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")


# ----------------------------------------------------------------------
# 菜单（保证 ⌘Q / ⌘W 可用）
# ----------------------------------------------------------------------
def build_menu():
    main_menu = NSMenu.alloc().init()

    app_item = NSMenuItem.alloc().init()
    main_menu.addItem_(app_item)
    app_menu = NSMenu.alloc().init()

    app_name = "TG Chat Studio"
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        f"退出 {app_name}", "terminate:", "q"
    )
    app_menu.addItem_(quit_item)
    app_item.setSubmenu_(app_menu)

    edit_item = NSMenuItem.alloc().init()
    main_menu.addItem_(edit_item)
    edit_menu = NSMenu.alloc().initWithTitle_("编辑")
    for title, action, key in (
        ("撤销", "undo:", "z"),
        ("重做", "redo:", "Z"),
        ("剪切", "cut:", "x"),
        ("拷贝", "copy:", "c"),
        ("粘贴", "paste:", "v"),
        ("全选", "selectAll:", "a"),
    ):
        edit_menu.addItem_(
            NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        )
    edit_item.setSubmenu_(edit_menu)

    NSApp.setMainMenu_(main_menu)


def main():
    setup_logging()
    log.info("TG Chat Studio v%s 启动（Python %s）", __version__, sys.version.split()[0])

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    build_menu()

    # 保持引用，避免 delegate 被回收
    globals()["_delegate_ref"] = delegate

    app.run()


if __name__ == "__main__":
    main()
