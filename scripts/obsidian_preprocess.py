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
  2. > [!tip] 标题      → > **标题**（callout 标题行）；引用正文行不动。
  3. [[文件]] / [[文件#块]] → 《文件》纯文本（公众号正文零超链接）。
  4. ![[文件#块]]       → 展开被引用文件中对应 ## 块的全文（含代码块）。
                          按 --vault 目录（默认与源文件同目录）查找同名 .md。
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


def expand_block_embed(s, vault):
    """展开 ![[文件#块]]：找 vault/文件.md 中「## 块」到下一个 ## 之间全文。"""
    def repl(m):
        target, block = m.group(1), m.group(2)
        path = os.path.join(vault, target + ".md")
        if not os.path.isfile(path):
            return m.group(0)  # 找不到就保留原样，交人工确认
        src = open(path, encoding="utf-8").read()
        if block:
            bm = re.search(r"^##\s+%s\s*$\n(.*?)(?=^## |\Z)" % re.escape(block),
                           src, re.S | re.M)
            if not bm:
                return m.group(0)
            return bm.group(1).strip()
        return src.strip()
    return re.sub(r"!\[\[([^\]\|#]+)(?:#([^\]]+))?\]\]", repl, s)


def preprocess(s, vault):
    s, title = extract_title_and_strip_fm(s)
    s = expand_block_embed(s, vault)
    # callout 标题行 → 引用内加粗（只动标记行，不动后续引用正文）
    s, n_callout = re.subn(r"^> \[!\w+\] (.+)$", r"> **\1**", s, flags=re.M)
    # wiki 链接 → 书名号纯文本（去块锚点）
    s, n_wiki = re.subn(r"\[\[([^\]\|#]+)(?:#[^\]]*)?\]\]", r"《\1》", s)
    # 超链接全部原样留给转换器：它会在任意章节收进 reference，
    # 正文只显示文字 + 蓝色角标；图片行同样不能被改写。
    n_link = len(re.findall(r"(?<!!)\[[^\]]+\]\(https?://[^)]+\)", s))
    return s, dict(title=title, callout=n_callout,
                   wiki=n_wiki, link=n_link)


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
    print("  H1 标题=%s · callout=%d · wiki链接=%d · 正文链接=%d"
          % (stats["title"] or "（原样）", stats["callout"],
             stats["wiki"], stats["link"]))


if __name__ == "__main__":
    main()
