# 浏览器通道：Agent 自带工具的复用契约

本文件回答一个问题：**扫码通道能不能不装 patchright，直接让 Agent 用它自己的浏览器能力做？** 分情况：**文章含代码块（需要代码高亮）→ 不能，patchright 必选**；工具路径的 `insertHTML` 保存后会被微信剥离代码块彩色 span，只有脚本路径的原生剪贴板粘贴能保住高亮（2026-11-27 实测）。**文章无代码块 → 能**，多数 Agent 是安装了 [chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) 才具备浏览器操作能力，也有宿主预装了别的等价工具、技能或插件；无论哪种，Agent 都是调接口操作浏览器。浏览器工具属于 Agent 侧能力，不属于本技能，也不绑定某个宿主：chrome-devtools 是独立开源项目，可装到多种 Agent 上。技能只要求能力满足契约，并把公众号后台的精确操作写成一份与工具无关的契约，让 Agent 用当前环境提供的接口去执行。

## 一、先探测当前 Agent 的浏览器工具

按宿主实际提供的能力选择，不要假设某一种工具一定存在。常见情况：

| 宿主 / 工具                          | 调用方式                                      | 适合本契约                          |
| ------------------------------------ | --------------------------------------------- | ----------------------------------- |
| chrome-devtools MCP / CLI（独立开源项目，多数 Agent 由此获得浏览器能力） | MCP 工具：`new_page` / `navigate_page` / `take_snapshot` / `evaluate_script` / `click` / `press_key` / `upload_file` / `take_screenshot` | ✅ 最合适：能执行 JS、能上传文件、有独立持久化 profile |
| chrome-devtools-cli skill            | shell 命令：`chrome-devtools evaluate_script ...`、`upload_file`、`press_key` 等 | ✅ 与 MCP 等价，适合脚本化执行      |
| computer-use 类工具                  | 截图 + 坐标点击 + 键盘                        | ⚠️ 可做，但慢且脆，**不要用坐标做正文注入** |
| 文章含代码块（需代码高亮）           | 必须真实剪贴板粘贴                            | ❌ 工具路径的 `insertHTML` 保存后会被微信剥离高亮，退回 `mp_*.py` |
| 无任何浏览器工具                     | —                                             | ❌ 退回技能自带 `mp_*.py`（patchright） |

探测按**能力**判断，不按工具名字。先列出宿主暴露的工具 / 已装 skill / MCP server 配置，再逐项核对六项必需能力：

1. 打开任意 URL（导航）；
2. 在页面里执行 JS——写剪贴板、读 DOM 都靠它；
3. 发送真实按键（Ctrl+V、Ctrl+A 等）；
4. 上传本地文件（图片库 file input）；
5. 独立的持久化浏览器环境，登录态不混入用户日常浏览器；
6. 截图（放大二维码给用户扫）。

**文章含代码块时，六项全满足也不走工具路径**——直接判定工具路径不满足契约，走 `mp_*.py` 脚本路径（patchright 必选）。文章无代码块时：六项全满足 → 走工具路径，把第二节契约单元翻译成该工具的接口调用（见第四节）。缺 2 或 4 任一项 → 正文注入或图片上传做不了，**退回 `mp_*.py` 脚本路径**，不要硬凑。computer-use 类工具没有第 2 项，只能承担扫码、按钮点击和上传，正文注入必须另有 JS 执行能力。

上面表格只列常见宿主；任何接口等价的工具（Playwright MCP、browser-use 等）都按同样方式适配，不用改契约。

## 二、契约的操作单元（工具无关）

每一步只描述“要达成什么”，参数给出可直接用的 JS / 选择器。Agent 把这些单元翻译成当前工具的具体调用。

### 0. 独立登录态

用浏览器工具自带的**持久化 profile**，不要复用用户日常 Chrome 的登录态。chrome-devtools MCP 用它的默认持久 profile；脚本路径用 `~/.config/gzh-md-compose-push/mp_profile/`。两者互不影响，也不会把 Cookies 放进技能目录。

### 1. 打开入口并取 token

入口必须是 `https://mp.weixin.qq.com/`。直接开无 `token` 参数的子页会被判「请重新登录」。从地址栏 URL 取 `token`，后续编辑页 URL：

```text
新建：https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token=<TOKEN>&lang=zh_CN&scene=21
覆盖：https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77&appmsgid=<ID>&token=<TOKEN>&lang=zh_CN
```

### 2. 扫码登录

未登录时页面出现二维码元素 `.login__type__container__scan__qrcode`。截图后放大约 4 倍交给用户扫（原始约 122px 扫不出）；最长等 900 秒；登录后删掉临时二维码图片。二维码约 4 分钟刷新，过期重新截。

### 3. 填标题 / 署名 / 摘要

- 标题：`.title-editor__input .ProseMirror`，先点击取得焦点 → `Cmd+A`（macOS）/ `Control+A`（其他）→ `Delete` → 输入标题（≤64 字）→ 回读前 6 字校验。
- 署名：`input#author`；摘要：`textarea#js_description`（≤120 字）。

### 4. 写正文（关键，唯一可靠路径）

正文编辑器是 `.mock-iframe-body .ProseMirror`（2026 版**无 iframe**）。必须按顺序：

1. 真实点击编辑器取得焦点，再 `Cmd+A`（macOS）/ `Control+A`（其他）→ `Delete` 清空；
2. 执行 JS 写剪贴板（同时写 `text/html` 和 `text/plain`）：

   ```js
   async (a) => {
     const item = new ClipboardItem({
       'text/html': new Blob([a.html], {type: 'text/html'}),
       'text/plain': new Blob([a.plain], {type: 'text/plain'})
     });
     await navigator.clipboard.write([item]);
   }
   ```

3. 发 `Cmd+V`（macOS）/ `Control+V`（其他平台）——修饰键必须按平台选，mac 上 Ctrl+V 不触发粘贴（2026-11-25 实测）；
4. 轮询最多 8 秒，若出现「内容结构检测」弹窗（`.weui-desktop-dialog`），点「继续插入」——不点内容会被静默丢弃；
5. 读 `.mock-iframe-body` 的 `innerText.length`，按 HTML 预期非空白字符数的 0.7 倍作下限（下限最小 20）；不达标则清空重试一次。

**为什么工具路径做不到剪贴板粘贴（2026-11-27 取证）**：chrome-devtools-mcp 1.12.0 的 `press_key` 底层是 `page.pptrPage.keyboard.down/press/up`（puppeteer 的 CDP 合成按键，`build/src/tools/input.js:628-661`），不是操作系统级真实按键；Chrome 不会把它当作可触发剪贴板读取的用户手势，所以 `navigator.clipboard.write` 明明成功，页面却没有原生 `paste` 事件。合成 `ClipboardEvent('paste')` 又被公众号编辑器忽略。`insertHTML` 绕过了编辑器的原生粘贴转换管道（这段管道会把 `text/html` 里的颜色 span 映射进 ProseMirror 的 mark），保存时 ProseMirror 按自己的模型序列化，代码块里的彩色 span 因此被丢弃。这不是「CLI 不能驱动浏览器」，而是**合成按键无法触发原生粘贴 + 兜底注入路径会丢样式**这两个具体能力缺口。

**工具路径的实测修正（2026-11-26，2026-11-27 补充关键限制）**：chrome-devtools CLI 在无头/有头下 `press_key` 发 `Cmd+V` / `Ctrl+V` 都不触发原生粘贴（正文只剩 10 字占位符），即使 `navigator.clipboard.write` 返回成功。此时可在同一 `evaluate_script` 里用 `document.execCommand('selectAll')` + `document.execCommand('delete')` + `document.execCommand('insertHTML', false, html)`（先真实点击编辑器取得焦点）写入全文，正文/图片/章节能保存并重开核验。**但 2026-11-27 实测：注入时 DOM 里代码高亮 span 完整（2434 个），保存后微信后端会把代码块里的彩色 span 全部剥离（重开只剩 152 个非代码块颜色）**——代码高亮必丢。因此**含代码块的文章判定工具路径不满足契约，必须改走 `mp_*.py` 的剪贴板粘贴路径**（实测保存重开后 1862 个代码高亮 span 全保留）；`insertHTML` 仅限无代码块的纯文本文章兜底。仍**禁止**合成 `ClipboardEvent('paste')` 和直接改 `innerHTML`。也**不要自己算坐标点击**：正文可高达数千像素，`scrollIntoView` 后坐标可能为负；用工具的 DOM 定位 / 选择器点击。

### 5. 正文配图

正文 `<img>` 的 src 必须是 `mmbiz.qpic.cn` URL。用 `mp_imglib_upload.py` 或工具的文件上传接口把图片进图片库后取 URL 拼进 HTML。数图时排除 ProseMirror 自动补的 `<img class="ProseMirror-separator">`，否则会多数一倍。

### 6. 保存草稿

精确匹配可见文字「保存为草稿」并点击（取最后一个可见匹配，避免点到同名隐藏按钮）。成功判据二者之一：短 Toast（≤12 字，含「保存成功 / 已保存 / 草稿已保存」）或 URL 出现 `appmsgid`。最多重试 2 次；都拿不到回执就报失败，不要当作成功。

**硬约束**：点击任何按钮前检查文字，命中「发表 / 群发 / 发布」一律拒绝。

### 7. 封面（可选）

- 封面来源三选一（AskUserQuestion 收集）：①用户自行提供（贴图 / 本地路径 / URL）；②AI 自动生成（消耗生成额度，先告知）；③不加。
- **不论来源，上传前先跑 `cover_prepare.py <路径或URL>` 归一化为 900×383**（中心裁剪 2.35:1，AI 生成图的水印随之去除），工具路径与脚本路径都用归一化后的文件；
- 选 ③ → 跳过，草稿封面为空，之后仍可在后台单独设置；
- 有封面 → **必须先存草稿拿到 `appmsgid`，再重开这篇草稿设封面**（保存前设会静默失败）。封面区 `#js_cover_area` 悬停才出现菜单，且页面有多个同名按钮，必须限定在可见弹窗内点。
- 图片库里 accept 含 `bmp` 的 file input 才是封面通道（含 jpg/png 的是正文插图通道，用错会把封面插进正文末尾）。图片条目是 `<i>` 的背景图，要用真实鼠标点击条目容器 `.weui-desktop-img-picker__item` 中心，`element.click()` 不触发选中。
- 刚上传的图要等条目标题等于文件名（最长 90 秒）再选，等不到就放弃，**绝不兜底选第一条**。
- 成功后读 `#js_cover_area .js_cover_preview_new` 的 `background-image` 相对基线是否变化来判定，不要数 `<img>`。

### 8. 回读核验

用 `appmsgid` 重开草稿，核对标题 / 署名 / 摘要有值、正文长度 > 20、真图数等于预期、封面非默认。全部满足输出 PASS，否则 FAIL 并按 `mp-wechat-notes.md` 排查。

### 9. 收尾：停掉工具 daemon（必做）

**工具路径用完后必须主动停 daemon**，不要留着常驻：chrome-devtools CLI 的后台服务是隐式启动、长期常驻的，一旦用它连过公众号后台（尤其带 `--user-data-dir` 指向推送专用 profile 时），它会一直占着 profile 和 Singleton 锁。后果有两个：① 长期占系统资源；② 下次走脚本路径 `mp_*.py` 推送时 `launch_persistent_context` 直接报 ProcessSingleton / SingletonLock 起不来（2026-11-27 实测踩过）。

- chrome-devtools CLI：`chrome-devtools stop`。
- 其它等价工具：用该工具提供的 stop / teardown 接口；没有就用 `mp_preflight.py --fix` 兜底清理。
- 停完再跑一次 `python3 scripts/mp_preflight.py`，确认输出 PASS，才算收尾干净。

对应地，**脚本路径每次推送前也要先跑 `mp_preflight.py --fix`**（见 SKILL.md 第 3 步第 0 项），这是兜底：即使工具路径忘了停，推送前也能自动清掉占用。两条合起来保证 profile 不会互相卡住。

## 三、为什么这不是「自然语言随便驱动」

「用 Agent 的浏览器能力」不等于「说一句人话让 Agent 自由发挥」。上面每一步都是**确定的工具调用**：URL、选择器、JS、判据、禁止动作都写死了。Agent 的角色是把这些单元翻译成当前环境的接口调用（chrome-devtools MCP 的 `evaluate_script` / `upload_file`，或 CLI 的同名命令，或 computer-use 的键盘 + 点击），而不是自己决定怎么操作公众号后台。浏览器能力可能来自 chrome-devtools-mcp，也可能来自其他等价工具/插件，以能力而非来源为准；这样同一份契约在不同 Agent 上执行结果一致。

脚本路径（`mp_*.py`）和工具路径执行的是**同一份契约**：脚本只是把上面的单元用 patchright 实现了一遍。所以「复用 Agent 自带工具」和「跑技能脚本」不是两套流程，是同一流程的两种执行器。

## 四、按探测结果动态生成调用

Agent 在运行时先探测宿主暴露的是 MCP 工具还是 shell 命令，再把第二节的单元翻译成对应调用；**不要写死某一种宿主的工具名**。以 chrome-devtools 为例：

```text
单元 1 打开入口        → MCP: new_page(url) / navigate_page(url)
                         CLI: chrome-devtools new_page "<url>"
单元 3 读标题          → MCP: evaluate_script("(s)=>document.querySelector(s)?.innerText", selector)
                         CLI: chrome-devtools evaluate_script "(s)=>..." --args <uid>
单元 4 写剪贴板 + 粘贴  → 脚本路径：evaluate_script(写 ClipboardItem 的 JS) + press_key("Meta+V"/"Control+V")
                         → 工具路径：先 click 编辑器，再 evaluate_script(execCommand selectAll/delete/insertHTML)
                         → 若用剪贴板：evaluate_script 轮询「继续插入」
                         CLI: chrome-devtools evaluate_script "<JS>" --pageId <id>
单元 7 设封面上传       → MCP: upload_file(uid, path) / 点击图片库条目
                         CLI: chrome-devtools upload_file <id> <uid> "<path>"
单元 8 核验             → MCP: evaluate_script(读标题/正文长度/真图数/封面背景)
```

computer-use 类工具只有截图 + 键盘 + 坐标点击：登录扫码、按钮点击、文件上传可用它，但**正文注入必须有能执行 JS 的工具**配合（写剪贴板或 insertHTML）；若该工具不能执行 JS，就不满足契约条件，应改用 `mp_*.py`。2026-11-26 实测：computer-use 的后台 `cmd+v` 在 Chrome 非前台时会被丢弃，工具路径不要依赖它注入正文。

生成调用时保留契约给定的三个东西：URL / 选择器（或等价的 DOM 定位）、JS 片段、成功判据。自然语言只用来向用户收集选择（主题、封面路径、覆盖还是新建），不用来决定「怎么点公众号后台」。
