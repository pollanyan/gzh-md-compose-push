#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微信读者端 Dark Mode 转换算法的静态移植（预览用）。

参考微信官方开源 wechatjs/mp-darkmode 的颜色计算逻辑（经 WeMD 文档整理）：
  - 微信客户端在读者端对文章 DOM 逐元素做深色转换，仅当颜色在深色下
    「看不清（对比度不足）或刺眼（亮度太高）」时才调整，色相保留。
  - 本脚本把同样规则应用到公众号正文片段的内联 style 上，供预览页
    模拟读者深色模式的观感。输出仍是合法内联样式，仅供预览，不推送。

规则阈值（与官方/WeMD 一致）：
  背景：近白（饱和度<10 且 HSL亮度>40，或感知亮度>235）→ HSL亮度改 100+10-原值
        （纯白 #FFFFFF → #1A1A1A）；感知亮度>190 按比例压到 190；HSL亮度<22 抬到 22
  文字：与背景（默认深底 rgb(25,25,25)，元素自带背景则用转换后的背景）的感知
        亮度差判定：≥250 保留；差>138 且底≤27 压到 138+底；差≥65 保留；
        差<65 按底色明暗分支调到可读
  代码块底：近白同上；其余感知亮度>40 压到 40
  代码块文字：HSL亮度>75 保留；否则饱和度 ×1.1+5、亮度至少 78
  边框/阴影：感知亮度<20 → 深色装饰（亮度夹 10–15、饱和度减半）；饱和度>15 →
        按背景规则（色相保留、亮度上限 190）；其余按文字规则
  不参与转换：颜色名称、var(--x)、图片；rgba/hsla 的透明度保留
"""

import re

# ───────────────────────── 色彩空间工具 ─────────────────────────

def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h[:3])
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb):
    return "#%s" % "".join("%02X" % _clamp(int(round(c)), 0, 255) for c in rgb[:3])


def rgb_to_hsl(r, g, b):
    r, g, b = (c / 255.0 for c in (r, g, b))
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return (0.0, 0.0, l * 100)
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d + (6 if g < b else 0))
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return (h * 60, s * 100, l * 100)


def hsl_to_rgb(h, s, l):
    h, s, l = (h % 360) / 360.0, _clamp(s, 0, 100) / 100.0, _clamp(l, 0, 100) / 100.0
    if s == 0:
        c = 0.0
    else:
        c = (1 - abs(2 * l - 1)) * s
    m = l - c / 2
    hp = h * 6
    x = c * (1 - abs(hp % 2 - 1))
    if hp < 1:   rgb = (c, x, 0)
    elif hp < 2: rgb = (x, c, 0)
    elif hp < 3: rgb = (0, c, x)
    elif hp < 4: rgb = (0, x, c)
    elif hp < 5: rgb = (x, 0, c)
    else:        rgb = (c, 0, x)
    return tuple(_clamp(int(round((v + m) * 255)), 0, 255) for v in rgb)


def perceived(rgb):
    return (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000.0


def _scale_to(rgb, target_p):
    p = perceived(rgb)
    if p <= 0:
        return rgb
    f = target_p / p
    return tuple(_clamp(int(round(c * f)), 0, 255) for c in rgb[:3])


# ───────────────────────── 转换规则 ─────────────────────────
DEFAULT_DARK_BG = (25, 25, 25)  # 官方深色底 #191919


def adjust_background(rgb):
    h, s, l = rgb_to_hsl(*rgb)
    p = perceived(rgb)
    if (s < 10 and l > 40) or p > 235:            # 近白 → 压成深底
        return hsl_to_rgb(h, min(s, 30) if s > 10 else 0, min(100, 100 + 10 - l))
    if p > 190:                                    # 太亮 → 按比例压到 190
        return _scale_to(rgb, 190)
    if l < 22:                                     # 太黑 → 抬到 22
        return hsl_to_rgb(h, s, 22)
    return rgb[:3]


def adjust_code_bg(rgb):
    h, s, l = rgb_to_hsl(*rgb)
    p = perceived(rgb)
    if (s < 10 and l > 40) or p > 235:
        return hsl_to_rgb(h, min(s, 30) if s > 10 else 0, min(100, 100 + 10 - l))
    if p > 40:
        return _scale_to(rgb, 40)
    return rgb[:3]


def adjust_text(rgb, bg_rgb):
    bg_rgb = bg_rgb or DEFAULT_DARK_BG
    p, bgp = perceived(rgb), perceived(bg_rgb)
    if p >= 250:
        return rgb[:3]
    diff = p - bgp
    if diff > 138 and bgp <= 27:                   # 太亮刺眼 → 压到 138+底
        return _scale_to(rgb, 138 + bgp)
    if diff >= 65:                                 # 对比度足够 → 保留
        return rgb[:3]
    h, s, l = rgb_to_hsl(*rgb)
    if bgp >= 100:                                 # 浅色背景
        if l > 50:
            return adjust_text(hsl_to_rgb(h, s, 90 - l), bg_rgb)
        return _scale_to(rgb, min(138, max(0, bgp - 65)))
    if l <= 40:                                    # 深色背景
        return adjust_text(hsl_to_rgb(h, s, 90 - l), bg_rgb)
    return _scale_to(rgb, min(138, bgp + 65))


def adjust_code_text(rgb):
    h, s, l = rgb_to_hsl(*rgb)
    if l > 75:
        return rgb[:3]
    return hsl_to_rgb(h, min(100, s * 1.1 + 5), max(l, 78))


def adjust_border(rgb):
    h, s, l = rgb_to_hsl(*rgb)
    p = perceived(rgb)
    if p < 20:                                     # 深色装饰 → 保持深色
        return hsl_to_rgb(h, s / 2, _clamp(l, 10, 15))
    if s > 15:                                     # 鲜艳色 → 按背景规则（色相保留）
        return adjust_background(rgb)
    return adjust_text(rgb, DEFAULT_DARK_BG)       # 其余按文字规则


# ───────────────────────── 内联样式转换 ─────────────────────────
COLOR_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)")


def _parse_color(tok):
    """返回 (rgb, alpha)。不支持的颜色写法返回 None。"""
    tok = tok.strip()
    if tok.startswith("#") and len(tok) in (4, 5, 7, 9):
        alpha = 1.0
        if len(tok) in (5, 9):                     # 带 alpha 的 HEX
            a = tok[-2:] if len(tok) == 9 else tok[-1]
            alpha = int(a * (2 if len(a) == 1 else 1), 16) / 255.0 if len(a) == 2 else int(a + a, 16) / 255.0
        try:
            return hex_to_rgb(tok), alpha
        except ValueError:
            return None, 1.0
    m = re.match(r"^rgba?\(\s*([^,]+),\s*([^,]+),\s*([^,]+)\s*(?:,\s*([\d.]+)\s*)?\)$", tok)
    if m:
        try:
            rgb = tuple(int(float(x)) for x in m.groups()[:3])
            alpha = float(m.group(4)) if m.group(4) else 1.0
            return rgb, alpha
        except ValueError:
            return None, 1.0
    return None, 1.0


def _convert_value(value, adjust_fn):
    """把 value 里的每个颜色用 adjust_fn 转换；返回 (新值, 首个颜色的转换结果)。"""
    first = None

    def repl(m):
        nonlocal first
        rgb, alpha = _parse_color(m.group(0))
        if rgb is None:
            return m.group(0)                      # 颜色名称/不认识 → 原样（不参与转换）
        out = adjust_fn(rgb)
        if first is None:
            first = out
        return rgb_to_hex(out) if alpha >= 1 else "rgba(%d,%d,%d,%.3g)" % (out[0], out[1], out[2], alpha)

    return COLOR_RE.sub(repl, value), first


def _kind(prop):
    if "background" in prop or prop == "bgcolor":
        return "bg"
    if prop.startswith("border") or prop.startswith("outline") or "shadow" in prop or "column-rule" in prop:
        return "border"
    if prop == "color" or prop.startswith("-webkit-text"):
        return "text"
    return None


def convert_html(html):
    """对公众号正文片段的内联 style 做深色转换（静态模拟 mp-darkmode）。"""
    def fix_style(m):
        decls = [d for d in m.group(1).split(";") if d.strip()]
        parsed = []
        for d in decls:
            if ":" in d:
                p, v = d.split(":", 1)
                parsed.append([p.strip().lower(), v.strip()])
            else:
                parsed.append([None, d.strip()])
        # 第一遍：背景（转换结果作为同元素文字的对比基准）
        bg_rgb = None
        for item in parsed:
            if item[0] and _kind(item[0]) == "bg":
                item[1], first = _convert_value(item[1], adjust_background)
                if first is not None and bg_rgb is None:
                    bg_rgb = first
        # 第二遍：文字 / 边框
        for item in parsed:
            if not item[0]:
                continue
            kind = _kind(item[0])
            if kind == "text":
                item[1] = _convert_value(item[1], lambda rgb: adjust_text(rgb, bg_rgb))[0]
            elif kind == "border":
                item[1] = _convert_value(item[1], adjust_border)[0]
        return 'style="%s"' % "; ".join("%s: %s" % (p, v) if p else v for p, v in parsed)

    return re.sub(r'style="([^"]*)"', fix_style, html)


def _parse_decls(s):
    out = []
    for d in s.split(";"):
        if ":" in d:
            p, v = d.split(":", 1)
            out.append((p.strip().lower(), v.strip()))
    return out


def dark_rules(html):
    """把 html 中每个唯一内联 style 的深色转换结果编译成 CSS 覆盖规则。

    返回 [(原始 style 属性值, "属性:转换值;..." 变化声明串)]——只含发生
    变化的声明。调用方可用 `[style="原始值"]{... !important}` 的属性选择器
    规则放进 `@media (prefers-color-scheme: dark)`，实现与微信读者端一致的
    深浅自适应预览（样式表 !important 优先级高于内联样式，DOM 原样保留，
    复制出去的富文本仍是浅色内联样式）。
    """
    rules = []
    for attr in dict.fromkeys(re.findall(r'style="([^"]*)"', html)):
        conv = convert_html('<i style="%s"></i>' % attr)
        m = re.search(r'style="([^"]*)"', conv)
        if not m:
            continue
        orig = dict(_parse_decls(attr))
        new = dict(_parse_decls(m.group(1)))
        changed = ";".join(
            "%s:%s" % (p, new[p]) for p in orig
            if p in new and new[p] != orig[p])
        if changed:
            rules.append((attr, changed))
    return rules


if __name__ == "__main__":
    import sys
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else src.rsplit(".", 1)[0] + "_深色转换.html"
    open(out, "w", encoding="utf-8").write(convert_html(open(src, encoding="utf-8").read()))
    print("✓ 深色转换预览: %s" % out)
