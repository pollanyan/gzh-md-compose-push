# 公众号后台浏览器通道 —— 实测踩坑清单

来源：from skill `wechat-mp-draft` v1.3.2（森智道）SKILL.md 提炼，全部为实测结论。
调用 mp_* 脚本前先读本文件；遇到失败优先在这里找对应条目。

## 认证与浏览器

- 入口 URL 必须是 `https://mp.weixin.qq.com/`。直接开 `/cgi-bin/home`（无 `?token=`）会被判「请重新登录」，误以为 cookie 失效。
- 独立 profile：`~/.config/gzh-md-compose-push/mp_profile/`（Cookies 在 `Default/Network/Cookies`；`GZH_MP_RUNTIME` 可改根目录）。与用户日常浏览器登录态不共享；与宿主 Agent 是否登录无关，浏览器工具归属哪个 Agent 都不影响这份 profile。**不放技能目录**，避免安装副本/分享时带走登录态（2026-11-26 复查定稿）。
- 登录态过期表现：脚本又去截二维码。`MP_LOGIN_WAIT` 默认 900 秒，登录成功立即返回。
- 二维码约 4 分钟刷新一次；用户要扫的是放大版 `~/.config/gzh-md-compose-push/mp-login-qrcode-big.png`（~490px），原始 122px 扫不出。
- profile 被占用（SingletonLock / ProcessSingleton）→ 先跑 `python3 scripts/mp_preflight.py --fix`：只结束命令行里带本技能 profile 的进程、删陈旧锁，不碰用户日常 Chrome；仍 FAIL 就停掉工具 daemon（`chrome-devtools stop`）再查（详见 `browser-tool-contract.md` 第 9 单元）。
- `logout` = 删配置目录下的 `mp_profile`；技能目录本身不应有登录态，无需分享前手工清理。

## 编辑器 DOM（2026 版）

- 没有 iframe（老教程 `#ueditor_0` 已废弃）。正文 `.mock-iframe-body .ProseMirror`；标题 `.title-editor__input .ProseMirror`；署名 `input#author`；摘要 `textarea#js_description`。
- 填 HTML 唯一可靠路径：真实点击聚焦 → `ctx.grant_permissions(['clipboard-read','clipboard-write'], origin='https://mp.weixin.qq.com')` → `navigator.clipboard.write` 写 `text/html` → `Cmd+V`（macOS）/ `Control+V`（Windows/Linux）。修饰键必须按平台选——2026-11-25 实测 mac 上 Control+V 不触发粘贴（注入只剩 10 字符），Control+A 也不全选。
  无效做法：合成 `ClipboardEvent('paste')`、直接改 `innerHTML`。chrome-devtools 的 `press_key` 底层是 puppeteer 的 CDP 合成按键，不是系统级真实按键，无法触发 Chrome 的原生粘贴（所以写剪贴板成功也不会有 paste 事件）；`insertHTML` 绕过编辑器原生粘贴转换，保存时 ProseMirror 序列化会丢代码块颜色。`execCommand('insertHTML')` 在 patchright 脚本路径实测无效；chrome-devtools 工具路径的 `evaluate_script` 里能写入正文，但 **2026-11-27 实测保存后微信后端会剥离代码块里的彩色 span**（注入时 2434 个、重开只剩 152 个非代码块颜色），**含代码高亮的文章必须走剪贴板粘贴的脚本路径**（保存后 1862 个代码高亮 span 全保留）；`insertHTML` 仅限无代码块的纯文本文章兜底。见 `browser-tool-contract.md`。
- 粘贴后可能弹「内容结构检测」，必须点「继续插入」，否则内容被静默丢弃（不是每次都弹，轮询 8 秒）。
- 结构检测两条硬规则：文字背景禁渐变（CTA 用纯色）；`line-height` 不能小于 `font-size`（19px→1.45、17px→1.55、14/13px→1.6）。
- 不要手算点击坐标（正文可高 5000+px，scrollIntoView 后 rect.y 为负）；用 `pg.click(selector)` 让 Playwright 算。
- 保存成功判据：短文本 Toast（≤12 字，形如「保存成功/已保存」）或 URL 出现 `appmsgid`；都没有就重试一次。
- 编辑器会自动存草稿——打开新建页并输入标题就可能落一篇草稿，调试残留用 `mp_drafts.py delete "关键字" --yes` 清。

## 封面

- 封面区悬停才出菜单；页面有 3 个同名 `.js_cover_btn_area`，`querySelector` 拿到的往往不是能点的。
- 可靠做法：先存草稿拿 `appmsgid`，再用 `mp_cover_set.py` 重开这篇设封面（保存前设封面会静默失败）。
- 图片库弹窗里 accept 含 `bmp` 的 file input 才是封面通道；accept 含 jpg/png 的是正文插图，用错会把封面图插进正文末尾。
- 图片库条目是 `<i>` 的 background-image，不是 `<img>`；必须真实鼠标点击条目容器 `.weui-desktop-img-picker__item` 中心坐标，`element.click()` 不触发选中。
- 刚上传的图微信要转码：条目已出现但标题为空、显示进度条时选中它 → 裁剪弹窗永远转圈。等「标题 == 文件名」再选，最长 90 秒；等不到就放弃，绝不兜底选第 0 条（会设错封面）。
- 「下一步 / 确认」要限定在可见弹窗内点击（`.weui-desktop-dialog` + `offsetParent` 过滤）；按钮文案是「确认」不是「确定」。
- 判断封面成功：读 `#js_cover_area .js_cover_preview_new` 的 `background-image` 相对本次基线是否变化，不要数 `<img>`（封面是 background-image，占位文案始终在 DOM）。

## 图片

- 正文图必须是 `mmbiz.qpic.cn` URL；file:/// 和 data-URI 无效。用 `mp_imglib_upload.py` 上传后按文件名取 URL 拼进 HTML。
- 缩略图是 `/300?wx_fmt=png`，换成 `/0?` 是原图；粘贴后微信改写为 `/640?` 并加 `class="rich_pages wxw-img"` 属正常。
- 每张正文图后面 ProseMirror 插一个 `<img class="ProseMirror-separator" src="">`；数图/删图必须排除它，6 张图的 `img` 总数是 12。
- 图片库是账号级的，同名图不会新增；重复上传会造成多份。
- **位图不参与 Dark Mode 转换，也无法按系统深浅自动换图**（2026-11-28 实测）：
  正文里 `<picture><source media="(prefers-color-scheme: dark)">` 的 `<source>`
  会被整条剥离（`pictureCount=1` 但 `sourceCount=0`，只剩浅色 `<img>`）；`<img>`
  上的 `data-darkmode-src` / `data-no-dark` 同样被剥离（编辑器把图片重构成
  `<section nodeleaf><img src data-src style>`）；但 `<p>` / `<span>` 等文本节点上的
  `data-no-dark` 会保留。GitHub README 的效果图自动切换靠 GitHub 原生支持
  `<picture>`，**不可照搬到公众号正文**。要同时展示深浅两版，只能把两版并列画进
  同一张位图（上下各一版、各带标签）让读者对照。拿不准平台是否支持某 HTML，
  先推一篇测试草稿回读 DOM 取证（测完用 `mp_drafts.py delete` 清理）。

## 核验

- `mp_check.py <appmsgid> [预期图数]`：退出后重开草稿核对，输出 PASS/FAIL。检查 title/author/digest 有值、bodyLen>20、realImgs==正文图数、封面非默认、原图尺寸。
- **横滑容器实测保留 `scroll-snap-type:x mandatory`**（2026-11-28）：`overflow-x:auto`
  + `scroll-snap-type:x mandatory` + 子图 `display:inline-block;width:100%` 保存后
  全部保留，`clientW=558` / `scrollW=3348`（一屏一张 ×6），吸附切换在微信端真实生效。
  探测时 `img.parentElement` 只是 ProseMirror 补的 `<span>`（`overflow=visible` /
  `clientW=0`），**真正的滚动容器在更上层 `section`**——从 img 沿 `parentElement`
  向上遍历、找 `getComputedStyle(e).overflowX==='auto'` 的祖先才是，别直接取父元素，
  否则会误判成「横滑丢失」。
- 草稿打不开三种形态：`系统错误(320003)` 草稿不存在、`此草稿已被删除`、`此草稿已发表`——不是选择器失效。

## 覆盖草稿

- `mp_full.py push <article.py> --appmsgid N` 覆盖指定草稿，避免半成品堆积。
- 草稿箱列表 DOM：一张卡 `.weui-desktop-publish__cover-item`，标题 `.weui-desktop-publish__cover__title`；操作组 `.weui-desktop-publish__opr` 悬停才浮出，组内第 1 个图标是删除、第 2 个是编辑。
- `mp_drafts.py delete` 每删一篇都重新拉列表比对标题，发现少了不含关键字的草稿立刻报警；删除按钮必须过滤 `offsetParent`（真假两个同名按钮）。
- 列表页可能有隐藏的「未授权使用切换账号能力」对话框——绝不要点它的「退出登录」。

## 短文章

- **微信编辑器会剥离 `<colgroup>/<col>`**（2026-11-25 手机实测：colgroup 里的
  列宽在公众号后台/手机端全部失效，table-layout:fixed 平分列宽；PC 浏览器预览
  正常所以此前未发现）。这是早期发现的坑；**最终解法是 `width="%"` HTML 属性**（见
  下文「列宽最终解」），不要再退回 colgroup / td 内联样式定宽——那些都会被微信剥离。
- 引用/正文的 `text-align` 必须显式写 `left`：微信手机端对未指定段落默认
  两端对齐，PC 浏览器默认左对齐——不写死则三端不一致（手机「两端对齐」实拍）。
- 引用段不加「QUOTE」等装饰性英文标签（用户定稿：影响阅读）。
- **列宽最终解：`width="%"` HTML 属性，且只靠它**（2026-11-25 三次手机实测 +
  探针实验定稿）：公众号新编辑器是 ProseMirror，粘贴时按自家 schema 重建表格——
  colgroup、td 的 style.width 都会被剥离；**HTML 属性 `width="16%"` 会被保留**，
  百分比随屏幕宽度自适应。
  关键反例：**同时写 `data-colwidth`(px) 会让微信按 px 定宽**，375px 手机上
  640px 表格超出屏幕 → 首列 102px 占屏 27%（探针实测：去掉 data-colwidth 后
  表格宽 = 容器宽 558px，列宽按 % 自适应，状态列 10%）。
  另：**不要写 `min-width`**（微信把表格宽度固化成该值，手机端溢出）。
  最终列宽通道：①`width="%"` 属性（微信+浏览器通用，唯一必需）；②单元格
  style width + colgroup（浏览器直开时的补充，微信会剥离）。引用段的 **加粗/`行内代码` 必须走 inline() 解析后再进 HTML，
  只 esc 会让 `**31**` 原样输出（2026-11-25 手机实拍）。
- **emoji 显示宽度按 3 个单位估**（🟢🔴 等，字形宽约 1.3 倍字号且不留换行
  余地就会竖排）——2026-11-25 手机实测「🟢 强」在 8% 列宽下竖向换行。
- **「单行列」按内容特征判定（single_line_cols，阈值 SINGLE_LINE_MAX=12）**：
  列内最长单元格显示宽 ≤ 12 单位 → 整列 td `white-space:nowrap` + 列宽按
  「整格最大宽 + 8」保底。状态/评级/短枚举列自动覆盖，与表头名称无关
  （此前的「表头=状态」特例已废弃）。
- **表格横向滚动的两条铁律**（2026-11-25 实战）：
  - ①**table 的 style 里 `width:100%` 必须写单个 `%`**——该字符串若不走 Python
    `%` 格式化，写成 `%%` 会原样输出成非法值 "width:100%%"，浏览器视为无效
    → 表格宽度回退 auto → **内容被压扁成细条、无横向溢出、滚动条消失**
    （本次事故真凶）。注意 `image_block` 那行**走了** `%` 格式化，那里 `%%`
    是正确的，不要一起改。
  - ②`width:100%` + `min-width:620px` 组合：窄屏下表格不小于 620px，外层
    `overflow-x:auto` 产生横向溢出 → **可左右滑动**（浏览器实测 canScroll
    true）。微信端会把 min-width 收敛、表格宽=容器宽，但**列的 width="%"
    属性保留**，读者端因此是「表格随屏 + 列按比例 + 长内容正常换行」，
    同样不压扁——微信不提供宽表格横滑，只能靠列宽比例让内容可读。
- **代码块默认被微信强制折行 → 显式 nowrap + 外层 overflow-x:auto**
  （2026-11-26 用户手机实测反馈）：微信编辑器把代码 `p` 的计算样式设为
  `white-space:break-spaces`，长代码行被强行折行。修复：每个代码行 `p` 加
  `white-space:nowrap`、外层代码块 section 加 `overflow-x:auto`——探针实证
  微信 ProseMirror **两个声明都保留**（保存后 `outerOverflow=auto`、
  `lineWs=nowrap`、行高 21px 单行），长行产生横向溢出可左右滑动。
  浏览器窄容器实测：外层 scrollWidth 545 > clientWidth 316、canScroll true；
  短代码块内容不超宽时无滚动条（正常）。注意用 nowrap 而非 `pre`（用户约定
  禁用 pre），且每行单 leaf 的结构不变。
- **一级标题被整行丢弃（Obsidian 多 # 大章稿）**（2026-11-26 用户反馈
  「产物与原物结构不一致」）：转换器主循环原本把**所有** `# ` 行都跳过
  （只取第一个作文章标题），源文的 `# 1 omp 是预置好的…` / `# 2 用扩展
  定制 Pi` 两大章凭空消失。定稿修法：标题从 Obsidian frontmatter 单独取
  （预处理写成 `<!-- gzh-title: ... -->`），正文 `#` 不再被当成标题吞掉；
  章节级别按正文实际标题判定——有 `#` 用 `#`（01/02 大章节），否则用
  `##`。代码块里的 `# 1) 备份…` 注释必须排除在标题扫描之外。
- **reference 只认「附：取证来源」小节**（2026-11-26 用户指出太特殊化）：
  正文章节标题里的 `[extensions](URL)` 之类链接会被预处理删成纯文字，URL
  永久丢失。定稿：`collect_refs()` 全篇扫描 Markdown 链接/裸 URL/`[N]` 条目
  统一编号，`_links_to_refs()` 在正文换成文字 + `[[N]]` 角标，文末重排附录；
  重复 URL 复用编号，代码块与图片行不计入。
- **代码块整段消失（2026-11-26 回归）**：标题改造时在 convert 主循环开头加了
  `if not s or fence[i]: continue`，把 ``` 开围栏也跳过，代码块分支永远走不到，
  于是 12 个代码块（含块嵌入的「可复制提示词」全文）全没了，草稿里表现为
  「下面嵌入…全文，可整段复制使用：」后面空白。修法：主循环只用
  `if not s: continue`，代码块由 ``` 分支一次性消费；fence 数组只用于预扫描标题
  与 reference。交付前必须核对代码块数量与源稿围栏数一致（24 根围栏 = 12 块）。
- **小标题与引用块双竖线很别扭**（2026-11-26 用户截图反馈）：h3 去掉
  `border-left`；引用块改为浅灰底 `#F5F5F5` + `#D4D4D8` 左侧 2px 细线 +
  `#3F3F3F` 字（深色方案 `#383838`/`#A1A1AA`/`#A5A5A5`），照用户提供的
  其他公众号深浅截图定稿；深浅自适应预览仍由微信读者端算法转换。
- 旧版用魔数 `正文长度<=200` 判注入失败，导致短文被重复粘贴。现按预期非空白字符数判定（下限=预期×0.7），每次尝试前先 `Ctrl+A`+`Delete` 清空。
