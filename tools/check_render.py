# -*- coding: utf-8 -*-
"""对 README 的渲染结果做像素级校验。

流程：渲染预览页 → 无头 Chrome 截图 → Pillow 逐区块断言。
本仓库的 README 视觉层全部是 SVG，线上只会因路径/属性问题塌掉，
所以这里逐个区块量尺寸、位置、颜色与对齐，确保改动不会悄悄破坏布局。

用法:
    python tools/check_render.py
"""
import os
import subprocess
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview  # noqa: E402

ROOT = preview.ROOT
BUILD = preview.BUILD
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 8901
VIEWPORT = (1000, 2000)

FAIL, OK = [], []


def check(cond, msg, detail=""):
    (OK if cond else FAIL).append(msg + (f" [{detail}]" if detail else ""))
    print(("  PASS  " if cond else "  FAIL  ") + msg + (f"  [{detail}]" if detail else ""))


def near(p, rgb, tol=10):
    return abs(p[0] - rgb[0]) <= tol and abs(p[1] - rgb[1]) <= tol and abs(p[2] - rgb[2]) <= tol


def lum(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def row_profile(img, pred):
    w, h = img.size
    px = img.load()
    return [sum(1 for x in range(w) if pred(px[x, y])) for y in range(h)]


def bands(profile, thresh, min_len=1):
    out, start = [], None
    for y, v in enumerate(profile):
        if v >= thresh:
            if start is None:
                start = y
        else:
            if start is not None:
                if y - start >= min_len:
                    out.append((start, y - 1))
                start = None
    if start is not None:
        out.append((start, len(profile) - 1))
    return out


def screenshot(url, out_path):
    subprocess.run([
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={VIEWPORT[0]},{VIEWPORT[1]}",
        f"--screenshot={out_path}", url,
    ], check=True, capture_output=True)
    return out_path


def analyze_light(path):
    print(f"\n=== {os.path.basename(path)} (浅色主题) ===")
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()

    # .wrap 纯白背景盒
    bx0, by0, bx1, by1 = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if px[x, y] == (255, 255, 255):
                if x < bx0: bx0 = x
                if x > bx1: bx1 = x
                if y < by0: by0 = y
                if y > by1: by1 = y
    check(bx1 > bx0 and by1 > by0, "定位 .wrap 白底盒", f"=({bx0},{by0})-({bx1},{by1})")
    cx0, cx1 = bx0 + 32, bx1 - 32
    cy0 = by0 + 32
    cw = cx1 - cx0 + 1
    bh = int(cw * 360 / 1200)
    print(f"  内容区 x=[{cx0},{cx1}] 宽={cw}  y起={cy0}")

    # ---------------- 1. banner ----------------
    xs = [x for x in range(bx0, bx1 + 1) if not near(px[x, cy0 + bh // 2], (255, 255, 255), 3)]
    check(bool(xs) and abs(xs[0] - cx0) <= 4, "banner 左边缘贴齐内容区",
          f"left={xs[0] if xs else None} expect={cx0}")
    check(bool(xs) and abs(xs[-1] - cx1) <= 4, "banner 右边缘贴齐内容区",
          f"right={xs[-1] if xs else None} expect={cx1}")
    sun = sum(1 for y in range(cy0 + 90, cy0 + bh)
              for x in range(cx0 + int(cw * 0.36), cx0 + int(cw * 0.64))
              if (lambda p: p[0] > 235 and 110 < p[1] < 235 and 90 < p[2] < 205)(px[x, y]))
    check(sun > 1200, "banner 条纹太阳渲染（暖色像素）", f"count={sun}")
    txs, tys = [], []
    for y in range(cy0 + 45, cy0 + 100):
        r = [x for x in range(cx0, cx1 + 1)
             if px[x, y][0] < 95 and px[x, y][1] < 85 and px[x, y][2] < 125]
        if len(r) > 30:
            txs += r
            tys.append(y)
    check(len(txs) > 1500, "banner 标题文字渲染", f"pixels={len(txs)}")
    if txs:
        tc = (min(txs) + max(txs)) / 2
        check(abs(tc - (cx0 + cx1) / 2) < 14, "banner 标题水平居中",
              f"center={tc:.1f} expect={(cx0+cx1)/2:.1f}")
        check(max(tys) - min(tys) < 60, "banner 标题高度合理", f"{max(tys)-min(tys)}px")

    # ---------------- 2. 终端面板 ----------------
    dp = row_profile(img, lambda p: lum(p) < 70)
    pb = [b for b in bands(dp, 400, min_len=40) if b[0] > cy0 + bh]
    check(len(pb) >= 1, "终端深色面板存在", f"bands={pb}")
    if not pb:
        return
    py0, py1 = pb[0]
    mid = (py0 + py1) // 2
    ext = [x for x in range(bx0, bx1 + 1) if lum(px[x, mid]) < 70]
    tl, tr = min(ext), max(ext)
    check(abs((tl + tr) / 2 - (cx0 + cx1) / 2) < 12, "终端面板水平居中",
          f"center={(tl+tr)/2:.1f} expect={(cx0+cx1)/2:.1f}")
    check(abs((tr - tl + 1) - 680) <= 14, "终端面板宽度符合 680", f"{tr-tl+1}px")
    check(tl >= cx0 and tr <= cx1, "终端面板不溢出内容区",
          f"panel=[{tl},{tr}] content=[{cx0},{cx1}]")
    check(abs((py1 - py0 + 1) - 470) <= 20, "终端面板高度符合 454→470", f"{py1-py0+1}px")
    dots = sum(1 for c in [(255, 95, 87), (254, 188, 46), (40, 200, 64)]
               if any(near(px[x, py0 + 23], c, 45) for x in range(tl + 8, tl + 75)))
    check(dots == 3, "终端标题栏红黄绿三点", f"{dots}/3")
    rows, best = 0, 0
    for y in range(py0 + 47, py1):
        c = sum(1 for x in range(tl + 10, tr - 10)
                if px[x, y][0] > 150 and px[x, y][1] > 150 and px[x, y][2] > 150)
        best = max(best, c)
        if c > 8:
            rows += 1
    check(rows >= 14, "终端面板内文字行", f"rows={rows} max={best}")

    # ---------------- 3. 技术栈 chip 行 ----------------
    chip_cols = [(14, 116, 144), (190, 24, 93), (21, 128, 61), (29, 78, 216),
                 (180, 83, 9), (15, 118, 110)]
    cp = row_profile(img, lambda p: any(near(p, c, 55) for c in chip_cols))
    cb_all = [b for b in bands(cp, 18, min_len=6) if b[0] > py1]
    cb = []
    for b in cb_all:
        row = img.crop((cx0, b[0], cx1, b[1] + 1))
        r = [i % row.size[0] for i, p in enumerate(row.getdata())
             if any(near(p, c, 55) for c in chip_cols)]
        if r and (max(r) - min(r)) > 600:
            cb.append(b)
    check(len(cb) >= 1, "技术栈 chip 行存在", f"bands={cb_all} -> 选中 {cb}")
    if cb:
        cy_a, cy_b = cb[0]
        crop = img.crop((cx0, cy_a, cx1, cy_b + 1))
        present = [c for c in chip_cols
                   if sum(1 for p in crop.getdata() if near(p, c, 55)) > 30]
        check(len(present) >= 6, "技术栈 chip 颜色齐全", f"{len(present)}/6")
        r = [i % crop.size[0] for i, p in enumerate(crop.getdata())
             if any(near(p, c, 55) for c in chip_cols)]
        check(r and (max(r) - min(r)) > 700, "chip 行横向铺开", f"span={max(r)-min(r)}px")
        check(cy_b - cy_a + 1 < 34, "chip 行高度合理", f"{cy_b-cy_a+1}px")
        emo = sum(1 for y in range(cy_b + 20, cy_b + 120) for x in range(cx0, cx1)
                  if max(px[x, y]) - min(px[x, y]) > 45 and px[x, y][2] > 120)
        check(emo > 200, "标题 emoji 渲染为彩色", f"pixels={emo}")

    # ---------------- 4. 项目表格 ----------------
    tp = row_profile(img, lambda p: near(p, (209, 217, 224), 24))
    tb = [b for b in bands(tp, 300, min_len=1)
          if b[0] > (cb[0][1] if cb else 0) and b[1] < by1 - 2]
    check(len(tb) >= 5, "项目表格有表头线 + 3 行分隔线（5 条）", f"lines={len(tb)} -> {tb}")
    if len(tb) >= 5:
        ty0, ty1 = tb[0][0], tb[-1][1]
        treg = img.crop((cx0, ty0, cx1, ty1 + 1))
        link = sum(1 for p in treg.getdata() if near(p, (9, 105, 218), 50))
        check(link > 500, "表格内项目链接为可点击蓝色文本", f"pixels={link}")
        check(ty1 - ty0 > 140, "表格含表头 + 3 行数据高度合理", f"{ty1-ty0}px")

    # ---------------- 5. 徽章 ----------------
    tbl_bottom = tb[-1][1] if len(tb) >= 5 else py1
    pinks = [(x, y) for y in range(tbl_bottom + 5, by1) for x in range(cx0, cx1)
             if near(px[x, y], (225, 29, 116), 30)]
    cyans = [(x, y) for y in range(tbl_bottom + 5, by1) for x in range(cx0, cx1)
             if near(px[x, y], (6, 182, 212), 30)]
    check(len(pinks) > 800, "GitHub 徽章粉色段", f"pixels={len(pinks)}")
    check(len(cyans) > 800, "Email 徽章青色段", f"pixels={len(cyans)}")
    if pinks and cyans:
        py = sum(p[1] for p in pinks) / len(pinks)
        cy = sum(p[1] for p in cyans) / len(cyans)
        check(abs(py - cy) < 6, "两个徽章同一行", f"y={py:.0f} vs {cy:.0f}")
        check(abs(min(p[0] for p in pinks) - cx0) <= 3, "徽章左对齐内容区",
              f"left={min(p[0] for p in pinks)} expect={cx0}")

        def accent_x(rgb):
            r = [x for y in range(int(py) - 12, int(py) + 13) for x in range(cx0, cx1)
                 if near(px[x, y], rgb, 26)]
            return (min(r), max(r)) if r else None

        pink_edge = accent_x((129, 23, 74))
        cyan_edge = accent_x((9, 106, 130))
        check(pink_edge is not None and cyan_edge is not None,
              "两个徽章的霓虹描边检出", f"pink={pink_edge} cyan={cyan_edge}")
        if pink_edge and cyan_edge:
            check(abs((pink_edge[1] - pink_edge[0] + 1) - 103) <= 5,
                  "GitHub 徽章右段宽度 103", f"{pink_edge[1]-pink_edge[0]+1}px")
            check(abs((cyan_edge[1] - cyan_edge[0] + 1) - 150) <= 5,
                  "Email 徽章右段宽度 150", f"{cyan_edge[1]-cyan_edge[0]+1}px")
            check(abs((pink_edge[0] - cx0) - 64) <= 4, "GitHub 标签段宽 64",
                  f"left={pink_edge[0]-cx0}")
            check(abs((cyan_edge[0] - cx0) - 228) <= 5, "Email 徽章位置 167+57",
                  f"left={cyan_edge[0]-cx0}")
        badge_bottom = max(p[1] for p in pinks + cyans)
    else:
        badge_bottom = tbl_bottom

    # ---------------- 6. 页脚 ----------------
    fp = row_profile(img, lambda p: lum(p) < 170)
    fb = [b for b in bands(fp, 8, min_len=1) if b[0] > badge_bottom]
    check(len(fb) >= 1, "页脚文字存在", f"bands={fb}")
    if fb:
        fy0, fy1 = fb[0]
        fxs = [x for y in range(fy0, fy1 + 1) for x in range(cx0, cx1) if lum(px[x, y]) < 170]
        if fxs:
            fc = (min(fxs) + max(fxs)) / 2
            check(abs(fc - (cx0 + cx1) / 2) < 30, "页脚居中",
                  f"center={fc:.1f} expect={(cx0+cx1)/2:.1f}")
        check(fy1 <= by1, "页脚在内容盒内（页面未被截断）",
              f"footer_end={fy1} wrap_bottom={by1}")


def analyze_dark(path):
    print(f"\n=== {os.path.basename(path)} (深色主题) ===")
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()

    bx0, by0, bx1, by1 = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if near(px[x, y], (13, 17, 23), 4):
                if x < bx0: bx0 = x
                if x > bx1: bx1 = x
                if y < by0: by0 = y
                if y > by1: by1 = y
    check(bx1 > bx0 and by1 > by0, "深色页内容盒存在", f"=({bx0},{by0})-({bx1},{by1})")
    if bx1 <= bx0:
        return
    cx0, cx1 = bx0 + 32, bx1 - 32
    cw = cx1 - cx0 + 1
    cy0 = by0 + 32
    bh = int(cw * 360 / 1200)
    print(f"  内容区 x=[{cx0},{cx1}] 宽={cw}")

    warm = sum(1 for y in range(cy0 + 90, cy0 + bh)
               for x in range(cx0 + int(cw * 0.36), cx0 + int(cw * 0.64))
               if (lambda p: p[0] > 200 and 40 < p[1] < 200 and 40 < p[2] < 190)(px[x, y]))
    check(warm > 1200, "深色 banner 条纹太阳渲染", f"count={warm}")
    deep = sum(1 for y in range(cy0, cy0 + bh) for x in range(cx0, cx1)
               if px[x, y][0] < 70 and px[x, y][1] < 50 and px[x, y][2] < 90)
    check(deep > cw * bh * 0.35, "深色 banner 背景为深紫", f"count={deep}")
    bright = sum(1 for y in range(cy0 + 40, cy0 + 150) for x in range(cx0, cx1)
                 if px[x, y][0] > 230 and px[x, y][1] > 230 and px[x, y][2] > 230)
    check(bright > 1000, "深色 banner 标题文字渲染", f"pixels={bright}")
    chip_cols = [(14, 116, 144), (190, 24, 93), (21, 128, 61), (29, 78, 216),
                 (180, 83, 9), (15, 118, 110)]
    cp = row_profile(img, lambda p: any(near(p, c, 55) for c in chip_cols))
    check(len([b for b in bands(cp, 18, min_len=6)]) >= 1, "深色页技术栈 chip 行存在")
    pink = sum(1 for p in img.getdata() if near(p, (225, 29, 116), 30))
    cyan = sum(1 for p in img.getdata() if near(p, (6, 182, 212), 30))
    check(pink > 800 and cyan > 800, "深色页徽章渲染", f"pink={pink} cyan={cyan}")


def main():
    print("渲染 README：")
    files = preview.build()
    httpd, port = preview.serve(0)
    try:
        shots = {}
        for key, page in (("light", "preview-readme.html"), ("dark", "preview-readme-dark.html")):
            out = os.path.join(BUILD, f"shot-{key}.png")
            screenshot(f"http://127.0.0.1:{port}/build/{page}", out)
            shots[key] = out
            print(f"  -> build/shot-{key}.png")
        analyze_light(shots["light"])
        analyze_dark(shots["dark"])
    finally:
        httpd.shutdown()

    print(f"\n通过 {len(OK)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("\n失败项：")
        for f in FAIL:
            print("  - " + f)
        sys.exit(1)
    print("全部通过。")


if __name__ == "__main__":
    main()
