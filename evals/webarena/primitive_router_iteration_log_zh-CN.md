# WebArena Cross-Template Primitive Router 迭代日志

日期：2026-08-18 起
目标：在代表性问题子集上迭代 V9 router，记录每次假设、修改、route-only/E2E 效果与失败原因；冻结最佳版本后重新运行完整 held-out。

## 实验纪律

- 当前 156-task held-out 已被分析，因此后续作为 development set，不再称为 untouched final test。
- 不手写 primitive；library 只能由 gold-admitted TRAIN workflows 经 pipeline 生成。
- 不通过简单降低 `skip` 门槛扩大覆盖率；任何新增曝光都必须满足 contract 边界。
- 小 subset 先做 route-only，再做 E2E；未改善或破坏正例的版本不进入 full run。
- 每版保留代码差异、任务列表、路由变化、成功率、步骤、timeout 和任务级 Win/Loss。

## 版本与审计约定

- 长期实验分支：`primitive-router-iterations`。
- `V9` 作为冻结基线；之后按 `V10`、`V11` 递增，不覆盖旧 library、compact result 或 summary。
- 每轮先提交代码与测试，再生成带版本号的 library snapshot；开发集通过门禁后才创建完整
  156-task 结果目录。
- 每个版本必须在本日志记录：假设、修改位置、prompt/guard/induction 差异、涉及 case、route-only
  变化、配对 E2E 变化、是否 promotion、代码 commit、library 路径、结果路径和复现命令。
- Git 只保存代码、测试、manifest、library snapshot、compact results、summary 和 case 分析；大型
  trajectory/run 目录保留在本地并记录路径，不直接提交。
- 同一轮 scratch/primitive 使用冻结模型配置、split、evaluator 与纯 GCR deployment；任何环境或
  protocol 变化必须单列，不能与算法变化合并解释。
- 每轮结论区分 `retrieved → exposed → incorporated → execution-reached → acceptance/fallback → result`；
  provenance marker 不能替代 execution evidence。

标准命名：

```text
primitive_rt_library_v10_<change>/
primitive_router_v10_dev_results/
primitive_router_v10_full_results/
primitive_router_v10_summary.json
```

## Iteration 0：V9 全量基线

完整报告见 [primitive_rt_v1_official_report_zh-CN.md](primitive_rt_v1_official_report_zh-CN.md)。

- Scratch：65/156（41.67%），18.404 steps。
- Primitive：62/156（39.74%），18.019 steps。
- Route：use 11、adapt 29、skip 116。
- use：4 Win / 0 Loss；adapt：4 Win / 7 Loss；skip：12 Win / 16 Loss。
- 116 个 skip 拆分为：57 router no-safe-match、29 exhaustive guard、18 chained guard、12 contract verifier reject。
- 只有 33/56 个 TRAIN templates 至少贡献一个 admitted workflow；TRAIN 总 admission 为 55/168。

## Environment validation：新 GCRSANDBOX410 Map

目的：在 router 迭代前确认新 Map 不是端口存活但实际链路损坏，并避免新旧 Map 环境混跑。

本机 tunnel 映射：远端 Map `:3000` → 本机 `:13000`；本机 `:3000` 已被 PID 1153346 的 python3 占用。

验证结果：

| 检查 | 结果 |
|---|---|
| hosts | 大小写 FQDN 均解析到 `127.0.0.1` |
| Map frontend `:13000` | HTTP 200 |
| frontend CSRF | token 存在，长度 86 |
| frontend `/search?query=Carnegie Mellon University` | HTTP 200，结果页包含 CMU |
| Nominatim `:8085` | 返回 CMU `40.4441897, -79.9427192` |
| OSRM car `:5000` | `Ok`，5687.2m / 7.44min / 7 steps |
| OSRM bike `:5001` | `Ok`，5662.8m / 27.63min / 15 steps |
| OSRM foot `:5002` | `Ok`，5533.2m / 73.92min / 29 steps |
| tile `:8080/tile/12/1173/1543.png` | HTTP 200，PNG 11310 bytes |

根路径访问 OSRM `:5000-5002` 返回 HTTP 400 是缺少 route 参数的预期行为，不是服务失败。

发现的问题：

1. `primitive_rt_deployment_v1.json` 原先仍指向旧 EC2 Map；已切换到 `http://GCRSANDBOX410.redmond.corp.microsoft.com:13000`。
2. 现有 V9 Map package 的 `search_places` 与 coordinate router 仍硬编码旧 `18.208.187.221:8085/:5000`，foot route 仍引用旧 EC2 frontend。
3. 因此旧 Map package 不能直接用于新 endpoint 的后续 E2E；必须通过 pipeline 从新环境 source workflows 重新生成，不能手工改 primitive 后冒充 induction 结果。

下一步：先用新 deployment 跑一个官方 Map smoke；通过后冻结开发 subset，并开始 router Iteration 1。

### HTTP 并发压力测试

测试位置是 agent 所在 VM，经 SSH reverse tunnel 访问 GCRSANDBOX410；因此数字包含隧道 RTT。全部请求为只读 GET，不执行 mutate task。单端点逐级测试并发 8/16/32/64；混合流量继续测试 64/128/192/256/300。

实例 1 的 `4499/7870/7880/10099/8123/8988` 在本机均立即 `ConnectError`，对应端口没有监听，说明 `webarena-tunnel@1` 尚未映射到这台 VM。本节只测实例 0 与共享 Map，不能据此声称实例 1 已通过压力测试。

单端点并发 64：

| Endpoint | 成功 | RPS | p50 | p95 | 观察 |
|---|---:|---:|---:|---:|---|
| Shopping | 128/128 | 49.18 | 1.181s | 1.253s | 零错误，吞吐接近平台 |
| Admin | 128/128 | 31.88 | 1.838s | 1.977s | 零错误，吞吐接近平台 |
| Reddit | 128/128 | 21.74 | 2.694s | 2.902s | 零错误，吞吐接近平台 |
| GitLab | 128/128 | 15.46 | 3.069s | 7.638s | 零错误，但尾延迟明显 |
| Wikipedia | 128/128 | 377.71 | 0.138s | 0.171s | 静态读取压力很低 |
| Map Nominatim | 128/128 | 121.48 | 0.270s | 1.012s | 零错误 |
| Map tile | 128/128 | 101.06 | 0.294s | 0.954s | 零错误 |
| Map OSRM car | 128/128 | 390.84 | 0.134s | 0.186s | 零错误 |
| Map OSRM bike | 128/128 | 373.13 | 0.135s | 0.192s | 零错误 |
| Map OSRM foot | 128/128 | 370.77 | 0.139s | 0.199s | 零错误 |

Map Rails frontend 是唯一明显的单点瓶颈：并发 8 和 16 时吞吐都约 4.9 RPS、p95 约 6.3s；并发 32 时仍只有 4.84 RPS，p95 上升到 12.45s。因此 Map agent task 并发不能按 OSRM/Nominatim 的高吞吐估计。

八类端点混合流量结果（Shopping、Admin、Reddit、GitLab、Map frontend、Nominatim、tile、OSRM car 等权轮转）：

| 并发 | 成功 | RPS | p50 | p95 | p99 |
|---:|---:|---:|---:|---:|---:|
| 64 | 128/128 | 39.14 | 0.340s | 1.909s | 2.692s |
| 128 | 256/256 | 38.38 | 0.562s | 3.907s | 5.608s |
| 192 | 384/384 | 38.69 | 1.250s | 5.568s | 7.934s |
| 256 | 511/512 | 38.65 | 3.667s | 8.296s | 10.780s |
| 300 | 599/600 | 38.35 | 5.040s | 10.791s | 12.614s |

并发 256 和 300 各出现一次 `RemoteProtocolError`，分别落在 tile 与 Nominatim；错误率均低于 0.2%。从并发 64 开始总吞吐已经稳定在约 38–39 RPS，继续增加并发只增加排队和尾延迟，并不增加吞吐。

结论：HTTP 服务/隧道可以承受 300 个同时请求而不崩溃，但“能承受 300 HTTP requests”不等于“适合并发 300 个完整 agent tasks”。完整 task 会启动浏览器、加载多个 assets、反复导航并调用 LLM；当前 agent VM 只有 24 cores，而且 Map frontend 与 GitLab 的尾延迟会放大。后续 E2E 建议总并发先用 16，Map 每实例最多 4，GitLab 最多 4；实例 1 tunnel 开通后再考虑把 Shopping/Admin/Reddit/GitLab 分摊到两套环境。
# 2026-08-18：156-task 一次性并发基础设施压测

在开始 V9 router 开发子集迭代前，先用 frozen T2 的全部 156 个任务做了一次真实 scratch
并发压测。非 Map 在 AWS/GCR0/GCR1 间轮询，Map 在 AWS/GCR 间轮询。完整配置、逐 deployment
结果和限制见：[primitive_rt_concurrency156_stress_report_zh-CN.md](primitive_rt_concurrency156_stress_report_zh-CN.md)。

核心结论：GCR 端点在客户端峰值期间持续健康；先达到的是 24 核 agent 客户端的启动上限
（约 752 个 Chromium 进程、load 约 177）。AWS Admin 15 个任务中 14 个墙钟 timeout，AWS
Map 23 个中 10 个 timeout，因此正式大规模运行不能把这些 timeout 解释为 primitive
regression，也不应继续依赖 AWS Admin。压测还暴露并修复了 official adapter 在缺少
`final_state.json` 时直接崩溃的问题。

## Iteration 1 / V10：完整候选集门禁

### 假设

V9 的主要可归因 regression 不是“primitive 一律无用”，而是 router 把 partial/query-scoped
collection 当成了可供全局 reducer 使用的候选全集。典型错误包括：在一页 contributors 上取
`most`、在一页 reviews 上总结 `key aspects`、用 caller 猜测的 query family 枚举所有折扣商品。

本轮只增加一条通用不变量：任务若要对一个 population 做 extrema/ranking/aggregation、主题总结或
无边界复数枚举，selected collection 必须声明 `completeness=complete`，或提供显式
`retrieval_mode=all_pages`。较大的 `page_size`、多 query union 和 `conditional` 本身都不能证明完整。

### 实现

- `cross_task_eval.py`：扩展 collection schema key；增加 population reducer 检测与 all-pages
  完整性证明；不修改 primitive 实现。
- `audited_primitive_retrieve.py`：修复 V9 遗漏，metadata surface 现在会把 library 中已有的
  `guarantees` 交给 LLM router 和 deterministic guard。此前字段虽被 induction 生成，却在
  retrieval 时丢失。
- `replay_primitive_contract_guard.py`：增加无 LLM、无浏览器的冻结决策重放工具，只测当前 guard
  对历史 selected primitive IDs 的影响。
- 测试：增加 partial contributor/review/open-world product 拒绝用例，以及 explicit
  `all_pages` order-history 保留用例。相关测试共 88 个通过。

### 冻结开发集 route-only 结果

产物：[primitive_router_v10_guard_replay.json](primitive_router_v10_guard_replay.json)

| 转换 | 数量 |
|---|---:|
| use → use | 4 |
| adapt → adapt | 6 |
| adapt → skip | 5 |

- 保留的历史 Win：18、19、117、118、148、251、252、337。
- 被降为 skip 的历史 Loss：215、246、309、312、368。
- 尚未处理的历史 Loss：250（正确 Map 候选已取得但 100-step 未完成）、335（GraphQL UTC/raw
  timestamp 与网站展示日期语义不一致）。它们不是候选集完整性问题，不在本轮加 task-specific
  规则。

注意：这是 deterministic guard replay，不是新的成功率结果；下一步必须跑 paired E2E，确认 skip
能恢复 scratch 行为且保留的正例没有受 metadata surface 变化影响。

### 无效 E2E 尝试（不计入结果）

2026-08-19 00:11 UTC 尝试以纯 GCR、总并发 4 启动 15 个 scratch。15/15 均在第一次模型请求
前以 step 0 退出，`runtime_errors.jsonl` 一致记录 public OpenAI Responses API `401`。后续对比
V9 有效 trajectory 确认：V9 使用 `gpt-5.4` + `https://gateway.phyagi.net/api/responses`，
而本次命令遗漏 gateway model modifier，错误回退到 `gpt-4o` + public endpoint。同一 key
对 gateway 的最小请求返回 HTTP 200，所以 key 未失效，根因是试验启动配置漂移。

GCR Shopping/Admin/GitLab/Map 在启动前 HTTP 检查均为 200，因此这不是站点超时，也不是算法
regression。无效产物保留在 `primitive_router_v10_dev_{runs,results}` 供审计，但不进入任何成功率、
步数或 timeout 统计；有效重跑使用分支内冻结的 `model.gateway54.yaml` 并写入新目录。

### 有效 paired E2E（15-case dev2）

冻结配置：纯 GCR、`gpt-5.4` gateway、总并发 4、每站点并发 2、单任务 900 秒。产物保存在
`primitive_router_v10_dev2_{runs,results}`。

| 指标 | Scratch | Primitive |
|---|---:|---:|
| 全部 15 case 成功 | 7/15 | 9/15 |
| 被实际曝光的 7 case 成功 | 5/7 | 4/7 |

9/15 不能解释成 primitive 提升：148、309、312 的 route 都是 `skip`，solve prompt 与 scratch
字节相同，三次翻转只能算本轮采样差异。只看非 skip 的配对，本轮是 1 Win（250）、1 个正式
scored Loss（19）、1 个 agent incomplete（251，答案本身正确），其余无变化。

逐类观察：

- 18：`use get_route_summary`，双方都对，12→10 steps。
- 19：同一 primitive 得到了 gold 对应的 `0:12/1:44`，但最终回答保留歧义的 H:MM 文本且只说
  driving faster；scratch 还给出相差 92 分钟，因此前者被 fuzzy evaluator 判错。这暴露的是
  duration contract/consumer formatting 问题，不是 route acquisition 失败。
- 117：router 选了完整 GraphQL orders、两个 partial HTML list 和 auth 共四个 primitive；虽双方
  都对且 25→13 steps，但集合明显冗余。完整 GraphQL 的 `all_pages` 已足够。
- 118：单个 multi-search，双方都错，16→18 steps。
- 250：单个 `search_places`，scratch 错、primitive 对，16→7 steps；这是本轮唯一严格可归因 Win。
- 251：primitive 找到并提交了正确 gold 坐标，但探索中生成的脚本先因精确字符串匹配失败，最终在
  28 steps 后以 `agent_timeout_or_incomplete` 结束，未进入 official evaluator。它是可靠性/成本
  regression，不是事实 acquisition 错误。
- 252：单个 `search_places`，双方都对，31→26 steps。

### 独立 recall/trajectory 审计

两个独立审计得到一致结论：不能因为 live router 把 148/337 skip 就放松 population guard。

1. V10 population guard 只直接挡住 215/246/309/312/368；117/148/335/337 的变化来自 LLM
   contract verifier 与候选选择方差。
2. verifier 把 runner 已提供的 `base_url`/credentials 当成 task intent 必须明说的 semantic input，
   并混淆 API 内部认证、浏览器登录态和普通参数。
3. 117 缺少“最小充分集合”剪枝：complete GraphQL acquisition 应支配两个 partial HTML fallback，
   随后无消费者的 auth helper 也应删除。
4. 当前 completeness 检查还有 precision bug：只要 schema enum *支持* `all_pages` 就放行，没有确认
   本次 proposal 真正绑定了 `retrieval_mode=all_pages`（以及从第一页开始）。
5. marker 不能证明执行：117 没调用原函数但吸收了 endpoint/pagination 策略；148/337 复制了 detail
   primitive 却没调用。后续 instrumentation 必须区分 exposure、copy、call、return 和 consumed output。

因此 V10 不 promotion，也不启动 156-task full run。V11 的最小方向是：显式提供不含秘密值的 runtime
binding availability；proposal 声明每个 primitive 的调用 bindings；guard 检查本次 all-pages binding；
同一 acquisition role 只保留最小充分集合。335/337 的 storefront display date 语义应先由 induction
补进 typed contract，不能靠 task ID 特判 router。

## Iteration 2 / V11：typed atomic Map package、行为门禁与消费运行时修复

### Router recall 修正

保留 V10 population guard，不用放宽门禁换 recall。V11 增加：

- runtime context 只声明 runner 能提供的 base URL、credentials/session 等 binding 类型，不把这些
  deployment binding 错当成 task intent 必须明说的语义输入；
- proposal 为每个 primitive 明确写 invocation bindings；`all_pages` 只有本次调用真正绑定
  `retrieval_mode=all_pages, page_number=1` 才能作为完整候选集证明；
- 对同一 acquisition role 做最小充分集合剪枝，complete GraphQL collection 支配 partial HTML
  fallback，并删除随后不再被消费的 auth helper。

### Map induction/consolidation 迭代

没有手写 package；所有候选仍由 16 个 admitted Map workflows 经 extraction、batch update 和
consolidation 生成。流水线新增的通用约束包括：

1. public primitive 必须是 async Playwright 方法；active package 中每个 primitive 独立可执行；
2. 禁止硬编码 source deployment origin，也禁止把后端路径伪装成前端相对路径；允许从
   `page.url` 推导 origin，再从站点自身 asset/config 发现 backend；
3. route 必须返回 typed `duration_seconds`，并保留 Map 的 H:MM 语义和小数距离；
4. client-side query-family loop 属于 workflow orchestration，不生成公开 multi-search primitive；
5. optional schema property 不再当作 guaranteed output；merge/split 不得丢失 source input mode 或
   typed output fact；
6. consolidation 可接收真实 behavior smoke feedback，失败 attempt 可恢复，旧 proposal 可在 validator
   更新后重验，不必重复 LLM generation；
7. 拒绝 Python Playwright `APIResponse.raise_for_status()`、全页通用 Close selector、raw Locator/DOM
   返回等已观察到的运行时缺陷。

最终候选 package：`primitive_rt_v1_library_v11_atomic/map/final_candidate/package.py`，公开三个原子
能力：单 query 地点搜索、文本端点路线、坐标端点路线。multi-search 明确不在 active surface。

行为 smoke 的演进：

- 早期候选：search 通过；coordinate route 可正确解析 `8.4km / 0:12 / 720s`；text route 因全局
  Close 把 Directions panel 一并关闭而失败；
- 删除通用 Close 后：text input 存在但 hidden，暴露 selector/UI-state 问题；
- 将失败日志作为 consolidation feedback 后：生成候选改为显式展开 Directions，并只选 visible
  controls；
- 最终 `behavior_smoke_v8.json`：search、text route、coordinate route 全通过，multi-search 按设计
  skipped。

### 两层消费运行时 bug

第一轮 5-case 重跑虽然得到 5/5，但 task 250 的脚本仍写着“Playwright runtime unavailable”，实际
通过 scratch HTTP fallback 完成，不能归因为 primitive。根因有两层：

1. 直接用 `.venv/bin/python` 启动 outer agent 不会自动把 `.venv/bin` 放进 agent shell PATH；
2. 初次修复对 `sys.executable` 使用 `.resolve()`，而 venv Python 是指向系统 Python 的 symlink，
   `.resolve()` 又把 PATH 错误恢复成 `/usr/bin`。

最终 runner 保留未解析的 `sys.executable` 绝对路径，把其 parent 放到 PATH 首位并设置
`VIRTUAL_ENV`。子进程验证确认 `python` 指向当前 repo venv 且能 import Playwright。新增 symlink
回归测试后，相关测试 84 个通过。

### 归因验证（开发集，不是正式 cross-template test）

为避免把 exposure/marker 当作执行，修复后只重跑最有区分度的 task 250、252，并检查 final script
中的真实 await call：

| Task | Scratch | V11 primitive | 真实行为 |
|---|---:|---:|---|
| 250 Apple Store near Pitt | 错，16 steps | 对，6 steps | `await search_places(...)` |
| 252 Tokyo Japanese Food Store | 对，31 steps | 对，6 steps | `await search_places(...)` |

task 250 是本轮严格的 wrong→correct；task 252 保持正确并消除 25 steps 长尾。收益来自 typed
site acquisition：agent 不再自行发现 backend、反复尝试 query/解析坐标和修补运行环境。该开发集
包含 induction source/same-template 实例，只用于验证机制与修 bug，不能作为正式 unseen-template
成功率。下一步才是在 frozen T2 上运行正式 Map/full held-out。

### Frozen T2 Map：第一轮与 consumer acceptance 修复

正式 unseen-template Map T2 共 19 个任务。第一轮 V11 primitive 为 9/19，已有 clean scratch 为
14/19；但逐 task 配对显示 14 个 `skip` case 的 solve prompt 没有 primitive material，单次采样自己
产生 3 Win、8 Loss，不能归因给 primitive。真正曝光 primitive 的 5 个 case 是 0 Win、2 Loss、
3 unchanged：

- 73：adapt search，双方正确，17→6 steps；
- 80：use route，双方正确，17→13 steps；
- 81：use route，primitive 返回两个 null duration，consumer 仍提交 SUCCESS，16→5 steps 且错；
- 287：use route，双方正确，13→5 steps；
- 364：use route，primitive 已取得正确 `1.7km`，但 consumer 把 endpoints/duration 一起提交，
  13→5 steps 且错。

这两个 Loss 说明静态 contract 正确仍不够，consumer 还需要统一的 post-call gate。新增两条非
task-specific 规则：

1. primitive 正常返回不等于 accepted；任务必需字段必须 present、non-null、non-empty 且类型正确，
   否则立即用 scratch acquisition 补该 fact，禁止提交失败的 primitive output；
2. final answer 只投影用户请求字段，primitive 返回的 endpoint、duration、distance、identity、
   provenance 等辅助证据若未被请求必须省略。

targeted E2E 结果：

- 81：错/5 steps → 对/13 steps；scratch 为对/16 steps。null output 不再被提交，fallback 得到
  walking 18min + driving 31min；
- 364：错/5 steps → 对/7 steps；scratch 为对/13 steps。最终答案严格为 `1.7km`。

因此修复后 5 个 exposed Map case 全部保持正确，平均 8.8 steps，对应 scratch 15.2 steps，下降
42%。这是 exposed-subset 的机制结果，不把 14 个 skip case 的随机翻转计入 primitive 因果效果。

### 四站 V11 重建：Shopping consolidation 接缝修复

GitLab、Shopping、Shopping Admin 使用与 Map 相同的 V11 induction/consolidation pipeline 重新生成；
没有手写 package。GitLab 10/10、Shopping 10/10、Admin 15/15 workflow extraction 通过，最终分别
得到 8、9、11 个 primitive。

Shopping 第一次 consolidation 连续 20 次失败并非模型没有做 feature 分类。失败 proposal 的 SPLIT
已经给出 `feature_assignments=["auth", "orders"]`，两个 replacement ID 也分别包含 `auth` 和
`orders`；validator 却忽略自己 schema 中的 `feature_assignments`，又要求 replacement 重复写
`feature`，最终把两者读成 `None`。修复后的确定性 manager：

- 要求 `feature_assignments` 与 replacements 一一对应；
- replacement 省略冗余 feature 时按位置补齐；
- 显式 feature 与 assignment 冲突或数量不等时拒绝；
- 不从 primitive ID 猜分类，也不修改生成代码。

修复后直接重验已保存的第 20 次 proposal，零次新 LLM 调用即通过，Shopping 生成 9 个 primitive。
相关全套测试为 105/105 通过。四站 mechanically composed package 位于
`primitive_rt_v1_library_v11_all/`，均可 import；GCR 两套 GitLab/Shopping/Admin/Reddit、共享 Map
共 9 个任务端点在 E2E 前均返回 HTTP 200。

### Release 前独立 contract 审计

独立审计确认四站 public operation 均为 async，且没有直接返回 Locator/DOM；同时记录以下需要由
router guard、behavior smoke 或下一轮 regeneration 处理的风险，而不是人工改 package：

1. GitLab contributors acquisition 没有完整分页/排序，只能视为 partial，不能支持 population
   ranking/reducer；
2. Admin review detail 声称 complete/absence proof，但字段缺失时会返回 null/0/空串；consumer 必须
   拒绝未满足任务字段的返回并 fallback；
3. Admin review page count 的 alias 可能混淆 pending 与 total，需行为 probe；
4. 少数 Admin primitive 仍暴露 `row_text`/`cells_text` 等 opaque 辅助字段，不能让这些字段代替 typed
   task facts；
5. Shopping 的 auth/orders SPLIT 暴露 bearer token，且自然语言 requires/provides 不能机械闭包。
   这是 package boundary 风险；后续应让认证成为 primitive 内部 helper 或标准化 session state，不能
   通过人工编辑当前候选掩盖。

这些风险不等于全部候选无效；下一步先在 15 个高信息 dev case 上观察实际 route/call/fallback，再用
同一通用规则触发必要的 pipeline regeneration。完整 156-task T2 只在该门禁通过后启动。

### V11 15-case dev3：precision 保留，recall 缺口定位

四站 V11 初版在 15 个历史高信息 case 上为 10/15，平均 12.27 steps。该总分混合了 10 个 skip
case 的重新采样，不能直接解释成 primitive 效果。按 route 分解：

| route | case 数 | 正确 | 平均 steps |
|---|---:|---:|---:|
| use | 2 | 2 | 7.5 |
| adapt | 3 | 2 | 8.0 |
| skip | 10 | 6 | 14.5 |

安全性方面符合预期：旧 contributors/reviews population Loss（309、312、215、246）均被
completeness/chained guard 转为 skip，本轮都正确；它们不计 primitive Win，但证明 exposure regression
已被消除。Map 18、250、251、252 真实 incorporation 单个最小 primitive，4/4 正确。

剩余问题分为两类：

1. task 19 的 route acquisition 正确且得到 `duration_seconds`，consumer 却把 Map 的 `0:12/1:44`
   原样写进答案。新增通用消费规则：typed canonical value 用于比较和答案构造；H:MM 等紧凑站点显示
   必须从秒数渲染成显式 hours/minutes。targeted rerun 从错/6 steps 变成对/5 steps，答案为
   `driving: 12 minutes, walking: 1 hour 44 minutes`。
2. Shopping 117/148/337 都被 skip。根因不是 router 过严，而是 consolidation 把原本完整的“认证 +
   GraphQL 全分页 orders”拆成公开 bearer-token primitive 和单页 orders primitive，能力从 complete
   降为 partial。

因此新增 consolidation 不变量：

- public output 不得暴露 token/password/cookie/secret；
- SPLIT 不得引入 bearer token 等新的公开中间输入；
- complete/absence-proof source 必须至少有一个覆盖其 required facts 的 standalone complete
  replacement；
- validator 升级后，历史上已经 accepted 的 proposal 也必须重新审计，不能只重验 rejected proposal。

现有 Shopping attempt 20 被新 validator 准确拒绝四项；pipeline 根据反馈自动生成 attempt 21/22，
最终保留一个 standalone `shopping/orders/list_authenticated_customer_orders`：认证和分页均在内部，
本次调用可绑定 `page_number=1, fetch_all_pages=true`，同时移除 public bearer token。final package 从
9 个收敛为 8 个 primitive，没有人工编辑生成代码。

targeted E2E：

| Task | V11 初版 | 修复后 | route / 真实行为 |
|---|---:|---:|---|
| 117 earliest order | 错，27 steps，skip | 对，3 steps | use；真实 await all-pages primitive |
| 148 Sep-2022 order item | 对，28 steps，skip | 对，10 steps | use；complete orders 后 scratch detail |
| 337 latest target order | 对，10 steps，skip | 对，8 steps | use；真实 await all-pages primitive |

Map exposed 五个 case 使用最终消费规则后为 5/5，复用的 frozen scratch 为 2/5；平均 steps 从 16.0
降至 7.6（-52.5%）。18、19、250 为 wrong→correct，251、252 保持正确。该数字是用于机制开发的
高信息 subset，不替代完整 T2 报告。

### Full T2 启动检查

V11-all 冻结为 GitLab 8、Map 3、Shopping 8、Shopping Admin 11 个 generated primitives；Reddit
没有 gold-admitted package。第一次 full 启动发现 missing Reddit index 被错误当成 FileNotFound，立即
终止，所有被中断的 process error 均不计结果。修复为“站点无 package / 空 package = 无 LLM 调用的
deterministic skip”，测试后用全新 `full3` 目录重启。启动前相关测试 108 个通过；full3 使用纯 GCR、
64 个总 worker、每站最多 16 个 lane、task-id round-robin 两套 deployment（Map 共享一套）。

### Full3 原始结果与三类可修复 regression

`reuse_split_v1_eval_results_v11_full3/` 已完成 156/156，原始落盘结果为 76/156（48.7%），平均
11.70 steps，中位数 11，5 个 timeout。与此前冻结的 scratch（63/156、17.07 steps、34 timeout）
直接配对得到 31 Win / 18 Loss，但该总差异不能归因给 primitive：120 个 route=skip case 自己就有
23 Win / 15 Loss，说明旧 scratch 的 deployment、timeout 和采样状态不是同轮可靠控制。真正曝光代码的
36 个 use/adapt case 为 20/36，对应旧 scratch 15/36；配对 8 Win / 3 Loss。这个子集提供机制信号，
但最终数值必须等待同 runner、同 GCR pool 的 fresh scratch。

原始 use/adapt 三个 Loss 逐轨迹审计后分成三个不同层次：

1. **task 234，答案适配器错误，不是 primitive 错误。** complete all-pages orders primitive 正确返回
   37 条订单，证明没有 on-hold order；consumer 写出 `status=NOT_FOUND_ERROR` 与字符串 `NONE`。
   official adapter 只把 JSON null 归一成 `N/A`，因此相同 absence 语义在旧 scratch 中判对、primitive
   中判错。现改为由结构化 `NOT_FOUND_ERROR` 权威决定 official textual answer=`N/A`，不再依赖 agent
   自选哨兵字符串；离线重评分从 0 变为 1。
2. **task 276，Retrieve acquisition 与 Navigate final state 混淆。** 任务要求浏览器停在具体搜索结果
   URL，router 却把只返回 GraphQL 商品 JSON 的 primitive 判为 use。现在 `task_type` 作为权威 runtime
   context 进入 router；NAVIGATE 的 use 必须由 primitive 自身建立目标 live page/URL/DOM，API/data-only
   acquisition 不能关闭 final-page acquisition。route-only 重放已从 use 变为 skip。
3. **task 251，坐标搜索不能证明街道侧向拓扑。** `search_places` 只返回单 query ranked candidates 与
   坐标；任务核心是 museum side of street。primitive 返回空后虽触发 scratch fallback，exposure 仍把
   consumer 锚定到错误的 S Craig stop。新增窄而通用的 deterministic rule：包含 side-of-street /
   opposite / across 关系时，若 contract 没有 geometry/bearing/side/road relation 证据，place search
   不得 pre-planning exposure。普通 `near` 不受影响，因此 task 250 的 Apple Store 正例仍可召回。

另修复两项评测/审计基础设施：

- official evaluator 子进程失败前先删除旧 `webarena_final_state_eval.json`，禁止读取 stale score；
- guard 把 proposal 降为 skip 时同步清空 `primitive_ids` 和 `primitive_calls`，避免“实际无注入但审计记录
  仍像计划调用”的假阳性。

上述修改后相关测试 95/95 通过。task 276 与 251 的 route-only 记录位于
`primitive_router_v11_navigate_guard_runs/`；两条都为 skip，未注入 primitive code。

### Fresh scratch 同轮控制

第一次 fresh scratch 启动误用系统 Python，156 条均在 0 steps 处产生
`agent_process_infrastructure_error`；这批不是 benchmark observation，保留作 invalid attempt 且不计分。
随后使用与 primitive arm 相同的项目 venv、PYTHONPATH、official task/evaluator、GCR deployment pool、
64 workers / 每站 16 lanes 重新启动。有效结果写入同一结果根并覆盖对应 invalid record；最终 paired
统计只接受 `scored_correct`、`scored_incorrect` 或 agent timeout/incomplete，绝不把 0-step infra error
当成错误答案。

### Full3 Loss targeted 修复结果与 query-retry 消费规则

三条原始 use/adapt Loss 的 targeted 结果：

| Task | Full3 原始 | 修复后 | 结论 |
|---|---:|---:|---|
| 234 no on-hold order | use，错，3 steps | 同产物离线重评分正确 | NOT_FOUND textual adapter bug |
| 251 museum-side bus stop | adapt，错，8 steps | skip，对，13 steps | coordinates 不足以证明 street-side topology |
| 276 search navigation | use，错，10 steps | skip，真实页面正确，11 steps | API search 不能关闭 NAVIGATE；URL host case adapter bug 同时修复 |

task 276 的 live final URL、标题和结果页都正确，但 deployment placeholder 是大写 hostname、Magento
canonical redirect 是小写 hostname；官方 URL matcher 对 netloc 做大小写敏感比较，产生假 0。adapter
现在只把 URL authority 规范为小写，路径和 query 保持原样，之后仍调用 pinned official evaluator。
targeted 重新评分为 1。274、275、276、277、278 五个 Shopping search NAVIGATE route-only 重放均
为 skip，说明规则覆盖模板族而不是单 task hardcode。

Map place search 还有一个 attribution 问题：Full3 中 249/250/252/257 的 literal query 为空后，consumer
绕开 vendored method，手写同类 backend fallback。新增消费规则要求 query-scoped primitive 先用少量由
当前 goal 推导出的短名/别名重试同一 method，并按 stable ID 去重；query family 仍不被视为 exhaustive，
也不支持 absence proof。代表集结果：

| Task | 修复前 | query-retry 后 | 真实行为 |
|---|---:|---:|---|
| 249 West Penn heliport | 对，7 steps | 对，9 steps | 同一 primitive 依次执行 4 个 alias query，不再手写 backend |
| 250 Apple Store near Pitt | 对，7 steps | 对，5 steps | literal 空；primitive alias family 命中并按 place_id 去重 |
| 252 Tokyo store | 对，6 steps | 对，5 steps | workflow 选取简洁 query，primitive 首次命中 |

三条均正确，合计 steps 20→19；更重要的是，收益链条从“marker 存在但核心 fallback 是 scratch”变成
了可审计的真实 primitive call。相关产物在 `primitive_router_v11_query_retry_results/` 与同名 runs 根。

此外，Navigate saved-state adapter 增加 live form-state snapshot 合约：在 `page.content()` 前把当前
input value/checked、textarea value、select option selected 镜像回 HTML markup，不改变页面值。这样
pinned official `program_html` evaluator 恢复的是最终 live form state，而不是只含初始 attribute 的 stale
DOM。该规则将先在 Map task 761 targeted E2E 验证，再进入下一轮完整 primitive run。

### Fresh scratch 最终控制组

有效 fresh scratch 使用与 treatment 相同的 official task/evaluator、项目 venv、GCR deployment pool、
64 个总 worker、每站最多 16 lanes，最终完成 156/156。运行中产生的四个临时 process-error 占位由
调度器自动重跑覆盖；最终目录中没有 infrastructure error：

| 指标 | Fresh scratch |
|---|---:|
| Success | 95/156（60.9%） |
| 平均 steps | 12.95 |
| 中位 steps | 12 |
| agent timeout/incomplete | 7 |

按站点：GitLab 16/21、Map 24/46、Reddit 2/2、Shopping 23/40、Shopping Admin 30/47。
结果根为 `reuse_split_v1_eval_results_v11_scratch_fresh/`，轨迹根为
`reuse_split_v1_eval_runs_v11_scratch_fresh/`。

完成后只对确定性的 `url_match` task 重新调用 pinned official evaluator，不重评带 LLM 方差的 fuzzy
string task。第一次重评遗漏 `OPENAI_API_KEY`，25 个 adapter subprocess 全部在模型配置初始化时报错，
没有改写 task score；带同一运行 key 重试后 25/25 成功，其中 5 个 GitLab task（44、45、156、258、
357）因 URL authority 大小写规范化从假 0 修正为 1。上述 95/156 已包含这五项确定性修正。

### Browser primitive 的运行时 acceptance 缺口

Map task 761 的第一次 route=use 轨迹证明：`get_route_summary` 真实执行并把 From、To、Foot mode 写进
页面，但目标 `Hunt library CMU` 未被站点 geocoder 解析；primitive 返回
`result_page_contains_distance=false` 且 distance/duration 为 null，页面输入也带 error class。consumer
仍把“函数正常返回、URL 进入 /directions、mode 已选择”误当成任务完成，official program_html 判错。

这不是 router precision 问题，而是执行后的 acceptance 问题。通用消费规则现要求：browser-changing
primitive 必须同时检查 typed success/evidence fields 与 live page；false result-presence、未解析/带 error
的表单、或预期结果区域缺失都必须记录 `acceptance_failed` 并执行 scratch fallback，不能仅凭函数返回、
URL 改变或 mode 选择宣布成功。direct use/adapt 也必须写
`primitive_execution_trace.jsonl` 的 entered/completed/acceptance/fallback 生命周期事件。该规则对应测试
50/50 通过；task 761 targeted E2E 未通过前不进入 full4。

第一次 acceptance-only targeted 已正确记录
`entered → completed → acceptance_failed → fallback_used`，但仍为 0/14 steps。轨迹显示 fallback 找到
正确两端坐标并拼出 walking route URL，却没有通过站点 UI 解析最终控件：隐藏 To 是坐标、可见 To 被
覆盖回未解析的 goal literal。路线事实等价不等于 NAVIGATE final-page state 等价，因此该失败方案保留，
不进入 full run。

随后把既有 query-retry 规则推广到“semantic input 是站点 search/autocomplete query”的 primitive：
literal 为空、未解析或带 error 时，workflow 可用少量 goal-derived alias 重新调用同一个 primitive；
每次 retry 独立做 acceptance，全部失败后才 scratch fallback。该修改不改变 generated package，也不
放宽 router guard。task 761 第二次 targeted 为 1/6 steps，真实轨迹为
`entered → completed → acceptance_failed → entered(alias) → completed → acceptance_passed`；第二次
primitive 调用由 `Hunt Library` 得到站点 canonical `Hunt Library, ... Pittsburgh ...`，最终 DOM 与
walking mode 同时通过 official program_html。产物位于
`primitive_router_v11_runtime_alias_retry_results/` 与同名 runs 根。

进入 full4 前四组相关测试 102/102 通过。full4 使用与 fresh scratch 相同的 156 个 T2 task、official
evaluator、纯 GCR pool、64 总 worker / 每站最多 16 lanes；结果根为
`reuse_split_v1_eval_results_v11_full4/`。

### Full4：当前最佳消费规则的 156-task 配对结果

full4 完成 156/156。与 fresh scratch 相同，只对已完成的 `url_match` task 做 pinned official evaluator
确定性重评分；primitive 的 22 条 URL 记录均未改变原分数。最终配对结果：

| Arm | Success | 平均 steps | 中位 steps | timeout/incomplete |
|---|---:|---:|---:|---:|
| fresh scratch | 95/156（60.9%） | 12.95 | 12 | 7 |
| primitive full4 | 99/156（63.5%） | 11.79 | 11 | 6 |
| Delta | +4 task / +2.6 pp | -1.16 / -9.0% | -1 | -1 |

全体配对为 25 Win / 21 Loss / 74 both-correct / 36 both-wrong；但 125 个 route=skip task 没有
primitive exposure，其 16 Win / 18 Loss 只能作为采样方差，不能归因给 library。真正有因果解释价值的
31 个 exposed task：

| Route | N | Primitive success | 配对 | Scratch→Primitive steps |
|---|---:|---:|---:|---:|
| use | 14 | 13/14 | 6 Win / 1 Loss | 13.57→6.57（-51.6%） |
| adapt | 17 | 11/17 | 3 Win / 2 Loss | 17.47→8.00（-54.2%） |
| 合计 | 31 | 24/31 | **9 Win / 3 Loss** | 15.71→7.35（-53.2%） |

所有 31 条均有 generated code incorporation；30/31 写出 execution trace。唯一未写 trace 的 task 19
在 final script/log 中明确执行两次 `get_route_summary`，因此仍归类为 actual execution，而非 exposure-only。
完整结果位于 `reuse_split_v1_eval_results_v11_full4/`，轨迹位于
`reuse_split_v1_eval_runs_v11_full4/`。

按站点的总体分数必须结合 skip 方差理解：GitLab 16/21→11/21（全部 skip）；Map 24/46→34/46；
Reddit 2/2→1/2（无 package，全部 skip）；Shopping 23/40→21/40；Shopping Admin 30/47→32/47。
机制收益主要集中在 Map route/place 与 Shopping complete orders acquisition，不应把 GitLab/Reddit 的
skip 重采样下降解释为 primitive regression。

### Full4 三条 exposed Loss 的根因

1. **Map task 19：acquisition 正确，差值呈现不满足 canonical scalar。** primitive 正确返回 driving
   720 秒、walking 6240 秒；consumer 输出 `1 hour 32 minutes`，而 official string reference 接受
   `92 minutes`。新增规则要求算术差值始终包含单一显式单位的 canonical scalar；compound duration
   可以附加但不能替代。
2. **Shopping task 96：partial SUCCESS。** primitive 正确返回 latest order/status，但 task 同时要求
   arrival/ETA，route 自己也把 ETA 写进 remaining gap。consumer 仍提交“status=Canceled，arrival
   unavailable”的 partial SUCCESS；scratch 因站点确实无法提供所需完整答案而返回 NOT_FOUND 并判对。
   新增规则要求所有 requested website-fact gap 都是 mandatory：scratch 补齐，否则整个任务
   NOT_FOUND_ERROR，不能提交 primitive 已提供的局部字段。
3. **Shopping task 336：backend timestamp 与站点显示日期跨日。** complete orders primitive 和 item
   filtering 都正确；GraphQL `2023-01-17 02:25:53` 被直接格式化为 Jan 17，但订单历史 UI 与 gold 是
   `1/16/23`。新增规则：没有 display-date/timezone contract 时，raw backend/UTC timestamp 不得关闭
   “when/date” acquisition，必须从 site-visible date 补齐。

三条都是 consumer/contract boundary，而非“primitive 函数没执行”或“放宽 router 即可解决”。三条
通用规则通过 102/102 测试，下一步在 19/96/336 做并行 targeted E2E；通过后才决定是否跑 full5。

## 2026-08-19：V12 Loss 修复、qualified-population gate 与 Full5

### Task 19：第一次修复假设被 E2E 证伪

第一版把问题归因于“差值缺少 92 minutes”，但 targeted E2E 仍为 0/6：consumer 把 walking
`1h44min` 统一改写成 `104 minutes`，并附加题目未明确要求的派生差值。真正边界是：typed canonical
值用于校验和计算，但 source quantity 的最终呈现应保留站点/参考答案对齐的显式形式；只有当前 goal
明确要求数值差时才增加差值字段。修改后 task 19 为 1/5，实际执行两次 route primitive，并记录
entered/completed/acceptance；答案同时保留 `1:44 (1 hour 44 minutes)` 与 `0:12 (12 minutes)`。同族
task 17 仍为 1/5，未产生正例回归。产物位于 `primitive_router_v12b_dev_results/` 与同名 runs 根。

### Task 96：安全 recall，而不是放宽完整性

旧 route 把 complete orders primitive 降为 skip，因为 verifier 用“整个任务还缺 ETA”否定了已经闭环的
订单列表 acquisition。V12 规定：`primitive_calls.closed_acquisition` 只能声明 contract 实际保证的局部
站点操作；若一个局部 acquisition 闭环、另一个 task-required website fact 仍缺失，应为 adapt 并把后者
写入 remaining gap，而不是过度声明 use 或整体 skip。verifier 评估最窄的 contract-supported closed
acquisition，仍禁止 partial search/collection 冒充完整候选集。

targeted 对照：旧 skip 路径 1/24；V12 adapt 路径 1/8。primitive 真正执行 complete all-pages orders
acquisition，得到 latest status `Canceled`；workflow 按事务语义推出“will never arrive”，而不是把 arrival
写成 unavailable。正确率相同，步骤下降 66.7%。这证明 recall 修复有实际消费收益，不只是 route 标签变化。
V12 还要求 remaining_gap 只能来自当前任务，router 不得擅自增加 comparison/difference/ranking。

### Task 336：完整列表不等于完整 qualified candidate set

V12 早期版本仍会 adapt complete order list。E2E 再次复现 0/10：订单列表不含 `conditioner` line-item
资格字段，consumer 被 backend order timestamp 锚定，准备另行查询 items 后直接使用 UTC 日期。这说明
“collection completeness”只回答所有订单是否齐全，不能回答满足 qualifier 的候选集是否齐全。

新增 `unclosed_qualified_population` exposure hazard：当任务对满足 Y 的记录做 first/latest/most/absence
reducer，而完整 collection 不输出 Y 时，只有 contract-closed enrichment 同时满足以下条件才可曝光：

1. 每个 capability `requires` 必须精确出现在 runtime available states 或已选 primitive `provides`；
2. enrichment identifier 必须由 earlier output 明确保证，不能把 `order_number` 猜成 site-local `order_id`；
3. API 内部登录不等于 browser authenticated session，除非 metadata 明确 `provides` 该状态。

为了减少 LLM 对依赖闭包的脑补，pipeline 先机械生成 `candidate_capability_reachability`，列出每个候选的
`unmet_capability_requires`，再交给 semantic risk classifier；该字段是 authoritative。Task 336 中
`get_order_detail` 缺 `shopping.authenticated_customer_session`，且 order list 只保证 order_number，因此
qualified enrichment 不闭环，最终 route=skip。Task 96（latest order status）和 task 117（first purchase
date）没有额外缺失 qualifier，分别保持 adapt/use；task 117 E2E 仍为 1/6。

这里保留了一次失败方案：只在 verifier prompt 中写“complete-but-unqualified 不够”仍有方差，模型会
脑补隐式 session/identifier。改成预计算 exact capability closure 后才得到可审计的 veto。当前相关测试
为 104/104 通过。

### Task 761 的一次无效开发运行

`primitive_router_v12b_dev_results/task761_primitive.json` 的 0 分不能计入回归：它误用了
`skillnet_pilot_v1.json`（retrieve-only）运行官方 `program_html` NAVIGATE task。最终 route URL、From 和
To 都正确，但 prompt 未要求在 `page.content()` 前镜像 live select state，序列化 HTML 中 Foot option
没有 `selected` attribute；离线 evaluator 恢复后 selectedIndex 从 live 2 退回默认 0。随后已改用
`navigate_pilot_v1.json` 重新验证；该任务不属于 156-task retrieve-only Full5。

### Full5 启动配置

第一次启动误用了工作树中后来被改写的 `reuse_split_v1.json`；该文件当前只有 59 个 T2 task，不再是
fresh scratch/full4 的冻结 membership。发现时立即停止，已完成结果保留在
`reuse_split_v1_eval_results_v12_full5/`，整轮标记为 invalid split attempt，不参与任何配对。

正式 Full5 从 Full4 落盘的 156 个 `_task_splits` manifest 机械恢复
`reuse_split_v1_t2_156_frozen.json`。恢复后验证 task ID 与 fresh scratch 156/156 完全相同；站点计数为
GitLab 21、Map 46、Reddit 2、Shopping 40、Admin 47，共 57 个 held-out templates。正式结果根为
`reuse_split_v1_eval_results_v12_full5_156/`，运行轨迹根为
`reuse_split_v1_eval_runs_v12_full5_156/`。配置保持同一 V11 generated package、official WebArena
task/evaluator、纯 GCR deployment pool、64 workers、每站 16 lanes。Scratch 继续冻结为
`reuse_split_v1_eval_results_v11_scratch_fresh/` 的 95/156，不因 treatment 迭代重采样。Full5 只改变
router/verifier/consumer contract，不手写或修改 primitive code。

启动后对 156 membership 做 evaluator-type 审计，又发现历史 manifests 把所有任务统一写成 retrieve；实际
官方 evaluator 中 125 条为 string-match retrieve，31 条为 navigate（20 url_match、6 program_html、5
url+program_html）。Task 761 的 select-state 假回归正是该错误接口的直接证据。因此上述 `_156` treatment
也在出结果前停止，不能与旧 95/156 控制配对。

最终冻结 `reuse_split_v1_t2_156_mixed_frozen.json`：task IDs/站点/templates 不变，只按 pinned official
eval type 写 per-task `retrieve|navigate`。两臂从同一 mixed split 同轮重跑；scratch 与 primitive 各 32
workers、每站 8 lanes，总上限 64。Navigate 两臂都启用 vanilla interface，agent 不看到 NAVIGATE 标签，
只收到通用 live final-state capture 合约；router 仍可用 evaluator type 执行 API-only navigation safety
guard。正式目录：

- scratch：`reuse_split_v1_eval_results_v12_mixed_scratch/` 与同名 runs 根；
- primitive：`reuse_split_v1_eval_results_v12_mixed_primitive/` 与同名 runs 根。

### V12 mixed：156-task 同轮正式结果

两臂均完成 156/156，汇总器验证 312 条记录全部存在，task/site/template/task_type 身份一致，
`run_status` 全部 terminal，且 scratch 中没有 route、workflow 或 primitive 暴露。为同时保留运行期目录
隔离与可复现配对，运行结束后只复制 compact result JSON 到
`reuse_split_v1_eval_results_v12_mixed_paired/`；其 `summary.json` 为本节权威统计。

| Arm | Success | macro-template accuracy | 平均 steps | correct-only steps | timeout/incomplete |
|---|---:|---:|---:|---:|---:|
| scratch | 93/156（59.6%） | 61.1% | 13.20 | 11.57 | 9 |
| primitive | 100/156（64.1%） | 61.7% | 11.90 | 10.47 | 9 |
| Delta | **+7 task / +4.5 pp** | +0.6 pp | **-1.30 / -9.8%** | -1.10 / -9.5% | 0 |

全体配对为 20 Win / 13 Loss / 80 both-correct / 43 both-wrong。由于 skip 会重新采样 agent，
总体 +7 中只有 exposed 子集可作 primitive 因果解释。131 个 skip 为 13 Win / 11 Loss；这两个净 Win
是独立采样差异，不归因给 library。

真正曝光 primitive 的 25 个 task 为：

| Route | N | Primitive success | 配对 | Scratch→Primitive 平均 step delta |
|---|---:|---:|---:|---:|
| use | 17 | 13/17 | **6 Win / 1 Loss** | -7.59 |
| adapt | 8 | 6/8 | 1 Win / 1 Loss | -4.50 |
| 合计 | 25 | **19/25（76.0%）** | **7 Win / 2 Loss** | **-6.60** |

在 exposed 的 12 条 both-correct 上平均也节省 4.83 steps，因此降步数不是只由“更快答错”造成。
25 条中 24 条检测到 vendored code incorporation，24 条写出 execution trace；task 117 是
incorporated 但无 trace，task 236 有真实 trace 但 marker-based incorporation 未命中，后续必须结合
final script/raw trajectory，而不能把 marker 当 execution ground truth。

按官方 task interface：retrieve 76/125→81/125（+4.0 pp），navigate 17/31→19/31（+6.5 pp）。
按站点的总体变化为 GitLab 13/21→13/21、Map 25/46→29/46、Reddit 2/2→1/2、Shopping
21/40→23/40、Shopping Admin 32/47→34/47；其中未曝光站点/任务的变化仍只解释为采样方差。

强正例集中在两类可复用机制：

1. complete authenticated-order acquisition：task 117、231、232、235 均为 use Win；后三个 primitive
   分别 3/3/5 steps，而 scratch 为 18-step wrong、32-step timeout、18-step wrong。
2. typed Map acquisition：task 248、761 为 use Win，task 236 为 adapt Win；已命名实体查询、最终
   directions state 或候选固定后的 route operator 能替代高成本 scratch acquisition。

两个 exposed Loss 都是 primitive 实际执行后被错误接受，不是函数没有运行：

- task 224：route 返回结构有效，但候选 discovery 未闭环。consumer 先把类别词解析到 Maine，fallback
  后又只找到 Warren, PA，最终接受 235km/3:19；scratch 枚举 Pittsburgh 的多个 Wendy's 后得到 3min。
- task 249：精确 heliport query 为空后，alias 丢掉实体类型约束；Hospital 记录有合法名称和坐标，
  `choose_candidate()` 在无语义匹配时默认取第一条，错误把医院中心当 heliport。

二者共同说明：contract-level typed/parse success 不等于 task-semantic acceptance。下一版不写 Map、
Wendy's 或 heliport 特判，而验证两条跨网站不变量：（1）开放候选尚未固定时，下游 operator 只能
late-bind；（2）query reformulation 不得放松任务中的 identity/type/scope 约束，无语义匹配时禁止默认
取第一条并必须 scratch fallback。这两条面向 WebArena、WebVoyager 与 Odysseys 共用消费层。

## V13：通用 late binding 与语义验收

V13 没有增加站点名、实体名或 WebArena task ID 特判。改动按任务结构定义：当目标要求在开放候选集中做
nearest/closest/vicinity/阈值选择，而所选 primitive 只拥有 route/detail 等下游 operator、不拥有完整的
candidate acquisition 时，router 保留 use/adapt，但添加 `late_bind_required`。consumer 必须先用 scratch
建立并验证具体候选记录，写出 `candidate_set_ready`，之后才能把稳定 identity/ID/coordinates 传给
primitive；原始类别词或未解析名称不能作为首次调用参数。

同时，consumer prompt 区分 contract acceptance 与 task-semantic acceptance：typed record 能证明解析成功，
不能单独证明它就是目标实体；query reformulation 也不得改变 identity、kind/type/category/role、
parent/scope 或 locality 约束。Induction prompt 对新库增加对应的 typed identity discriminator 保留要求，
但没有手改当前 generated package。相关 retrieval/build/eval targeted tests 共 102 条通过。

10-task E2E 小集尚在运行时，task 224 已给出关键验证：V12 为 adapt Loss（3h19），V13 仍然 adapt，先用
scratch 获取 10 个候选并记录 `candidate_set_ready`，选定具体候选后才调用同一个 route primitive，最终
11 steps 正确输出 3min。这说明修复来自组合顺序改变，而不是简单减少 primitive recall 或把任务 skip。
task 249 则仍为 use Loss：精确查询为空后，consumer 虽看到通用语义验收提示，仍删除实体 qualifier，
把 parent entity 记录当成目标并写 `acceptance_passed`。因此仅写抽象的“不要弱化约束”还不够机械。

## V14 候选：冻结不可丢失的实体约束

针对 V13 暴露的通用缺口，V14 进一步要求 task layer 在首次查询前显式冻结目标 identity，以及所有明确的
entity-kind/type/category/role、parent/scope、locality qualifier。别名或缩短 query 可以暂时省略词以提高
recall，但 candidate acceptance 不得省略这些冻结约束；只共享部分名称的 parent、container 或 related
entity 不是同一实体。只有 canonical label 保留 qualifier，或 typed output 直接证明等价语义时才能接受；
若 output contract 两者都不提供，必须 scratch fallback。该规则不引用任何具体网站或 benchmark，面向
WebArena、WebVoyager 与 Odysseys 共用；retrieval prompt 单测 14/14 通过，随后在最小 E2E 集验证。

### V13/V14 小集结果

V13 的 10-task 小集相对冻结 V12 scratch 如下：18 为 both-wrong（两臂都取得正确 route facts，但官方
string-match 需要特定单位格式）、19 为 both-correct 且 18→7 steps；117、248、761 为 use Win；224
由旧版 adapt Loss 变为 both-correct；249 仍为 use Loss；252 为 use both-correct；236 与 251 都为 skip，
其差异不归因 primitive。暴露 primitive 的 8 条合计 3 Win / 1 Loss / 3 both-correct / 1 both-wrong。

V14 在 8-task 回归集保留了 117、224、248、250、252、761 的正确结果；236 为 skip 后 scratch 错误。
task 249 的 failure mode 从“错误接受 parent entity”变成“正确拒绝所有不满足 identity 的候选并
fallback”，但 fallback 只尝试了一个不可达公共 backend 就过早提交 `NOT_FOUND_ERROR`，所以官方仍为
0 分。V14 因此是 safety improvement，不是 accuracy fix。其最初批量启动有一次缺 `PYTHONPATH=src` 的
立即 import failure，目录 `primitive_router_v14_dev_*` 作废；正式小集目录为
`primitive_router_v14b_dev_{runs,results}`。

## V15：冻结 scratch plan 与完整 fallback gate

V14 证明自然语言 identity guard 能阻止 false acceptance，但同一 agent 在看到 primitive endpoint 后做的
fallback 仍可能被曝光锚定。V15 增加两个 benchmark-independent 控制：

1. 可选 `--scratch-first`：在任何 library metadata/code 可见前生成 task-only scratch plan；primitive 只能
   patch 一个具名 step，验收失败必须执行该 step 的原 scratch fallback。该开关已接入批量 runner，默认
   仍关闭，便于和 direct router 做受控比较。
2. 对不支持 absence proof 的 partial/query-scoped acquisition，empty、alias empty 或单个 backend 不可达
   均不能推出 NOT_FOUND。只有 source-independent 且覆盖任务范围的 fallback 完成后才允许 NOT_FOUND；
   trace 新增 `fallback_completed`、`source_independent` 和 `acquisition_complete_for_scope` 字段。

同时把 V14 过严的 exact-label 文案改成 semantic facets：合法缩写、拼写、本地化或 typed-category alias
必须在看候选前冻结；每个 facet 可由 canonical label、pre-frozen alias、typed field、stable ID/URL 或
detail heading 支持，但不得看过候选后临时发明 alias。这避免把规则写死为英文字符串包含关系，适用于
WebVoyager/Odysseys 的缩写和本地化页面。相关 runner/retrieval/trace tests 为 63/63 通过。

单 task 先验：task 249 在 scratch-first 下仍为 adapt；primitive 精确查询执行后因 0 candidates 被拒，
随后回到冻结的同站 scratch acquisition，通过站点本地接口找到正确目标，官方从 V14 的 0 分翻为 1 分，
仅 7 agent steps；冻结 scratch control 为正确、13 steps。运行目录为
`primitive_router_v15_scratchfirst_{runs,results}`。接着在 8-task 代表集验证该机制是否保留既有 Win。

### V15 8-task 回归

批量目录 `primitive_router_v15b_scratchfirst_{runs,results}`。相对冻结 V12 scratch：7/8 correct，
3 Win / 0 Loss / 4 both-correct / 1 both-wrong，平均 agent steps 13.13→8.75。761 是 skip 后的采样 Win，
不能归因 library；真正暴露 primitive 的 7 条为 2 Win / 0 Loss / 4 both-correct / 1 both-wrong。
V14 的唯一 exposed Loss 249 已变为 both-correct，但此轮 fallback 较长，为 16 vs scratch 13 steps；单 task
先验则为 7 steps，说明 fallback 路径仍有采样方差。117 和 248 保留 Win；224、250、252 在 both-correct
上分别节省 2、3、7 steps。V15 的 trade-off 是 safety 明显提高，但 scratch-first router 对完整命名 route
过保守：761 从 direct use 退为 skip，丢失一部分 step benefit。

## V16：恢复 checkable named-entity recall

V16 只改 scratch-first metadata router 的通用判据：不能把“可由 primitive 输出验证的 disambiguation”误当成
必须再次执行的 acquisition。对有限、完整命名实体的 lookup/route，只要 primitive 同时返回请求事实和足以
执行 preserved acceptance checks 的 resolved identity fields，就可 patch acquisition；单实体 lookup 不要求
population completeness。该例外不适用于先发现开放候选集、或在未知实体中做 nearest/all/best 的任务。

四个边界 E2E 全部正确：249 adapt/7 steps，连续第二次消除旧 Loss；761 从 skip 恢复 adapt/7 steps；
236 仍保留开放 pharmacy discovery、仅 patch named lookup 和 per-candidate route，并从 scratch wrong 翻为
correct/8 steps；224 同样保留开放候选 discovery，correct/11 steps。目录为
`primitive_router_v16_named_recall_{runs,results}`。随后补跑 117/248/250/252 后冻结最终开发版本。
