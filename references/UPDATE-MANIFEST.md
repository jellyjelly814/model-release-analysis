# update-manifest v3

v3 增加范围相关权限、表格原始回读、事实清单、文档版本绑定及续跑记录。用 `sync_run.py init` 生成准备态，不复制历史完成态。旧 v2 用 `migrate --output <新文件>` 保留原件；新字段需要当前证据，旧 pass 全部清除。

## 基础结构

- `schema_version: 3`；`run_id` 是新建 UUID；`created_at` 带时区；`mutation_generation` 随写入递增。
- `model_identity`：company、name、version、release_date。标题可变化，但版本必须精确。
- `mode`：默认 `feishu_sync`；用户明确仅阅读时为 `read_only`。
- `sync_target`：parent_doc、parent_wiki_node、vendor_heading、scope、allowed_link_hosts、permission_preflight。
- `permission_preflight`：identity 为 `user_access_token`；docx_read、docx_read_write、media_read_write、sheets_read_write、wiki_node_manage 是实际检查结果；status 为 pending/complete/blocked/failed。只要求范围内需要的能力。
- `parent_section`：wiki_node、vendor、model_entry、status。
- `child_wiki_doc`：parent_node、parent_node_token、node_token、obj_token、title、status、operation（create/update）。父子 token 来自当前回读。
- `target_status`：A/B/C 各自 pending/failed/verified 等真实状态。范围外保留原始状态。

## Sheet 清单和检查计划

`table_inventory` 与当前父页全部 `block_type: 30` 的 Sheet 一一对应，包含 `block_id`、原始 `sheet_token`、`relevant` 和理由。无关表也列出；无表只有实时扫描结果为空才成立。

每个 relevant 项在 `related_tables` 有且仅有一个计划：

```json
{
  "block_id": "actual_sheet_block",
  "spreadsheet_token": "actual_spreadsheet",
  "sheet_id": "actual_sheet_id",
  "model_column": "A",
  "model_keys": ["Exact Model v1"],
  "expected_occurrences": 1,
  "header_range": "A1:C1",
  "header": ["模型", "输入价格", "成本公式"],
  "action": "updated",
  "status": "pending",
  "reason": "当前版本输入价格变化",
  "checks": [{
    "range": "A8:C8",
    "expected_values": [["Exact Model v1", 2, 4]],
    "expected_formulas": [[null, null, "=B8*2"]]
  }]
}
```

`action` 是计划 updated/checked_no_change；`status`、`checked_rows`、`remaining_mismatches` 由实际表格 validator 结果回填。缺失计数不等于零。

每个矩形必须完整声明值与公式；null 代表预期空值/无公式，不代表“忽略此格”。避免把数值 2 和字符串 "2" 混用。普通值、富文本、公式表示必须以当前读取返回为准；不支持的接口返回会报 operational failure。

校验器会扫描模型列全部物理行（每 500 行一批），包含空行后数据和隐藏行。每个匹配模型行必须在预期检查中；受本次更新影响的列均应覆盖。需要大范围时拆成多个 checks，不能忽略截断提示。

## screenshots

每条记录保留 v2 的 id、model_entry、kind、source_class、source_url、source_section、source_original、method、local_path、content_sha256、parent_image_block、child_image_block、caption、caption_block、caption_before_image、display_width、display_height、size_policy、template_reference、parent_placement、child_placement、visual_check、status。

- local_path 可相对 manifest 目录，文件必须位于研究目录内。
- content_sha256 绑定真实图片。A/C 远端会下载媒体并比较，全部已发布图片必须有记录。
- source_class 枚举：official_page、official_social、github_or_model_repo、independent_benchmark、external_media_or_kol。
- 同一原图不同裁切 source_original 保持一致，开场证据墙不得重复该值。
- 开场图写 `child_placement: opening_evidence_wall`，允许 caption_block=null、caption_before_image=false；其余图提供实际上下文/图注 block。
- 社媒图 A/C 均在 scope 时两处 ID 必填；单范围只绑定相应 ID。visual_check 要 verified、verification_method=view_image、blank=false、login_wall=false、complete_post=true。
- 所有候选图只写 screenshot_candidates，不预填 image block；完成图移入 screenshots。

## evidence_policy.artificial_analysis

- `unchecked`：仅准备态，尚未查询。
- `available`：有当前模型页面内容。C 在范围内时要求两张不同 source_section/hash/child block 的真实 AA 图。
- `checked_unavailable`：已查但当前版本未收录或无内容。
- `not_applicable`：发布类型不适用于该平台。

后两种状态提供 checked_urls、reason、alternatives；与已完成的 AA 图片记录不能并存。访问失败需在 reason 明确区别于未收录。

## claims 与 claim_coverage

详见 CLAIMS-AND-EVALS。准备态 coverage 可 pending；完成态每个分类有 claim_ids 或真实缺口说明。源文件和 published placement 都需要可追溯。

## verification：派生结果

只用 `record_validator_result.py` 从实际 JSON 记录 child/vendor/tables 结果。记录器保存不可变证据文件，清除旧 freshness。

通过结果包括 status、violation_count、document、model_entry、run_id、validated_at、document_revision_id、manifest_input_sha256、snapshot_sha256、result_file、result_sha256。child 另含 wiki_node/parent_node；vendor 另含 vendor/validation_scope=current_entry。

`manifest_input_sha256` 排除 verification、journal、preflight 和派生状态；模型、目标、权限、图片、来源、表格期望或 mutation_generation 改变会使它失效。哈希解决意外错用与过期结果，不能证明恶意伪造 JSON 的真实性。

统一 verify 在 validator 后再次读取远端，记录 freshness（checked_at、输入哈希、结果集合哈希）。完整门禁会重读本地结果文件、核对快照哈希和各表计数。15 分钟后重新实时复核；离线通过不是永久有效状态。

## journal

step_id 唯一；target=A/B/C；state=started/written；保存开始/结束时间、前后快照哈希、真实回执路径与哈希及 receipt_kind（operation/recovery_readback）。started 表示结果不确定；resume 不重放写入。written 也需最终 validator，不能视为完成。
