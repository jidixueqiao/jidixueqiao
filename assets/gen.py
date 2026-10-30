# -*- coding: utf-8 -*-
"""
生成 README 用的霓虹终端面板 / 技术栈 chip。

为什么是脚本生成而不是手写 SVG：
GitHub 的 Markdown 渲染管线会剥掉全部 style 属性，任何靠 inline style 做的
配色/边框/深色面板在 README 里都会失效。SVG 文件不受该限制，因此把可视层
全部画进 SVG，文字层仍用 Markdown 保持可搜索、可点击。

用法：  python assets/gen.py
"""
import os
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

FS = 15          # 正文字号
ADV = FS * 0.6   # 等宽字体步进宽度
LH = 22          # 行高
PAD_X = 20
TITLEBAR = 46


def width(s):
    """显示宽度：CJK / 全角字符占 2 列。"""
    total = 0
    for ch in s:
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------- 终端面板
def build_terminal(lines, title="jidixueqiao — ~/profile", path="terminal.svg"):
    maxw = max(width("".join(t for t, _ in ln)) for ln in lines)
    w = int(PAD_X * 2 + maxw * ADV) + 4
    h = TITLEBAR + PAD_X + LH * len(lines) + 14

    out = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="terminal profile">'
    )
    out.append("""<defs>
  <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#00e5ff"/><stop offset="50%" stop-color="#7c3aed"/><stop offset="100%" stop-color="#f92672"/>
  </linearGradient>
  <linearGradient id="titleGrad" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#00e5ff"/><stop offset="100%" stop-color="#f92672"/>
  </linearGradient>
  <linearGradient id="scanBar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#ffffff" stop-opacity="0"/>
    <stop offset="50%" stop-color="#ffffff" stop-opacity="0.045"/>
    <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
  </linearGradient>
  <pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">
    <rect width="4" height="1.5" fill="#ffffff" opacity="0.035"/>
  </pattern>
  <clipPath id="panel"><rect x="1" y="1" width="{{W}}" height="{{H}}" rx="10"/></clipPath>
</defs>""".replace("{{W}}", str(w - 2)).replace("{{H}}", str(h - 2)))

    # 面板底 + 霓虹描边
    out.append(f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="10" fill="#0d1117"/>')
    out.append(f'<rect x="1.5" y="1.5" width="{w-3}" height="{h-3}" rx="10" fill="none" '
               f'stroke="url(#edge)" stroke-width="1.5" opacity="0.85"/>')
    # 标题栏
    out.append(f'<g clip-path="url(#panel)">')
    out.append(f'<rect x="1" y="1" width="{w-2}" height="{TITLEBAR}" fill="#161b22"/>')
    out.append(f'<rect x="1" y="{TITLEBAR}" width="{w-2}" height="1" fill="#30363d"/>')
    out.append('</g>')
    # 红黄绿三点
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        out.append(f'<circle cx="{18 + i*16}" cy="{TITLEBAR/2}" r="5" fill="{c}"/>')
    out.append(f'<text x="{w/2}" y="{TITLEBAR/2 + 5}" text-anchor="middle" fill="#8b949e" '
               f'font-size="13" font-family="ui-monospace,SFMono-Regular,Consolas,monospace">{esc(title)}</text>')

    # 正文
    out.append(f'<g font-family="ui-monospace,SFMono-Regular,Consolas,\'Liberation Mono\',monospace" '
               f'font-size="{FS}" fill="#c9d1d9">')
    y = TITLEBAR + PAD_X + FS
    for ln in lines:
        x = PAD_X
        for text, color in ln:
            if text:
                out.append(f'<text x="{x:.1f}" y="{y}" fill="{color}">{esc(text)}</text>')
            x += width(text) * ADV
        y += LH
    out.append('</g>')

    # CRT 扫描线 + 滚动亮带
    out.append(f'<g clip-path="url(#panel)">')
    out.append(f'<rect x="1" y="1" width="{w-2}" height="{h-2}" fill="url(#scan)"/>')
    out.append(f'<rect x="1" y="-60" width="{w-2}" height="60" fill="url(#scanBar)">'
               f'<animate attributeName="y" from="-60" to="{h+60}" dur="8s" repeatCount="indefinite"/></rect>')
    out.append('</g>')
    out.append('</svg>')

    with open(os.path.join(HERE, path), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"  -> {path}  ({w}x{h})")


# ---------------------------------------------------------------- chip 行
def build_stack(items, path="stack.svg", fs=13):
    adv = fs * 0.6
    gap, hpad, vpad = 10, 14, 6
    chips = []
    total_w = 0
    for label, color in items:
        cw = int(width(label) * adv) + hpad * 2
        chips.append((label, color, cw))
        total_w += cw + gap
    total_w -= gap
    h = fs + vpad * 2 + 2
    w = total_w + 2

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           f'role="img" aria-label="tech stack">']
    x = 1
    for label, color, cw in chips:
        out.append(f'<rect x="{x}" y="1" width="{cw}" height="{h-2}" rx="7" fill="{color}1f" '
                   f'stroke="{color}" stroke-opacity="0.5" stroke-width="1"/>')
        out.append(f'<text x="{x + cw/2:.1f}" y="{h/2 + fs*0.36:.1f}" text-anchor="middle" fill="{color}" '
                   f'font-size="{fs}" font-family="ui-monospace,SFMono-Regular,Consolas,monospace">{esc(label)}</text>')
        x += cw + gap
    out.append('</svg>')

    with open(os.path.join(HERE, path), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"  -> {path}  ({w}x{h})")


# ---------------------------------------------------------------- 徽章
def build_badge(label, value, color, path):
    """双段式徽章：左段实色标签 + 右段深底描边的取值，风格与终端面板一致。"""
    fs = 13
    adv = fs * 0.6
    h = 26
    pad = 9
    lw = int(width(label) * adv) + pad * 2
    vw = int(width(value) * adv) + pad * 2
    w = lw + vw

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           f'role="img" aria-label="{esc(label)} {esc(value)}">']
    # 左段：实色标签
    out.append(f'<path d="M1 1 H{lw-1} V{h-1} H1 A1 1 0 0 1 0 {h-1} V2 A1 1 0 0 1 1 1 Z" fill="{color}"/>')
    out.append(f'<text x="{lw/2:.1f}" y="{h/2 + fs*0.35:.1f}" text-anchor="middle" fill="#ffffff" '
               f'font-size="{fs}" font-weight="600" font-family="ui-monospace,SFMono-Regular,Consolas,monospace">'
               f'{esc(label)}</text>')
    # 右段：深底 + 霓虹描边
    out.append(f'<rect x="{lw}" y="1" width="{vw-1}" height="{h-2}" fill="#0d1117"/>')
    out.append(f'<rect x="{lw+0.5}" y="1.5" width="{vw-2}" height="{h-3}" fill="none" '
               f'stroke="{color}" stroke-opacity="0.55" stroke-width="1"/>')
    out.append(f'<text x="{lw + vw/2:.1f}" y="{h/2 + fs*0.35:.1f}" text-anchor="middle" fill="{color}" '
               f'font-size="{fs}" font-family="ui-monospace,SFMono-Regular,Consolas,monospace">'
               f'{esc(value)}</text>')
    out.append('</svg>')

    with open(os.path.join(HERE, path), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"  -> {path}  ({w}x{h})")


# ---------------------------------------------------------------- 内容
C_PROMPT = "#7ee787"   # $ 提示符
C_CMD = "#e6edf3"      # 命令
C_OUT = "#8b949e"      # 普通输出
C_PATH = "#79c0ff"     # 路径 / 文件名
C_HOT = "#ff7b72"      # 警告 / 强调
C_KEY = "#d2a8ff"      # 关键字

TERMINAL = [
    [("$ ", C_PROMPT), ("whoami", C_CMD)],
    [("jidixueqiao", C_KEY), ("  —  AI 安全方向开发者", C_OUT)],
    [("Python · MCP · SQL · Vue · JavaScript · 网络基础设施", C_OUT)],
    [],
    [("$ ", C_PROMPT), ("cat ", C_CMD), ("focus.txt", C_PATH)],
    [("让 AI 有能力碰生产数据库，但没有能力搞坏它。", C_OUT)],
    [],
    [("$ ", C_PROMPT), ("ls -la ", C_CMD), ("~/projects", C_PATH)],
    [("drwxr-xr-x  ", C_OUT), ("sql_mcp", C_PATH), ("          Python  MIT   ", C_OUT),
     ("安全审计型 SQL MCP Server", C_OUT)],
    [("drwxr-xr-x  ", C_OUT), ("ai-minesweeper", C_PATH), ("   Vue     MIT   ", C_OUT),
     ("用 cursor ai 写出来的扫雷", C_OUT)],
    [("drwxr-xr-x  ", C_OUT), ("person-web", C_PATH), ("       JS      --    ", C_OUT),
     ("个人网站 (Pages)", C_OUT)],
    [],
    [("$ ", C_PROMPT), ("systemctl status build", C_CMD)],
    [("● ", C_PROMPT), ("active (running)", C_KEY), ("   since 2017-08-19", C_OUT)],
    [],
    [("$ ", C_PROMPT), ("echo ", C_CMD), ("$FOCUS", C_PATH)],
    [("让 AI 安全地操作真实数据", C_HOT)],
]

STACK = [
    ("Python", "#0e7490"),
    ("MCP", "#be185d"),
    ("SQL", "#0e7490"),
    ("MySQL", "#15803d"),
    ("PostgreSQL", "#1d4ed8"),
    ("SQLite", "#b45309"),
    ("Vue", "#15803d"),
    ("JavaScript", "#b45309"),
    ("AI Safety", "#be185d"),
    ("Network", "#0f766e"),
]

BADGES = [
    ("GitHub", "jidixueqiao", "#e11d74", "badge-github.svg"),
    ("Email", "2043832968@qq.com", "#06b6d4", "badge-email.svg"),
]

if __name__ == "__main__":
    print("生成 README 资源：")
    build_terminal(TERMINAL)
    build_stack(STACK)
    for label, value, color, path in BADGES:
        build_badge(label, value, color, path)
    print("完成。")
