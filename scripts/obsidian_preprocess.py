#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Obsidian Markdown → 公众号排版器可直接消费的纯净 Markdown。

背景：md_to_gzh.py 只认标准 Markdown + 自定义 [[N]] 角标；Obsidian 稿里
常见的 frontmatter / callout / wiki 链接 / 块嵌入它会当成正文原样吐出，
2026-11-26 实战踩坑后把预处理正式化为本脚本。

处理的 5 类语法：
  1. YAML frontmatter  → title 单独写成 <!-- gzh-title: ... --> 标记行
                          （转换器据此取文章标题，正文里不再插 # 标题）；
                          其余 frontmatter 块整段删除（否则半角引号等触发告警）。
  2. > [!tip] 标题      → 原样保留 callout 头（含 +/- 折叠标记、类型、标题），
                          由 md_to_gzh.py 按 Obsidian 官方类型渲染带色卡片；
                          旧版在此降级成 > **标题** 会把类型/图标全丢（2026-11-27 修）。
  3. [[文件]] / [[文件#块]] → **双场景处理**（2026-11-27 用户二次定稿）：
                          · 该文件已通过 ![[...]] 在本文展开 → 保留为《文件》
                            纯文本（读者在文中读得到，不算伪装资料）；
                          · 未引入 → 擦除引用并修复上下文：名词性短语 + 引导词
                            （见/参见/可参考/详见）改成「不在此展开」，完整
                            分句则连引导词一起删，避免「排查方法；」「冲突
                            具体案例。」这类残句。代码块/行内代码里的不动。
  4. ![[文件#块]]       → 展开被引用文件中对应 ## 块的全文（含代码块）。
                          按 --vault 目录（默认与源文件同目录）查找同名 .md。
                          这是内容嵌入，读者能直接读到展开后的正文，不擦除；
                          成功展开的文件名记入集合，供第 3 类判定「已引入」。
  5. 正文行内 [文字](https://url) 原样保留——转换器会在任意章节把超链接
                      换成「文字 + [[N]] 角标」，并在文末统一生成附录；
                      整行图片 ![alt](url) 同样原样保留（要识别为插图）。

用法:
    python3 obsidian_preprocess.py article.md -o article_纯净.md
    python3 obsidian_preprocess.py article.md -o out.md --vault /path/to/Obsidian/目录
"""
import argparse
import os
import re
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 内部引用本体：[[文件]] / [[文件#块]] / [[文件|别名]]。
# 注意 [[:space:]] 这类 POSIX 字符类也长得一样，靠 _map_outside_code 保护代码块。
WIKI_REF = re.compile(r"\[\[([^\]\|#]+)(?:#[^\]\|]*)?(?:\|[^\]]*)?\]\]")
# 紧邻引用、只为指向它存在的引导词；一起删掉才不会留下「见 。」
REF_LEAD = re.compile(r"(?:参见|可参考|详见|请见|参考|见)\s*$")
# 引导词前若是「光秃秃的名词短语」，删掉引用后句子会残缺（「排查方法。」），
# 这类改成「不在此展开」；若是完整分句（「按…核算，见 X」）则连引导词一起删。
# 名词短语判据：分句以「的」结尾，或只由名词性短语构成（不含句末动词/标点）。
NOUN_TAIL = re.compile(r"(?:的|方法|案例|细节|说明|背景|资料|记录|清单|提示词|复盘)$")
REF_CLAUSE_SPLIT = re.compile(r"[。！？；，、：]")
INLINE_CODE = re.compile(r"(`[^`\n]*`)")


def extract_title_and_strip_fm(s):
    """抽 frontmatter title → 独立标记行；删除 YAML 块。无 frontmatter 时原样返回。"""
    fm = re.match(r"\A---\n(.*?)\n---\n", s, re.S)
    if not fm:
        return s, None
    m = re.search(r"^title:\s*['\"]?(.+?)['\"]?\s*$", fm.group(1), re.M)
    if not m:
        return s[fm.end():], None
    title = m.group(1).strip()
    return "<!-- gzh-title: %s -->\n\n%s" % (title, s[fm.end():]), title


def expand_block_embed(s, vault, expanded=None):
    """展开 ![[文件#块]]：找 vault/文件.md 中「## 块」到下一个 ## 之间全文。

    expanded 若传入集合，成功展开的文件名会记入其中——供后续判定
    [[文件]] 是「已引入」（文中读得到）还是「仅链接」（读者看不到）。
    """
    def repl(m):
        target, block = m.group(1), m.group(2)
        path = os.path.join(vault, target + ".md")
        if not os.path.isfile(path):
            return m.group(0)  # 找不到就保留原样，交人工确认
        with open(path, encoding="utf-8") as f:
            src = f.read()
        if block:
            bm = re.search(r"^##\s+%s\s*$\n(.*?)(?=^## |\Z)" % re.escape(block),
                           src, re.S | re.M)
            if not bm:
                return m.group(0)
            text = bm.group(1).strip()
        else:
            text = src.strip()
        if expanded is not None:
            expanded.add(target.strip())
        return text
    return re.sub(r"!\[\[([^\]\|#]+)(?:#([^\]]+))?\]\]", repl, s)


def _is_fence(line):
    """``` / ~~~ 围栏，支持 > 引用前缀。"""
    t = line.lstrip()
    while t.startswith(">"):
        t = t[1:].lstrip()
    return t.startswith("```") or t.startswith("~~~")


_CODE_TOKEN = "\x00GZHKEEP%d\x00"   # 行内代码占位符，处理完还原
# 找不到文件的块嵌入保留原样交人工确认，不能被内部引用擦除当成 [[...]] 删掉
BROKEN_EMBED = re.compile(r"(!\[\[[^\]]+\]\])")


def _map_outside_code(s, fn):
    """只在正文（非围栏代码块、非行内代码）上应用 fn，代码原样保留。

    行内代码按整行提取 → 占位 → 对整行 fn（不能用 re.split 逐段处理，
    否则每段末尾被当成句尾，`、` 等标点会被误删）。
    """
    out = []
    fence = False
    for line in s.splitlines(keepends=True):
        if _is_fence(line):
            fence = not fence
            out.append(line)
            continue
        if fence:
            out.append(line)
            continue
        kept = []
        def _stash(m):
            kept.append(m.group(0))
            return _CODE_TOKEN % (len(kept) - 1)
        masked = BROKEN_EMBED.sub(_stash, line)
        masked = INLINE_CODE.sub(_stash, masked)
        masked = fn(masked)
        for i, code in enumerate(kept):
            masked = masked.replace(_CODE_TOKEN % i, code)
        out.append(masked)
    return "".join(out)


def _tidy_punctuation(s):
    """擦除引用后收拾悬空标点，让句子读起来连贯。"""
    s = re.sub(r"[，、；：]\s*([。！？；])", r"\1", s)          # 「，。」→「。」
    s = re.sub(r"(?:^|(?<=[。！？\n]))[，、；：]+\s*", "", s)   # 句首孤立逗号
    s = re.sub(r"(?:^|(?<=[。！？\n]))[。]+\s*", "", s)         # 整句被删干净留下的孤句号
    s = re.sub(r"(?m)^(\s*(?:[-*+]|\d+\.|>)+\s*)[。；，]+", r"\1", s)  # 列表项里的孤标点
    s = re.sub(r"[，、；：]+(?=\s*\|)", "", s, flags=re.M)     # 表格单元格行尾逗号（留空格）
    s = re.sub(r"(?:见|文档|案例)\s+《", lambda m: m.group(0).replace(" ", ""), s)  # 「见 《X》」→「见《X》」
    s = re.sub(r"[。]{2,}", "。", s)
    return s


def erase_internal_refs(s, embedded=None):
    """处理 Obsidian 内部引用，返回 (文本, 擦除数, 保留数)。

    · 文件已通过 ![[...]] 引入 → 换成《文件名》纯文本保留（读者文中读得到），
      连「见 / 可参考」引导词一起保留，句子结构不动。
    · 仅链接未引入 → 擦除。名词性短语作主语时（「冲突具体案例，可参考 X」）
      在原位写「不在此展开」，避免变成「冲突具体案例。」的残句；完整分句
      （「按…核算，见 X」）则连引导词一起删，前半句本就通顺。
    """
    embedded = embedded or set()
    spans = []          # (start, end, replacement)
    kept = 0
    for m in WIKI_REF.finditer(s):
        a, b = m.span()
        name = m.group(1).strip()
        if name in embedded:
            # 已引入：保留为书名号纯文本，句子结构完全不动
            spans.append((a, b, "《%s》" % name))
            kept += 1
            continue
        lead = REF_LEAD.search(s[:a])
        start = lead.start() if lead else a
        replacement = ""
        if lead:
            # 引导词前最后一个分句——判断是不是「光秃秃的名词短语」
            clause = s[:lead.start()]
            parts = [p.strip() for p in REF_CLAUSE_SPLIT.split(clause) if p.strip()]
            tail = parts[-1] if parts else ""   # 分句末尾可能是逗号，取最后一个非空段
            if NOUN_TAIL.search(tail):
                # 名词短语 + 引导词 + 引用 → 连引导词一起换成「不在此展开」
                # start 保持 lead.start()，否则会留下「见 不在此展开」的病句
                # 若名词短语与引导词之间还有逗号（「冲突具体案例，可参考 X」），
                # 一并吸收，避免出现「案例，不在此展开」的生硬断句。
                if s[start - 1:start] == "，":
                    start -= 1
                replacement = "不在此展开"
        spans.append((start, b, replacement))
    for start, end, replacement in reversed(spans):
        s = s[:start] + replacement + s[end:]
    return _tidy_punctuation(s), len(spans) - kept, kept


def preprocess(s, vault):
    s, title = extract_title_and_strip_fm(s)
    embedded = set()
    s = expand_block_embed(s, vault, embedded)
    counts = dict(callout=0, wiki=0, wiki_kept=0)

    def transform(seg):
        # callout 头原样保留，让 md_to_gzh.py 按 Obsidian 官方类型渲染
        # （类型色竖条 + 淡背景 + 图标 + 标题 + 折叠标记）。旧版在这里改成
        # `> **标题**`，类型/折叠信息全丢，所有 callout 都是一个样（2026-11-27 修）。
        n_callout = len(re.findall(r"^> \[![A-Za-z0-9_-]+\][+-]?", seg, flags=re.M))
        seg, n_wiki, n_kept = erase_internal_refs(seg, embedded)
        counts["callout"] += n_callout
        counts["wiki"] += n_wiki
        counts["wiki_kept"] += n_kept
        return seg

    s = _map_outside_code(s, transform)
    # 超链接全部原样留给转换器：它会在任意章节收进 reference，
    # 正文只显示文字 + 蓝色角标；图片行同样不能被改写。
    n_link = len(re.findall(r"(?<!!)\[[^\]]+\]\(https?://[^)]+\)", s))
    return s, dict(title=title, callout=counts["callout"],
                   wiki=counts["wiki"], wiki_kept=counts["wiki_kept"],
                   link=n_link)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md", help="Obsidian Markdown 源文件")
    ap.add_argument("-o", "--output", required=True, help="输出的纯净 Markdown")
    ap.add_argument("--vault", help="块嵌入查找目录（默认与源文件同目录）")
    args = ap.parse_args()

    if not os.path.isfile(args.md):
        sys.exit("✗ 找不到源文件: %s" % args.md)
    vault = args.vault or os.path.dirname(os.path.abspath(args.md))
    s = open(args.md, encoding="utf-8").read()
    result, stats = preprocess(s, vault)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    open(args.output, "w", encoding="utf-8").write(result)
    print("✓ 预处理完成: %s" % args.output)
    print("  H1 标题=%s · callout=%d · 内部引用擦除=%d · 已引入保留=%d · 正文链接=%d"
          % (stats["title"] or "（原样）", stats["callout"],
             stats["wiki"], stats["wiki_kept"], stats["link"]))


if __name__ == "__main__":
    main()
