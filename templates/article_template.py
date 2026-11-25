# -*- coding: utf-8 -*-
"""文章模板：复制本文件改名后填内容，再 `python scripts/mp_full.py push 本文件.py`。

两条硬规则（不遵守会被微信结构检测拦下）：
  1. 文字背景禁用渐变，一律纯色；
  2. 每个 font-size 都要配 line-height，且 line-height 不小于 font-size。

正文里要放图，用下面的 `_img("文件名.png")`：它从同目录的 imglib_urls.json 取
微信侧的 mmbiz URL。先跑一次上传：
    python scripts/mp_imglib_upload.py 图1.png 图2.png
（该脚本默认把 imglib_urls.json 写到当前工作目录，也就是本文件所在目录。）
直接写本地路径或 data-URI 都不生效。
"""
import json
import os

TITLE = "在这里写标题（≤64 字符）"
DIGEST = "在这里写摘要，留空则由正文开头自动抓取"

# 署名：默认从用户配置自动读取（配置项 author，见 scripts/push_config.py）。
# 优先级：本文件显式改这一行 > 配置文件 > 默认空字符串（署名留空）。
def _load_author():
    import json as _json
    _p = os.environ.get(
        "GZH_PUSH_CONFIG",
        os.path.expanduser("~/.config/gzh-md-compose-push/config.json"))
    try:
        with open(_p, encoding="utf-8") as _f:
            return (_json.load(_f).get("author") or "").strip()
    except (OSError, ValueError):
        return ""

AUTHOR = _load_author()

_IMGLIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imglib_urls.json")


def _p(text, size=16, lh=1.75, color="#3F3F46", mb=16, bold=False):
    return (
        '<p style="margin:0 0 %spx;font-size:%spx;line-height:%s;color:%s;'
        'font-weight:%s;letter-spacing:.3px;">%s</p>'
        % (mb, size, lh, color, 700 if bold else 400, text)
    )


def _h2(text):
    return (
        '<section style="margin:30px 0 14px;padding-left:12px;'
        'border-left:4px solid #0E9384;">'
        '<span style="font-size:19px;line-height:1.45;font-weight:800;color:#18181B;">'
        '%s</span></section>' % text
    )


def _quote(text):
    # 注意：纯色背景，不要用 linear-gradient
    return (
        '<section style="margin:20px 0;padding:16px 18px;background:#F0FAF8;'
        'border-radius:10px;">'
        '<p style="margin:0;font-size:15px;line-height:1.7;color:#0F766E;">%s</p>'
        '</section>' % text
    )


def _img(name, caption="", width=100):
    """插入一张正文图。name 是上传时的**文件名**（不是本地路径）。

    <img src> 必须是 mmbiz.qpic.cn 的 URL —— 本地路径 / data-URI 粘过去都是死图。
    URL 来源：`python scripts/mp_imglib_upload.py <图...>` 生成同目录的
    imglib_urls.json（键为 file / title，值 full 是原图 URL）。
    """
    if not os.path.exists(_IMGLIB):
        raise SystemExit(
            "找不到 %s\n先跑：python scripts/mp_imglib_upload.py %s" % (_IMGLIB, name))
    with open(_IMGLIB, encoding="utf-8") as fh:
        items = json.load(fh)
    for it in items:
        if it.get("file") == name or it.get("title") == name:
            url = it["full"]
            break
    else:
        raise SystemExit("imglib_urls.json 里没有 %s（现有：%s）"
                         % (name, ", ".join(i.get("title", "?") for i in items)))
    cap = ('<p style="margin:8px 0 18px;font-size:13px;line-height:1.6;'
           'color:#8A8A93;text-align:center;">%s</p>' % caption) if caption else ""
    return ('<img src="%s" style="width:%s%%;display:block;margin:18px auto 0;'
            'border-radius:8px;"/>%s' % (url, width, cap))


def build_content():
    """返回正文 HTML。必须全内联样式——公众号会剥离 <style> 和 class。"""
    parts = []
    parts.append(_p("开头两句话点题，让读者知道这篇能给他什么。", size=16))
    parts.append(_h2("一、第一个小节"))
    parts.append(_p("正文段落。"))
    # 要放图就取消下面这行注释（前提是先跑过 mp_imglib_upload.py）：
    # parts.append(_img("封面图.png", "图注写这里"))
    parts.append(_quote("想强调的一句话放这里。"))
    parts.append(_h2("二、第二个小节"))
    parts.append(_p("正文段落。"))
    return "".join(parts)
