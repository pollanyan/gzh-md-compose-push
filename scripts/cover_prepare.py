#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面归一化：把任意来源的封面图处理成微信封面标准 900×383（2.35:1）。

支持的输入（三种来源统一走这里，再交给上传/设封面步骤）：
  1) 本地文件路径
  2) 网络 URL（http/https，自动下载）
  3) AI 生成的封面图（生成后落成本地文件，走同一入口；
     生成图右下角的「AI生成」水印位于底边，中心裁剪 2.35:1 后必然被去掉）

处理规则：
  - 中心裁剪到 2.35:1（微信封面比例），再缩放到 900×383；
  - 输出 PNG；--out 省略时输出为 <源名>_封面_900x383.png。

用法：
  python cover_prepare.py <图片路径或URL> [--out 输出.png]

依赖：Pillow（pip install pillow）。下载 URL 需要网络。
"""
import os
import re
import sys
import urllib.request

try:
    from PIL import Image
except ImportError:
    Image = None

W, H = 900, 383  # 微信封面 2.35:1 标准尺寸


def _load(path_or_url):
    """返回 (PIL.Image, 临时文件路径或 None)。URL 自动下载到临时文件。"""
    if Image is None:
        sys.exit("✗ 需要 Pillow：python3 -m pip install pillow")
    tmp = None
    if path_or_url.lower().startswith(("http://", "https://")):
        tmp = os.path.join(os.path.expanduser("~"), ".workbuddy", "tmp_cover_download")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        req = urllib.request.Request(path_or_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
            f.write(r.read())
        path_or_url = tmp
    if not os.path.isfile(path_or_url):
        sys.exit("✗ 找不到图片：%s" % path_or_url)
    im = Image.open(path_or_url).convert("RGB")
    return im, tmp


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="本地路径或 http(s) URL")
    ap.add_argument("--out", help="输出 PNG（默认 <源名>_封面_900x383.png）")
    args = ap.parse_args()

    im, tmp = _load(args.image)
    w, h = im.size
    target_h = max(1, int(w / 2.35))
    if target_h <= h:
        top = (h - target_h) // 2
        im = im.crop((0, top, w, top + target_h))
    else:  # 图比 2.35:1 更「矮胖」→ 以高定宽裁左右
        target_w = int(h * 2.35)
        left = max(0, (w - target_w) // 2)
        im = im.crop((left, 0, min(w, left + target_w), h))
    im = im.resize((W, H), Image.LANCZOS)

    out = args.out or re.sub(r"\.[a-zA-Z]+$", "", os.path.basename(str(args.image).split("?")[0])) \
        + "_封面_900x383.png"
    out = os.path.abspath(out)
    im.save(out)
    if tmp:
        os.unlink(tmp)
    print("✓ 封面已归一化: %s (%dx%d)" % (out, W, H))


if __name__ == "__main__":
    main()
