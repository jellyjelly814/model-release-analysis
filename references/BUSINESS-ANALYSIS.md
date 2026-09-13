# 市场与业务分析合同

本文件定义 `business_analysis` v1。它服务于市场、销售、产品和业务决策，仍然要求每个数字能回到当前模型版本的原始来源。它不把结构校验当成事实准确率，也不允许凭截图猜测榜单算法。

## 输出结构

每个模型 manifest 增加：

```json
{
  "business_analysis": {
    "profile": "business-v1",
    "topics": ["pricing", "leaderboards"],
    "summary": [{
      "label": "适合 Coding 场景",
      "claim_ids": ["coding-fit"],
      "limitation": "工具权限和部署成本仍需单独核实"
    }],
    "pricing": {
      "peer_selection": "选择同一输入/输出模态且公开版本的 API 竞品；排除不同档位",
      "official_check": {"status": "checked", "checked_at": "...", "checked_urls": ["..."]},
      "openrouter_check": {"status": "checked", "checked_at": "...", "checked_urls": ["..."]},
      "quotes": []
    },
    "leaderboards": {
      "checks": [],
      "entries": [],
      "aa_methodology": {}
    },
    "report": {"local_path": "pricing-report.md", "sha256": "...", "section_heading_block": "..."}
  }
}
```

`topics` 是本次任务范围。只做价格时使用 `pricing`，只做榜单时使用 `leaderboards`。`summary` 中的 `label` 是业务标签，不是综合分；每项都要给 `limitation` 和 claim IDs。

## 价格口径

价格记录是独立报价行。每行必须有 `channel`（`official` 或 `openrouter`）、`model_id`（名称与精确版本）、`provider`、`endpoint`、`routing`、`currency`、`effective_date`、`region`、`tier`、`context_window`、`max_output` 和 `fee_notes`。`rates` 的每一项（`input`、`output`、`cache_read`、`cache_write`、`batch_input`、`batch_output`）都要明确 `available`、`unavailable` 或 `not_applicable`。

可用价格记录 `amount` 与 `per_tokens`，脚本只把它规范化显示为每百万 token；固定请求费、图片费、搜索费和推理费不能塞进 token 单价。未公开不是零价格。不同币种、地区、上下文门槛、缓存规则、批处理折扣和供应商路由必须分行或写进费用条件，不能暗中合并。

官方页面是价格主来源。OpenRouter Compare/API 记录的是观察到的供应商价格、端点和路由状态，不替代官方价格。OpenRouter 的价格字段以每 token/request/unit 表达，可能包含 `prompt`、`completion`、缓存和条件覆盖；在比较时记录原始字段和读取时间（[OpenRouter models API 文档](https://openrouter.ai/docs/guides/overview/models)）。OpenRouter 供应商排序可能按价格、吞吐或延迟，路由设置也要保留（[Provider Selection](https://openrouter.ai/docs/guides/routing/provider-selection)）。

本版本不预设请求量，不计算普通对话、长上下文或 Coding/Agent 的任务成本。若用户提供真实用量，可在单独报告中计算，并明确 token 构成、缓存命中、请求费、币种和日期；不能把该结果写成通用成本。

## 榜单口径

每个榜单条目必须记录：榜单名称和版本、精确模型版本、effort、provider、任务类型、指标与单位、分数、排名及排名总体（或 `rank: null`）、测试集/数据集版本、harness、工具权限、采样设置、观测日期、claim IDs 和 `comparable`。任何关键条件未知都使用 `unknown` 并设 `comparable: false`，不做精确横向排序。

能力簇使用：`coding_agent`、`general`、`knowledge_work`、`scientific_reasoning`、`multimodal` 或 `other`。Coding / Agent 证据单独成簇；DeepSWE、Terminal-Bench、CyberGym 等名字先根据原始页面判断其是 benchmark、排行榜、模型/Agent 项目还是讨论帖，不能只看名字归类。

### Artificial Analysis 方法变更

AA 记录 `current_version`、`previous_version`、`evaluation_changes`、`weight_change`、`current_weights`、`previous_weights` 和 `impact_explanation`。任务替换、类别权重变化、单项权重变化和模型成绩变化是四个不同字段。

只有方法说明或变更日志明确支持时，才能写“该变化可能使某类能力在总榜中占比变大/变小”；不能从排名截图单独推出因果。无法取得方法说明时，保留检查 URL 和原因，所有权重与影响写 `unknown`。不要填写 `causal_share`，因为单个模型的排名损失还可能来自分数、样本、归一化、并列和可比性变化。

例如，分析“Coding 指标很高但 AA 总榜不突出”时，应并排展示：AA 版本与组成、AA 类别/单项权重、Coding 能力簇分数、通用/Agent 能力簇分数、测试条件和比较总体。结论使用“与这些条件一致的观察”或“需要进一步验证的假设”，不直接写成权重导致的确定因果。

## 写作和发布

独立报告的可读顺序是：业务标签与限制 → 每百万 token 价格表 → 渠道/供应商/路由条件 → 榜单能力簇 → AA 方法变化 → 来源和可比性边界。报告中的每一行都能回到 claim；报告生成后保存 SHA-256。

将报告写入现有模型子 Wiki 的根级 H1“商业与定价”。它是该子页的一章，不新建同名模型页；写入后登记真实 heading block ID，并重新回读正文、表格、链接和报告哈希对应的关键片段。图片可以作为来源证据，但截图本身不能替代原始方法说明或价格页。
