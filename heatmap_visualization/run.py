import http.server
import socketserver
import os
import webbrowser
import sys


PORT = 8090


class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print("=" * 60)
    print("🔥 群聊热力图可视化服务器")
    print("=" * 60)
    print(f"📁 工作目录: {script_dir}")
    print(f"🌐 访问地址: http://localhost:{PORT}")
    print(f"\n按 Ctrl+C 停止服务器\n")

    try:
        with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
            print("✅ 服务器已启动! 正在打开浏览器...\n")
            webbrowser.open(f"http://localhost:{PORT}")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 服务器已停止")
    except OSError as e:
        if e.errno == 10048:
            print(f"❌ 端口 {PORT} 已被占用，请修改 PORT 变量或关闭占用程序")
        else:
            print(f"❌ 启动失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
