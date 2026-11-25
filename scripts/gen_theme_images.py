#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 README 用的主题效果图（每套主题浅色 + 深色两张 PNG）。

用法:
    python gen_theme_images.py [--md assets/themes/demo.md] [--out assets/themes]

机制:
  - 浅色图 = 主题原样渲染；深色图 = wechat_dark（微信读者端 mp-darkmode
    算法静态移植）转换后的观感——与读者开深色模式看到的效果一致。
  - 渲染用真实 Chrome（chrome-devtools CLI），480px 版心 + zoom:2 输出
    960px 宽整页截图，与既有效果图尺寸一致。
  - README 用 <picture> + prefers-color-scheme 让两张图随系统明暗自动切换
    （GitHub 原生支持）。

前置: 本机已安装 chrome-devtools CLI（npm 全局包 chrome-devtools-mcp）。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import md_to_gzh as M  # noqa: E402
from wechat_dark import convert_html  # noqa: E402

PAGE_TPL = ('<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '</head><body style="margin:0;background:%s;">'
            '<div style="width:480px;zoom:2;">%s</div></body></html>')


def run_cli(args):
    return subprocess.run(["chrome-devtools"] + args, capture_output=True, text=True)


def ensure_daemon():
    st = run_cli(["status"]).stdout
    if "--no-sandbox" not in st:
        run_cli(["stop"])
        run_cli(["start", "--chromeArg=--no-sandbox",
                 "--chromeArg=--disable-dev-shm-usage"])


def shoot(page_html, out_path):
    """把一段完整 HTML 渲染成 960px 宽整页截图并保存到 out_path。"""
    ensure_daemon()
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8") as f:
        f.write(page_html)
        tmp = f.name
    try:
        # new_page 只接受合法 URL，本地文件必须带 file:// 前缀
        r = run_cli(["new_page", "file://" + tmp])
        # 输出是页面列表，新页面带 [selected] 标记——不能取第一个 ID（可能是 about:blank）
        m = re.search(r"^\s*(\d+):.*\[selected\]", r.stdout, re.M)
        if not m:
            pages = run_cli(["list_pages"]).stdout
            ids = re.findall(r"^\s*(\d+):", pages, re.M)
            if not ids:
                raise RuntimeError("无法创建页面: %s%s" % (r.stdout, r.stderr))
            pid = ids[-1]
        else:
            pid = m.group(1)
        run_cli(["resize_page", pid, "960", "900"])
        r = run_cli(["take_screenshot", pid, "--fullPage", "true",
                     "--output-format", "json"])
        mm = re.search(r'"filePath":"([^"]+)"', r.stdout)
        if not mm:
            raise RuntimeError("截图失败: %s%s" % (r.stdout, r.stderr))
        shutil.copy(mm.group(1), out_path)
    finally:
        os.unlink(tmp)
        try:
            pages = run_cli(["list_pages"]).stdout
            ids = re.findall(r"^\s*(\d+):\s*\S*%s" % re.escape(os.path.basename(tmp)), pages)
            for i in ids:
                run_cli(["close_page", i])
        except Exception:
            pass


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=os.path.join(BASE, "..", "assets", "themes", "demo.md"))
    ap.add_argument("--out", default=os.path.join(BASE, "..", "assets", "themes"))
    args = ap.parse_args()
    md = open(args.md, encoding="utf-8").read()
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    for key, t in M.THEMES.items():
        _, light_html = M.convert(md, key, "light")
        dark_html = convert_html(light_html)
        for scheme, html, bg in (("浅色", light_html, "#FFFFFF"),
                                 ("深色", dark_html, "#1A1A1A")):
            out = os.path.join(out_dir, "%s%s.png" % (key, "" if scheme == "浅色" else "_dark"))
            shoot(PAGE_TPL % (bg, html), out)
            print("✓ %s %s → %s" % (t["name"], scheme, out))
    print("完成：%d 套主题 × 2 = %d 张效果图" % (len(M.THEMES), len(M.THEMES) * 2))


if __name__ == "__main__":
    main()
