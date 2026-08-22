# ASI 库 × Webwright agent：跨 harness 迁移的结果与分析

2026-08-21，WebArena 实例 4，官方 cross-template 留出集。机器即将下线，本文是完整交接。

---

## 1. 一句话结论

**28 个 ASI 诱导函数注入了 220 道题的 prompt，被引用 0 次。**

这不是"跨 harness 迁移失败"，是**这个库本来就没有可迁移的东西**——它在 ASI 自己的 harness 里
就已经基本不被使用（28 个函数只有 5 个被调用过，覆盖 7% 的任务，且全部是 map）。

---

## 2. 跑了什么

| | |
|---|---|
| 库 | ASI 在 cross-template TRAIN（413 题）上诱导出的 28 个函数，冻结 |
| 测试集 | cross-template TEST，399 题（93 训练模板 / 97 测试模板，零重叠） |
| Agent | Webwright，`cross_task_eval.py` 的新 `asi` 臂 |
| 环境 | WebArena 实例 4，跑前 reset，指纹 `"drift": {}` |
| 模型 | gpt-5.4（phyagi 网关） |

**实际完成 220 / 399 题**：只读 lane 211 题全部跑完；写 lane（188 题 mutate）跑了 9 题后按要求中止。

---

## 3. 主结果

### 3.1 库的使用情况（不依赖任何对照，独立成立）

| 指标 | 值 |
|---|--:|
| 注入库的题数 | 220 |
| **引用过任一诱导函数的题数** | **0** |
| 照抄 bid 序列（如 `click('349')`）的题数 | 0 |
| 尝试 `page.get_by_test_id(<bid>)` 的题数 | 0 |

检测方式是**函数名匹配**，扫描每题的 `final_script.py` 和全部 `steps/*.sh`。
不用 marker 注释检测，因为 prompt 里没有要求 agent 保留 marker——要求它记录用法就预设了会用，
而使用率正是本臂要测的东西。这一点与 SkillWeaver 那个臂的做法一致
（`skillnet_hint.py:_marker` 的 docstring 写明了同一理由）。

`bid 抄写 0` 这一栏一度报成 1，是我的正则误报：`page.locator(...).select_option('1')` 是普通
Playwright 按 value 选项，被当成了 bid 调用。已改成只认**裸调用**（前面不能有 `.`）后归零。

### 3.2 准确率（**不可单独引用**）

| lane | task_type | n | 正确 | 通过率 |
|---|---|--:|--:|--:|
| read | retrieve | 156 | 98 | 62.8% |
| read | navigate | 54 | 27 | 50.0% |
| write | mutate | 9 | 4 | 44.4% |
| **合计** | | **219** | **129** | **58.9%** |

按站点：

| site | n | 正确 | 通过率 | 超时 | 库引用 | 中位步数 |
|---|--:|--:|--:|--:|--:|--:|
| wikipedia | 5 | 4 | 80.0% | 0 | 0 | 7 |
| shopping_admin | 51 | 34 | 66.7% | 0 | 0 | 11 |
| map | 57 | 36 | 63.2% | 0 | 0 | 11 |
| shopping | 61 | 33 | 54.1% | 0 | 0 | 9 |
| reddit | 4 | 2 | 50.0% | 0 | 0 | 11 |
| gitlab | 33 | 16 | 48.5% | 0 | 0 | 9 |

**超时 0**，判分成功 219/220。

**为什么不可引用**：配对的 scratch 对照臂没有跑。手头唯一的 scratch 基线是 8/20 的 full812 那轮，
它跑在不同实例、不同 prompt spec（旧 `FINAL_STATE_SPEC`）、不同 harness 上。
拿它比出来是 +1.0%（`analysis/vs_full812_scratch.txt`），但**这个数没有意义**：
库引用为 0，任何 delta 都不可能是库效应。splits/README §5 实测同批题重跑的任务级翻转率 21%，
399 题配对检验的 MDE 是 6.5%——±1.0% 完全在噪声里。

---

## 4. 为什么库没被用：库的形状问题，不是 harness 问题

28 个函数的参数构成：

| site | 函数数 | 有语义参数的 |
|---|--:|--:|
| shopping | 10 | **0** |
| shopping_admin | 7 | 2 |
| gitlab | 1 | **0** |
| map | 10 | 6 |
| reddit | 0 | — |

19/28 是纯 bid 序列包装器，典型形态：

```python
def open_recent_purchase_details(account_id, orders_id, period_id, product_id):
    click(account_id); click(orders_id); click(period_id); click(product_id)
```

每个参数都是 AXTree bid ——**每次渲染重新分配的元素下标**，不是元素身份。
只有第一个 bid 能从当前页面读到，其余要等它本该省下的那次导航发生之后才存在。
**必须先做完任务才能凑齐参数。** 而且调用之间没有观察，第一次跳转后即便猜对也会点错。

在 browsergym 里 bid 靠 `frame_mark_elements.js` 在每次 observation 时现场写进 DOM
（`get_elem_by_bid` → `page.get_by_test_id(bid)`）。Webwright 写的是独立 Playwright 脚本，
页面上没有这个属性，所以这些函数在这个 runtime 里**结构上不可执行**——
prompt 里明说了这一点，agent 也确实没去硬抄（bid 抄写 0）。

有真语义参数的那批不一样：`search_nearby_places(bid, location, place_type)` 只有 1 个 bid、
2 个语义参数——而 map 正是 ASI 自己 harness 里唯一用到库的站点。
**诱导质量取决于任务有没有显式的自然语言参数，而不是站点难度。**

---

## 5. 注入了什么（保真度）

注入块是 ASI 自己 `CustomActionSet.describe(with_long_description=True, with_examples=True)`
的输出，**逐字节冻结**，不是手工改写。保留了 ASI 自己的不对称
（`custom_action_set.py:163` 的 `add_code`）：

- browsergym 基础原语 → 签名 + 描述 + 示例，**无函数体**
- 诱导出的技能 → 完整 `inspect.getsource`，**含函数体**

ASI **没有检索**（`RETRIEVABLE_ACTIONS_DICT` 五个站点全空，那套 gte-Qwen2 top-k 是死代码），
所以本臂也不做选择，整站库原样注入。站点顺序follow数据集，与 ASI 的 `sites_for()` 一致（不排序）。

各站注入体积：

| 组合 | 字符 | 其中诱导部分 | 诱导占比 |
|---|--:|--:|--:|
| map+shopping_admin | 15319 | 11590 | 75.7% |
| map | 11481 | 7752 | 67.5% |
| shopping | 8955 | 5226 | 58.4% |
| shopping_admin | 7567 | 3838 | 50.7% |
| gitlab | 4280 | 551 | 12.9% |
| reddit | 3729 | 0 | **0%** |

每个块里固定有 3729 字符是 browsergym 原语说明。reddit 没有诱导产物，
所以它的 50 道题拿到的是一整块**在本 runtime 里一个都不能调用**的 API 文档，外加一句
"优先使用高层函数"——而一个高层函数都没有。这是保真的代价，按要求保留。

### 三处有意的偏离（全部记在 `PROMPT_FREEZE.json`）

1. **删**了 `agent.py:264-272` 的两个思维链示例和 "Only wrap the to-be-executed action in
   triple backticks"——它们教的是 ASI 的动作发射格式，与 Webwright 的 JSON+bash 契约直接冲突。
   实测 `format_errors: 0`，删对了。
2. **加**了一句：bid 是每次渲染分配的 AXTree 下标，本 runtime 不解析它。
   这是 hint 里唯一非 upstream 的文字。不加的话 agent 会照抄坏代码；加了才是说实话。
   先例是 skillnet 臂对相对 `page.goto("/x")` 的同类处理。
3. **不**要求 marker 注释、**不**要求 usage json（与 primitive 臂不同），理由见 §3.1。

保留了 `describe()` 末尾那句 `Multiple actions can be provided at once...`——它是 ASI 自己
`agent.py:88` 显式设 `multiaction=True` 的产物。担心它会让 agent 误以为能一次发多个动作，
实测 `format_errors: 0`，没有发生。

---

## 6. 过程中踩到并修掉的坑

按代价排序。每一条都曾**静默产生错误结果**，而不是报错。

### 6.1 harness 在跑批中途被并发修改（作废了 146 题）

`cross_task_eval.py` 在 21:29 那轮运行期间被改：`OFFICIAL_FINAL_STATE_SPEC` 中途取代了
`OFFICIAL_RETRIEVE_SPEC`，新 spec 不再要求 `agent_response.json`，但当时计分路径还在读它。
后果是 151 道已完成的 retrieve 题**分裂在两套输出契约下**（119 旧 / 32 新），
另有 15 题在过渡窗口内崩溃。分裂是事后靠哈希才发现的。

对策：`freeze_prompt.py` 把 harness、每个 spec 常量、库的 sha256 全部 pin 住，并渲染出
每个站点组合的完整 prompt；`guard_harness.py` 在跑批期间每 20 秒比对，漂移即报。
重跑前用它验证过实发 prompt 与冻结版本**逐字节一致**。

### 6.2 evaluator 的 401 让 32 题无法判分

`webarena_final_state_eval.py:_judge_call` 读 `OPENAI_BASE_URL`，没有就打 `api.openai.com`。
`~/.env` 只有 key，于是网关的 key 被发到 OpenAI 官方端点 → 401 → `evaluator_infrastructure_error`。
对照 primitive 臂的进程环境才发现它有 `OPENAI_BASE_URL` / `OPENAI_API_BASE`（指向
`https://gateway.phyagi.net/api`），它 0 个这类错误。补上后消失。

顺带确认：网关上 `gpt-4o`、`gpt-5.4` 可用，官方硬编码的 `gpt-4-1106-preview` 是
**404 model.not_registered**（HANDOVER §3 记的那个坑），adapter 已默认改用 `gpt-4o`。

### 6.3 `set -e` 静默跳过整条 188 题写 lane

`run_reuse_eval` 在有任何 `process_error` 时 `return int(failures > 0)` = 1，
`run_arm.sh` 的 `set -euo pipefail` 于是在只读 lane 结束后直接退出，**写 lane 一题没跑**，
脚本还报 exit 0。部分任务失败是正常结果，不该阻断下一条 lane。

### 6.4 `per_site_workers == workers` 让站点串行

`site_lanes()` 给**每个站点**建 `per_site_workers` 条 lane，全部丢进 `--workers` 大小的池。
两者相等时第一个站点的 lane 占满全部线程，其余站点饿死——正是 `lanes.md` §3 说明要避免的模式。
现象是"只有 gitlab 和 map 出结果"，而且 8 路全压单站导致 map 出现 2 个超时
（map 后端全实例共用）。改成每站 8 / 全局 48 后，六站点并行，**超时归零**。

### 6.5 auth 的两个坑

- `auto_login.main()` 用 `ThreadPoolExecutor` 且从不调 `.result()`，浏览器起不来会被吞掉，
  **报成功却什么都没写**。必须串行生成（`make_auth_inst4.py`）。
- `replica.sh reset` 销毁重建容器，**服务端 session 全清**，但 `storage_state` 文件还在、
  格式合法。失效表现是"元素找不到超时"而不是鉴权错误。reset 后必须重新生成。

### 6.6 `${1:?usage: ... {a|b}}` 的花括号提前闭合

`$ARM` 变成 `asi}`，argparse 拒绝，整轮空转。没有任务执行，但浪费了一次启动。

---

## 7. 数据在哪

```
EXPORT-2/webwright-asi-skill/
  FINDINGS.md                 本文：结论与分析
  RESULTS.md                  纯数字：判分状态、库使用、按站点/lane/type、逐题 220 行
  PROVENANCE.md               代码在哪个仓库、哪个分支、哪个 commit
  README.md                   目录说明与复现步骤
  PROMPT_FREEZE.json          冻结的 prompt + 全部哈希 + 偏离清单
  prompt_freeze/              10 个站点组合的完整 prompt 原文
  library/                    实际注入的 10 个块 + MANIFEST
  code/                       本臂全部脚本（9 个文件）
  results/                    逐题结果 json（220）
  analysis/summary_by_site.txt        按站点汇总
  analysis/per_task.json              逐题 lane / type / correct / steps
  analysis/analysis_asi.json          逐题库引用检测明细
  analysis/vs_full812_scratch.txt     与旧基线的临时对比（附不可引用理由）
  logs/                       完整运行日志
  splits/                     划分与 lane 定义
  trajectories-all-raw.tgz            全部 226 题的完整轨迹（读+写 lane）
  discarded_mixed_spec/       被作废那轮的结果与日志
```

**GitHub**（机器下线后唯一留存）：

| 仓库 | 分支 |
|---|---|
| `DEM1TASSE/Webwright` | `webwright-asi-skill-0821` |
| `DEM1TASSE/agent-skill-induction` | `asi-webarena-eval-0821` |

轨迹包 1.8G 不在 git 里，只在本导出目录。

---

## 8. 没做完的，以及下次该怎么做

1. **写 lane 188 题 mutate 只跑了 9 题。** 这是最大的缺口——mutate 恰是 ASI 原论文里
   差异最大的一档（+13.5%），也是 admin 那几个偏写操作的函数
   （`notify_customer_on_order`、`submit_report`）唯一可能被用到的地方。
   61 条写作用域链已经算好并冻结在 `code/serial_groups_test399.json`，直接可用。

2. **配对的 scratch 对照臂没跑。** 这是让 58.9% 变成可引用数字的唯一途径：
   同实例、同 spec、同 harness、同 lane 结构，中间 reset。只读 lane 约半小时。
   命令就是 `bash code/run_arm.sh scratch`。

3. **噪声地板仍未测。** splits/README §5 那个 21% 是端到端观测不一致率的**上界**
   （两次运行之间 prompt 和 harness 都改过），不是方差下限。真正的地板要用
   完全相同的系统跑两遍。在测出来之前，任何单次 delta 都不该下结论。

4. **值得单独看的一个观测**：map 的 6 个带语义参数的函数
   （`search_nearby_places`、`get_walking_directions_to_place` 等）是全库唯一
   bid-free 成分较高的部分，也是 ASI 自己唯一用过的。它们在 Webwright 里同样没被引用。
   如果要论证"带语义参数的诱导技能可以跨表示迁移"，这批是唯一的证据来源，
   而目前的证据是**否定的**。
