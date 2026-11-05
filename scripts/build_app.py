#!/usr/bin/env python3
"""打包 macOS arm64 独立应用（PyInstaller）。

用法：
    .venv/bin/python scripts/build_app.py

产物：
    dist/TG Chat Studio.app
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_NAME = "TG Chat Studio"
ICON = os.path.join(ROOT, "build", "AppIcon.icns")


def main():
    os.chdir(ROOT)
    if not os.path.exists(ICON):
        subprocess.run([sys.executable, "scripts/make_icon.py"], check=True)

    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--osx-bundle-identifier", "io.tgchat.studio",
        "--icon", ICON,
        "--target-arch", "arm64",
        "--add-data", f"app/web:app/web",
        "--hidden-import", "objc",
        "--hidden-import", "Foundation",
        "--hidden-import", "AppKit",
        "--hidden-import", "WebKit",
        "--hidden-import", "PyObjCTools",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "app/main.py",
    ]
    print("执行:", " ".join(args))
    subprocess.run(args, check=True)

    app_path = os.path.join(ROOT, "dist", f"{APP_NAME}.app")
    if not os.path.exists(app_path):
        raise SystemExit("打包失败：未生成 .app")
    print("打包完成:", app_path)


if __name__ == "__main__":
    main()
