# 事实清单和真实任务评测

## 关键结论清单

为身份、可用性、价格、能力、benchmark、发布过程、社区各建立 claim_coverage。每个分类标 covered 并引用 claim_ids；无资料用 not_public/not_applicable 加 checked_urls/reason。准备态可 pending，不预填已核实。

```json
{
  "id": "pricing-input",
  "kind": "fact",
  "statement": "当前版本输入价格为每百万 token 2 美元",
  "model_version": "exact-v1",
  "sources": [{
    "url": "https://official.example/pricing",
    "retrieved_at": "2026-09-11T12:00:00+08:00",
    "locator": "Pricing > exact-v1 > input",
    "local_path": "html/pricing.html",
    "content_sha256": "实际源文件SHA256"
  }],
  "review_status": "verified",
  "placements": [{"target": "B", "block_id": "actual_sheet_block", "range": "A8:C8"}]
}
```

kind：fact、official_benchmark、independent_benchmark、external_opinion、inference、unknown。推断用 basis_claim_ids 引用基础事实，不能冒充来源直接结论。无资料不填分数；比价格时注明币种、输入/输出/缓存/批处理、token 单位和生效日期。

benchmark 额外提供 conditions：dataset_version、harness、tools、sampling、measured_at；不明写 unknown 并设 comparable=false。任何精确排序都要先核对这些条件可比。官方自测不改写为独立评测。

review_status=verified 的前提是逐条读过源文件并核对 statement；placements 对应最终真实 block/范围。validate_claims 只验证结构和缓存哈希，不能证明语义正确，也不能识别所有误读或网页伪造。

启用 `business_analysis` 时，价格 quote 和榜单 entry 还要用 `subject_model` 绑定其实际比较对象（例如 `DeepSeek V4.1`），而 `model_version` 继续绑定本次研究任务。价格来源、OpenRouter 端点/路由和 AA 方法说明必须回到已有 claim 的原始 URL 与缓存哈希；榜单条件未知时显式设 `comparable: false`，不能以 validator 通过替代业务结论审阅。

## 评测用例与边界

`evals/evals.json` 保存用户任务与验收点，包括：只有官宣、缺少独立评测、同名不同版本、仅更新价格、多模型部分失败、明确只读、恢复已创建子页、Skill 自身评审。

维护时：

1. 先用 packaged tests 验证确定性错误：错链接、错 hash、漏表、公式覆盖、过期通过、权限范围、断点续跑。
2. 用旧版/新版分别执行相同任务，输出行动计划或使用隔离的 fixture helper；测试不得接触真实飞书目标。若另有明确授权的测试空间，再做远端验收。
3. 记录每例事实与预期的差异、遗漏、是否误写入、完成状态、wall time；能获得真实 token usage 时才记录，不估算。
4. 人工审阅来源与结论。事实准确率的分母是有 ground truth 的原子事实，不能用 validator pass rate 替代。
5. 对来源缺失的情况，验收正确标注和部分完成，不奖励编造四张图或没有条件的榜单。
6. 明确区分脚本回归、Agent 行为评测、真实远端验收；最终报告分别标通过/未测试。
