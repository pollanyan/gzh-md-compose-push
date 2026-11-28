#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gzh-md-compose-push 回归测试：覆盖 README 宣称能力与 doc/方案设计规格 硬要求。

用法：
    python3 -m unittest discover -s tests -v
    # 可选：连真实公众号草稿回读（需登录态 + GZH_APPMSGID）
    GZH_LIVE=1 GZH_APPMSGID=100000356 python3 -m unittest discover -s tests -v

设计原则：默认全离线、只写临时目录，不改技能目录、不碰公众号、不提交代码。
新增/修改规则时先改断言，再改实现；全部测试通过才算规则变更完成。
"""
import hashlib
import importlib.util
import os
import py_compile
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import md_to_gzh as mdg                    # noqa: E402
import obsidian_preprocess as obsp         # noqa: E402
import validate_gzh_html as validator      # noqa: E402
from wrap_preview import build_dark_css    # noqa: E402

PY = sys.executable
SKILL_INSTALL = os.path.expanduser("~/.workbuddy/skills/gzh-md-compose-push")
EXCLUDE_DIRS = {".git", ".workbuddy", "__pycache__", "mp_profile"}
EXCLUDE_FILES = re.compile(r"(mp-shot-.*|mp-login-qrcode.*|.*\.log|.*\.swp)$")


def run(*args, **kw):
    """运行脚本子进程，统一 UTF-8 输出。"""
    return subprocess.run([PY] + list(args), cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", **kw)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, content):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


FIXTURE = """<!-- gzh-title: 测试文章 -->
# 1 第一章 [扩展](https://example.com/ext)
## 1.1 小节
正文里有 [Pi](https://example.com/pi) 和裸链 https://example.com/raw 。见 [[1]]。
> 提示
> 这是引用 **加粗** 与 `代码`。
| 工具 | 状态 |
| --- | --- |
| 一个很长的工具名字用于测试列宽自适应 | 🟢 强 |
![示意图](https://img.example.com/a.png)

```
# 1) 这不是标题
const x = "abc";
```
# 2 [第二章](https://example.com/ch2)
### 三级标题
[9] 手动条目: https://example.com/manual
## 附：取证来源
- [已有](https://example.com/dup)
"""


class ConverterTests(unittest.TestCase):
    """README：标题/章节/引用/表格/代码块/行内代码；规格第 4、7、8 条。"""

    @classmethod
    def setUpClass(cls):
        cls.title, cls.html = mdg.convert(FIXTURE)

    def test_title_marker_and_h1_chapters(self):
        self.assertEqual(self.title, "测试文章")
        self.assertEqual(self.html.count(">CHAPTER<"), 2)
        self.assertIn(">APPENDIX<", self.html)
        # 代码块里的 # 1) 注释留在代码行里，不会多出一个大章节
        self.assertEqual(self.html.count("这不是标题"), 1)

    def test_h2_chapters_when_no_body_h1(self):
        md = ("<!-- gzh-title: 标题 -->\n"
              "## 第一章\n正文。\n## 第二章\n更多正文。\n")
        title, html = mdg.convert(md)
        self.assertEqual(title, "标题")
        self.assertEqual(html.count(">CHAPTER<"), 2)

    def test_single_h1_fallback(self):
        title, html = mdg.convert("# 老稿标题\n## 第一章\n正文。\n")
        self.assertEqual(title, "老稿标题")
        self.assertEqual(html.count(">CHAPTER<"), 1)

    def test_h3_has_no_left_bar(self):
        h3s = re.findall(r'<p style="font-size:16px;font-weight:700[^>]*>', self.html)
        self.assertTrue(h3s)
        self.assertFalse(any("border-left" in tag for tag in h3s))

    def test_code_block_survives_and_highlights(self):
        sections = re.findall(
            r'<section style="[^"]*overflow-x:auto[^"]*">', self.html)
        self.assertTrue(sections)  # 代码块与表格都带横滑外层
        code = self.html[self.html.find("Courier New"):]
        self.assertIn("white-space:nowrap", code)
        self.assertGreaterEqual(len(re.findall(r'<span style="color:[^;]+;">', code)), 3)
        lines = re.findall(
            r'<p style="[^"]*Courier New[^"]*white-space:nowrap[^"]*">'
            r'<span leaf="">(.*?)</span></p>', self.html, re.S)
        self.assertEqual(len(lines), 2)  # 每行一个 leaf
        self.assertIn("这不是标题", lines[0])

    def test_table_layout_and_width_attributes(self):
        rows = [["工具", "状态"],
                ["一个很长的工具名字用于测试列宽自适应", "🟢 强"]]
        table = mdg.data_table(rows, mdg.resolve_theme("graphite-minimal"))
        self.assertIn("width:100%;min-width:620px", table)
        self.assertNotIn("width:100%%", table)
        self.assertNotIn("data-colwidth", table)
        self.assertRegex(table, r'<th width="\d+%"')
        self.assertIn("white-space:nowrap", table)
        widths = [int(x) for x in re.findall(r'<col style="width:(\d+)%;">', table)]
        self.assertEqual(len(widths), 2)
        self.assertEqual(sum(widths), 100)

    def test_references_from_any_chapter(self):
        self.assertNotIn("<a ", self.html)
        for url in ("https://example.com/ext", "https://example.com/pi",
                    "https://example.com/raw", "https://example.com/ch2",
                    "https://example.com/manual", "https://example.com/dup"):
            self.assertIn(url, self.html)
        self.assertGreaterEqual(self.html.count("vertical-align:super"), 6)
        self.assertIn(">APPENDIX<", self.html)
        self.assertIn(">References<", self.html)

    def test_image_line_is_image_not_reference(self):
        self.assertIn('<img src="https://img.example.com/a.png"', self.html)
        self.assertIn("示意图", self.html)
        self.assertNotIn("https://img.example.com/a.png",
                         self.html.split(">APPENDIX<")[-1])

    def test_quote_block_style_and_inline_marks(self):
        self.assertIn("background:#F5F5F5", self.html)
        self.assertIn("border-left:2px solid #D4D4D8", self.html)
        self.assertIn("#2563EB", self.html)  # 行内代码/角标蓝
        dark = mdg.convert("> 深色引用\n", scheme="dark")[1]
        self.assertIn("background:#383838", dark)

    def test_validate_fixture_clean(self):
        errors, warnings, leaves = validator.validate(self.html, "fixture")
        self.assertEqual(errors, [], errors)
        self.assertEqual(warnings, [], warnings)
        self.assertGreater(leaves, 20)

    def test_all_themes_and_dark_scheme_cli(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "article.md")
            preset = os.path.join(td, "themes")
            write(src, FIXTURE)
            r = run(os.path.join(SCRIPTS, "md_to_gzh.py"), src,
                    "--all-themes", "--preview-dir", preset)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            files = os.listdir(preset)
            self.assertEqual(len([f for f in files if f.endswith(".html")]),
                             len(mdg.THEMES) * 2 + 1)  # 12 + index
            for name in files:
                if name == "index.html":
                    self.assertIn("选择排版主题", read(os.path.join(preset, name)))
                    continue  # 主题选择页不是公众号正文片段，不走 leaf 校验
                errors, warnings, _ = validator.validate(
                    read(os.path.join(preset, name)), name)
                self.assertEqual(errors, [], (name, errors))
                self.assertEqual(warnings, [], (name, warnings))
            out = os.path.join(td, "dark.html")
            r = run(os.path.join(SCRIPTS, "md_to_gzh.py"), src,
                    "--theme", "graphite-minimal", "--scheme", "dark", "-o", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            t = mdg.resolve_theme("graphite-minimal", "dark")
            self.assertIn("background:%s" % t["bg"], read(out))


class PreprocessTests(unittest.TestCase):
    """README：Obsidian frontmatter/callout/wiki/块嵌入/超链接保留。"""

    def test_cli_preprocess(self):
        with tempfile.TemporaryDirectory() as td:
            vault = os.path.join(td, "vault")
            src = os.path.join(vault, "主笔记.md")
            write(os.path.join(vault, "被引用.md"),
                  "# 被引用\n\n## 可复制提示词\n嵌入段落 **加粗**。\n")
            write(src, "---\ntitle: ' Obsidian 标题 '\ntags: [x]\n---\n"
                       "# 1 第一章\n"
                       "> [!tip] 小提示\n> 引用正文。\n"
                       "参见 [[另一篇#小节]] 与 ![[被引用#可复制提示词]]。\n"
                       "链接 [Pi](https://example.com/pi) 保留。\n"
                       "![图](https://img.example.com/b.png)\n")
            out = os.path.join(td, "clean.md")
            r = run(os.path.join(SCRIPTS, "obsidian_preprocess.py"), src,
                    "-o", out, "--vault", vault)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            md = read(out)
            self.assertIn("<!-- gzh-title: Obsidian 标题 -->", md)
            self.assertNotIn("tags:", md)
            self.assertIn("> [!tip] 小提示", md)  # callout 头保留，交由转换器按类型渲染
            self.assertNotIn("另一篇", md)          # 内部笔记引用擦除，不写《》
            self.assertNotIn("《", md)
            self.assertIn("嵌入段落 **加粗**。", md)  # 块嵌入展开保留
            self.assertIn("[Pi](https://example.com/pi)", md)
            self.assertIn("![图](https://img.example.com/b.png)", md)
            title, html = mdg.convert(md)
            self.assertEqual(title, "Obsidian 标题")
            self.assertEqual(html.count(">CHAPTER<"), 1)
            self.assertIn("https://example.com/pi", html)

    def test_invalid_embed_does_not_invent_content(self):
        s, stats = obsp.preprocess("![[不存在#块]]\n", "/tmp")
        self.assertIn("不存在", s)  # 保留可识别的名字供人工处理
        self.assertNotIn("嵌入段落", s)  # 绝不编造被引用内容
        self.assertIsNone(stats["title"])

    def test_internal_refs_erased_with_coherent_context(self):
        """仅链接未引入：名词短语补「不在此展开」、完整分句删引导词、代码不动。"""
        s, stats = obsp.preprocess(
            "背景案例见 [[Pi 上下文压缩死循环事故复盘]]。\n"
            "核算，见 [[引用二]] | 表格单元格\n"
            "用 [[引用三#小节]] 和 `code [[:space:]] here` 以及 [[引用四|别名]]。\n"
            "```bash\nsed -E '/^[[:space:]]*x/d' \"$1\"\n```\n", "/tmp")
        self.assertEqual(stats["wiki"], 4)          # 擦除 4 处
        self.assertEqual(stats["wiki_kept"], 0)     # 无嵌入，全部擦除
        self.assertNotIn("[[", s.replace("[[:space:]]", ""))  # 正文引用全清，代码里的保留
        self.assertNotIn("《", s)                   # 未引入的不写成书名号
        self.assertNotIn("Pi 上下文压缩死循环事故复盘", s)
        self.assertNotIn("别名", s)
        self.assertFalse(re.search(r"见\s*。", s))
        self.assertIn("背景案例不在此展开。", s)    # 名词短语 → 原位补说明，不是残句
        self.assertIn("核算 | 表格单元格", s)        # 完整分句 → 连引导词一起删
        self.assertIn("`code [[:space:]] here`", s)
        self.assertIn("sed -E '/^[[:space:]]*x/d'", s)

    def test_embedded_ref_kept_as_title(self):
        """已通过 ![[文件#块]] 展开的笔记：[[文件]] 保留为《文件》，引导词留着。"""
        with tempfile.TemporaryDirectory() as td:
            write(os.path.join(td, "提示词.md"),
                  "# 提示词\n\n## 可复制提示词\n正文 **加粗**。\n")
            s, stats = obsp.preprocess(
                "排查方法见 [[提示词]]；下面嵌入 ![[提示词#可复制提示词]]。\n", td)
            self.assertEqual(stats["wiki"], 0)
            self.assertEqual(stats["wiki_kept"], 1)
            self.assertIn("排查方法见《提示词》；", s)   # 已引入 → 保留，句子完整
            self.assertIn("正文 **加粗**。", s)          # 块嵌入仍展开
            self.assertNotIn("[[", s)

    def test_mixed_refs_in_one_sentence(self):
        """同一句内：已引入的保留、未引入的改写，互不干扰（用户实测案例）。"""
        with tempfile.TemporaryDirectory() as td:
            write(os.path.join(td, "提示词.md"),
                  "# 提示词\n\n## 可复制提示词\n正文。\n")
            s, stats = obsp.preprocess(
                "排查方法见 [[提示词]]；冲突具体案例，可参考 [[事故复盘]]。\n"
                "![[提示词#可复制提示词]]\n", td)
            self.assertEqual(stats["wiki_kept"], 1)
            self.assertEqual(stats["wiki"], 1)
            self.assertIn("排查方法见《提示词》；冲突具体案例不在此展开。", s)
            self.assertNotIn("事故复盘", s)

    def test_inline_code_separators_preserved(self):
        s, _ = obsp.preprocess("| `a`、`b`、`c` | 见 [[内部笔记]] |\n", "/tmp")
        self.assertIn("`a`、`b`、`c`", s)
        self.assertNotIn("内部笔记", s)


class CalloutTests(unittest.TestCase):
    """Obsidian callout：官方 13 类型 + 别名 + 折叠 + 无标题 + 回退 note。"""

    def test_all_default_types_have_color_icon_title(self):
        spec = mdg.CALLOUT_TYPES
        for key in ("note", "abstract", "info", "todo", "tip", "success",
                    "question", "warning", "failure", "danger", "bug",
                    "example", "quote"):
            self.assertIn(key, spec)
            self.assertTrue(re.fullmatch(r"#[0-9A-Fa-f]{6}", spec[key]["color"]))
            self.assertIn(key, mdg.CALLOUT_ICONS)          # 每种类型有单色线条符号
            self.assertTrue(mdg.CALLOUT_ICONS[key])
            self.assertTrue(spec[key]["title"])
        # 公众号实测：SVG/clip-path/dataURI 全被剥离，图标必须是纯文本符号
        self.assertNotIn("<svg", mdg.callout_icon("#FF9800", "warning"))
        self.assertIn("⚠", mdg.callout_icon("#FF9800", "warning"))

    def test_aliases_and_case_insensitive_fallback(self):
        for alias, base in mdg.CALLOUT_ALIASES.items():
            self.assertIn(base, mdg.CALLOUT_TYPES)  # 别名都指向内置类型
        # 未知名/大小写不敏感 → 回退 note，不报错
        _, html = mdg.convert("> [!custom-x] 自定义\n> 正文。\n")
        self.assertIn(mdg.CALLOUT_TYPES["note"]["color"], html)
        _, html_up = mdg.convert("> [!WARNING] 大写\n> 正文。\n")
        self.assertIn(mdg.CALLOUT_TYPES["warning"]["color"], html_up)

    def test_fold_marker_and_title_only(self):
        _, folded = mdg.convert("> [!faq]- 折叠题\n> 答案。\n")
        self.assertIn("▸", folded)   # 默认折叠
        _, opened = mdg.convert("> [!faq]+ 展开题\n> 答案。\n")
        self.assertIn("▾", opened)   # 默认展开
        _, no_title = mdg.convert("> [!tip]\n> 正文。\n")
        self.assertIn(mdg.CALLOUT_TYPES["tip"]["title"], no_title)  # 用中文默认名

    def test_callout_inline_and_validation(self):
        """callout 正文的加粗/行内代码/角标仍生效，且整篇校验 0 WARNING。"""
        md = "<!-- gzh-title: 测试 -->\n> [!important] 口径\n> **加粗** 与 `代码`。\n"
        title, html = mdg.convert(md)
        self.assertEqual(title, "测试")
        self.assertIn("font-weight:700", html)
        self.assertIn("font-family:Courier New", html)
        path = os.path.join(tempfile.gettempdir(), "gzh_callout_fixture.html")
        write(path, html)
        r = run(os.path.join(SCRIPTS, "validate_gzh_html.py"), path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("WARNING", r.stdout)


class PreviewTests(unittest.TestCase):
    """README：单个预览页深浅自适应 + 手动切换 + 复制按钮。"""

    def test_preview_shell(self):
        with tempfile.TemporaryDirectory() as td:
            body = os.path.join(td, "article.html")
            write(body, mdg.convert(FIXTURE)[1])
            out = os.path.join(td, "article_预览.html")
            r = run(os.path.join(SCRIPTS, "wrap_preview.py"), body, out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            p = read(out)
            self.assertIn("@media (prefers-color-scheme: dark)", p)
            self.assertIn("gzhCycleMode", p)
            self.assertIn("复制到公众号", p)
            self.assertNotIn('class="gzh-dark"', p)
            self.assertIn(build_dark_css(read(body))[:80], p)
            # SKILL.md 约定：只保留一个自适应预览文件，不生成单独的深色版
            self.assertFalse(os.path.exists(os.path.join(td, "article_预览_深色.html")))


class RepoHygieneTests(unittest.TestCase):
    """规格安全边界、依赖口径、只写草稿；文档与代码一致性。"""

    @classmethod
    def setUpClass(cls):
        cls.skill_md = read(os.path.join(ROOT, "SKILL.md"))
        cls.readme = read(os.path.join(ROOT, "README.md"))
        cls.spec = read(os.path.join(ROOT, "doc/方案设计规格.md"))
        cls.contract = read(os.path.join(ROOT, "references/browser-tool-contract.md"))
        cls.survey = read(os.path.join(ROOT, "references/ecosystem-survey.md"))
        cls.requirements = read(os.path.join(ROOT, "requirements.txt"))
        cls.mp_full = read(os.path.join(SCRIPTS, "mp_full.py"))
        cls.api = read(os.path.join(SCRIPTS, "wx_api_publish.py"))

    def test_layout_and_frontmatter(self):
        for d in ("scripts", "references", "templates", "assets", "doc"):
            self.assertTrue(os.path.isdir(os.path.join(ROOT, d)), d)
        self.assertTrue(re.search(r"^name:\s*gzh-md-compose-push\b", self.skill_md, re.M))
        self.assertIn("display_name: 公众号排版与发布助手(Obsidian/Markdown)", self.skill_md)
        themes = [f for f in os.listdir(os.path.join(ROOT, "assets"))
                  if f.endswith(".png")]
        self.assertEqual(len(themes), 12)
        self.assertFalse(os.path.isdir(os.path.join(ROOT, "assets", "themes")))

    def test_readme_local_links_exist(self):
        paths = re.findall(r"\]\((?!https?://|#)([^)]+)\)", self.readme)
        paths += re.findall(r'(?:src|srcset)="([^"]+\.png)"', self.readme)
        paths += [p.strip() for group in
                  re.findall(r'srcset="([^"]+)"', self.readme)
                  for p in group.split(",")]
        for path in paths:
            path = path.split()[0]
            if path in (".", "...") or path.startswith("<"):
                continue  # 文档里的占位写法，不是真实文件
            self.assertTrue(os.path.exists(os.path.join(ROOT, path)), path)

    def test_dependency_wording_current(self):
        self.assertIn("chrome-devtools-mcp", self.readme)
        self.assertIn("patchright", self.readme)
        self.assertIn("~/.config/gzh-md-compose-push", self.readme)
        self.assertIn("~/.config/gzh-md-compose-push", self.spec)
        self.assertNotIn("技能目录下的独立浏览器环境", self.readme)
        self.assertNotIn("本机已于 2026-11-26 卸载", self.spec)
        self.assertIn("三段式", self.skill_md)

    def test_highlight_contract_current(self):
        self.assertIn("含代码块", self.contract)
        self.assertIn("必须", self.contract)
        self.assertIn("CDP", self.contract)
        self.assertIn("含代码块", self.readme)
        self.assertIn("含代码块", self.spec)

    def test_patchright_mandatory_for_highlighted_scan(self):
        """规则：扫码 + 含代码块 → patchright 必选；各文档口径须一致。"""
        docs = {
            "README": self.readme,
            "SKILL": self.skill_md,
            "规格": self.spec,
            "契约": self.contract,
            "生态盘点": self.survey,
            "requirements": self.requirements,
        }
        for name, text in docs.items():
            self.assertIn("patchright", text, name)
            # 每份文档都要同时点出「代码块/代码高亮」与「必选/必装」，不能只写兜底口径
            self.assertTrue(
                ("代码块" in text or "代码高亮" in text) and
                ("必选" in text or "必装" in text),
                "%s 未声明含代码高亮的扫码通道 patchright 必选" % name,
            )
        # 无代码高亮时可省的表述仍须保留，避免误导成「一律必装」
        self.assertIn("无代码块", self.readme)
        self.assertIn("无代码块", self.skill_md)
        self.assertIn("无代码高亮", self.spec)

    def test_internal_ref_rule_in_docs_and_no_dev_section_in_readme(self):
        """内部引用按「已引入/仅链接」双场景写进文档；README 不放开发章节。"""
        convention = read(os.path.join(ROOT, "references/user-conventions.md"))
        for name, text in (("README", self.readme), ("SKILL", self.skill_md),
                           ("规格", self.spec), ("约定", convention)):
            self.assertIn("已引入", text, name)        # 已引入 → 保留
            self.assertIn("不在此展开", text, name)    # 仅链接 → 改写，不是残句
        self.assertIn("分场景", self.readme)
        self.assertIn("双场景", self.skill_md)
        self.assertNotIn("回归测试", self.readme)
        self.assertNotIn("unittest", self.readme)

    def test_callout_rule_in_docs(self):
        """callout 按官方类型渲染的口径写进文档，不再降级成加粗引用。"""
        for name, text in (("README", self.readme), ("SKILL", self.skill_md),
                           ("规格", self.spec)):
            self.assertIn("callout", text, name)
        self.assertIn("13 种类型", self.readme)
        self.assertIn("callout_block()", self.skill_md)
        self.assertIn("原样保留", self.spec)

    def test_callout_icon_is_text_not_svg_in_docs(self):
        """图标方案口径：单色线条 Unicode 符号，不用 SVG（公众号实测剥离）。"""
        for name, text in (("README", self.readme), ("SKILL", self.skill_md),
                           ("规格", self.spec)):
            self.assertIn("SVG", text, name)          # 说明了为什么不用 SVG
            self.assertIn("Unicode", text, name)      # 明确改用 Unicode 线条符号
        self.assertIn("⚠", self.skill_md)
        self.assertIn("U+26A0", self.spec)

    def test_preflight_and_daemon_teardown_rule(self):
        """推送前检查脚本存在且安全；停 daemon 收尾口径写进文档。"""
        pf_path = os.path.join(SCRIPTS, "mp_preflight.py")
        self.assertTrue(os.path.exists(pf_path))
        pf = read(pf_path)
        self.assertIn("PROFILE not in cmd", pf)          # 只认占用本 profile 的进程
        self.assertIn("daemon.js", pf)                   # 能识别 chrome-devtools daemon
        self.assertIn("SIGTERM", pf)                     # 温和结束，不 kill -9
        self.assertIn("SingletonLock", pf)
        self.assertIn("RESULT:", pf)
        self.assertIn("PASS 可以推送", pf)
        # 推送流程与契约/规格都写明了两条规则
        self.assertIn("mp_preflight.py --fix", self.skill_md)
        self.assertIn("推送前环境检查", self.skill_md)
        self.assertIn("chrome-devtools stop", self.contract)
        self.assertIn("停掉工具 daemon", self.contract)
        self.assertIn("mp_preflight.py --fix", self.spec)
        self.assertIn("自动检查专用浏览器环境", self.readme)

    def test_no_runtime_secrets_in_skill(self):
        scripts_dir = os.path.join(ROOT, "scripts")
        for name in os.listdir(scripts_dir):
            self.assertIsNone(EXCLUDE_FILES.search(name), name)
        self.assertFalse(os.path.exists(os.path.join(scripts_dir, "mp_profile")))
        self.assertIn("GZH_MP_RUNTIME", self.mp_full)
        self.assertIn(".config/gzh-md-compose-push", self.mp_full)

    def test_publish_guardrails(self):
        self.assertIn('FORBIDDEN_LABELS = ("发表", "群发", "发布")', self.mp_full)
        self.assertIn("拒绝点击危险按钮", self.mp_full)
        self.assertIn("/draft/add", self.api)
        self.assertNotIn('"/freepublish"', self.api)
        self.assertNotIn('"/masssend"', self.api)

    def test_no_stale_doc_claims(self):
        """文档与代码注释不得残留已被推翻的旧口径（二维码路径/行数/列宽/SVG 图标）。"""
        conv = read(os.path.join(SCRIPTS, "md_to_gzh.py"))
        pre = read(os.path.join(SCRIPTS, "obsidian_preprocess.py"))
        notes = read(os.path.join(ROOT, "references/mp-wechat-notes.md"))
        # 二维码只落配置目录，绝不写进 scripts/
        self.assertNotIn("scripts/mp-login-qrcode", self.skill_md)
        self.assertIn("~/.config/gzh-md-compose-push/mp-login-qrcode-big.png",
                      self.skill_md)
        # callout 头在预处理里原样保留（不降级成加粗），图标不是 SVG
        self.assertNotIn(r"→ > **标题**", pre)
        self.assertNotIn("图标是 Lucide 线条 SVG", conv)
        # 列宽最终解是 width="%" 属性，不再主张 th/td 内联样式定宽；
        # 该文件曾同时存在两种口径，现统一指向「列宽最终解」。
        self.assertNotIn("列宽必须同时写在**每个 th/td 的内联样式**上", notes)
        self.assertIn("`width=\"%\"` HTML 属性", notes)
        # profile 占用先走预检脚本，不再只写手动删 profile
        self.assertIn("mp_preflight.py --fix", notes)

    def test_config_and_image_upload_paths(self):
        cfg = read(os.path.join(SCRIPTS, "push_config.py"))
        self.assertIn("GZH_PUSH_CONFIG", cfg)
        self.assertIn(".config/gzh-md-compose-push", cfg)
        tpl = read(os.path.join(ROOT, "templates/article_template.py"))
        self.assertIn("AUTHOR", tpl)
        self.assertIn("push_config", tpl)
        uploader = read(os.path.join(SCRIPTS, "upload_md_images.py"))
        self.assertIn("data:", uploader)
        self.assertIn(r"https?://", uploader)

    def test_all_python_sources_compile(self):
        for name in os.listdir(SCRIPTS):
            if name.endswith(".py"):
                path = os.path.join(SCRIPTS, name)
                py_compile.compile(path, doraise=True)
        py_compile.compile(os.path.join(ROOT, "templates", "article_template.py"),
                           doraise=True)

    def test_installed_copy_matches_source(self):
        if not os.path.isdir(SKILL_INSTALL):
            self.skipTest("未安装技能副本，跳过一致性检查")

        def snapshot(base):
            out = {}
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for f in files:
                    if EXCLUDE_FILES.search(f):
                        continue
                    p = os.path.join(root, f)
                    rel = os.path.relpath(p, base)
                    with open(p, "rb") as fh:
                        out[rel] = hashlib.sha256(fh.read()).hexdigest()
            return out

        self.assertEqual(snapshot(ROOT), snapshot(SKILL_INSTALL))


@unittest.skipUnless(os.environ.get("GZH_LIVE") == "1",
                     "需 GZH_LIVE=1 + GZH_APPMSGID 才跑真实草稿回读")
class LiveDraftTests(unittest.TestCase):
    """可选：真实公众号草稿回读，覆盖 README「确认真的保存成功」。"""

    def test_draft_readback(self):
        appmsgid = os.environ.get("GZH_APPMSGID")
        self.assertTrue(appmsgid, "请设置 GZH_APPMSGID")
        r = run(os.path.join(SCRIPTS, "mp_check.py"), appmsgid, "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("RESULT: PASS", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
