# WebArena 156-task 一次性并发压测

日期：2026-08-18（UTC）

## 目的

一次性启动 frozen T2 held-out 的全部 156 个 task，判断瓶颈来自 agent 客户端、模型网关，
还是 WebArena deployment。本轮只跑 scratch；它是容量测试，不作为 primitive 效果数字。

## 配置

- split：`primitive_rt_template_disjoint_v1.json`
- 并发：156 个 task 同时启动；每个 task 独立 agent / Chromium 过程
- 每任务墙钟上限：900 秒
- 非 Map：AWS、GCR instance 0、GCR instance 1，按 `task_id % 3` 分流
- Map：AWS、GCR，经本机隧道的 `:13000`，按 `task_id % 2` 分流
- deployment pool：`primitive_rt_deployment_pool_v1.json`
- runner：`run_reuse_eval.py --workers 156 --per-site-workers 156 --round-robin-deployments`
- 原始运行：`primitive_rt_concurrency156_scratch_runs/`
- compact results：`primitive_rt_concurrency156_scratch_results/`

任务组成：GitLab 21、Shopping 40、Shopping Admin 47、Reddit 2、Map 46。

## 观测

### 客户端峰值

- 156/156 个 `cross_task_eval.py` 同时启动。
- Chromium 相关进程峰值约 752。
- 本机为 24 核、216 GiB RAM；load average 峰值约 177。
- 内存峰值不是问题：可用内存始终在 170 GiB 左右。
- 前 2--3 分钟是明显的浏览器启动风暴；随后 load 和浏览器数持续回落。

因此，本轮首先达到的是 **24 核 agent 客户端的 CPU / 调度 / I/O 上限**，不是 128 核
GCR 服务端的上限。

### GCR 服务健康

在客户端最拥塞时，对 GCR 的实时探测仍全部返回 HTTP 200：

- GitLab：约 0.31--0.39 秒
- Shopping：约 0.21--0.27 秒
- Admin：约 0.25--0.30 秒
- Reddit：约 0.33--0.35 秒
- Map：约 0.13--0.17 秒

没有观察到 GCR 站点级连接失败或 5xx。

### 900 秒内的完成情况

原始一次性运行中，155 个 task 写出了 compact result；Map task 255 因缺失
`final_state.json` 触发 runner 异常，没有写 compact result。该异常属于客户端评分适配器，
不是 Map 服务故障。

155 个 compact result 中：

- 正常进入 evaluator：116（62 correct、54 incorrect）
- `agent_timeout_or_incomplete`：39
- 其中真实墙钟 timeout：34
- 另外 5 个是 agent 自身结束但输出不完整，并未达到 900 秒

准确率不是本压测的有效结论：这轮 scratch workspace 仍能搜索仓库中的历史实验产物，且 156-way
超订阅显著改变了任务墙钟时间。

## Deployment 归因

| Deployment | 分配任务 | 正常评分 | incomplete | 墙钟 timeout | runner error |
|---|---:|---:|---:|---:|---:|
| GCR Map | 23 | 18 | 4 | 3 | 1 |
| AWS Map | 23 | 13 | 10 | 10 | 0 |
| GCR Shopping `:7770` | 15 | 13 | 2 | 1 | 0 |
| GCR Shopping `:7870` | 11 | 8 | 3 | 0 | 0 |
| AWS Shopping | 14 | 12 | 2 | 2 | 0 |
| GCR Admin `:7780` | 17 | 16 | 1 | 1 | 0 |
| GCR Admin `:7880` | 15 | 15 | 0 | 0 | 0 |
| AWS Admin | 15 | 1 | 14 | 14 | 0 |
| GCR GitLab `:8023` | 6 | 6 | 0 | 0 | 0 |
| GCR GitLab `:8123` | 5 | 5 | 0 | 0 | 0 |
| AWS GitLab | 10 | 8 | 2 | 2 | 0 |
| AWS Reddit | 2 | 1 | 1 | 1 | 0 |

由于只有两个 Reddit task，`task_id % 3` 恰好都分到了 AWS；本轮不能判断 GCR Reddit 的
真实 agent-task 容量。

## 结论

1. **GCR 新 deployment 足以承载本轮分配给它的流量。** 没有证据需要先增加 GCR worker
   或 container。
2. **AWS Admin 是明确失败点。** 15 个任务中 14 个墙钟 timeout；正式大规模运行不应再把
   Admin 分给该 deployment。
3. **AWS Map 明显弱于 GCR Map。** 在同一 156-way 压力下，墙钟 timeout 为 10/23，GCR 为
   3/22。
4. **一次性 156-way 对 24 核 agent 客户端过度超订阅。** 它可以启动全部任务，但会把 34 个
   长任务推到 900 秒上限；增加 WebArena container 无法解决客户端启动风暴。
5. 正式 scratch/primitive 配对实验建议使用 GCR deployment，并把 agent 执行移到 128 核主机，
   或在当前 24 核机把并发限制在经实测可稳定完成的区间。不要把本轮 timeout 当作模型或
   primitive regression。

## Runner 修复

压测暴露了一个确定性异常：official task 已写 `agent_response.json`、却没有
`final_state.json` 时，adapter 会直接读取缺失文件并使整个 job 成为 process error。现已改为在
进入 official evaluator 前检查 `final_state.json`；缺失时记录为
`agent_timeout_or_incomplete`，而不是评分基础设施崩溃。

修复后，在负载峰值结束后单独补跑 task 255：26 steps，正常评分且 correct。该补跑证明
GCR Map 本身可完成任务，但它不回填或改变上表记录的原始 156-way 压测归因。compact result
目录现在包含完整 156 个 task；分析一次性并发容量时必须把 task 255 标为 post-stress rerun。
