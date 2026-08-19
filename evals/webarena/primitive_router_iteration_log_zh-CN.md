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
