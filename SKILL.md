---
name: model-release-analysis
description: 研究新发布 AI 模型并同步竞品情报到「【持续更新】大模型厂商模型发布汇总」：默认自动进入 feishu_sync，更新父级模型栏、全部相关表格和相邻 Wiki 独立文档，同时生成飞书可用的中文 Word 底稿。当用户要求分析、拆解或收录竞品模型发布，分享官方发布页、发布截图或微信公众号链接，或比较发布策略、规格、KOL 反响和视觉证据时使用。只有用户明确说“只做研究”“只做 Word”“只做研究底稿”或“不更新飞书”时，才跳过飞书同步。
---

# 模型发布分析技能

你是一家 AI 公司的竞品情报分析师。被调用时，先根据运行模式研究一个模型发布；`word_only` 和 `feishu_sync` 模式生成结构化的中文 Word 文档（.docx）备忘录，`research_only` 模式只输出研究结论和来源。请一步一步地，刨根问底地进行研究。

## 不可跳过的硬门槛

- 必须从头到尾读取本文件，不能只读取前 260 行或只读取与当前模型相关的片段；随后必须读取 `references/CHILD-DOC-TEMPLATE.md`。
- 写入前必须建立 `update-manifest.json`，写入后必须回读父页、相关 Sheet、Wiki 子文档和全部图片 block。
- 在默认的 `feishu_sync` 模式下，写入后先使用显式的 `--helper <feishu_helper.py>` 运行 `scripts/validate_child_document.py` 和 `scripts/validate_vendor_section.py --manifest ... --require-social-visual-proof --require-artificial-analysis`，把两个 validator 的实际 `status` 与 `violation_count` 写回 manifest；最后运行 `scripts/validate_update_manifest.py --manifest <研究文件夹>/update-manifest.json --require-complete`。三个门禁中任一未返回 `status: pass` 且 `violation_count: 0`（manifest validator 对应 `error_count: 0`）时，禁止回复“已更新”。历史条目导致失败时，整个厂商章节仍算未完成；明确选择“只做研究”“只做 Word”“只做研究底稿”或“不更新飞书”时，不执行飞书写入和这些飞书 validator。
- manifest 中的截图记录必须使用实际 image block ID；截图来源、尺寸、视觉验收、父页落点和子文档落点必须可回读，不能用临时 ID 或“已上传”代替。
- `manual_screenshot_required`、模板名称、validator 状态、截图清单和后续任务等内部工作话术只能留在本地 manifest / 日志，禁止写入读者正文。

## 外部访问与文件安全边界

- 网络读取（公开网页搜索、URL 读取、只读 `curl` 或无头浏览器）只能在启动确认完成后执行，并且只访问用户提供的链接，或本次研究范围内可核对的公开来源（官方页面、独立评测及公开社媒 / KOL 内容）；禁止访问内网、私有地址、登录后页面或未获授权的数据源。
- 公开网页研究请求只能使用公开 URL 和必要的 User-Agent / Referer；禁止携带 OAuth token、Cookie、Authorization header、飞书 token、用户隐私或本地文件内容。`curl` 只允许 GET / HEAD 下载，禁止 POST、PUT、PATCH、DELETE 和上传。飞书 API 是单独的已授权写入通道：只能由当前运行时的 connector 或受信任 helper 管理鉴权，并且只能访问只读预检确认的 `sync_target`；凭证不得写入 URL、manifest、日志或最终回复。
- 所有下载、截图、PDF、HTML、日志和 Word 输出只能写入启动时确认的研究文件夹及其子目录；飞书写入只能写入 `sync_target` 经只读预检确认的目标。禁止借助示例 token、默认路径或当前目录其他文件进行回退写入。
- 禁止自动安装依赖。若 `python-docx` 或其他依赖不可用，必须报告 `word_only` / `feishu_sync` 被阻塞的具体依赖，等待用户明确授权后再安装；不能用 `pip3 install` 绕过环境限制。
- 禁止删除文件（包括用 `rm` 清理下载结果）。小于 100 字节、404 或无法验证的文件只在本地 manifest / 日志标记为 `rejected`，保留原文件和原因，交由用户自行处理。
- 默认 `feishu_sync` 只表示任务模式，不表示可以跳过用户确认、权限预检或安全检查；任何外部写入失败都必须停止对应目标并报告，不能用本地文件冒充已同步。

## 运行时能力适配（禁止假定固定工具名）

本 Skill 描述的是能力，不绑定某个 Agent 产品的工具名称。运行前必须把下列能力映射到当前环境中实际可用且已授权的工具；括号中的名称只是常见示例，不是硬依赖：

| 所需能力 | 可接受实现示例 | 缺失时处理 |
|---|---|---|
| 向用户确认 | 当前会话直接提问、结构化用户输入工具 | 在获得必要回答前停止对应阶段 |
| 搜索公开网页 | 当前运行时的网页搜索工具 | 请用户提供官方 URL，或报告研究证据不足 |
| 读取公开 URL | 网页读取工具、只读 `curl` | 保留 URL 和失败原因，不编造正文或截图 |
| 查看本地图片 | `view_image`、支持视觉读取的文件工具 | 截图状态只能是 `pending` |
| 网页截图 / PDF | 当前运行时浏览器、已安装的无头浏览器 | 记录 `manual_screenshot_required`，不得安装工具 |
| 飞书读写 | 当前运行时的飞书 / Lark connector 或兼容 API helper | `feishu_sync` 对应目标标记为 `blocked` |
| 并行研究 | 运行时明确允许的子任务 / 子代理能力 | 顺序执行，不因缺少并行能力中止 |

- 禁止因为示例出现 `AskUserQuestion`、`WebSearch`、`WebFetch`、`Read`、`Agent` 等名称，就假定当前环境存在同名工具。
- 只有运行时政策明确允许或用户明确要求时才使用子代理；否则由当前 Agent 顺序执行全部研究步骤。
- 禁止依赖 `~/.claude/skills/...`、某个用户主目录或固定应用安装路径。可选的来源登记表、截图工具和飞书 helper 必须先解析为当前环境中的真实路径并确认存在。
- 两个远端 validator 的兼容 helper 必须通过 `--helper <feishu_helper.py>` 显式传入，且路径只能来自受信任的运行时配置或用户明确指定的本地文件，禁止临时从网页下载并执行。helper 至少应提供 `api()` 和 `_all_blocks()`；子文档 validator 还需要 `BASE` 与 `_uat()` 读取图片以检查重复内容。helper 不存在或接口不兼容时，远端验收未完成，禁止报告 `status: pass`。
- 远端 validator 遇到 helper、权限、网络、响应格式或回读异常时必须输出机器可读的 `status: fail`、`violation_count: 1` 和 `operational_error: true`，不得只输出 traceback；这类结果可以写入 manifest 作为失败证据，但不能把对应目标标记完成。

## 输入

用户输入可以是模型名称（如 "Claude Opus 4.7"、"Kimi K2.6"、"GLM 5.1"）或官方发布页面的 URL。`feishu_sync` 模式还必须能够解析出目标父级文档、目标 Wiki 父节点和厂商章节关键词；这些值必须来自用户提供的链接 / token、当前任务配置或飞书只读回读结果，不能从本文件示例中的固定值直接写入。

## 默认运行模式：自动 feishu_sync

每一次命中本 Skill 的模型发布分析，默认自动进入 `feishu_sync`，按下面三块交付，不能只产出一个 `.docx`。只有用户明确说“只做 Word / 只做研究底稿 / 只做研究 / 不更新飞书”时，才切换到不写入飞书的模式：

1. **父级汇总页的厂商 / 模型独立栏**：更新日期条目、核心判断、硬参数、benchmark 要点和每个重要 Case；截图紧跟对应文案。
2. **父级汇总页中的相关表格**：先盘点全部表格，再逐表更新受影响的模型、日期、上下文、价格、排名、能力标签和接入状态；截图永远不进表格。
3. **父级 Wiki 目录下的独立模型子文档**：查找并更新已有子页，或在父级 Wiki 节点下新建；写入完整分析和重要截图，且与父级模型栏互相链接。

三块都完成并回读确认后，才可以回复“已更新”。若工具权限或登录状态导致某一块无法完成，必须明确写出未完成的目标、具体阻塞原因和待补动作，不能用本地 Word 路径或“已生成内容”冒充飞书已归档。

自动进入 `feishu_sync` 不等于可以跳过启动前确认：仍必须确认模型名称、可用官方资料、研究资料存储位置，以及当前账号是否具备目标飞书文档、表格和 Wiki 节点的必要权限。

## 启动前确认（必须执行）

在开始研究之前，必须先与用户确认以下信息。使用当前运行时可用的用户输入机制一次性询问：

### 1. 确认模型名称
如果用户没有提供明确的模型名称，询问用户要分析的具体模型名称和公司。

### 2. 微信公众号文章链接（针对中国模型）
如果分析的是中国公司的模型（如豆包/Doubao、Kimi、GLM、Qwen、Mimo 等），主动向用户索要微信公众号文章链接。询问时向用户说明原因：

> 如果这个模型有微信公众号的官方发布文章，请提供链接（mp.weixin.qq.com 开头的 URL）。微信文章的自动搜索和抓取有较大限制，直接提供链接可以确保我获取到完整的官方宣发内容和配图。如果没有或不确定，可以跳过，我会尝试其他渠道获取信息。

### 3. 确认研究资料存储位置
所有研究资料（下载的 HTML、图片、PDF；`word_only` / `feishu_sync` 模式还包括最终生成的 Word 文档）默认存储在当前目录下的子文件夹中。向用户确认：
- **默认文件夹名称**：`<模型名称>_竞品分析_<YYYYMMDD>`（例如 `Doubao-Seed-2.0_竞品分析_20260511`）
- **默认位置**：当前工作目录下
- 询问用户是否同意这个文件夹名称和位置，或者是否想要自定义

### 4. 确认飞书同步目标与权限（仅 `feishu_sync`）

在任何飞书写入前，必须完成只读预检并向用户回显：

- **目标父级文档**：文档 URL 或 `docx token`；
- **目标 Wiki 父节点**：启动确认时可提供 Wiki URL；写入 manifest 前必须回读并保存 canonical `parent_node_token`，完成态不能只保存 URL；
- **厂商章节关键词**：用于定位目标厂商章节；
- **本次修改范围**：目标 A、B、C 是否全部执行，以及是否允许修改历史条目；
- **权限结果**：用户身份不是 bot，并具备 Docx 读写、图片媒体读写、嵌入式 Sheet 所需读写权限，以及 Wiki 节点创建 / 移动权限。

如果目标文档、Wiki 父节点、厂商章节或必要权限无法确认，必须在写入前停止，报告具体缺失项；不得回退到本文件、示例 manifest 或脚本默认值中的固定 token。只读预检通过后，才可以建立写入 manifest 并执行目标 A / B / C。

### 确认问题示例

使用当前运行时可用的用户输入机制同时询问以上问题，例如：

```
请确认以下信息：

1. **模型名称**：请确认要分析的模型全称（例如 "Doubao-Seed-2.0-lite"）
2. **微信文章链接**：如果有该模型的微信公众号官方发布文章，请提供链接。微信文章的自动搜索和抓取有较大限制，直接提供链接能确保获取完整的官方宣发内容。没有可跳过。
3. **存储位置**：研究资料将存储在 `./Doubao-Seed-2.0-lite_竞品分析_20260511/` 文件夹中，是否同意？或请指定其他位置。
4. **飞书同步目标与权限（仅 feishu_sync）**：请确认目标父级文档、Wiki 父节点、厂商章节关键词，以及当前用户是否具备文档、图片、Sheet 和 Wiki 节点所需权限。
```

确认完毕后，创建研究文件夹，然后进入正式工作流程。

## 研究资料存储

所有下载和生成的文件统一存放在确认后的研究文件夹中，结构如下：

```
<研究文件夹>/
├── images/          # 下载的图片（官网截图、benchmark 图表、KOL 截图等）
├── html/            # 下载的网页 HTML 文件
├── pdf/             # 保存的网页 PDF
└── <模型名称>_竞品分析_<YYYYMMDD>.docx   # 仅 word_only / feishu_sync 生成
```

在第一阶段开始前，先创建文件夹结构：

```bash
mkdir -p "<研究文件夹>/images" "<研究文件夹>/html" "<研究文件夹>/pdf"
```

## 工作流程

按以下阶段执行。运行时明确允许并行研究时可拆成独立子任务，否则顺序执行。

### 第一阶段：发现与下载

所有下载的文件存入研究文件夹对应的子目录中（HTML → `html/`，图片 → `images/`，PDF → `pdf/`）。

1. **找到官方发布页面。** 如果当前项目或运行时配置了可读取的官方发布来源登记表，先使用并记录其实际路径；没有登记表时，用当前环境的公开网页搜索能力查询 `"<公司> <模型> 官方发布公告"`。如果用户已提供微信文章链接，直接用。任何登记表缺失都不能回退到 `~/.claude/...` 等固定私人路径。
2. **判断 URL 类型并选择抓取策略。** 根据 URL 域名选择合适的抓取方式（见下方"中国网站抓取策略"）：
   - **普通网站**（英文博客、官网等）：使用当前环境的公开 URL 读取能力。
   - **中国平台**（微信公众号、知乎、微博、B站等）：使用只读 curl + 移动端 UA 或当前环境可用的浏览器抓取；被反爬机制拦截时记录失败，不自动安装或绕过访问控制。
3. **抓取完整文章文本。** 提取：
   - 完整文章文本
   - 所有图片 URL（主图、基准测试图表、散点图、评估图表 — 跳过公司 logo 和小图标）
4. **下载或生成证据图。** 根据图片来源选择下载方式（见下方"中国平台图片下载"）。图片保存到 `<研究文件夹>/images/`，优先使用 `<模型>-capability-*.png`、`<模型>-benchmark-*.png`；只有用户明确要求时才使用 `<模型>-hero.png`。
5. **将网页保存为 PDF。** 保存到 `<研究文件夹>/pdf/`。优先使用当前运行时已有的浏览器 / PDF 能力；使用本地无头浏览器时，先解析实际可执行文件为 `<browser_executable>`，不得假定 macOS Chrome 固定路径。没有可用工具时记录阻塞，不自动安装 `wkhtmltopdf` 或浏览器。对于微信文章，使用移动端 User-Agent（见下文）。
6. **验证下载。** 检查文件大小（`ls -lh`），验证图片（`file`）；任何小于 100 字节、返回 404 或无法验证的文件都标记为 `rejected` 并记录原因，不删除原文件。
7. **读取每张下载的图片**，使用当前运行时的视觉读取能力理解图表内容（坐标轴标签、数据点、对比模型名称）。记录关键数据点用于备忘录。
8. **网上官方的、KOL 的和合作品牌的 social media 宣发证据** 必须检索。优先截官方 X post（包括正文、发布时间、互动数据和前几条关键评论），再截 KOL 或合作品牌帖子；如果因登录墙、地区限制或页面不可读无法截图，必须保留帖子 URL，并在 manifest 的 `screenshot_candidates[]` 标记 `manual_screenshot_required`，不能把“找到 URL”写成“截图已完成”。
   - 默认优先级固定为：能力 / benchmark 证据图 -> 知识工作、视觉或科学能力图 -> 可选 API / 定价局部图。官网首页首屏 / hero 不是默认交付物，只有用户明确要求时才截取。
   - benchmark / capability 图作为正文证据主图；若官方没有适合嵌入的图表，可基于已核对事实生成紧凑能力图，但不得把整理图写成官方截图。
   - 截图必须裁掉滚动条、浏览器边框和大块空白；如果裁剪后文字仍不可读，重新截图或下载原图，不能交付模糊证据。
   - 父级总表文案要参考同类条目（例如 K2.6、Opus 4.7）的颗粒度，优先用“核心能力 / 关键数据 / 评测 / 社媒 / 参考文献”的短结构，不写成长篇解读。
   - 子页图注只保留短标签（如“Benchmark：编码与 Agent”“Benchmark：知识工作与视觉”“定价”），不要写“这张截图”“官方 hero 主视觉与 CTA”这类解释句。
9. **官网上的 system card** 如果模型有 system card 的话，也请下载。

### 中国网站抓取策略

中国平台（微信公众号、知乎、微博、B站等）常有反爬机制。通用 URL 读取工具可能返回验证页面或连接被重置，必须检查实际响应内容。以下是候选抓取策略，不保证在所有运行时可用：

#### 微信公众号文章（mp.weixin.qq.com）

**注意：Chrome 无头模式对微信可能返回 ERR_CONNECTION_RESET，不可靠。优先使用 curl。**

**方法一（推荐）：curl + 移动端 UA 下载 HTML，然后用 Python 解析：**

```bash
# 第一步：下载完整 HTML
curl -s -L \
  -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  -H "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8" \
  -H "Referer: https://mp.weixin.qq.com/" \
  "<微信文章URL>" \
  -o "<研究文件夹>/html/wechat-article.html"
```

```python
# 第二步：用 Python 解析提取标题、正文、图片URL
import re

with open('<研究文件夹>/html/wechat-article.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 检测是否被拦截
if '环境异常' in html or '完成验证' in html:
    print('被拦截，需尝试其他方法')
else:
    # 提取标题
    title_match = re.search(r'id="activity-name"[^>]*>(.*?)</h1', html, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ''

    # 提取公众号名称
    author_match = re.search(r'id="js_name"[^>]*>(.*?)</a', html, re.DOTALL)
    author = author_match.group(1).strip() if author_match else ''

    # 提取图片URL（微信用 data-src 懒加载，注意 &amp; 需解码为 &）
    imgs = re.findall(r'data-src="(https://mmbiz\.qpic\.cn[^"]+)"', html)
    imgs = [img.replace('&amp;', '&') for img in imgs]

    # 提取正文文本
    content_match = re.search(r'id="js_content"[^>]*>(.*?)</div>', html, re.DOTALL)
    if content_match:
        text = re.sub(r'<[^>]+>', '', content_match.group(1))
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'\s+', ' ', text).strip()
```

**方法二（备用）：已安装的无头浏览器保存为 PDF**（如 curl 被拦截时尝试）：

```bash
"<browser_executable>" \
  --headless --disable-gpu --no-sandbox \
  --user-agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1" \
  --print-to-pdf="<研究文件夹>/pdf/<模型>-wechat.pdf" --print-to-pdf-no-header \
  "<微信文章URL>"
```

如果 PDF 只有1页且内容为 "This site can't be reached"，说明 Chrome 无头模式无法连接，回退到方法一。

#### 微信图片下载（mmbiz.qpic.cn）

微信图片有 Referer 防盗链。下载时必须设置空 Referer：

```bash
# 空 Referer 下载（已验证有效）
curl -s -o "<输出文件>.png" -H "Referer:" "<mmbiz.qpic.cn完整图片URL>"
```

**关键注意事项：**
- 图片 URL 必须是完整的，包含 `/640?wx_fmt=png&from=appmsg` 等参数，不能截断
- HTML 中的 `&amp;` 必须解码为 `&` 后再用于 curl
- 微信 CDN 图片 URL 有时效性（数小时到数天），发现后应立即下载
- 下载后用 `file` 命令验证图片格式；小于 100 字节的无效文件只标记为 `rejected` 并记录原因，不删除原文件

#### 知乎（zhihu.com）

知乎需要浏览器环境，但反爬比微信宽松：

```bash
# 已安装的无头浏览器；先确认 <browser_executable> 的真实路径
"<browser_executable>" \
  --headless --disable-gpu --no-sandbox \
  --user-agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  --print-to-pdf="<研究文件夹>/pdf/<输出>.pdf" --print-to-pdf-no-header \
  "<知乎URL>"
```

#### 微博（weibo.com）

微博公开内容可以用 curl + User-Agent 直接获取：

```bash
curl -s -L \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  "<微博URL>" \
  -o "<研究文件夹>/html/weibo.html"
```

#### 平台识别规则

| 域名 | 平台 | 抓取方式 |
|---|---|---|
| `mp.weixin.qq.com` | 微信公众号 | 只读 curl + 移动端 UA；必要时使用当前可用浏览器 |
| `zhihu.com` | 知乎 | 当前可用浏览器 + 桌面端 UA |
| `weibo.com` / `m.weibo.cn` | 微博 | 只读 curl + UA / 当前可用浏览器 |
| `bilibili.com` | B站 | 当前可用浏览器 + 桌面端 UA |
| `36kr.com` | 36氪 | 公开 URL 读取能力或当前可用浏览器 |
| `mp.toutiao.com` | 头条号 | 当前可用浏览器 + 移动端 UA |
| 其他国际网站 | — | 公开 URL 读取能力（优先） |

### 第二阶段：深度研究

收集以下信息；只有运行时政策明确允许或用户明确要求时，才拆给子代理并行执行：
- **KOL / 意见领袖反应**：X、Reddit、微博、知乎
- **Arena / Chatbot Arena / LMArena 排名**
- **OpenRouter 排行榜位置**
- **竞品对比**（价格、基准测试、定位）
- **与前代对比**（相比上次发布有什么变化）
- **架构细节**（参数量、MoE vs 稠密架构，如已知）

### 第三阶段：生成 Word 文档

使用已安装的 `python-docx` 创建结构化的 `.docx` 文件。如果依赖不可用，停止 Word 生成并报告缺失依赖；只有用户明确授权后，才能在项目约定的环境中安装依赖。

### 第四阶段：三目标同步（更新汇总页时强制执行）

在 `feishu_sync` 模式下，这次任务不是只生成 Word。必须完成下面三个目标；任何一个没有完成，都不能回复“已更新”。

#### 目标 A：父级汇总页里的厂商 / 模型独立栏

在已通过只读预检的 `<verified_parent_wiki_node>` 下，找到对应厂商的独立章节，再找到本次模型的日期条目。以用户给的 Gemini 示例为准：

```text
3. Google DeepMind (Gemini)
厂商画像：……

【2026/02/19】Gemini 3.1 Pro
详细追踪 -> 【2026/02/19】Gemini 3.1 Pro：Google 在编码推理上的反攻
核心判断：……
硬参数速览：……

官方 benchmark 对比图
要点总结：……

SVG 动画生成
[截图]
ISS 遥测仪表盘
[截图]
3D 椋鸟群飞模拟
[截图]
“呼啸山庄”作品集
[截图]
```

必须更新或补齐：

#### 父级模型条目的固定模板（硬规则）

父级汇总页的每个新模型条目统一按下面顺序写，保持短句、分组和换行，不要把所有内容压成一段长文。**结构必须是“标题 -> 详细追踪 -> 主能力两列 grid -> 宣发/社媒标题 -> 社媒两列 grid”，不能把核心能力、关键参数、测评或社媒内容平铺成根文档 bullet，也不能把宣发内容塞回主能力 grid。**

```text
【YYYY/MM/DD】<模型名>
详细追踪 -> 【YYYY/MM/DD】<模型名>：<一句话主题>

左列：
核心能力：
- <能力方向 1>：<读者能理解的能力变化>
- <能力方向 2>：<产品 / 交付价值>
- <能力方向 3>：<长程任务、Agent、视觉、办公或创意能力>

展示的 Case：
- Demo 1 · <Case 名>：<任务规模 / 迭代轮数 / 结果指标>
- Demo 2 · <Case 名>：<任务规模 / 迭代轮数 / 结果指标>
- Demo 3 · <Case 名>：<没有数值时写清交付物和主观任务难点>

右列：
关键参数：
- <参数量 / 激活参数 / 架构>
- 上下文窗口：<值>
- 模态：<值>
- 发布方式：<开源协议 / 闭源 / Preview>
- 其他关键限制或价格：<值>

测评（<比较范围，例如开源权重组>）：
- <评测类别>：<排名 / 相对定位>
- <评测类别>：<关键分数和对手对比>
- <工程级 / Agent / 视觉 / 交互评测>：<结论>

官方 benchmark 对比图（右列测评末尾，短图注 -> 图片）

根级文本标题：宣发/社媒

社媒两列 grid：
左列：
<渠道、外部背书、社区传播方式和声量判断，2-4 句>

网页：
- 开发者 Doc：<URL>
- 博文：<URL>
- X 官宣：<URL>

右列：
<一张完整官方社媒帖截图；保留作者、正文、配图、发布时间和互动区>
```

执行要求：核心能力写“能力方向 + 价值”，展示 Case 写“任务 + 过程 + 结果”；有指标就给指标，没有指标就明确交付物和迭代过程。测评部分优先按编码 / Agent / computer use / 知识工作 / 视觉 / 交互分类，并写相对定位，不要只堆分数。主能力 grid 只放能力、Case、参数、测评和 benchmark 图；benchmark 图位于右列测评末尾，最大 `600x300`。`核心能力`、`展示的 Case`、`关键参数`、`测评` 和 benchmark 图注是普通正文中的加粗标签，不能生成 `Heading 1/2/3`；父页只有厂商标题使用 `Heading 2`、模型条目标题使用 `Heading 3`。社媒 grid 左列必须有传播判断、`网页` 和至少两个可点击 URL，右列必须恰好一张经过视觉验收的完整社媒帖截图；推荐接近 GLM 5.1 的 `603x859`，硬上限 `720x1000`。所有图片都在表格外。详细子文档可以继续使用两列能力 grid，但不得把父页模板误写成“平铺 bullet + 单独大图 + 另一组 grid”。

#### 父级 benchmark 图完整性合同（硬规则）

- 父级模型条目只能采用：`标题 -> 详细追踪 -> 主能力两列 grid -> 宣发/社媒标题 -> 社媒两列 grid`。benchmark 图必须位于主 grid 的右列、测评文案末尾；社媒图必须位于社媒 grid 的右列。不得另起根级图片块，也不得把图片放进表格。
- 只要官方图是多行 benchmark / Arena 对比表，最终图片必须同时看见表头、第一行、最后一行，以及表格自带的 methodology / footnote（如果存在）。不得只截首屏或顶部几行。
- 截图来源优先级为：官方原始 PNG / SVG / PDF 图表 > 官方网页元素完整截图 > 整理图。网页表格跨越视口时必须用 full-page 截图，逐个查看纵向切片后再定位完整边界；禁止把某一个切片直接当最终证据图。
- 裁剪只允许去掉导航、正文标题、页脚和大块空白；不得为了满足尺寸上限而裁掉数据行、列、表头或脚注。尺寸不合适时按原比例缩放，宁可让窄表变窄，也不能改变内容完整性。
- **完整证据优先于局部截图。** 只要局部裁图会留下半截标题、上一行 / 下一行残片、缺失坐标轴 / 图例 / 首尾行、右侧侧栏窄条，或让文字不可读，就立即放弃该裁图。优先换官方原图；拿不到可独立使用的原图时，直接使用完整网页、完整文章或完整当前帖子截图，禁止继续硬裁。
- **产品定位图必须是完整逻辑区块。** 如果正文使用官网发布页证明产品定位，截图至少同时保留该区块的标题、模型名 / 主视觉、定位正文和该段结尾；不能从标题下方或正文中间开始，也不能在下一段逻辑尚未结束时截断。无法得到干净区块时，直接保留完整网页或足够长的连续页面截图。
- 本地验收必须用当前运行时的视觉读取能力打开最终裁图，明确确认“第一行是什么、最后一行是什么、共保留多少行”。如果看不到最后一行或 methodology，状态只能是 `pending`，不得上传。
- 飞书上传后必须回读 image block 的真实 `width` / `height`、`parent_id` 和前一个 sibling。确认图片在右列、图注紧邻前置、图片不在 table / table cell，并删除旧的半截图片块；只看上传 API 成功不算完成。

#### 读者正文与执行备注隔离（硬规则）

- 飞书正文只写读者需要的事实、判断、限制、来源和可执行建议。截图选择、图片落点、章节安排、模板对照、validator、manifest、block ID、OAuth、后续补图等内容只能留在本地日志和 manifest，不能进入正文。
- 禁止把“怎么写 / 怎么排 / 怎么截”的过程句写成读者内容，例如“下面使用完整发布页逻辑区块”“把具体榜单放到 Benchmark 逐项拆解”“避免用一张总览图代替能力分析”“不再使用截断截图”“应写成…… / 不能写成……”“普通截图不纳入 Demo 证据”。
- 需要表达同一结论时，改写成直接事实或判断：例如“速度是该模型最明确的优势”“该成绩处于中上位置”“完整发布材料显示其产品定位是……”。不要解释 Agent 为什么选择了某张图或某种排版。
- 写入前先对所有 `b.text_block`、`b.paragraph`、`b.bullet` 和父级文案做一次读者视角审计；写入后必须运行 child validator，并确保 `reader_text_hits: []`。命中任何内部话术时，目标 C 仍是未完成，禁止向用户报告已更新。

- 厂商画像：只有在本次发布确实改变厂商叙事时才改；不要每次重复改写旧画像。
- 日期、模型名称、详细追踪链接、核心判断、硬参数速览。
- 官方 benchmark / Artificial Analysis / Arena 等事实和相对定位。
- 发布页展示的每一个重要 Demo / Case。页面明确展示的 SVG 动画、ISS 遥测仪表盘、3D 椋鸟群飞模拟、《呼啸山庄》作品集等，不能只写文字后跳过截图。
- 截图必须插在对应更新文案的下面，不能插进表格单元格，也不能只放在文末让读者猜对应关系。父级模型条目中的 benchmark 图固定放在右列测评末尾；子文档中的能力图按对应小节放置。
- 父级汇总页的视觉 Part 固定使用一行两列 grid；独立子文档按 GPT-5.5 模板分层：开场证据墙四列、能力 Case 通常两列、发布过程 / 合作伙伴 / 社区反馈允许三列。不要把四张图拼成一张长图。
- **标题级别必须按真实 block tree 使用。** `block_type: 3/4/5` 分别代表 Heading 1/2/3；先按 `parent_id` 和根级 `children` 回读标题树，再判断层级，不能把扁平的 block 列表当成同一级内容。根级主章节使用 Heading 1，章节内真正的能力 / 发布小节使用 Heading 2；Heading 3 只有在存在真实三级内容时才允许，不能直接挂在文档根级。产品定位、生态承接、Case 名、官方 benchmark、`Benchmark：质量与 token 效率`、AA 榜单名、图注和三列区块标签都使用加粗普通正文，尤其不能在 grid / column 内创建 Heading block。写入后必须同时回读根级标题树和所有 grid 后代，确认没有错误升级的 H2/H3。
- 默认展示模型能力和 benchmark 证据，不把官网整页截图当首选。优先使用清晰的 benchmark / capability chart；但如果无法得到完整、清晰、无残片的局部证据，就使用完整网页或完整当前帖子，完整图优先于劣质裁图。如果官方没有适合嵌入的图表，可以基于已经核对过的数据整理能力图，但必须标明“根据已核对数据整理”，不得凭空补分或伪装成官方截图。

#### 目标 B：父级汇总页中的所有相关表格

父级文档里的表格不是装饰。每次模型更新前先完整盘点所有表格：记录表格 block ID、表头、行内容、涉及的厂商 / 模型、最后更新时间。逐表判断本次发布是否影响它。

- 影响到的表格必须更新：模型名、发布时间、上下文、价格、能力标签、排名、接入状态、最新模型列等，按表格已有列填入。
- 发布时间必须逐行核对，不能只检查本次新增模型。以官方首次公开发布时间为准，并统一换算为北京时间自然日；禁止用月初占位（如 `2025/09/01`）、季度文本、文章补发 / 修改日期或“约在某月”冒充精确发布日期。跨时区导致日期不同的，在 manifest 记录原始时区和换算结果。
- 嵌入式 Sheet 的日期列必须写入真实日期值，并统一设置 `yyyy/MM/dd` formatter；禁止混入 `2025 Q3`、`2026 年 4 月`、`4/17 出现、4/20 官宣` 等说明性文本。发布过程说明放到要点列，不占用日期单元格。
- 写入后重新读取全部厂商 Sheet 的完整日期列，与 manifest 中的模型日期映射逐行比较。只有 `checked_rows` 覆盖全部非空模型行且 `remaining_mismatches: 0`，日期更新才算完成。
- 只更新事实，不把长篇分析塞进表格；长判断放在模型独立栏下面。
- 表格单元格内只放文本、数字或短链接，**禁止放截图**。截图统一放在对应更新文案之后。
- 本次没有变化的相关表格，也要在本地更新 manifest 中写明“已检查、无变化、原因”，不能因为没改就跳过盘点。
- 不要新增一个重复表格来逃避更新原表；除非原表结构确实无法表达新字段，并在汇总页说明原因。

#### 表格类型判断（硬规则）

飞书文档不是 MDX；Markdown 只是读写普通文档内容时的中间表示。盘点 block 时必须区分：

- `block_type: 31`：普通文档表格。内容属于 docx block 树，按文档 API 读取和更新，不需要 Sheets 权限。
- `block_type: 30`：嵌入式飞书电子表格。内容不在文档 Markdown 中，必须使用 Sheets API 读取和更新；不能因为文档正文里只显示一个表格占位块，就把它当成普通表格或跳过。

嵌入式 Sheet 的 `block.sheet.token` 可能是复合引用 `<spreadsheet_token>_<sheet_id>`。更新前先按最后一个 `_` 拆分，分别调用 spreadsheet metadata、sheet query 和 values API，确认真实工作表及有效范围；保留已有行，不重排旧模型。写入后必须回读单元格，并检查日期格式、链接、换行和行高是否继承原表样式。遇到 Sheets 权限错误，目标 B 必须标记为未完成，不能用“文档正文已更新”代替表格更新。

#### 目标 C：父级 Wiki 目录旁的独立模型文档

每个模型的详细追踪文档必须放在父级汇总 Wiki 的相邻 / 子级 Wiki 目录中，不得只生成一个落在“我的空间”根目录的孤立 docx。

- 开始写目标 C 前必须读取 `references/CHILD-DOC-TEMPLATE.md`。GPT-5.5 参考页和用户确认的四张截图是唯一模板；其他模型子文档只能用于发现待修问题，不能当作排版参照。默认阅读路径为：`读者摘要 callout -> 四列开场证据 -> 基本信息 -> 按真实能力拆分的 Case -> 条件性安全 / Token 效率 -> Benchmark -> 发布目标与对比表 -> 官方发布与外部反馈 -> 社区 Demo -> MiniMax 可以借鉴的 -> 返回链接`。
- 子文档不是父页五块结构的放大版。父页负责短摘要；子文档负责完整竞品拆解、发布策略、外部证据和可借鉴点。
- 独立子文档必须继承 GPT-5.5 参考页的完整阅读路径和分析密度。四列、两列和三列只是对应内容的排版方式，不能反过来为了凑版式制造内容；父页的紧凑尺寸和两列规则不得套到子文档。
- **模板名、执行规则和验收提醒不得写入可见正文。** 禁止出现“规范化摘要（按 GPT-5.5 子文档模板）”“优先保留……”“社区反馈按……”“后续继续补……”等写给 Agent 的元说明。模板只约束结构，读者看到的必须是该模型的事实、判断和证据。
- **正文与内部工作区必须彻底分离。** `update-manifest.json`、截图清单、模板对照、校验结论和“应该怎么写/怎么截/怎么分类”的说明只留在本地文件。飞书正文的标题、图注、callout 和表格只能写读者需要的事实、判断、来源和限制；任何一句话如果是在指导下一位 Agent，而不是帮助读者理解模型，就不得上传。
- **禁止用生成式摘要卡或占位卡充当能力 / Case 截图。** “核心能力”“展示 Case”这类程序生成卡片只能用于内部草稿，写入飞书前必须替换为官方 benchmark、真实任务结果、产品输出或可核对的外部评测图。
- 三列发布 / 社区区块是语义分栏，不是图片配额。某列只有可靠文字证据时就保持纯文字；只有拿到与该列内容直接对应的官方、客户或社区证据时才放图，禁止为了“每列有图”塞普通转发、无关 benchmark 或重复 Demo。不得同时保留整页长截图和其紧凑裁图。
- **一图只证明一个紧邻结论。** 上传前必须实际打开图片，逐项核对模型名、指标名、图例、首尾行、作者、时间和结果是否完整可见。图中看不出图注所声称的内容，或需要靠 Agent 的背景知识才能解释对应关系，视为错图，必须替换。
- **开场证据墙不是重复图片缓存。** 四张图在后文用文字展开，但同一图片文件不得再次插入能力、Benchmark、社媒或 Demo 区。正文内发现相同图片 token、相同像素内容或仅缩放后的重复图，校验必须失败。
- **不可读图片不能通过。** 明显缩成缩略图、关键文字无法辨认、只截到表格中段、漏掉坐标轴/图例/模型名、社媒帖缺作者/正文/时间，或包含大面积无关网页区域，都按缺图处理，不能用“已上传”代替视觉验收。
- Benchmark 小节固定使用两列：左列写分类测评和相对定位，右列放一张完整 benchmark 图；发布过程必须包含一张“上一代 / 主要竞品 vs 本次发布”的对比表。
- 社区 Demo 没有高质量材料时保留该标题并写“暂无高质量外部复现”，不能拿普通转发或无结果截图凑数。
- 先查找同一模型的既有 Wiki 子文档；有则更新原文档，没有才在正确的 Wiki 父节点下新建。
- 父级节点下所有标题以 `【YYYY/MM/DD】` 开头的模型子文档，必须按标题日期从新到旧排列。每次创建或更新子页后都重新检查全部同级子页；同一天的页面保留调整前的相对顺序，不按修改时间排序，不删除、合并或借排序处理重复页面。
- 排序完成后必须重新读取全部同级节点，逐项确认日期单调递减、节点数量未变、每个 node token 仍存在。Wiki 节点移动需要知识库目录管理权限；普通文档编辑权或重复授权不能替代。权限不足时明确报告缺少的是 Wiki 空间管理员 / 节点管理权限。
- 新建前确认标题格式：`【YYYY/MM/DD】<模型>：<一句话主题>`。
- 独立文档必须包含：核心判断、硬参数、能力与 Case、benchmark、宣发对比、KOL / 社媒证据、官方链接、截图。
- 独立文档中的重要证据图也必须真实插入；默认至少包括编码 / Agent benchmark 和知识工作、视觉或科学能力中的一组。首页 / 发布主视觉、定价或 API 截图只有在用户明确要求或该信息无法用正文准确表达时才加入。所有图放在对应小节下面，不放进对比表格。
- 写完回读 Wiki 节点和文档 block，确认它确实位于已确认的 Wiki 目录，并把链接写回父级模型栏。必须分别保存 `node_token`、`obj_token` 和 `parent_node_token`：validator 的 `--parent-node` 只能传 API 回读得到的 `parent_node_token`，不能误传当前子页自己的 `node_token`。示例中的子页 token 和父节点 token 只用于说明字段关系，实际值必须来自当前目标的 API 回读。
- 文末“返回汇总页”必须是可点击的 `text_run` 链接或 `mention_doc`，只把 URL 作为普通文字粘贴不算完成。
- 写完必须运行 `python3 scripts/validate_child_document.py --helper <feishu_helper.py> --doc <child_doc_or_wiki_token> --parent-node <actual_parent_node_token>`；只有 `status: pass` 且 `violation_count: 0`，目标 C 才能标记为完成。
- 如果当前工具没有创建 Wiki 子节点或上传图片的能力，必须明确报告“C 未完成”的原因，不能用本地路径冒充已归档。

#### 三目标同步的固定顺序

1. **只读盘点 + 强制结构审计**：读取 `sync_target.parent_doc` 的全文和 block 列表；列出厂商章节、模型条目、全部相关表格、已有图片、已有独立 Wiki 子文档。随后运行 `python3 scripts/validate_vendor_section.py --helper <feishu_helper.py> --doc <sync_target.parent_doc> --vendor "<sync_target.vendor_heading>"`。审计范围是整个厂商章节，不是只有本次新增模型；初次审计允许还没有 manifest，因此只判结构和尺寸。
2. **建立更新 manifest**：在研究文件夹保存 `update-manifest.json`，至少包含 `sync_target`、`target_status`、`parent_section`、`related_tables`、`screenshots`、`child_wiki_doc`、`verification`；模型条目写在 `parent_section.model_entry` 中，目标 A/B/C 状态分别写在 `target_status.A/B/C`。
3. **先准备事实和截图**：完成资料抓取、图片下载、截图验证，再写 Word 和飞书，避免先写半成品。
4. **更新目标 A**：改厂商 / 模型独立栏，文案后立即插入对应截图。
5. **更新目标 B**：逐个更新相关表格，图片不进表格。
6. **更新目标 C**：先读取 `references/CHILD-DOC-TEMPLATE.md`，再更新或创建正确 Wiki 目录下的独立模型文档，插入同一批经过验证的关键截图和发布对比表。
7. **回读验收**：重新读取父级文档和子文档，核对标题、日期、表格单元格、图片 block、子文档位置和相互链接；先使用已确认的 `--helper <feishu_helper.py>` 运行 `scripts/validate_child_document.py`，再运行带 manifest 的 `scripts/validate_vendor_section.py`。将两个 validator 的原始 JSON 输出分别保存后，分别运行 `python3 scripts/record_validator_result.py --manifest <研究文件夹>/update-manifest.json --validator child --result-file <child-validator-output.json>` 和 `python3 scripts/record_validator_result.py --manifest <研究文件夹>/update-manifest.json --validator vendor --result-file <vendor-validator-output.json>` 写回 manifest，不要手工改写 `status` 或 `violation_count`。
8. **最终完整门禁**：在两个远端 validator 结果已经写回 manifest 后，最后运行 `python3 scripts/validate_update_manifest.py --manifest <研究文件夹>/update-manifest.json --require-complete`。只有 manifest、目标厂商和子文档均通过，且每个返回 `status: pass` 与 `violation_count: 0`，才能报告合规。若历史条目仍失败，必须一起迁移，或明确报告整个厂商章节仍未完成；不能因为本次新增条目写对了就说“这一栏没问题”。

#### 三块同步的硬性完成条件

- 目标 A、B、C 必须分别有 `target_status.A/B/C`，不能用一个总状态代替。
- `target_status.A/B/C` 必须与对应的 `parent_section.status`、相关表格状态和子文档 validator 结果一致；不能只把顶层状态写成 `complete` 来绕过证据检查。
- 目标 C 的 `status` 必须来自子文档 validator 的实际回读结果，不能只凭写入 API 成功。
- 每个 `screenshots[]` 项必须同时填写 `parent_placement` 和 `child_placement`；任一落点为空，该截图视为未完成。
- 每个重要 Case 必须有独立的 `case-*` 截图记录；一张总览图不能替代多个 Case。
- 父级模型栏中的截图必须紧跟对应的 Case / benchmark / 定价文案；独立子文档中的同一截图必须紧跟对应小节。截图放在表格外。
- 相关表格必须逐个写出 `updated` 或 `checked_no_change`，不能只写“已检查表格”。
- 回读必须确认实际的图片 block 数、表格单元格内容、子文档父节点和父子链接；只检查 API 返回成功不算验收。

#### 更新 manifest 最低格式

`update-manifest.json` 是 `feishu_sync` 模式的机器可读验收清单，不是读者正文。下面的字段合同必须统一遵守：

- 顶层必填：`sync_target`、`target_status`、`parent_section`、`related_tables`、`screenshots`、`child_wiki_doc`、`verification`；未上传的截图候选另放在可选的 `screenshot_candidates`，不能混入 `screenshots[]`。
- `sync_target` 必须记录已回读的 `parent_doc`、canonical `parent_wiki_node`、`vendor_heading`、本次 `scope` 和 `permission_preflight`；用户提供的 Wiki URL 只能作为预检输入，预检未完成时状态只能是 `pending`，不得写入。
- `target_status` 必须分别记录目标 A、B、C 的状态，不能用一个总状态代替；进入 `--require-complete` 前三项都必须是完成状态，并且必须分别与父级栏、相关表格、独立子文档的实际状态一致。
- `parent_section` 必须有 `wiki_node`、`vendor`、`model_entry` 和独立 `status`；该状态不能代替 `target_status.A/B/C`。
- `related_tables[]` 必须逐表记录 `block_id`、`header`、`reason` 和 `status`；准备阶段允许使用 `pending` / `blocked` / `failed`，但进入 `--require-complete` 前每一项只能是 `updated` 或 `checked_no_change`。涉及完整日期核对时，还要记录非负整数 `checked_rows` 和 `remaining_mismatches`，完成时后者必须为 `0`。
- `screenshots[]` 只记录已经上传或已经产生实际 block 的截图。每项必须有 `id`、`kind`、`source_class`、`source_url`、`source_section`、`source_original`、`method`、`local_path`、实际 `image_block`、`caption`、`caption_block`、`caption_before_image`、`display_width`、`display_height`、`size_policy`、`template_reference`、`parent_placement`、`child_placement`、`visual_check` 和 `status`。不得使用临时 ID、空的 image block 或“已上传”文字。
- `visual_check` 至少记录 `status` 和 `verification_method`；社媒截图还必须明确记录 `login_wall: false`、`blank: false`、`complete_post: true`；Artificial Analysis 截图至少必须明确记录 `blank: false`。这些字段必须反映实际 `view_image` 检查，不得只凭脚本返回值填写。
- Artificial Analysis 截图必须使用 `source_class: independent_benchmark`，来源 URL 必须是 `artificialanalysis.ai`，每个模型至少两项且 `source_section` 不同；每项必须有真实 `image_block`、`local_path`、`child_placement` 和已验证的 `visual_check`。
- 如果截图尚未上传或被登录墙阻塞，只能写入 `screenshot_candidates[]`，记录 `id`、`source_url`、`reason` 和 `status: manual_screenshot_required` 或 `pending`；候选记录不能被 validator 当作已完成截图。
- `child_wiki_doc` 必须记录 `parent_node`、`node_token`、`obj_token`、`parent_node_token`、`title` 和独立 `status`；`parent_node` 与 `parent_node_token` 必须保存 API 回读的真实父节点 token，不能只填 Wiki URL。
- `verification` 必须记录父页、表格、截图、子文档回读状态，并保存两个 validator 的实际 `status` 和 `violation_count`；未运行时不能写 `pass`。
- `scripts/validate_update_manifest.py` 会在本地强制检查上述字段合同和目标状态交叉一致性，但不会访问飞书确认 block 是否真实存在；`validate_child_document.py` 和 `validate_vendor_section.py` 仍必须通过真实回读完成远端验收。不能因为本地脚本通过就省略字段或跳过 API 回读。

#### 校验器回归测试（维护 Skill 或校验脚本时）

修改 `scripts/validate_update_manifest.py`、`scripts/record_validator_result.py`、manifest 字段合同或相关校验逻辑后，必须在项目根目录运行：

```bash
python3 scripts/run_local_validation.py
```

该一键命令会执行 AST 语法检查、全部 Python 回归测试和全部本地 / 远端 validator 的 `--help` 合同检查；只使用 Python 标准库和临时文件，不访问飞书、不联网，也不写入 Python 字节码缓存。全部步骤通过后，才可把本地校验器改动视为可交付。回归测试不能替代真实飞书 API 回读和两个远端 validator。

```json
{
  "sync_target": {
    "parent_doc": "<verified_parent_doc_token>",
    "parent_wiki_node": "<verified_parent_wiki_node>",
    "vendor_heading": "<verified_vendor_heading>",
    "scope": ["A", "B", "C"],
    "permission_preflight": {
      "identity": "user_access_token",
      "docx_read_write": false,
      "media_read_write": false,
      "sheets_read_write": false,
      "wiki_node_manage": false,
      "status": "pending"
    }
  },
  "target_status": {
    "A": "pending",
    "B": "pending",
    "C": "pending"
  },
  "parent_section": {
    "wiki_node": "<verified_parent_wiki_node>",
    "vendor": "Google DeepMind (Gemini)",
    "model_entry": "【2026/02/19】Gemini 3.1 Pro",
    "status": "pending"
  },
  "related_tables": [
    {
      "block_id": "<verified block id>",
      "header": ["模型", "发布时间", "上下文", "价格"],
      "reason": "本次发布影响价格和上下文",
      "status": "pending"
    }
  ],
  "screenshots": [],
  "screenshot_candidates": [
    {
      "id": "model-aa-overview",
      "source_url": "https://artificialanalysis.ai/",
      "reason": "待获取模型总览截图并完成视觉验收",
      "status": "pending"
    },
    {
      "id": "model-aa-breakdown",
      "source_url": "https://artificialanalysis.ai/",
      "reason": "待获取榜单分解截图并完成视觉验收",
      "status": "pending"
    },
    {
      "id": "model-social-official",
      "source_url": "https://example.com/official-social-post",
      "reason": "待获取完整社媒帖截图；若遇登录墙则人工补图",
      "status": "manual_screenshot_required"
    }
  ],
  "child_wiki_doc": {
    "parent_node": "<verified_parent_wiki_node>",
    "node_token": "<actual child node token>",
    "obj_token": "<actual child document token>",
    "parent_node_token": "<verified_parent_wiki_node>",
    "title": "【2026/02/19】Gemini 3.1 Pro：Google 在编码推理上的反攻",
    "status": "pending"
  },
  "verification": {
    "parent_readback": false,
    "tables_checked": false,
    "screenshots_checked": false,
    "child_readback": false,
    "child_validator": {"status": "pending", "violation_count": null},
    "vendor_validator": {"status": "pending", "violation_count": null}
  }
}
```

### 截图合同：每张截图都要能回答“从哪里截、截什么、放哪里”

截图不是“尽量找”。对每个模型发布，先按下表建立截图清单；官方页面有对应内容就必须截图，没有才写“暂无”。

| 截图 ID | 去哪里找 | 截什么 | 截图方式 | 放置位置 |
|---|---|---|---|---|
| `capability-*` | 官方发布页 Benchmark / Evaluations / Demo 小节，或本地已核对数据 | 能让读者看懂模型能力的 benchmark / capability chart；无合适官方图时整理数据图 | 优先原图下载；否则用已验证的 selector 裁图或本地生成紧凑图，并通过当前视觉读取能力验证 | 对应 Part 文案下的两列 grid |
| `hero` | 官方发布页首页首屏 | 模型名、发布定位、核心口号或产品入口 | 仅用户明确要求时使用当前可用的网页截图能力截取首屏 | 模型更新文案下，不能替代能力图 |
| `benchmark` | 官方发布页 Benchmark / Evaluations 小节 | 对比表、雷达图、性能曲线、关键评测结果 | 优先原图下载；否则用已验证的 selector 裁图并完成视觉验收；也可整理为能力图，但要标明数据来源 | Benchmark 文案下的两列 grid |
| `pricing` | 官方 API / 定价页 | 输入输出价格、缓存价、上下文分档、渠道 | 优先裁定价表或下载原图 | 硬参数 / 商业化文案下 |
| `case-*` | 官方发布页每个 Demo / Case 小节 | 能力真实输出，而非纯海报 | 按每个 Case 单独截图；不要四个 Case 合成一张 | 对应 Case 文案下 |
| `safety` | system card / safety report / safety section | 安全评估图、风险分类、对齐结论 | 下载原图或裁对应图表 | 安全与对齐小节下 |
| `social-*` | 官方 X / 官方社媒、KOL 或合作品牌帖子 | 完整帖子：作者、正文、配图、发布时间、互动或关键评论 | 有登录态用浏览器截图；裁掉登录框、浏览器边框、大块空白和后续无关帖子，但不得截断当前帖子；无登录态截不到就保存 URL，禁止把登录墙当证据 | 父页模型条目“宣发/社媒”两列 grid 右列；子页 KOL / 宣发小节下 |

#### 每张截图的实际操作要求

1. **先锁定官方来源**：记录 URL、页面标题、页面小节名和截图理由；第三方文章只能作为线索，不能替代官方证据。
2. **静态页面**：只有需要截取官方局部证据时，使用当前运行时已提供且已确认可用的网页截图能力，输出到 `<研究文件夹>/images/<id>.png`；不得回退到 `~/.claude/...` 等固定脚本路径，也不要默认截官网整页。
3. **指定区域**：如确实需要网页证据，先确认页面结构，再用 `--selector` 裁 `main`、`article`、`table` 或已验证的 CSS 选择器；不要把整页截图作为默认交付物，也不要凭猜测写一个未验证的 selector。若 selector 无法完整覆盖当前证据，或裁后出现半截标签、数据缺失、侧栏残条和不可读小字，停止裁剪并改用完整网页 / 完整文章 / 完整当前帖子截图。
4. **原始图表优先**：页面里已有 PNG / SVG / PDF 原图时，下载原图并用 `file` 检查；不要把清晰图表重新截成模糊网页图。
5. **能力图优先**：父页使用紧凑图；子文档优先保留官方高分辨率原图，并按模板组织为四列开场证据墙、两列能力 Case 和三列发布 / 社区区块。若数据来自正文整理，图中和 manifest 中都要标明来源性质。
   - 子文档四列开场证据墙必须覆盖至少 3 类来源：官方网页 / 文档、官方社媒、GitHub / 模型仓库 / 生态接入、独立 benchmark / Arena / 模型市场、外部媒体 / KOL。
   - 同一张原始 benchmark 最多占一格。左右裁图、上下裁图、局部放大和完整表格仍算同一个来源，禁止用四个裁片制造“有四张图”的假象。
   - GitHub 证据必须直接出现模型名，并证明发布、集成、兼容、配置或真实使用；没有相关证据时不要强塞 GitHub，改用独立评测、模型市场、媒体或官方社媒。
   - 每格在 manifest 中记录 `source_class`、`source_url` 和 `source_original`。四格少于 3 类来源、复用同一原始 benchmark、或缺少来源元数据时，子文档校验必须失败。
6. **动态页面**：使用 `--wait 6000` 到 `--wait 10000` 或 `--wait-selector`；榜单和数据看板要等待数字真正出现。
7. **登录墙处理**：X、小红书、部分知乎页面如果只能看到登录框、骨架屏或空白，不算截图成功。保存 URL，并在 manifest 的 `screenshot_candidates[]` 标记 `manual_screenshot_required`；不要把候选记录编造成已完成截图。
8. **逐张视觉验收**：每张图都必须用当前运行时的视觉读取能力实际打开，确认不是登录墙、空白、骨架屏、浏览器边框、过度留白、右侧侧栏残条、上一行 / 下一行残片或不可读小字。只看脚本返回 `ok:true` 不算完成。任何局部图未通过时，必须退回完整页面截图，不能以“已上传”通过。
   - 开场四图还要逐张确认来源页面彼此不同或证据职责明确不同；404、注册弹窗、登录墙、无关仓库和裁断的 benchmark 一律淘汰。
   - 社媒帖额外确认：作者、正文、主配图、发布时间和互动区均可见；不能只截帖子上半段。manifest 的 `visual_check` 必须写 `status: verified`、`verification_method: view_image`、`login_wall: false`、`blank: false`、`complete_post: true`。
9. **命名和 caption**：文件名使用 `<model>-<screenshot-id>.<ext>`；图注写“Benchmark：编码与 Agent”“Case：长程软件工程”“外部验证：Arena 排名”等短标签，不写模板规则、截图操作或给 Agent 的提醒。
10. **落点检查**：父级模型栏和独立文档都要有对应图片 block；父页固定两列，子文档按四列 / 两列 / 三列用途布局。除开场四列证据墙外，图片必须在同列或紧邻位置有对应文字；任何图片都不能放进表格。

#### 多行 benchmark 表的专用截图流程

1. 先在官方页面或原始媒体中确认表格的完整范围：表头、第一行、最后一行、脚注 / methodology。
2. 如果表格超过首屏，运行 full-page 截图，不使用 `--viewport`；将长图按纵向切片查看，禁止只查看第一张切片后裁图。
3. 裁图时保留整张表的左右列和上下边界，只去掉页面导航、表格前后正文和无关空白。裁后再打开图片，核对第一行和最后一行仍在。
4. 将完整裁图按原比例缩放到父页右栏默认最大 `600x300`。高表可以变窄，但不得通过删除底部行来“适配”高度。
5. manifest 中记录 `source_type`、`crop_boundary`、`first_visible_row`、`last_visible_row`、`row_count` 和 `display_size`；任一缺失或无法核对，截图状态为 `pending`。

#### 发布页 Case 的逐项覆盖（按需）

如果用户明确要求官方 Case 截图，或某个 Case 是本次分析的核心能力证据，才逐项处理；默认用两列能力图表达模型能力，不强制复刻发布页 Demo：

- `SVG 动画生成`：截生成结果和页面能说明能力的上下文，caption 用“SVG 动画生成”。
- `ISS 遥测仪表盘`：截仪表盘实际画面和关键数据区域，caption 用“ISS 遥测仪表盘”。
- `3D 椋鸟群飞模拟`：截完整 3D 场景和交互 / 代码上下文，caption 用“3D 椋鸟群飞模拟”。
- `“呼啸山庄”作品集`：截作品集页面和能证明模型完成度的内容区域，caption 用“呼啸山庄作品集”。

如果需要 Case 截图且发布页的 Case 名称不同，按官方页面实际列出的每个一级 Case 建立 `case-*` 项；数量以页面为准，不得用一张总览图冒充多个 Case。

#### Gemini 3.1 Pro 示例：四个 Case 的固定取图位置

以 Gemini 3.1 Pro 为例，只有在用户明确要求官方 Case 证据时，才从官方发布文章和官方模型 Hands-on 页面分别取证；默认仍以两列 benchmark / capability grid 为主：

| 内容 | 首选官方页面 | 具体取图位置 | caption |
|---|---|---|---|
| Hero / 发布定位 | Google Blog 的 Gemini 3.1 Pro 发布文章 | 页面首屏标题、模型定位和发布时间区域 | `首页首屏` |
| Benchmark | DeepMind Gemini 3.1 Pro 模型页或 Model Card | `Performance` / `Evaluation` 表格区域；优先下载原图或裁选区，不截官网整页 | `官方 benchmark` |
| SVG 动画生成 | DeepMind 模型页 `Hands-on` | “Build lightweight, scalable animations directly into your codebase”对应的 slide / demo 画面 | `SVG 动画生成` |
| ISS 遥测仪表盘 | Google Blog 或 DeepMind 模型页 `Hands-on` | “Transform real-time data into a stunning, interactive visualization”对应的 aerospace dashboard | `ISS 遥测仪表盘` |
| 3D 椋鸟群飞模拟 | Google Blog 或 DeepMind 模型页 `Hands-on` | “Prototype sensory-rich interfaces with complex, interactive 3D simulations”对应的完整 3D 场景 | `3D 椋鸟群飞模拟` |
| “呼啸山庄”作品集 | Google Blog 或 DeepMind 模型页 `Hands-on` | “Translate complex literary themes into functional code…”对应的 portfolio 画面 | `呼啸山庄作品集` |
| 定价 / API | 对应厂商的官方 API pricing / model docs | 当前模型 ID、输入输出价格、缓存和上下文分档表 | `定价` |

启用 Case 截图时，每一行都要在 manifest 中落一条记录，并在父级模型栏和独立文档各插入一张对应图片。若 `Hands-on` 是轮播或视频：先等页面渲染，再按每个 slide 单独截图；不能只截轮播第一张，也不能用一张总览图代表四个 Case。

仅在 `word_only` 或 `feishu_sync` 模式下，编写一个生成 Word 文档的 Python 脚本，遵循以下结构和指南，然后执行；`research_only` 不执行本步骤。

## 文档结构

除非用户另有指定，遵循以下结构：

独立 Wiki 子文档和对应 Word 底稿默认使用 `references/CHILD-DOC-TEMPLATE.md` 的完整结构。本节提供各章节的写法；若与该 reference 的章节顺序冲突，以 reference 为准。父级汇总页仍使用前文的五块短模板，不能套用子文档长结构。

### 标题
日期 + 体现模型发布宣发主题的核心主题概括，可以参考网上对此次模型发布的评论来寻找灵感，给出1个主标题和2个备选标题。例如：`【2026/04/22】V2.5 & V2.5-pro 低调的发布`，或 `【2026/04/24】GPT-5.5 对Anthropic的攻坚战`。

### 基本信息
集中判断区域。4-6 条要点观察，使用加粗 + 浅黄色高亮标注。所有主观判断都放在这里。正文部分只放事实，判断集中在此。
硬参数速览，**使用 bullet points 列出**，每条用最少的文字写出最值得 highlight 的信息：
- **模型大小**：总参数量 / 激活参数量（MoE 架构需列出两者）
- **上下文窗口**：256k / 1M 等
- **API 定价**：输入 / 输出 / 缓存，按百万 token 计
- **模态**：纯文本 / 视觉 / 音频 / 全模态
- **发布类型**：公开测试版 / 正式版 / 开源 / 闭源
- **发布时间 + 时区**
- 其他最值得注意的发布信息（如模型 ID、可用渠道、最大输出 token 等，仅在有亮点时列出）

每条 bullet 一行写完，加粗最突出的亮点。不要写成一整段话。

### 模型特点 + 展示 Case
对每个能力用标签式简短描述。独立子文档开头用四列证据墙快速展示四个重点；能力 Case 通常使用两列 grid；发布过程、合作伙伴、客户评价和社区反馈允许三列 grid。每张图都要在后文或同列有 1–2 条上下文说明。优先展示编码 / Agent，以及知识工作、视觉或科学能力；不要为了覆盖官网首页而插入整页截图或纯宣传图。
本节描述模型能力证据，不要求复刻官方发布页的版式。若官方没有适合嵌入的图表，可基于已经核对的数据生成紧凑能力图，并在图中或 manifest 标明“根据已核对数据整理”。

### Benchmark 对比
嵌入官方基准测试图表或基于已核对数据整理的能力图。添加简短的"要点"总结，使用相对定位词汇（见下文）；整理图必须注明数据来源性质。除非数据直接来自官方发布页面，否则不要引用具体分数。
Artificial Analysis 关键基准 + Arena Elo 排名。附截图建议。**不要单独生成竞品定价对比表格**——定价信息在"基本信息"的 bullet points 中提及即可。

### 安全与对齐
如果安全数据是该模型的主要话题之一，或模型有 system card，嵌入图表并描述定位。

### 发布过程

#### 宣发对比
对比表：本次发布 vs 上次发布。维度：预热、行业背书、合作伙伴、社区讨论，以及你认为合适的和你看到的最大差异的另外1-2个维度。

#### 声势评价
一段短评，最多2-3行。对营销策略和定位的核心判断。主要判断集中在此。

#### KOL 口碑观察
附截图或文字证据。覆盖 X、Reddit、中文平台。如果反响较弱，直接说明。如有头部 KOL/合作品牌的评价引用，附上他们的名字。如果官网有引用客户评价，请数出有多少个客户评价，并给出其中最有代表性的几个。

#### 宣发截图
必须检索网上官方、KOL 和合作品牌的 social media 宣发证据。优先截官方 X post（正文、作者、发布时间、互动数据和前几条关键评论），再截 KOL 或合作品牌帖子；如果登录墙、地区限制或页面不可读导致无法截图，保留帖子 URL，并在 `update-manifest.json` 的 `screenshot_candidates[]` 标记 `manual_screenshot_required`，不能把 URL 当作已完成截图。能力证据必须覆盖多个来源。Artificial Analysis 截图是硬性要求：同一模型页存在多个有效区块时，至少截两张互不重复的图，分别覆盖模型总览（如 Intelligence Index、速度、价格、上下文）和 benchmark / 排名分解（如 Intelligence、Agent、coding、cost 等）；不能用一张整页总览图冒充多项证据，也不能重复使用同一文件。每张图都要在 `screenshots[]` 标记 `source_class: independent_benchmark`、完整来源 URL、`source_section`、实际本地文件、`image_block`、视觉验收结果和父页 / 子文档落点；两张图都必须插入独立子文档。

Artificial Analysis 有多个榜单面板时，选中的榜单必须**逐项单独截图、逐项分析**，禁止把 Intelligence、Speed、Cost per Task、GDPval、Agent 等面板拼成一张长图后用一段总评带过。硬性下限是两张互不重复的图：一张覆盖模型总览或最强独立优势，一张覆盖中上 / 短板榜单或排名分解；成本 / 速度与产品定位直接相关且页面有可靠面板时，再增加第三张。每张榜单图必须完整保留面板标题、指标解释、全部对比柱 / 点、模型名、图例或坐标轴，不能混入上一榜单或下一榜单残片。正文必须明确分成“强项 / 中上 / 非优势”，写清该模型在哪些榜单领先、哪些只是可用、哪些不能当作宣发主轴；低 API 单价不得直接等同于最低 Cost per Task。

#### 官网与宣发链接
**只收集官方链接**（官方博客、产品页面、API 文档、云服务商公告、官方更新日志）。不收录第三方新闻网站、自媒体转载或聚合站点的链接。

#### 对比MiniMax最新模型的宣发，给MiniMax的建议
请搜索MiniMax当前最新主推模型（截至本 skill 维护时为 MiniMax-M3，以官网/`token-plan-watch` 的 SSOT 为准，不要写死版本号）、OpenAI、Anthropic、Gemini、Xiaomi Mimo、Kimi (Moonshot AI)、GLM (Z.ai) 和 Qwen 最新模型的官网宣发文，然后根据这个模型的宣发，对比看看有什么是MiniMax团队可以借鉴的宣发手段，最值得考虑的方向包括很特别的 show case 和其他有创意的宣发手段，尤其是在网上被人受到好评的对于这个模型的官方宣发的手段。

## 语气与语言规则

### 写作风格
- **判断存在但集中放置**——仅在"基本信息"和"声势评价"区域
- **正文部分描述事实，不对能力发表主观意见**
- **严格1:1引用官方口号。** 使用中文引号："“更强的智能体，更长的专注力”"。注意：凡是要引用的英文原文，请附上中文翻译版本，仅对最重要的营销口号可以在中文翻译旁保留英文原文。
- **基准测试使用相对定位，不用绝对分数**

### 基准测试描述词汇（使用以下短语）：
- 与头部模型齐平
- 贴身追 Gemini / 逼近 Claude Opus
- 已超过 Claude，处于领先位置
- 大幅领先前代
- 略低一档
- 打平
- 已进入全球前三

### 禁止使用的AI腔
完全避免：赋能、助力、打造、引领、聚焦、驱动、构建、全方位、相辅相成、息息相关、与时俱进、标志着、意味着 X 时代的到来、"不仅…而且…"、"在…的背景下"、seamless、groundbreaking、cutting-edge、comprehensive、robust、pivotal、leverage、utilize、delve、harness

### 推荐使用的口语化表达（增加人味）：
- 这次、这代、上一代、这轮
- 跑偏、不靠谱、能打、新鲜
- "Cue 了一下 XX"
- "没有特殊能力，就是 XX"
- "感觉宣发也累了"
- "有点 X，的确是 Y"

### 句子节奏
- 3字短句和20字长句混搭
- 用句子片段强调重点（"打平。"、"暂无。"）
- 使用“ ”作为中文引号，不用英文直引号 `" "` 或「」
- 全文最多使用一个破折号

## 文字颜色与高亮规则

**所有文字必须为黑色。** 不使用彩色字体（不要红色、绿色、橙色字体颜色）。使用 `RGBColor(0x00, 0x00, 0x00)` 或不设置字体颜色（默认为黑色）。

**重要文字 → 浅黄色高亮。** 使用 `python-docx` 的高亮功能 `WD_COLOR_INDEX.YELLOW` 或自定义浅黄色 XML 底纹标注关键短语。

```python
from docx.enum.text import WD_COLOR_INDEX

# 重要文字：加粗 + 黄色高亮
run.bold = True
run.font.highlight_color = WD_COLOR_INDEX.YELLOW

# 建议/占位符：加粗 + 斜体（无颜色，无高亮）
run.bold = True
run.italic = True
```

**加粗**用于：关键数字、模型名称标签、带有结论性的短语

**加粗 + 黄色高亮**用于：关键差异化特征、警告/关注点、主要模型名称标签、正面信号（领先、全球前三）、核心判断

**加粗 + 斜体**（无高亮）用于：添加截图的建议、不确定的信息

## 图片放置规则

**只放有信息量的图片，不放纯宣传海报。** 允许放置的图片类型仅限以下三类：

1. **官方文章中的图表**：benchmark 对比图、性能曲线、评估雷达图、架构示意图、定价对比表截图等含有数据或结构信息的图表
2. **Demo / Case 演示截图**：官方展示的具体能力演示、代码生成示例、多模态输入输出截图等
3. **社交媒体 post 截图**：官方 X post、KOL 评测帖、合作品牌宣发帖的截图（含互动数据）

**明确不放的图片**：纯宣传海报、品牌 logo 横幅、无数据的营销配图、装饰性插图、模型名称大字报。这类图片不含任何对分析有用的信息。

每个主要章节应至少有一张上述类型的图片，或一条**加粗 + 斜体的黑色截图建议（无高亮）**。Word 底稿使用 `doc.add_picture(path, width=Inches(5.2))`，主图使用 `Inches(5.5)`；这只控制 Word，不代表飞书图片块尺寸。

| 章节 | 使用的图片 |
|---|---|
| Benchmark | 官方基准测试图表截图 |
| Token 效率 | 散点图 / 性能-成本图表 |
| Case 演示 | 每个 Demo 一张截图 |
| 安全 | 安全/对齐评估图表 |
| 声势证据 | X 互动截图、Arena 排名截图 |
| KOL 反应 | 高赞评论截图、意见领袖评测截图 |

### 飞书图片尺寸与图文模板（硬规则）

**父级汇总页和独立子文档使用不同图片策略。** 父页必须在上传前缩放到紧凑尺寸；独立子文档保留高分辨率原图直接上传，让读者可以点开查看细节，不得用父页尺寸上限压缩子页证据图。

| 落点 | `display_width` | 适用内容 |
|---|---:|---|
| 父级汇总页模型条目右列 benchmark 对比图 | `600` | 完整官方 benchmark / Arena 表；同时设置 `display_height: 300`，按原比例缩放，不裁数据行 |
| 父页两列能力 / 证据 grid | `720` | 仅父页补充视觉 Part；同时设置 `display_height: 480` |
| 子文档四列 / 两列 / 三列视觉区块 | 原图 | 不传 `display_width` / `display_height`，保留原始分辨率 |
| 父页“宣发/社媒”grid 右列 | `603` | 完整官方社媒帖；同时设置 `display_height: 859`，硬上限 `720x1000` |

父页继续按上表尺寸上传。子文档不重采样原图；四列、两列和三列 grid 由飞书页面自动适配显示宽度，图片 block 保留原始像素尺寸。

父级汇总页的 benchmark 对比图使用单独的 `600x300` 上限。完整表格比例不足以填满这个框时，保持原比例产生更窄的图；禁止通过裁掉最后几行、表头或 methodology 来填满宽高。

生成父页飞书 blocks 时，每个 image spec 必须带展示尺寸，例如：

```json
{"type":"grid","columns":[
  {"caption":"Benchmark：编码与 Agent","path":".../model-coding-agent.png","display_width":720,"display_height":480},
  {"caption":"Benchmark：知识工作与视觉","path":".../model-knowledge-vision.png","display_width":720,"display_height":480}
]}
```

父页长图使用 `display_height` 作为第二个上限。子文档 image spec 不传展示尺寸，GIF 和高分辨率长图保留原文件。上传完成后都必须回读 image block；父页核对上限，子页核对原图尺寸没有被缩小。

修复父页超大图片块时，不能只调用 `replace_image`：该操作可能只替换媒体 token，不刷新旧 block 的宽高元数据。必须在原父 block 的原 index 新建缩放后的 image block，上传并回读新尺寸，再用 `children/batch_delete` 删除旧 block。子文档的高分辨率原图不是“超大图错误”，不得因此缩小或替换。

### 每张图都必须配文字（硬规则）

每一张图必须有两层文字关系：

1. **对应更新文案**：先写 1–2 句事实或要点，说明这张图证明什么；图片紧跟在这段文案下面。
2. **图文关系**：父页 benchmark、Case、定价等证据图在 image block 正前方放 2–16 字短图注。子文档除开场四列证据墙外，可以使用短图注，也可以像 GPT-5.5 参考页一样用同列 1–2 句 Case 说明承担图注作用。社媒截图由所在“发布过程与社区声势”列的文字说明。

父页普通视觉 Part 遵循 `文案 -> 两列 grid（每列：短图注 -> 图片）`；父页社媒 Part 固定为 `宣发/社媒根级标题 -> 两列 grid`。子文档遵循 `四列开场证据墙 -> 两列能力 Case -> 三列发布 / 社区区块`。图片仍然禁止进入 table / table cell。

每张图在 manifest 中至少记录：`caption`、`caption_block`、`image_block`、`caption_before_image`、`display_width`、`display_height`、`size_policy`、`template_reference`、`parent_placement`、`child_placement`。缺任意字段，截图项状态只能是 `pending`。

### 写入后的图片验收

回读父页和子页全部 image block，逐张检查：

- 父页图片符合对应 `display_width` / `display_height` 上限；子文档图片保持原始分辨率，没有被父页规则重采样；
- 父页除社媒 grid 右列外，image block 前一个同父 block 是非空文本；子文档除四列开场证据墙外，图片在同列或紧邻位置有对应说明；
- 父页图注位于图片前；子文档允许短图注或同列 Case 说明，社媒图由所在发布 / 社区列的文字配对；
- 图片不在 table / table cell 中；
- 父页与子页的图片数量、落点和 manifest 一致；
- 父页发现超大图必须修复；子文档高分辨率原图属于正常模板。无文字图、图文错列或证据与文案不对应仍必须修复。

## 未知信息处理

| 情况 | 处理方式 |
|---|---|
| 架构未公开 | 删除该部分或保留并标注"推测" |
| 无第三方背书 | 写 **暂无** |
| KOL 反响较弱 | 直接写明并附证据 |
| 直觉/推测 | 标注为"观察"而非"结论" |

## 篇幅控制

**独立子文档默认 2500–6000 个中文字符，约 5–10 分钟阅读。** 资料少时可以更短；资料丰富时允许更长，但不能靠重复 benchmark 数字或堆截图撑篇幅。父级汇总页仍保持短摘要。

篇幅过长时，按以下顺序删减：
1. 形容词
2. 判断性语句
3. 重复信息
4. 保留：事实、官方引用、截图、对比表

## Word 文档技术说明

```python
# 中文字体设置 — 所有文字为黑色
from docx.oxml.ns import qn
from docx.enum.text import WD_COLOR_INDEX

# 字体名：本机（macOS）生成时系统中文字体是 PingFang SC，无 Microsoft YaHei。
# 但产出 .docx 多在 Windows/飞书端打开，那里 YaHei 才是标准。
# 做法：正文 eastAsia 字体写 "PingFang SC"（保证本机生成预览正常），
# 若你希望在 Windows Word 里也统一，可改 CHINESE_FONT 常量。两者都是黑色无色差。
CHINESE_FONT = "PingFang SC"   # Windows 端可改 "Microsoft YaHei"

style = doc.styles["Normal"]
font = style.font
font.name = CHINESE_FONT
font.size = Pt(10.5)
font.color.rgb = RGBColor(0x00, 0x00, 0x00)  # 黑色
style.element.rPr.rFonts.set(qn("w:eastAsia"), CHINESE_FONT)

# 重要文字：加粗 + 浅黄色高亮
run.bold = True
run.font.highlight_color = WD_COLOR_INDEX.YELLOW

# 表格样式
table.style = "Light Grid Accent 1"

# 图片居中
doc.add_picture(path, width=Inches(5.2))
doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
```

**重要提示：** 在 Python 字符串中嵌入中文弯引号（"“ ”"）时，使用单引号 Python 字符串（`'...'`）以避免解析器冲突。

## 提交前检查清单

根据运行模式执行对应清单。没有标记为当前模式的项目，不得作为该模式的失败条件。

### 通用检查（所有会产生研究结果的模式）

- [ ] 标题包含日期 + 事件概括
- [ ] 基本信息包含硬参数速览（参数量、价格、上下文、模态等）
- [ ] 每个主要章节有图表 / Demo 截图 / 社媒截图或截图建议（不放纯宣传海报）
- [ ] 每张截图都用当前运行时的视觉读取能力打开确认，不是登录墙、空白页、骨架屏或不可读小字
- [ ] 每张多行 benchmark 图都能看见表头、第一行、最后一行和存在的 methodology / footnote；没有用顶部切片冒充完整表格
- [ ] 官方口号严格 1:1 引用
- [ ] 基准测试部分使用相对定位，不用绝对分数
- [ ] 无背书的章节标注为“暂无”
- [ ] `word_only` / `feishu_sync` 的富文本产物已应用加粗和高亮；`research_only` 纯文本输出不以富文本样式作为完成条件
- [ ] 包含本次 vs 上次发布对比表
- [ ] 包含 KOL 口碑 / Arena 证据；没有可靠证据时明确写“暂无”
- [ ] 判断集中（未散布在正文各处）
- [ ] 包含所有官方链接
- [ ] 网络请求仅访问已确认的公开来源，没有携带 token / Cookie / 本地文件内容，也没有执行外部写请求
- [ ] 没有自动安装依赖或删除文件；无效下载已在 manifest / 日志标记为 `rejected` 并保留原文件

### `word_only` 检查

- [ ] 已生成可打开的 `.docx` 文件，并保存在确认的研究文件夹
- [ ] Word 文档章节、图片、表格和字体样式符合本 Skill 的写作规则
- [ ] Word 文档中的图片与相邻文案对应，且没有图片进入表格单元格
- [ ] 向用户报告 `.docx` 文件路径、文件大小、章节数、图片数和表格数
- [ ] 没有执行飞书写入、Wiki 节点操作或飞书 validator

### `feishu_sync` 检查

- [ ] 已按 `parent_id` 回读标题树：根级主章节为 H1，真实小节为 H2，root H3+ 和 grid 内 Heading block 均为 0
- [ ] 截图 manifest 已逐项填写来源、截图方法、caption、父级落点、子文档落点和验收状态
- [ ] 子文档包含四列开场证据墙、两列能力 Case 和三列发布 / 社区区块；父页仍严格使用紧凑两列
- [ ] 父级模型条目严格为“标题 -> 详细追踪 -> 主能力两列 grid -> 宣发/社媒标题 -> 社媒两列 grid”；benchmark 图在主 grid 右列，完整社媒帖在社媒 grid 右列，图片不在表格内
- [ ] 社媒左列含传播判断、`网页` 和至少两个可点击 URL；右列恰好一张图，尺寸不超过 `720x1000`，manifest 视觉验收字段齐全
- [ ] 所有截图都放在对应更新文案下，**没有任何截图进入表格单元格**
- [ ] 父级总表文案已参考同类条目，子页图注已收敛为短标签
- [ ] 目标 A：父级厂商 / 模型独立栏已更新，模型文案下紧跟对应图片
- [ ] 目标 B：父级所有相关表格已逐个盘点；影响的表格已更新，无变化的表格有 manifest 记录
- [ ] 目标 C：独立模型文档已位于正确的 Wiki 相邻 / 子级目录，不是“我的空间”根目录孤立文档
- [ ] `target_status.A/B/C` 已分别填写，并与父级栏、相关表格和子文档 validator 的实际状态一致
- [ ] 父级 Wiki 下 dated 子文档已按 `【YYYY/MM/DD】` 从新到旧排列；同日顺序稳定，回读节点数量和 node token 无变化
- [ ] 已显式传入当前运行时确认存在的 `--helper <feishu_helper.py>`，且 `scripts/validate_child_document.py` 返回 `status: pass`、`violation_count: 0`
- [ ] `scripts/validate_update_manifest.py --manifest <研究文件夹>/update-manifest.json --require-complete` 返回 `status: pass`、`error_count: 0`、`violation_count: 0`
- [ ] 使用同一已确认 helper 运行的 `scripts/validate_vendor_section.py` 返回 `status: pass`、`violation_count: 0`
- [ ] 父级模型栏已链接到独立文档，独立文档回读确认图片和正文完整
- [ ] 子文档文末返回汇总页为真实可点击链接或 `mention_doc`，不是普通 URL 文本
- [ ] 独立子文档篇幅与资料量匹配，没有为了压到 3 分钟而删掉发布过程、社区证据或可借鉴点
- [ ] 向用户报告三目标同步结果：父级模型栏、相关表格、独立 Wiki 文档分别的写入和回读状态

### `research_only` 检查

- [ ] 只输出研究结论和来源，不生成 Word 或写入飞书
- [ ] 没有执行飞书写入、Wiki 节点操作、图片 block 操作或飞书 validator

## 输出

所有模式都把研究资料存储在启动时确认的研究文件夹中。只有 `word_only` 和 `feishu_sync` 模式生成 Word；只有 `feishu_sync` 模式写入飞书。

```
<研究文件夹>/
├── images/          ← 下载的图片和截图
├── html/            ← 下载的网页原始HTML
└── pdf/             ← 下载的PDF文件
```

`word_only` 和 `feishu_sync` 模式额外生成：

```text
<研究文件夹>/<模型名称>_竞品分析_<YYYYMMDD>.docx
```

向用户报告：
1. 研究文件夹路径
2. 下载的研究资料数量（图片、HTML、PDF）
3. 需要手动添加的缺失截图（Word 中以加粗 + 斜体黑字列出，不使用彩色字体或高亮）
4. `word_only` 和 `feishu_sync` 模式：`.docx` 文件大小、章节数、图片数和表格数
5. `feishu_sync` 模式：三目标同步结果——父级模型栏、相关表格、独立 Wiki 文档分别的写入和回读状态
6. `research_only` 模式：明确报告未生成 Word、未写入飞书

## 飞书汇总页同步（仅 `feishu_sync` 模式）

本节只在 `feishu_sync` 模式执行。Word 文档（.docx）是研究底稿和可下载备忘录；当任务目标包含父级汇总页时，飞书同步是任务本身的一部分，不能只交 Word 后说“已收录”。

这份分析最终写入 `sync_target` 中经只读预检确认的父级飞书文档和 Wiki 父节点，作为一个**模型子页**使用。子页内容架构参考 `【2026/04/23】GPT-5.5 & 5.5Pro 对抗Opus4.7`，详细规则见 `references/CHILD-DOC-TEMPLATE.md`；新标题统一为 `【YYYY/MM/DD】<模型>：<一句话主题>`。本文件中的 token 仅能作为字段格式示例，不能直接作为当前任务的写入目标。

执行顺序：
1. 读父级 Wiki 的全文和 block 列表，定位厂商章节、模型条目、所有相关表格和已有图片；先完成 `update-manifest.json`，再写。
2. `feishu_sync` 模式默认按目标 A / B / C 执行；`research_only` 和 `word_only` 模式不进入本节，并在最终回复中说明未执行飞书同步。
3. 使用只读预检确认的用户身份（`user_access_token`，非 bot）读写；如果 API 返回 token 过期、身份错误或权限不足，立即停止后续写入，报告具体 API 错误和受影响目标，不得通过重复授权话术或本地文件冒充完成。若目标 B 含 `block_type: 30`，还必须确认 token 具备 `sheets:spreadsheet:read` 与对应写权限；仅有 docs 权限不算授权完成。
4. 父级模型栏：更新短文案和链接，图片作为独立 image block 紧跟在对应文案下。
5. 父级表格：更新原有表格的事实单元格，图片不得写入表格；不要用新增重复表格绕过原表。
6. 独立文档：先读取 `references/CHILD-DOC-TEMPLATE.md`，再查找或创建在 `sync_target.parent_wiki_node` 正确 Wiki 目录下的子文档，写入正文、发布对比表和重要图片；不能落在“我的空间”根目录后冒充 Wiki 子页。
7. 写完必须回读父级和子文档，核对 block 数、表格单元格、图片 block、标题、日期、链接和 Wiki 父节点，并使用显式的 `--helper <feishu_helper.py>` 运行 `scripts/validate_child_document.py`；把结果写入 manifest 和最终回复。

> 注意：飞书子页与 Word 是**同一份内容的两种载体**，不要为了发飞书牺牲 Word 质量。先把 Word 做扎实，飞书是导出。
