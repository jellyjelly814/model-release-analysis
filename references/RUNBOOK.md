# 初始化、写入登记、恢复与验收

统一入口只负责本地状态和远端只读验证。内容写入仍由当前已认证飞书工具执行；没有通用自动重试写入器。

## 初始化

使用 SKILL.md 的 init 示例。targets.json 字段见 config/targets.example.json。预检实时检查父 Wiki 到 doc 的映射和全部嵌入 Sheet；它不会把“读取成功”升级为写权限通过。根据当前身份/资源权限检查填 permission_preflight。

安装版依赖 Python 3.9+ 标准库和已配置的 lark-cli。验证默认 helper 在 scripts/feishu_lark_cli_helper.py；每次传入其绝对路径。也可以使用兼容 helper，方法契约见下文。

模型名称/版本有歧义时先解决身份，不创建多个猜测版本。多个版本分别使用独立目录/manifest；单个通过不能代表整批完成。

## 正文写入

新模型先查询已有子 Wiki：不存在时创建节点并登记 obj_token/node_token，再更新父页的真实子页链接。普通链接和 mention 均可。之后按数据依赖写 A/B/C，每次结构改动重取 block ID。

```bash
python3 scripts/sync_run.py begin-write --manifest "<run>/update-manifest.json" \
  --helper "<helper绝对路径>" --step-id "parent-entry-v1" --target A \
  --description "更新当前模型条目及子页链接"
# 在此调用已授权的 lark 文档工具，保存实际成功 JSON 回执到研究目录。
python3 scripts/sync_run.py checkpoint --manifest "<run>/update-manifest.json" \
  --helper "<helper绝对路径>" --step-id "parent-entry-v1" --receipt-file "<run>/parent-receipt.json"
```

begin-write 在副作用发生前清除旧校验结果；相同 step-id 再次调用会拒绝。checkpoint 保存回执和远端快照，不自动判断写入语义正确。原操作回执用默认 `--receipt-kind operation`；请求超时、原回执丢失时，在核对精确模型、父节点与真实 token 后，将查询工具的实际成功输出作为 `--receipt-kind recovery_readback` 保存，两种证据不能混写。创建新子页时 begin-write 可先保存父页上下文；checkpoint 前填入 API 返回的新子页 token。

## 断点恢复

```bash
python3 scripts/sync_run.py resume --manifest "<run>/update-manifest.json" --helper "<helper绝对路径>"
```

- uncertain_do_not_replay：请求可能生效但回执丢失。先查询子页/条目/媒体，确认真实结果，再保存当前实际查询/恢复工具输出，并用 `checkpoint --receipt-kind recovery_readback` 标明恢复证据；不能伪造已丢失的原创建回执。不要直接重建节点或上传同一图。
- already_written：最近一步内容与记录匹配，可以继续后续步骤。仍需最终 verify。
- changed_reconcile：快照已变；重新读取后修订计划。
- superseded：同一目标有更新步骤，以最近记录和实时状态为准。

resume 不执行远端写入，总是使缓存的完成状态失效。修复失败步骤用新的 step-id，保留旧记录；只有已确认未生效或已补回执的步骤才能结束不确定状态。

## 最终验收

```bash
python3 scripts/sync_run.py verify --manifest "<run>/update-manifest.json" --helper "<helper绝对路径>"
```

范围内按 C、A、B 运行 validator 并保存结果，再复核全部当前快照和媒体。任何一个失败保留真实状态；全部通过后才执行最终 manifest 完整门禁。源资料读取核对与最终可读性视觉检查由 Agent 完成；工具不把格式正确等同于事实准确。

单独运行诊断工具时，都显式传当前 manifest/helper：

```bash
python3 scripts/validate_tables.py --manifest "<run>/update-manifest.json" --helper "<helper绝对路径>"
python3 scripts/validate_claims.py --manifest "<run>/update-manifest.json" --require-complete
python3 scripts/validate_update_manifest.py --manifest "<run>/update-manifest.json" --require-complete
```

## v2 迁移

```bash
python3 scripts/sync_run.py migrate --manifest "<run>/update-manifest.json" --output "<run>/update-manifest-v3.json"
```

保留旧文件和来源哈希，清除旧通过状态。补 model_identity、allowed_link_hosts、table_inventory、表格期望、事实清单与权限后重新 preflight/verify。不根据旧 pass 推断新字段。

## 只读 helper 契约

api(GET,path) → (unused, {code:0,data:{...}})；_all_blocks(doc) → 全部原始 block；download_media(token) → 原始 bytes。

表格需 sheet_metadata(spreadsheet_token,sheet_id) → {row_count,column_count,sheet_id}；read_sheet_range(token,sheet_id,"A1:C8") → {range,row_indices,col_indices,values,formulas}。values/formulas 完整矩阵且坐标真实；空白位置显式 null。CLI helper 使用 +workbook-info / +cells-get，遇未知结构、warning、has_more、truncated 或缺失坐标直接失败。不要把未支持接口适配写成远端测试通过。

文档使用 revision_id 前后检查，表格连续读两次比较内容哈希。接口超时 60 秒；分块读取不静默漏页，循环分页 token 会停止。接口返回可能随 CLI 版本变化，先对照当前 --help 和真实返回适配，再重跑离线/远端检查。
