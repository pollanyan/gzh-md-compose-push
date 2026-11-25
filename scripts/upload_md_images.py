#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描 Markdown 插图，上传到微信图床并替换 src（本地图 / 远程图 / data URI 通吃）。

用法:
    python upload_md_images.py article.md [-o article_wechat.md] [--dry-run]

处理规则:
    1. 匹配 Markdown 图片语法 ![alt](src "title")；src 可以是本地路径、
       http/https URL 或 data:image/...;base64,...。
    2. 远程图下载、data URI 解码到临时目录；本地图按 Markdown 文件所在目录解析。
    3. 调用同目录 mp_imglib_upload.py 批量上传到公众号图片库，读回微信图床 URL。
    4. 只写新文件（默认 <原名>_微信图.md），原 Markdown 不动；图片地址全部替换。

注意: 上传需要公众号后台登录态，依赖 mp_imglib_upload.py 的浏览器通道。
"""
import argparse
import base64
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
IMG_RE = re.compile(r"(!\[[^\]]*\]\()([^)]+)(\))")
UA = "Mozilla/5.0 (compatible; gzh-md-compose-push/1.0)"


def split_src(raw):
    """把 ![alt](src "title") 的 src 与 title 拆开。"""
    raw = raw.strip()
    if raw.startswith("<") and ">" in raw:
        src, rest = raw[1:].split(">", 1)
        return src.strip(), rest.strip()
    parts = raw.split(None, 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def safe_name(src, idx):
    if src.startswith("data:"):
        base = "inline"
    elif re.match(r"^https?://", src):
        base = os.path.basename(urllib.parse.urlparse(src).path) or "remote"
    else:
        base = os.path.basename(src) or "image"
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:60] or "image"
    base = os.path.splitext(base)[0] or base  # 扩展名由 ext_for 按真实字节补，避免重复
    return "img_%03d_%s" % (idx, base)


def ext_for(name, data):
    ext = os.path.splitext(name)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
        return ext if ext != ".jpeg" else ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"GIF8"):
        return ".gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def materialize(md_path, src, idx, workdir):
    """把 src 落地成 workdir 下的唯一文件名，返回 (绝对路径, 错误信息)。"""
    name = safe_name(src, idx)
    if src.startswith("data:"):
        try:
            header, payload = src.split(",", 1)
            data = base64.b64decode(payload)
        except Exception as e:
            return None, "data URI 解码失败: %s" % e
    elif re.match(r"^https?://", src):
        try:
            req = urllib.request.Request(src, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
        except Exception as e:
            return None, "下载失败 %s: %s" % (src, e)
    else:
        path = src if os.path.isabs(src) else os.path.join(os.path.dirname(os.path.abspath(md_path)), src)
        if not os.path.isfile(path):
            return None, "本地图片不存在: %s" % path
        with open(path, "rb") as f:
            data = f.read()
    if not data:
        return None, "图片为空: %s" % src
    path = os.path.join(workdir, name + ext_for(name, data))
    with open(path, "wb") as f:
        f.write(data)
    return path, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md", help="Markdown 文件路径")
    ap.add_argument("-o", "--output", help="输出 Markdown（默认 <原名>_微信图.md）")
    ap.add_argument("--dry-run", action="store_true", help="只列出待上传图片，不调用浏览器")
    args = ap.parse_args()

    md_path = os.path.abspath(args.md)
    if not os.path.isfile(md_path):
        sys.exit("找不到 Markdown: %s" % md_path)
    out_path = os.path.abspath(args.output or (os.path.splitext(md_path)[0] + "_微信图.md"))
    md = open(md_path, encoding="utf-8").read()
    matches = list(IMG_RE.finditer(md))
    if not matches:
        open(out_path, "w", encoding="utf-8").write(md)
        print("Markdown 中没有插图，已原样写出: %s" % out_path)
        return

    workdir = tempfile.mkdtemp(prefix="gzh-md-images-")
    try:
        files, errors, infos = [], [], []
        for i, m in enumerate(matches, 1):
            src, title = split_src(m.group(2))
            path, err = materialize(md_path, src, i, workdir)
            if err:
                errors.append((m.start(), src, err))
                infos.append(None)
            else:
                files.append(path)
                infos.append((src, title, path))

        print("待上传 %d 张，落地成功 %d 张" % (len(matches), len(files)))
        for err in errors:
            print("!! %s" % err[2])
        if args.dry_run:
            for _, title, path in [x for x in infos if x]:
                print("DRY-RUN %s %s" % (os.path.basename(path), title))
            return

        if not files:
            sys.exit("没有可上传的图片，未写出新文件")

        subprocess.run([sys.executable, os.path.join(BASE, "mp_imglib_upload.py"),
                        *files, "--out", workdir], check=False)
        json_path = os.path.join(workdir, "imglib_urls.json")
        if not os.path.isfile(json_path):
            sys.exit("图片库未返回 imglib_urls.json（登录态或上传失败），未写出新文件")
        import json
        items = json.load(open(json_path, encoding="utf-8"))
        by_name = {}
        for it in items:
            for k in ("file", "title"):
                if it.get(k):
                    by_name[os.path.basename(str(it[k]))] = it.get("full", "")
        by_path = {os.path.basename(p): by_name.get(os.path.basename(p), "") for p in files}

        missing = [os.path.basename(p) for p in files if not by_path[os.path.basename(p)]]
        for name in missing:
            print("!! 没拿到微信 URL: %s（将保留原地址）" % name)

        pieces, pos, replaced = [], 0, 0
        for m, info in zip(matches, infos):
            pieces.append(md[pos:m.start()])
            src, title = split_src(m.group(2))
            url = by_path.get(os.path.basename(info[2]), "") if info else ""
            if url:
                pieces.append(m.group(1) + url + ((" " + title) if title else "") + m.group(3))
                replaced += 1
            else:
                pieces.append(m.group(0))
            pos = m.end()
        pieces.append(md[pos:])
        open(out_path, "w", encoding="utf-8").write("".join(pieces))
        print("已替换 %d/%d 张图片地址，写出: %s" % (replaced, len(matches), out_path))
        if replaced != len(matches):
            sys.exit(1)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
