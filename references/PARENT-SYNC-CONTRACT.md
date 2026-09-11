# 父级汇总页同步合同

本文件约束目标 A（当前模型条目）和目标 B（相关表格）。默认只交付当前 `parent_section.model_entry`；历史条目仅在用户明确要求全量迁移时进入门禁。

## 1. 厂商章节与当前条目

父级文档用厂商 H2 划分章节，每个模型用 dated H3：

```text
厂商 H2
└── 【YYYY/MM/DD】模型名：一句话主题 H3
    ├── 详细追踪：mention_doc 或可点击子页链接
    ├── 主能力两列 grid
    ├── 宣发/社媒（普通正文）
    └── 宣发两列 grid
```

当前条目严格使用五个根级 block；分隔符或空正文可跟在末尾。不得在条目根级追加散落图片、额外标题或复制表格。

`详细追踪` 必须指向目标 C 的真实 Wiki 子文档。写入后回读 mention/link 的目标，不只检查可见文本。

## 2. 主能力两列 grid

左列包含：

- 核心能力：1–3 条最重要能力与限制。
- 展示的 Case：每个关键 Case 写任务、过程和结果。
- 不放宣发链接或网页清单。

右列包含：

- 关键参数：日期、模态、上下文、输出长度、价格和入口。
- 测评：官方与独立指标分开，注明版本和口径。
- 恰好一张完整 benchmark 图，前一个同父 block 是非空短图注。

父页 benchmark 图片上限为 `600x300`，保持原比例；不能为了填满尺寸裁掉表头、首尾行、图例、脚注或 methodology。

## 3. 宣发两列 grid

左列写传播判断，并给 `网页` 及至少两个真实可点击 URL。普通 URL 字符串不算可点击链接。

右列可以有零或一张社媒图：

- 有图时使用完整帖子，上限 `720x1000`；A/C 均在 scope 时 manifest 中同一记录必须有 `parent_image_block` 与 `child_image_block`；仅 A 时只要求 parent block。
- 无法取得可读社媒图时允许纯文字，但必须如实写证据缺口，不放登录墙、空白页或普通海报。

## 4. 图片与正文

- 图片禁止进入 table/table cell。
- benchmark 图前必须有同列短图注。
- 社媒图由左列传播分析承接。
- 父页使用紧凑尺寸；子页保留高分辨率原图。
- 替换图片后以 API 返回的新 block ID 和回读尺寸为准。仅替换媒体 token 可能保留旧尺寸；必要时原位置新建 image block，确认后删除旧 block。

## 5. 当前条目门禁

默认运行：

```bash
python3 scripts/validate_vendor_section.py \
  --helper "<feishu_helper.py>" \
  --doc "<parent_doc_token>" \
  --vendor "<vendor_heading>" \
  --model-entry "<current_model_entry>" \
  --manifest "<研究文件夹>/update-manifest.json" \
  --require-social-visual-proof \
  --require-artificial-analysis
```

这只把当前模型条目纳入完成判定，并在输出的 `historical_entries` 中列出未审计历史条目。用户明确要求厂商章节全量迁移时，才把 `--model-entry` 改为 `--all-entries`。

## 6. 相关表格

先从父级 block 列表定位所有嵌入式 Sheet，再逐表检查：

- 表头与字段类型。
- 当前模型是否已有行、是否重复。
- 模型名、版本、日期、上下文、价格、能力、排名、入口等受影响列。
- 公式、lookup 或格式是否会被普通值覆盖。

对每个表在 manifest 记录 block ID、表头、检查行数、更新原因、状态和剩余不一致数。无变化写 `checked_no_change`；有变化写 `updated`。完成态 `remaining_mismatches` 必须为实际读取计算的 0，不能缺省。使用 v3 的 table_inventory、checks.expected_values 和 checks.expected_formulas，再运行独立 validate_tables.py；详见 UPDATE-MANIFEST.md。

图片永远不进表格。不要新建重复表格绕开原表，也不要只更新当前可见的第一个 Sheet。

## 7. 写后回读

每次结构修改后重新读取当前 section，因为 block_replace/insert/delete 会使旧 ID 失效。最终至少核对：

- 厂商 H2、当前 H3 和五个根级 block 顺序。
- 子页链接、主 grid、benchmark 图注与图片。
- 宣发 grid、可点击 URL 与社媒图。
- 每个相关 Sheet 的目标行、公式与剩余不一致。
- manifest 的 `parent_image_block`、表格 block ID 和 validator provenance 与回读一致。
