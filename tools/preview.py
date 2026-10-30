# -*- coding: utf-8 -*-
"""把 README.md 渲染成 GitHub 风格的本地预览页。

为什么走 GitHub 官方接口而不是本地 markdown 库：
GitHub 的渲染管线会剥掉全部 inline style，并给 <img> 注入 max-width。
只有用官方接口渲染，才能看到线上真实效果。

用法:
    python tools/preview.py            # 只生成预览 HTML
    python tools/preview.py --serve    # 生成并起本地服务
"""
import argparse
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
API = "https://api.github.com/markdown"

BASE_CSS = """
* { box-sizing: border-box; }
body { margin: 0; padding: 28px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif,
               "Apple Color Emoji", "Segoe UI Emoji";
  background: #f6f8fa; }
.wrap { max-width: 896px; margin: 0 auto; background: #fff;
  border: 1px solid #d1d9e0; border-radius: 6px; padding: 32px; }
.markdown-body { font-size: 16px; line-height: 1.5; color: #1f2328; word-wrap: break-word; }
.markdown-body p[align="center"] { text-align: center; }
.markdown-body p[align="left"] { text-align: left; }
.markdown-body img { max-width: 100%; box-sizing: content-box; }
.markdown-body h3 { font-size: 1.25em; margin: 24px 0 16px; font-weight: 600; line-height: 1.25; }
.markdown-body table { border-spacing: 0; border-collapse: collapse; display: block;
  width: max-content; max-width: 100%; overflow: auto; }
.markdown-body table th { font-weight: 600; }
.markdown-body table th, .markdown-body table td { padding: 6px 13px; border: 1px solid #d1d9e0; }
.markdown-body table tr { background-color: #fff; border-top: 1px solid #d1d9e0; }
.markdown-body table tr:nth-child(2n) { background-color: #f6f8fa; }
.markdown-body code { padding: .2em .4em; margin: 0; font-size: 85%; background-color: rgba(175,184,193,.2);
  border-radius: 6px; font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; }
.markdown-body a { color: #0969da; text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
themed-picture { display: inline-block; }
"""

DARK_CSS = """
body { background: #010409; }
.wrap { background: #0d1117; border-color: #30363d; }
.markdown-body { color: #e6edf3; }
.markdown-body table th, .markdown-body table td { border-color: #30363d; }
.markdown-body table tr { background-color: #0d1117; border-top-color: #30363d; }
.markdown-body table tr:nth-child(2n) { background-color: #161b22; }
.markdown-body code { background-color: rgba(110,118,129,.4); color: #e6edf3; }
.markdown-body a { color: #4493f8; }
"""

PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>README preview</title><style>{css}</style></head>
<body><div class="wrap"><div class="markdown-body">
{body}
</div></div></body></html>
"""


def render_md(md_text):
    """调 GitHub 官方 markdown 接口，拿到与线上完全一致的 HTML。"""
    req = urllib.request.Request(
        API,
        data=json.dumps({"text": md_text, "mode": "gfm"}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "dsh-readme-preview"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def force_banner(html, src):
    """把 <themed-picture> 整块换成直接指向指定 banner 的 <img>。

    本机 Chrome 的 prefers-color-scheme 是 dark，保留 <picture> 会让两个预览
    都渲染成深色 banner，无法分别校验，所以预览里显式指定。
    """
    m = re.search(r"<themed-picture.*?</themed-picture>", html, re.S)
    if not m:
        raise RuntimeError("渲染结果里没有 themed-picture 块")
    block = m.group(0)
    alt = re.search(r'alt="([^"]*)"', block)
    alt = alt.group(1) if alt else "banner"
    width = re.search(r'width="([^"]*)"', block)
    width = width.group(1) if width else "100%"
    return html.replace(block, f'<img src="{src}" alt="{alt}" width="{width}">')


def build():
    """渲染并写出预览页，返回 {名称: 绝对路径}。"""
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        md = f.read()

    html = render_md(md)
    os.makedirs(BUILD, exist_ok=True)
    out = {}

    def write(name, text):
        p = os.path.join(BUILD, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        out[name] = p
        print(f"  -> build/{name}  ({len(text)} chars)")

    write("body.html", html)
    # 预览页放在 build/ 下，README 里的 ./assets/xxx.svg 要相应改成 ../assets/xxx.svg
    rel = html.replace("./assets/", "../assets/")
    write("preview-readme.html",
          PAGE.format(css=BASE_CSS, body=force_banner(rel, "../assets/banner-light.svg")))
    write("preview-readme-dark.html",
          PAGE.format(css=BASE_CSS + DARK_CSS, body=force_banner(rel, "../assets/banner.svg")))
    return out


def serve(port=0):
    """在仓库根目录起一个静态服务，让相对路径的 ./assets/*.svg 能被解析。

    port=0 时由系统分配一个空闲端口，避免和上次残留的服务撞端口。
    返回 (httpd, 实际端口)。
    """
    os.chdir(ROOT)

    class Server(socketserver.TCPServer):
        allow_reuse_address = True

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

    httpd = Server(("127.0.0.1", port), QuietHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="生成后起本地预览服务")
    ap.add_argument("--port", type=int, default=8901)
    args = ap.parse_args()

    print("渲染 README：")
    build()
    if args.serve:
        httpd, port = serve(args.port)
        print(f"\n预览地址： http://127.0.0.1:{port}/build/preview-readme.html")
        print(f"          http://127.0.0.1:{port}/build/preview-readme-dark.html")
        try:
            while True:
                threading.Event().wait(1)
        except KeyboardInterrupt:
            httpd.shutdown()
            sys.exit(0)
