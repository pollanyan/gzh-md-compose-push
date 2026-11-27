#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown → 微信公众号 HTML（纯内联、span leaf 合规、多主题、代码高亮）。

用法:
    # 单主题生成（浅色配色）
    python md_to_gzh.py article.md --theme graphite-minimal -o out.html
    # 单主题生成（深色配色：焊死深底浅字，读者任何模式下都稳定显示深色卡）
    python md_to_gzh.py article.md --theme graphite-minimal --scheme dark -o out.html
    # 生成全部主题×配色预览（写一页 index.html，供用户挑选）
    python md_to_gzh.py article.md --all-themes --preview-dir ./themes

设计要点（踩坑修正）:
  1. 代码块「每行一个 <span leaf>」，行内高亮用**不带 leaf 的彩色 span**。
     实测：每个 token 一个 leaf 会被公众号编辑器当成原子节点重排，
     导致一行被拆成多行、缩进错位、行距撑大。每行单 leaf 可避免。
  2. 缩进用 &nbsp; 放在 leaf 内（保住宽度），字体 Courier New，
     line-height 1.6，不用 white-space:pre / class。
     长行用 white-space:nowrap（微信默认 break-spaces 会强行折行）+ 外层
     overflow-x:auto 支持左右滑动，微信编辑器实测两者都保留。
  3. 正文中文必须包 leaf；中文标点全角；代码/URL/英文专名原样。
  4. 所有样式内联，禁 style/script/div/class/id/position/float/grid/CSS 变量。
"""
import argparse
import html
import os
import re
import sys
import unicodedata

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ───────────────────────── 主题（源自 gzh-layout-pro theme-index） ─────────────────────────
THEMES = {
    "moyu-green":       dict(name="摸鱼绿",     primary="#059669", accent="#A7F3D0", ink="#1F2937", body="#4B5563", muted="#9CA3AF", line="#E5E7EB", bg="#F0FDF4", quote="#059669", scene="教程、测评、清单、工具盘点"),
    "red-white":        dict(name="红白色系",   primary="#DC2626", accent="#FECACA", ink="#1F2937", body="#4B5563", muted="#9CA3AF", line="#E5E7EB", bg="#FEF2F2", quote="#DC2626", scene="深度分析、观点、力量感话题"),
    "graphite-minimal": dict(name="石墨极简风", primary="#52525B", accent="#52525B", ink="#27272A", body="#52525B", muted="#A1A1AA", line="#E4E4E7", bg="#FAFAFA", quote="#52525B", scene="设计、科技评论、专业观点、高端品牌"),
    "zen-whitespace":   dict(name="留白禅意风", primary="#4A5D52", accent="#B5C8BC", ink="#2F3B35", body="#4A5D52", muted="#9CA79E", line="#E3E9E4", bg="#F6F8F5", quote="#4A5D52", scene="禅意、极简生活、深度随笔、艺术留白"),
    "moyu-ticket":      dict(name="摸鱼票据风", primary="#059669", accent="#A7F3D0", ink="#1F2937", body="#4B5563", muted="#9CA3AF", line="#D1D5DB", bg="#ECFDF5", quote="#059669", scene="测评、工具对比、创意评测"),
    "olive-journal":    dict(name="橄榄手记",   primary="#1e1f23", accent="#ed7b2f", ink="#1e1f23", body="#444444", muted="#9CA3AF", line="#E5E7EB", bg="#F7F7F5", quote="#ed7b2f", scene="内刊手记、深度评测、案例复盘"),
}

# 深色配色方案（每套主题一份）：焊死深底浅字。
# 为什么不「不写死颜色交给微信反色」：实测 inherit 方案在浅色环境会落到白字
# （2026-11-25 用户测试踩坑），且公众号正文禁 @media，做不了运行时自适应；
# 显式深色是唯一稳定的做法。代码块用比页面更深的底 + 亮色高亮。
DARK_SCHEMES = {
    "moyu-green":       dict(name="摸鱼绿·深色",   bg="#0F1D16", ink="#ECFDF5", body="#D1D5DB", muted="#8CA79A", line="#2E3B33", primary="#34D399", accent="#34D399", quote="#34D399"),
    "red-white":        dict(name="红白色系·深色", bg="#1E1414", ink="#FEF2F2", body="#D6D0D0", muted="#A89A9A", line="#3D2C2C", primary="#F87171", accent="#F87171", quote="#F87171"),
    "graphite-minimal": dict(name="石墨极简风·深色", bg="#18181B", ink="#FAFAFA", body="#D4D4D8", muted="#A1A1AA", line="#3F3F46", primary="#A1A1AA", accent="#A1A1AA", quote="#A1A1AA"),
    "zen-whitespace":   dict(name="留白禅意风·深色", bg="#141B17", ink="#F0F5F1", body="#CFDCD3", muted="#8FA79A", line="#2C3A31", primary="#8FBC9F", accent="#8FBC9F", quote="#8FBC9F"),
    "moyu-ticket":      dict(name="摸鱼票据风·深色", bg="#0F1D16", ink="#ECFDF5", body="#D1D5DB", muted="#8CA79A", line="#374151", primary="#34D399", accent="#34D399", quote="#34D399"),
    "olive-journal":    dict(name="橄榄手记·深色", bg="#191A1E", ink="#F4F4F5", body="#D4D4D8", muted="#9CA3AF", line="#3A3B40", primary="#ED7B2F", accent="#ED7B2F", quote="#ED7B2F"),
}
DEFAULT_THEME = "graphite-minimal"

# 代码高亮配色（ graphite 系的紫/绿/蓝，微信实测保留）
C_KW = "#7C3AED"     # 关键字
C_STR = "#15803D"    # 字符串
C_CONST = "#2563EB"  # 常量
C_NUM = "#C2410C"    # 数字
C_PUNCT = "#71717A"  # 标点
C_CODE = "#27272A"   # 普通标识符

# 深色配色方案的代码高亮：深底块上的亮色系
CODE_DARK_BG = "#101014"
CODE_LIGHT_ON_DARK = dict(KW="#C4B5FD", STR="#86EFAC", CONST="#93C5FD",
                          NUM="#FDBA74", PUNCT="#A1A1AA", CODE="#E4E4E7")

# 深色配色下，行内代码/角标用更亮的蓝（白底用 #2563EB，深底太暗）
BLUE_DARK = "#5C9DFF"

KW = {"export", "const", "as", "true", "false", "null", "let", "var", "function",
      "return", "import", "from", "new", "class", "if", "else", "def", "self",
      "print", "for", "in", "while", "try", "except", "with", "lambda", "await",
      "async", "type", "interface", "public", "private", "void", "int", "str"}


def esc(s):
    return html.escape(s, quote=False).replace("'", "&#39;")


def leaf(s):
    return '<span leaf="">%s</span>' % s


def cspan(txt, color):
    """行内彩色 span —— 不带 leaf（关键：避免被当原子节点拆行）。"""
    return '<span style="color:%s;">%s</span>' % (color, esc(txt))


def code_line(line, lang, t=None):
    """把一行代码转成「一个 leaf」：缩进 &nbsp; + 行内彩色 span。

    white-space:nowrap —— 微信编辑器默认把 p 设成 break-spaces（长代码行
    被强行折行，2026-11-26 用户手机实测反馈）；nowrap 让行保持单行，
    配合外层 overflow-x:auto 实现左右滑动查看（微信探针实证两者都保留）。
    """
    lead = len(line) - len(line.lstrip(" "))
    indent = "&nbsp;" * lead
    inner = _highlight(line[lead:], lang, t)
    return '<p style="margin:0;font-family:Courier New,monospace;font-size:13px;line-height:1.6;white-space:nowrap;">' \
           '<span leaf="">%s%s</span></p>' % (indent, inner)


def _highlight(line, lang, t=None):
    pal = CODE_LIGHT_ON_DARK if (t and t.get("code_dark")) else dict(
        KW=C_KW, STR=C_STR, CONST=C_CONST, NUM=C_NUM, PUNCT=C_PUNCT, CODE=C_CODE)
    toks, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c in ('"', "'", "`"):
            j = i + 1
            while j < n and line[j] != c:
                if line[j] == "\\":
                    j += 1
                j += 1
            j = min(j + 1, n)
            toks.append(cspan(line[i:j], pal["STR"])); i = j; continue
        if line[i:i + 2] == "//" or (lang in ("py", "python", "sh", "bash") and c == "#"):
            toks.append(cspan(line[i:], pal["PUNCT"])); break
        if c.isalpha() or c == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] in "_$"):
                j += 1
            w = line[i:j]
            if w in KW:
                col = pal["KW"]
            elif re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", w):
                col = pal["CONST"]
            else:
                col = pal["CODE"]
            toks.append(cspan(w, col)); i = j; continue
        if c.isdigit():
            j = i
            while j < n and (line[j].isdigit() or line[j] in ".x_"):
                j += 1
            toks.append(cspan(line[i:j], pal["NUM"])); i = j; continue
        toks.append(cspan(c, pal["PUNCT"])); i += 1
    return "".join(toks)


def code_block(code, lang="text", title="", t=None):
    # overflow-x:auto：长代码行 nowrap 后产生横向溢出 → 可左右滑动查看；
    # 微信 ProseMirror 保留该声明（探针实证：父 section overflowX=auto，
    # scrollWidth 1237 > clientWidth 554）。2026-11-26 用户手机实测后加。
    head = ('<section style="margin:0 10px 22px;border:1px solid %s;border-left:3px solid %s;overflow-x:auto;">'
            % (t["line"], t["primary"]))
    if title:
        head += ('<section style="padding:7px 14px;border-bottom:1px solid %s;">'
                 '<span leaf="" style="font-size:11px;color:%s;font-family:Courier New,monospace;letter-spacing:1px;">%s</span>'
                 '</section>' % (t["line"], t["muted"], esc(title)))
    body_bg = ';background:%s' % CODE_DARK_BG if t and t.get("code_dark") else ""
    body = '<section style="padding:12px 14px;%s">' % body_bg if body_bg else '<section style="padding:12px 14px;">'
    for ln in code.split("\n"):
        body += code_line(ln, lang, t)
    return head + body + '</section></section>'


# ───────────────────────── 行内标记 ─────────────────────────
BLUE = "#2563EB"  # 行内代码/引用角标专用蓝（用户指定，无底色）

# Obsidian 预处理把 frontmatter title 单独写成这一行；正文里不再插 # 标题。
TITLE_MARK = re.compile(r"^<!--\s*gzh-title:\s*(.*?)\s*-->\s*$", re.I)
# 全篇统一收集超链接：任何章节的 [文字](URL) / 裸 URL 都进「附：取证来源」。
MD_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\((https?://[^)]+)\)")
BARE_URL = re.compile(r"(?<![\w(<])(https?://[^\s)）\]>,，。；;]+)")
REF_LINE = re.compile(r"^\[(\d+)\]\s*(.+?)[:：]\s*(https?://\S+)\s*$")
REF_ITEM = re.compile(r"^[-*]\s+\[[^\]]+\]\((https?://[^)]+)\)\s*$")
APPENDIX_HEAD = re.compile(r"^#{1,3}\s+(?:\d+(?:\.\d+)*\s+)?附[：:]?\s*取证来源")


def ref_sup(n, t=None):
    """正文引用角标 [[N]] → 蓝色上标（右上角，font-size:10px）。
       明暗自适应主题用 #3B82F6（明暗两底都 readable），其余用 #2563EB。"""
    blue = t.get("blue", BLUE) if t else BLUE
    return ('<span style="color:%s;font-weight:700;">'
            '<span style="font-size:10px;vertical-align:super;">%s</span></span>'
            % (blue, leaf("[%s]" % n)))


def _links_to_refs(text, t):
    """把正文里的 Markdown 链接/裸 URL 换成「文字 + [[N]]」；N 来自全篇统一编号。"""
    by_url = t.get("_ref_urls") or {}

    def repl(m):
        n = by_url.get(m.group(2).strip())
        return m.group(1) + ("[[%s]]" % n if n else "")

    text = MD_LINK.sub(repl, text)

    def bare(m):
        u = m.group(0).rstrip(".,;:，。；)")
        n = by_url.get(u)
        return u + ("[[%s]]" % n if n else "")

    return BARE_URL.sub(bare, text)


def inline(text, t):
    """行内标记（全部包 leaf）：
       **加粗** → 主色加粗；`代码` → 蓝色无底色；[[N]] → 蓝色右上标；
       ==高亮== → 主题下划线；普通文本 → leaf。
       注意：公众号正文不插超链接，任何超链接统一换成文字 + 角标，URL 走附录。"""
    text = _links_to_refs(text, t)
    slots = []
    def stash(rx, kind):
        nonlocal text
        def f(m):
            slots.append((kind, m.group(1)))
            return "\x01%d\x02" % (len(slots) - 1)
        text = re.sub(rx, f, text)
    stash(r"`([^`]+)`", "code")
    stash(r"\*\*([^*]+)\*\*", "bold")
    stash(r"\[\[(\d+)\]\]", "ref")
    stash(r"==([^=]+)==", "ul")
    pat = re.compile(r"\x01\d+\x02")
    out, pos = [], 0
    for m in pat.finditer(text):
        if m.start() > pos:
            out.append(leaf(esc(text[pos:m.start()])))
        kind, val = slots[int(m.group()[1:-1])]
        if kind == "code":
            out.append('<span style="color:%s;font-family:Courier New,monospace;font-size:14px;font-weight:600;">%s</span>'
                       % (t.get("blue", BLUE), leaf(esc(val))))
        elif kind == "bold":
            out.append('<span style="color:%s;font-weight:700;">%s</span>' % (t.get("bold", t["primary"]), leaf(esc(val))))
        elif kind == "ref":
            out.append(ref_sup(val, t))
        else:  # 下划线（主题色）
            out.append('<span style="border-bottom:2px solid %s;font-weight:600;">%s</span>'
                       % (t["accent"], leaf(esc(val))))
        pos = m.end()
    if pos < len(text):
        out.append(leaf(esc(text[pos:])))
    return "".join(out) if out else leaf("")


def para(text, t):
    return ('<p style="margin:0 0 22px;font-size:15px;line-height:1.8;color:%s;'
            'text-align:left;letter-spacing:0.3px;">%s</p>' % (t["body"], inline(text, t)))


def number_chapter(no, en, title, t, first=False):
    """大号章节编号（44px）+ 英文标签 + 中文标题；附录用这种同款组件。"""
    return ('<section style="margin-top:%s;margin-bottom:24px;padding:0 10px;">'
            '<section style="padding-bottom:16px;border-bottom:1px solid %s;">'
            '<p style="font-size:44px;font-weight:900;color:%s;margin:0;line-height:1;letter-spacing:-2px;">%s</p>'
            '<section style="margin-top:-6px;">'
            '<p style="font-size:10px;color:%s;letter-spacing:3px;margin:0 0 6px;">%s</p>'
            '<h3 style="font-size:20px;font-weight:800;color:%s;margin:0;line-height:1.4;">%s</h3>'
            '</section></section></section>'
            % ("16px" if first else "56px", t["line"], t["line"], leaf(no),
               t["muted"], leaf(en), t["ink"], inline(title, t)))


def h3(title, t):
    """小章节标题：不加左侧竖线（2026-11-26 用户反馈与引用块竖线叠在一起别扭）。"""
    return ('<p style="font-size:16px;font-weight:700;color:%s;margin:28px 0 14px;'
            'line-height:1.4;">%s</p>'
            % (t["ink"], inline(title, t)))


def quote_block(text, t, label=None):
    """引用段：浅灰底 + 柔和左侧细线（照用户给的其他公众号截图，2026-11-26 定稿）。
    浅色 #F5F5F5 底 / #D4D4D8 细线 / #3F3F3F 字；--scheme dark 时用深灰版本。
    预览的深色自适配由 wrap_preview 的微信读者端算法自动转色，不需要第二套文件。
    正文走 inline() 行内解析（**加粗**/`行内代码`/角标都要生效）；text-align 显式 left。"""
    dark = bool(t.get("code_dark"))
    bg = "#383838" if dark else "#F5F5F5"
    bar = "#A1A1AA" if dark else "#D4D4D8"
    fg = "#A5A5A5" if dark else "#3F3F3F"
    return ('<section style="background:%s;border-left:2px solid %s;'
            'padding:14px 16px;margin:0 10px 28px;">'
            '<p style="font-size:16px;font-weight:700;color:%s;margin:0;line-height:1.7;text-align:left;">%s</p>'
            '</section>' % (bg, bar, fg, inline(text, t)))


def image_block(src, alt, t):
    """整行 ![alt](src) → 带细线框的图片块（无底色），图下左对齐一行说明。
       src 必须是 mmbiz 图床 URL 或可访问的 http(s) URL；本地路径由
       upload_md_images.py 在推送前替换，纯预览时远程 URL 原样输出。"""
    cap = ""
    if alt:
        cap = ('<p style="font-size:12px;color:%s;margin:8px 0 0;text-align:left;">%s</p>'
               % (t["muted"], leaf(esc(alt))))
    return ('<section style="margin:0 10px 24px;border:1px solid %s;padding:10px;">'
            '<img src="%s" alt="%s" style="max-width:100%%;display:block;margin:0 auto;">%s</section>'
            % (t["line"], html.escape(src, quote=True), html.escape(alt, quote=True), cap))


IMG_LINE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$")


def _text_width(s):
    """显示宽度：CJK/全角 = 2，emoji（非 BMP 字符，如 🟢🔴）= 3（实测字形
    宽约 1.3 倍字号，按 3 估才不会把状态列挤到换行），变体选择符/零宽连接符
    = 0，ASCII = 1（忽略行内代码反引号与加粗标记）。"""
    w = 0
    for ch in s.replace("`", "").replace("**", ""):
        o = ord(ch)
        if o in (0xFE0F, 0x200D):
            continue
        if o > 0xFFFF:
            w += 3
        else:
            w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


# 单行列阈值：列内最长单元格显示宽 ≤ 此值（单位：ASCII=1/CJK=2/emoji=3）
# 时，整列按「内容必然单行」处理——td 加 white-space:nowrap、列宽按
# 整格最大宽 + 8 保底。按内容特征判定，与表头叫什么无关（2026-11-25
# 由「状态列」特例泛化而来：状态/评级/短枚举列都自动覆盖）。
SINGLE_LINE_MAX = 12


def _col_stats(rows, ncol):
    """每列的 (最大显示宽, 最长不可断片段, 正文平均宽)。"""
    maxw, tokw, avg = [0] * ncol, [0] * ncol, [0.0] * ncol
    for ri, r in enumerate(rows):
        cells = (r + [""] * ncol)[:ncol]
        for ci, c in enumerate(cells):
            plain = c.replace("`", "").replace("**", "")
            w = _text_width(plain)
            if w > maxw[ci]:
                maxw[ci] = w
            if ri > 0:
                avg[ci] += w
            for piece in re.split(r"[\s\-—–、，,;；/|（()）]+", plain):
                pw = _text_width(piece)
                if pw > tokw[ci]:
                    tokw[ci] = pw
    return maxw, tokw, avg


def single_line_cols(rows, ncol):
    """按内容判定「整列单行」的列号集合：最长单元格都放得下，就该 nowrap
    并按整格保底列宽——不依赖表头名称。"""
    maxw = _col_stats(rows, ncol)[0]
    return {ci for ci in range(ncol) if maxw[ci] <= SINGLE_LINE_MAX}


def auto_col_widths(rows, ncol, single=None):
    """按内容自动分配列宽（百分比列表，和为 100）。

    依据（用户约定「表格列宽按内容适配」）：
      - 权重 = 0.55×列最大显示宽 + 0.45×列平均显示宽（正文行），
        长文列宽、短文列窄，单行超长不至于独占；
      - 不可断片段（空格/连字符/顿号等分隔符之间的 ASCII 连续串，
        如 @narumitw/pi-goal）+ 内边距作保底，避免词中折行；
      - single（单行列，见 single_line_cols）单元格渲染时 white-space:nowrap
        强制单行，保底按**整格最大宽 + 8** 算（2026-11-25 手机实测
        「🟢 强」在 8% 列宽下竖排换行）；
      - 夹在 8%–60% 后重归一，防止单列过窄或独占。
    """
    maxw, tokw, avg = _col_stats(rows, ncol)
    if single is None:
        single = single_line_cols(rows, ncol)
    body_n = max(1, len(rows) - 1)
    weights = []
    for ci in range(ncol):
        w = 0.55 * maxw[ci] + 0.45 * (avg[ci] / body_n)
        floor = (maxw[ci] + 8) if ci in single else (tokw[ci] + 5)
        w = max(w, floor, 6.0)
        weights.append(w)
    pct = [x / sum(weights) * 100 for x in weights]
    pct = [min(max(p, 8), 60) for p in pct]
    s2 = sum(pct)
    ints = [int(round(p / s2 * 100)) for p in pct]
    ints[-1] += 100 - sum(ints)
    return ints


def data_table(rows, t, col_widths=None, status_col=None):
    """表格：外层 overflow-x:auto + table-layout:fixed + <colgroup> 按内容比例分配列宽
       （col_widths 缺省时用 auto_col_widths 自动计算）；单元格全边框（含竖线网格），
       表头居中加粗、下边框主题色 2px；status_col 列（强/平/弱）加粗。"""
    if not rows:
        return ""
    header, body = rows[0], rows[1:]
    ncol = len(header)
    if col_widths is None and ncol >= 2:
        single = single_line_cols(rows, ncol)
        col_widths = auto_col_widths(rows, ncol, single=single)
    out = ['<section style="margin:0 10px 24px;overflow-x:auto;">',
           # 注意：本串**不走 % 格式化**，百分号必须写单个 %（写成 %% 会原样
           # 输出成 "width:100%%"，浏览器视为非法值 → 表格宽度回退 auto →
           # 内容被压扁成细条且不产生横向溢出，滚动条消失。2026-11-25 实测。
           # 表格宽度：width:100%（随容器）+ min-width:620px（窄屏不被压扁、
           # 外层 overflow-x:auto 产生横向溢出 → 可左右滑动）。
           # ① 关键：**本串不走 % 格式化，百分号只能写单个 %**——写成 %% 会原样
           #    输出成 "width:100%%"，浏览器视为非法值 → 表格宽度回退 auto →
           #    内容被压扁成细条、无横向溢出、滚动条消失（2026-11-25 实测）。
           # ② 微信 ProseMirror 会把 min-width 收敛成 100px、表格宽=容器宽，
           #    但**列宽 width="%" 属性保留**——读者端因此是「表格随屏、列按
           #    比例、长内容正常换行」，不会压扁（探针实证）。
           '<table style="width:100%;min-width:620px;border-collapse:collapse;table-layout:fixed;font-size:13px;line-height:1.7;">']
    if col_widths and len(col_widths) == ncol:
        out.append('<colgroup>' + "".join('<col style="width:%d%%;">' % w for w in col_widths) + '</colgroup>')
    # 列宽三保险（2026-11-25 手机实测：微信 ProseMirror 编辑器按自家 schema
    # 重建表格，colgroup 与 style 里的 width 都被剥离 → 平分列宽）：
    # ① data-colwidth（px，prosemirror-tables 的列宽正式通道，编辑器会保留
    #    并在序列化时还原成单元格宽度）；② 每个 th/td 内联 style width；
    # ③ colgroup（浏览器直接打开 HTML 时用）。
    # 列宽通道（2026-11-25 手机实测 + 探针实验定稿）：
    #  ① width="%" 属性 —— 微信 ProseMirror 保留 HTML 属性形式、剥离 style
    #     里的 width；百分比随屏幕宽度自适应。**必须只靠它**：同时写
    #     data-colwidth(px) 时微信按 px 定宽，手机上 640px 表格超出 375px 屏，
    #     首列占比飙到 27%（探针实证：去掉 data-colwidth 后表格宽=容器宽
    #     558px，列宽按 % 自适应，状态列 10%）。
    #  ② 单元格 style width + colgroup —— 浏览器直开用；微信会剥离。
    cwid = lambda ci: (' width="%d%%"' % col_widths[ci]) \
        if (col_widths and len(col_widths) == ncol) else ""
    wstyle = lambda ci: ("width:%d%%;" % col_widths[ci]) if (col_widths and len(col_widths) == ncol) else ""
    # 单行列（内容短、强制单行）用更小的水平内边距，避免该列视觉偏宽
    pad = lambda ci: ("padding:8px 6px;" if ci in single else "padding:8px 12px;")
    padh = lambda ci: ("padding:9px 6px;" if ci in single else "padding:9px 12px;")
    out.append("<tr>" + "".join(
        '<th%s style="text-align:center;%sborder:1px solid %s;border-bottom:2px solid %s;color:%s;font-weight:800;white-space:nowrap;%s">%s</th>'
        % (cwid(ci), padh(ci), t["line"], t["primary"], t["ink"], wstyle(ci), leaf(esc(c))) for ci, c in enumerate(header)) + "</tr>")
    for r in body:
        cells = (r + [""] * ncol)[:ncol]
        tds = []
        for ci, c in enumerate(cells):
            cell = inline(c, t)
            if status_col is not None and ci == status_col:
                cell = '<span style="font-weight:800;color:%s;">%s</span>' % (t["ink"], leaf(esc(c)))
            # 状态列内容短（🟢 强 等）且必须单行：white-space:nowrap 兜底防换行；
            # 其余内容列保持可换行
            nowrap = "white-space:nowrap;" if ci in single else ""
            tds.append('<td%s style="%sborder:1px solid %s;color:%s;vertical-align:top;overflow-wrap:break-word;%s%s">%s</td>'
                       % (cwid(ci), pad(ci), t["line"], t["body"], nowrap, wstyle(ci), cell))
        out.append("<tr>" + "".join(tds) + "</tr>")
    out.append("</table></section>")
    return "".join(out)


def appendix(refs, t):
    """取证来源大章节：蓝色来源名 + 右上角标；References 小节纯文本 URL（无超链接）。
       refs = [(n, 标题, url), ...]"""
    s = [number_chapter("附", "APPENDIX", "取证来源", t),
         '<section style="padding:0 10px;">']
    for n, label, url in refs:
        s.append('<p style="margin:0 0 10px;font-size:14px;line-height:1.8;color:%s;text-align:left;">'
                 '<span leaf="">• </span><span style="color:%s;">%s</span>%s</p>'
                 % (t["body"], t.get("blue", BLUE), leaf(esc(label)), ref_sup(n, t)))
    s.append(h3("References", t))
    for n, label, url in refs:
        s.append('<p style="font-size:13px;color:%s;margin:0 0 12px;line-height:1.7;text-align:left;font-family:Courier New,monospace;">'
                 '<span leaf="">[%s] %s:</span><br><span leaf="">%s</span></p>'
                 % (t["muted"], n, esc(label), esc(url)))
    s.append('</section>')
    return "".join(s)


def bullet_list(items, t, ordered=False):
    out = ['<section style="margin:0 10px 22px;">']
    for i, it in enumerate(items):
        mark = ("%d." % (i + 1)) if ordered else "•"
        out.append('<p style="margin:0 0 8px;font-size:15px;line-height:1.8;color:%s;">%s&nbsp;%s</p>'
                   % (t["body"], leaf(mark), inline(it, t)))
    out.append("</section>")
    return "".join(out)


# ───────────────────────── Markdown → HTML ─────────────────────────
def resolve_theme(theme_key, scheme="light"):
    """浅色用 THEMES 原配色；深色叠加 DARK_SCHEMES（焊死深底浅字 + 亮色代码高亮）。"""
    t = dict(THEMES.get(theme_key, THEMES[DEFAULT_THEME]))
    if scheme == "dark":
        d = DARK_SCHEMES.get(theme_key)
        if d:
            t.update(d)
            t["code_dark"] = True
            t["blue"] = BLUE_DARK
    return t


def _fence_flags(lines):
    """标记哪些行位于 ``` 代码块内：代码注释里的 `# 1)` 不能当标题/引用。"""
    flags, inside = [], False
    for ln in lines:
        if ln.strip().startswith("```"):
            flags.append(True)
            inside = not inside
        else:
            flags.append(inside)
    return flags


def _parse_title(lines, fence):
    """优先用 Obsidian frontmatter 单独给出的 title；否则第一个 # 作标题。"""
    for n, ln in enumerate(lines):
        if not fence[n]:
            m = TITLE_MARK.match(ln.strip())
            if m:
                return m.group(1).strip(), n
    for n, ln in enumerate(lines):
        if not fence[n] and ln.startswith("# "):
            return ln[2:].strip(), n
    return "", -1


def _heading_levels(lines, fence, title_idx):
    """正文里的一级/二级标题行号（标题行与代码块行已排除）。"""
    h1, h2 = [], []
    for n, ln in enumerate(lines):
        if fence[n] or n == title_idx:
            continue
        if ln.startswith("# "):
            h1.append(n)
        elif ln.startswith("## "):
            h2.append(n)
    return h1, h2


def collect_refs(lines, fence):
    """全篇扫描超链接 → [(编号, 标题, URL)] 与 URL→编号 映射。
       任何章节的 [文字](URL)/裸 URL/[N] 标题: URL 都收；重复 URL 复用编号。"""
    refs, by_url, used = [], {}, set()

    def add(num, label, url):
        url = url.strip()
        if url in by_url:
            return by_url[url]
        if num is None:
            num = 1
            while num in used:
                num += 1
        n = str(num)
        used.add(num)
        by_url[url] = n
        refs.append((n, label.strip(), url))
        return n

    for n, ln in enumerate(lines):
        if fence[n]:
            continue
        s = ln.strip()
        if IMG_LINE.match(s):  # 插图 URL 不是 reference
            continue
        m = REF_LINE.match(s)
        if m:
            add(int(m.group(1)), m.group(2), m.group(3))
            continue
        for lm in MD_LINK.finditer(s):
            add(None, lm.group(1), lm.group(2))
        masked = MD_LINK.sub(lambda m: " " * len(m.group(0)), s)
        for bm in BARE_URL.finditer(masked):
            u = bm.group(0).rstrip(".,;:，。；)")
            add(None, u, u)
    return refs, by_url


def convert(md, theme_key=DEFAULT_THEME, scheme="light"):
    t = resolve_theme(theme_key, scheme)
    lines = md.split("\n")
    fence = _fence_flags(lines)
    title, title_idx = _parse_title(lines, fence)
    refs, by_url = collect_refs(lines, fence)
    t["_ref_urls"] = by_url
    h1_idx, h2_idx = _heading_levels(lines, fence, title_idx)
    # 有正文一级标题就用 # 分大章；只有一个标题 #（或无 #）就用 ## 分大章。
    # Obsidian 的 title 来自 frontmatter 标记，正文的 # 1/# 2 全部是大章。
    chapter_level = 1 if h1_idx else (2 if h2_idx else None)
    # 浅色方案根背景保持 #FFFFFF（历史成品与「正文零背景色」约定）；
    # 深色方案用主题深色 bg。
    root_bg = t["bg"] if scheme == "dark" else "#FFFFFF"
    body = ['<section style="max-width:677px;margin:0 auto;background:%s;'
            'font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\',sans-serif;'
            'color:%s;line-height:1.8;overflow-x:hidden;">' % (root_bg, t["body"])]
    i, chapter_no = 0, 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1; continue
        # 注意：不能在这里用 fence[i] 提前 continue——那会把 ``` 开围栏也跳过，
        # 导致整段代码块丢失。代码块由下面的 ``` 分支一次性消费（2026-11-26 回归）。
        if TITLE_MARK.match(s):  # frontmatter 标题行：取过就不再进正文
            i += 1; continue
        # 来源章节 heading 与来源条目在任意位置出现都跳过，统一在文末重排
        if APPENDIX_HEAD.match(s) or REF_LINE.match(s) or REF_ITEM.match(s):
            i += 1; continue
        if s.startswith("# ") or s.startswith("## "):
            level = 1 if s.startswith("# ") else 2
            title_text = s[2:].strip() if level == 1 else s[3:].strip()
            if level == chapter_level:
                chapter_no += 1
                body.append(number_chapter("%02d" % chapter_no, "CHAPTER",
                                           title_text, t, first=(chapter_no == 1)))
            else:
                body.append(h3(title_text, t))
            i += 1; continue
        if s.startswith("```"):
            lang = s[3:].strip() or "text"
            i += 1; buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            body.append(code_block("\n".join(buf), lang, t=t))
            continue
        if s.startswith("### "):
            body.append(h3(s[4:].strip(), t)); i += 1; continue
        if s.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip()); i += 1
            body.append(quote_block(" ".join(buf), t)); continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            sc = rows[0].index("状态") if rows and "状态" in rows[0] else None
            body.append(data_table(rows, t, status_col=sc)); continue
        m_img = IMG_LINE.match(s)
        if m_img:
            body.append(image_block(m_img.group(2), m_img.group(1), t)); i += 1; continue
        if re.match(r"^[-*]\s+", s):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip())); i += 1
            body.append(bullet_list(items, t)); continue
        if re.match(r"^\d+\.\s+", s):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip())); i += 1
            body.append(bullet_list(items, t, ordered=True)); continue
        if re.match(r"^(---+|\*\*\*+)$", s):
            i += 1; continue
        body.append(para(s, t)); i += 1
    if refs:
        body.append(appendix(refs, t))
    body.append("</section>")
    return title, "\n".join(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md", help="Markdown 文件路径")
    ap.add_argument("--theme", default=DEFAULT_THEME, choices=list(THEMES))
    ap.add_argument("--scheme", default="light", choices=["light", "dark"],
                    help="配色方案：light=浅色（默认），dark=深色（焊死深底浅字）")
    ap.add_argument("-o", "--output", help="输出 HTML（干净正文片段）")
    ap.add_argument("--all-themes", action="store_true", help="生成全部主题×配色到 --preview-dir")
    ap.add_argument("--preview-dir", help="主题预览目录（配 --all-themes）")
    args = ap.parse_args()

    md = open(args.md, encoding="utf-8").read()
    if args.all_themes:
        if not args.preview_dir:
            ap.error("--all-themes 需要 --preview-dir")
        os.makedirs(args.preview_dir, exist_ok=True)
        title, _ = convert(md, args.theme)
        cards = []
        for key, t in THEMES.items():
            files = []
            for scheme, label in (("light", "浅色"), ("dark", "深色")):
                _, html = convert(md, key, scheme)
                fn = "%s.html" % key if scheme == "light" else "%s_深色.html" % key
                open(os.path.join(args.preview_dir, fn), "w", encoding="utf-8").write(html)
                files.append((fn, label, scheme))
            row = []
            for fn, label, scheme in files:
                tt = resolve_theme(key, scheme)
                row.append(
                    '<a href="%s" style="display:inline-block;padding:10px 16px;margin:0 8px 8px 0;'
                    'border:1px solid %s;border-left:4px solid %s;text-decoration:none;">'
                    '<strong style="color:%s;font-size:14px;">%s %s</strong></a>'
                    % (fn, tt["line"], tt["primary"], tt["primary"], label, esc(tt["name"])))
            cards.append(
                '<p style="font-size:15px;color:%s;margin:18px 0 8px;"><strong>%s</strong>'
                '<span style="color:#6B7280;font-size:13px;"> — %s</span></p>%s'
                % (t["ink"], esc(t["name"]), esc(t["scene"]), "".join(row)))
        index = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
                 '<title>主题预览 — %s</title></head><body style="font-family:-apple-system,sans-serif;'
                 'max-width:760px;margin:32px auto;padding:0 16px;">'
                 '<h1 style="font-size:22px;">选择排版主题</h1>'
                 '<p style="color:#6B7280;">文章：%s（每套主题均有 浅色 / 深色 两种配色）</p>%s</body></html>'
                 % (esc(title), esc(title), "".join(cards)))
        idx_path = os.path.join(args.preview_dir, "index.html")
        open(idx_path, "w", encoding="utf-8").write(index)
        print("主题预览索引: %s" % idx_path)
        print("共 %d 套主题 × 浅色/深色 = %d 个预览，逐页查看后把主题与配色填回" % (len(THEMES), len(THEMES) * 2))
        return

    title, html = convert(md, args.theme, args.scheme)
    if not args.output:
        ap.error("单主题模式需要 -o/--output")
    open(args.output, "w", encoding="utf-8").write(html)
    t = resolve_theme(args.theme, args.scheme)
    print("标题: %s" % title)
    print("主题: %s (%s / %s)" % (t["name"], args.theme, args.scheme))
    print("输出: %s" % args.output)


if __name__ == "__main__":
    main()
