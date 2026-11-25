#!/usr/bin/env python3
"""把已校验的公众号正文片段（纯 <section>）包成带「复制」按钮的浏览器预览页。

用户打开预览页 → 点右上角「复制」按钮 → 按钮选中并复制里面渲染后的富文本
（等价手动 Ctrl+A/Ctrl+C，样式全保留）→ 到公众号编辑器 Ctrl+V 粘贴即可。

按钮和 JS 只存在于预览外壳里，**不在被复制的 section 内**，所以粘进公众号的
仍是干净合规的正文，不含 <script>/<button>。校验请对原始 section 文件跑
validate_gzh_html.py（本预览页含 script/style，不参与校验）。

用法:
    wrap_preview.py <section.html> [output.html]
    wrap_preview.py <section.html> --dark [output.html]   # 生成即强制深色
    默认输出 <section去扩展名>_预览.html

深浅自适应机制（与微信读者端一致）：
    公众号的深浅自适配由微信客户端在读者端完成——官方开源算法
    wechatjs/mp-darkmode 逐元素转换颜色（白底→深底、深字→浅字、色相保留）。
    本脚本把同一算法的静态移植（wechat_dark.py）编译成 CSS 覆盖规则，
    放进 `@media (prefers-color-scheme: dark)` + 属性选择器 + !important：
    预览页在深色环境自动呈现读者深色模式的观感，与用浏览器打开公众号
    链接的行为一致；也可用工具栏🌗按钮手动切换（自动/深/浅）。
    DOM 内联样式原样保留，复制的富文本仍是浅色样式（由微信读者端转换）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wechat_dark import dark_rules  # noqa: E402

HINT_DEFAULT = "👇 下方是排版效果 · 点右侧 <b>复制</b> 直接粘到公众号"
HINT_ADAPTIVE = "👇 下方是排版效果 · 深浅色<b>自适应</b>（跟随系统，可点 🌗 切换）· 点右侧 <b>复制</b> 粘到公众号"

SHELL_DARK_CSS = """  /* ---- 预览外壳深色（自适应） ---- */
  html.gzh-dark body{background:#101014;}
  html.gzh-dark .gzh-toolbar{background:#1b1e24;box-shadow:0 1px 10px rgba(0,0,0,.55);}
  html.gzh-dark .gzh-hint{color:#9ca3af;}
  html.gzh-dark .gzh-hint b{color:#e5e7eb;}
  html.gzh-dark .gzh-mode{background:#374151;color:#e5e7eb;}
  @media (prefers-color-scheme: dark){
    html:not(.gzh-light) body{background:#101014;}
    html:not(.gzh-light) .gzh-toolbar{background:#1b1e24;box-shadow:0 1px 10px rgba(0,0,0,.55);}
    html:not(.gzh-light) .gzh-hint{color:#9ca3af;}
    html:not(.gzh-light) .gzh-hint b{color:#e5e7eb;}
    html:not(.gzh-light) .gzh-mode{background:#374151;color:#e5e7eb;}
  }
"""


def build_dark_css(html):
    """把读者端深色转换结果编译成两套等价规则：强制深色（html.gzh-dark）
    与自动深色（@media prefers-color-scheme: dark 且未被强制浅色）。"""
    rules = dark_rules(html)
    if not rules:
        return ""

    def block(prefix):
        lines = ['  %s#gzh-content img{filter:brightness(.7);}' % prefix]
        for attr, body in rules:
            # 每条声明都要带 !important：不带时打不过内联样式（这是上次
            # 「根背景压不掉、始终浅色」的根因）
            body_imp = body.replace(";", " !important;") + " !important;"
            lines.append('  %s#gzh-content [style="%s"]{%s}'
                         % (prefix, attr, body_imp))
        return "\n".join(lines)

    return ("  /* ---- 微信读者端深色转换模拟（wechatjs/mp-darkmode 静态移植） ---- */\n"
            + block("html.gzh-dark ")
            + "\n  @media (prefers-color-scheme: dark){\n"
            + block("html:not(.gzh-light) ")
            + "\n  }\n")


def main():
    dark = "--dark" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if a != "--dark"]
    if len(args) < 1:
        print("用法: wrap_preview.py <section.html> [--dark] [output.html]")
        sys.exit(1)
    src = args[0]
    if not os.path.isfile(src):
        print(f"✗ 找不到文件: {src}")
        sys.exit(1)

    content = open(src, encoding="utf-8").read().strip()
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "assets", "preview-template.html")
    tpl = open(tpl_path, encoding="utf-8").read()

    css = build_dark_css(content)
    tpl = tpl.replace("</style>", css + SHELL_DARK_CSS + "</style>")
    tpl = tpl.replace(HINT_DEFAULT, HINT_ADAPTIVE)
    if dark:
        # 生成即处于强制深色档（仍可点 🌗 切回自动/浅色）
        tpl = tpl.replace('<html lang="zh-CN">', '<html lang="zh-CN" class="gzh-dark">')

    title = os.path.splitext(os.path.basename(src))[0]
    out_html = tpl.replace("{{TITLE}}", title).replace("<!--GZH_CONTENT-->", content)

    suffix = "_预览_深色.html" if dark else "_预览.html"
    out = args[1] if len(args) > 1 else os.path.splitext(src)[0] + suffix
    open(out, "w", encoding="utf-8").write(out_html)
    print(f"✓ 已生成自适应预览页{'（初始深色）' if dark else ''}: {out}")
    print("  浏览器/面板深色模式自动呈现微信深色渲染；🌗 按钮可手动切换；复制出去的仍是浅色内联样式。")


if __name__ == "__main__":
    main()
