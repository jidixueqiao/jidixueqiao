# -*- coding: utf-8 -*-
"""对真实线上主页（https://github.com/jidixueqiao）截图做像素校验。

这一步验证的是最终结果：GitHub 自己渲染出来的页面里，
banner / 终端面板 / chip 行 / 项目表格 / 徽章 是否都真的画出来了。
"""
import os
import subprocess
import sys

from PIL import Image

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "build", "live-profile.png")
URL = "https://github.com/jidixueqiao"

FAIL, OK = [], []


def check(cond, msg, detail=""):
    (OK if cond else FAIL).append(msg + (f" [{detail}]" if detail else ""))
    print(("  PASS  " if cond else "  FAIL  ") + msg + (f"  [{detail}]" if detail else ""))


def near(p, rgb, tol=14):
    return abs(p[0] - rgb[0]) <= tol and abs(p[1] - rgb[1]) <= tol and abs(p[2] - rgb[2]) <= tol


def lum(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def bbox(pred, img, step=1):
    w, h = img.size
    px = img.load()
    x0, y0, x1, y1, n = w, h, -1, -1, 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            if pred(px[x, y]):
                n += 1
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    return n, (x0, y0, x1, y1)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    subprocess.run([
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--window-size=1400,2600",
        "--virtual-time-budget=20000", f"--screenshot={OUT}", URL,
    ], check=True, capture_output=True)

    img = Image.open(OUT).convert("RGB")
    w, h = img.size
    print(f"截图 {w}x{h}")

    dark_bg = sum(1 for p in img.getdata() if lum(p) < 45)
    light_bg = sum(1 for p in img.getdata() if lum(p) > 230)
    theme = "dark" if dark_bg > light_bg else "light"
    print(f"页面主题：{theme}  (暗像素 {dark_bg} / 亮像素 {light_bg})")

    # --- 终端面板：#0d1117 深色矩形 + 霓虹描边 ---
    n, tb = bbox(lambda p: near(p, (13, 17, 23), 4), img, 2)
    print(f"  #0d1117 像素 {n} bbox={tb}")

    neon = [(0, 229, 255), (124, 58, 237), (249, 38, 114)]
    nn, nb = bbox(lambda p: any(near(p, c, 30) for c in neon), img, 2)
    check(nn > 400, "终端面板霓虹描边渲染", f"pixels={nn} bbox={nb}")

    if theme == "light":
        # 浅色页面上终端面板表现为一块明显比周围暗的矩形
        check(n > 50000, "终端面板深底在浅色页面上可见", f"pixels={n}")
    else:
        # 深色页面板与背景同色，靠霓虹描边与面板内浅色文字判定
        txt = sum(1 for p in img.getdata() if p[0] > 175 and p[1] > 175 and p[2] > 175)
        check(txt > 3000, "深色页终端文字渲染", f"pixels={txt}")

    # --- banner：横幅区域应有暖色太阳 ---
    warm, wb = bbox(lambda p: p[0] > 235 and 110 < p[1] < 235 and 90 < p[2] < 205, img, 2)
    warmd, wbd = bbox(lambda p: p[0] > 200 and 40 < p[1] < 200 and 40 < p[2] < 190, img, 2)
    check(max(warm, warmd) > 600, "banner 条纹太阳渲染", f"light={warm} dark={warmd} bbox={wb if warm else wbd}")

    # --- 技术栈 chip 颜色 ---
    chip_cols = [(14, 116, 144), (190, 24, 93), (21, 128, 61), (29, 78, 216),
                 (180, 83, 9), (15, 118, 110)]
    found = []
    for c in chip_cols:
        cn, cb = bbox(lambda p, c=c: near(p, c, 40), img, 3)
        if cn > 120:
            found.append((c, cn, cb))
    check(len(found) >= 5, "技术栈 chip 颜色渲染", f"{len(found)}/6 -> {[(c, n) for c, n, _ in found]}")

    # --- 徽章：粉色 + 青色，且青色徽章紧邻粉色徽章右侧 ---
    pn, pb = bbox(lambda p: near(p, (225, 29, 116), 30), img, 2)
    cn2, cb2 = bbox(lambda p: near(p, (6, 182, 212), 30), img, 2)
    check(pn > 600, "GitHub 徽章粉色段", f"pixels={pn} bbox={pb}")
    check(cn2 > 250, "Email 徽章青色段", f"pixels={cn2} bbox={cb2}")

    # 徽章：粉色标签块 64px、青色标签块 57px，同一行；
    # Email 徽章起点 = GitHub 徽章起点 + 167(总宽) + 4(HTML 空格) = +171
    px = img.load()
    w, h = img.size

    def solid_runs(y, rgb, lo, hi):
        out, cur = [], None
        for x in range(430, w):
            if near(px[x, y], rgb, 40):
                if cur is None:
                    cur = x
            else:
                if cur is not None:
                    if lo <= x - cur <= hi:
                        out.append((cur, x - 1))
                    cur = None
        if cur is not None and lo <= w - cur <= hi:
            out.append((cur, w - 1))
        return out

    found = []
    for y in range(h):
        pr = solid_runs(y, (225, 29, 116), 58, 68)
        cr = solid_runs(y, (6, 182, 212), 52, 62)
        if pr and cr:
            found.append((y, pr[0], cr[0]))
    check(bool(found), "定位徽章行（粉色 64px + 青色 57px 实色块）",
          f"candidates={found[:3]}")
    if found:
        y, (p0, p1), (c0, c1) = found[0]
        check(abs((p1 - p0 + 1) - 64) <= 4, "GitHub 徽章标签块宽 64", f"{p1-p0+1}px")
        check(abs((c1 - c0 + 1) - 57) <= 4, "Email 徽章标签块宽 57", f"{c1-c0+1}px")
        check(abs((c0 - p0) - 171) <= 8, "两徽章间距符合 167+4", f"delta={c0-p0}")
        check(p0 >= 430 and c1 <= w, "徽章在 README 主栏内", f"x={p0}..{c1}")
    else:
        check(False, "定位粉色徽章行带")

    # --- 项目表格：分隔线 + 蓝色链接 ---
    border = [(209, 217, 224), (48, 54, 61), (31, 35, 40)]
    bn, bb = bbox(lambda p: any(near(p, c, 14) for c in border), img, 2)
    blue, blb = bbox(lambda p: near(p, (9, 105, 218), 40), img, 2)
    check(blue > 400, "项目表格内蓝色可点链接", f"pixels={blue} bbox={blb}")

    print(f"\n通过 {len(OK)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        for f in FAIL:
            print("  - " + f)
        sys.exit(1)
    print("线上渲染全部通过。")


if __name__ == "__main__":
    main()
