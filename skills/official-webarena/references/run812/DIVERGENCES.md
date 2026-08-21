# 最终配置：与 WebArena 官方 / webwright 原生的全部偏离

跑批身份：Webwright (gpt-5.4) × 原版 WebArena，**全部 812 题**。
非 mutate 438 题跑实例 2（并行，只生成不重放）；mutate 374 题跑实例 1
（按写入作用域分 103 条链，链内串行），跑完重置实例 1 后按序重放一次。
两条 lane 全程不共享部署。
基线：官方 `web-arena-x/webarena@dce04686`；webwright 分支 `official-webarena-eval-skill`。

---

## A. 与 WebArena 官方的偏离

### A1. Judge 模型 —— 无法消除，需知晓
| | 官方 | 我们 |
|---|---|---|
| 模型 | `gpt-4-1106-preview` | `gpt-4o`（网关解析为 `gpt-4o-2024-11-20`）|
| prompt / temperature / max_tokens / top_p / 解析 | — | **逐字、逐参数一致（已用官方源码比对验证）** |

phyagi 网关不提供 `gpt-4-1106-preview`；`gpt-4-turbo` / `gpt-4-0125-preview` / `gpt-4` / `gpt-4o-2024-05-13` 均探测为不可用，GPT-4 系列只有 `gpt-4o`。
影响：118/401 走 `fuzzy_match`（其中 36 个走 `ua_match`）。
可审计：每条结果 JSON 含 `judge_model` 与 `official_judge_model`；可用 `WEBARENA_JUDGE_MODEL` 覆盖。

### A1b. Judge 实现在两轮之间变了 —— 跨轮比较的混淆项
上一轮（`legacy/run_401_official`）的 `llm_fuzzy_match` / `llm_ua_match` 是**重写的 prompt**、
带一条官方没有的 system message、跑在 gpt-5.4 上；本轮是官方 `helper_functions.py` 本体，
仅模型 id 不同（见 A1）。

影响 118 个 `fuzzy_match` 任务与 36 个 N/A 判别任务。**本轮更忠实**，但这意味着这两类的
跨轮差异同时受 prompt 与评分函数影响，无法归因给任一方。实测这两类的翻转率也最高
（`fuzzy_match` 38%）。

### A2. 五个站点辅助函数曾被替身化 —— **已解除**
`gitlab_get_project_memeber_role` / `reddit_get_post_url` / `shopping_get_latest_order_url` /
`shopping_get_sku_latest_review_author` / `shopping_get_sku_latest_review_rating` 一度被替换为抛
`UnsupportedSavedStateError`：官方 `helper_functions` 依赖 openai v0 API（`openai.error`），
而 webwright venv 装的是 openai 3.x，模块整体加载失败后退回替身。

已把评测侧的 openai 降到 `0.27.0`，官方 `helper_functions.py` 整体正常加载，五个函数走本体。
webwright 自身只用 httpx 调模型，不依赖 openai 包，降级不影响 agent。
mutate 题里 45 个 `func:reddit_get_post_url('__last_url__')` 因此可正常评测。

### A3. 从保存态评测，而非活浏览器 —— 架构性
官方在活着的浏览器上评测。webwright 浏览器用完即弃，故冻结三通道到磁盘：
`answer` → `StringEvaluator`；`final_url` → `URLEvaluator` 与 `__last_url__`；
`final_state.html` → `HTMLContentEvaluator` 的 `url:"last"` 目标。
`url≠last` 的目标由 evaluator 自行实地导航（与官方一致）。

### A4. Agent 接口 —— 研究命题本身
官方是「观察 accessibility tree → 预测单步动作」；webwright 是「写 Playwright 脚本」。
不是缺陷，是被测对象；但意味着数字与官方 leaderboard 不同源。

### A5. Prompt 内容
给 agent：`intent` 逐字 + `start_url` + `storage_state` 路径 + 统一产物 spec。
不给：任务类型、`eval_types`、参考答案、凭据、homepage/password.html 提示、N/A 之外的行为诱导。

**实测**：804 条实际下发的 prompt，去掉 intent、start_url、storage_state 路径后
**结构变体数 = 3**，且每一种都由任务自身字段决定，没有一处来自 eval config：

| 变体 | 条数 | 触发条件 |
|---|---|---|
| 含登录段 | 657 | 任务带 `storage_state` 字段 |
| 不含登录段 | 142 | 任务无 `storage_state`（map / wikipedia 等） |
| 多标签段 | 5 | 任务 `start_url` 用 ` \|AND\| ` 连接多个 URL（431–435，intent 本身写着 "from my open tabs"）|

多标签段的内容是把 `start_url` 里的若干 URL 列出并要求各开一个 tab，
这正是官方 harness 对这类任务的机械行为，不是解题提示。

产物 spec 的性质等同 SkillWeaver 的统一附加指令。其中"从 `$WORKSPACE_DIR` 派生所有路径"
一条是对**交付物**的约束（脚本必须能在别处执行），不是对解题方式的引导；
与之同类的"运行时读取当前值"一条被**刻意排除**，理由见 A6b。

### A6. 任务集 812/812 —— mutate 与非 mutate 同口径，头条均取 inline
不再排除任何任务。**mutate 的头条数字与非 mutate 一致，都取 inline**（agent 这一集跑完后的站点状态），
replay 作为第二列单独报告。

本轮曾主张 mutate 头条取 replay，理由是 webwright 的完成门禁
（`src/webwright/agents/default.py:213`）要求 agent 把 `final_script.py` 真实执行在
`final_runs/run_<id>/` 里并通过 self-reflection，不过就改脚本重跑（实测 25.4% 的任务执行过不止一次），
而 mutate 里 60.7% 非幂等，因而 inline 是在被累积写脏的站点上评出来的。

**实测否定了这个前提。** 全量重放（干净态 + 每个脚本恰好一次）后：

| | inline | replay | 不一致 |
|---|---|---|---|
| 374 题 | 53.2% | 45.2% | 两边都可评的 310 题中仅 3.9% |

门禁重跑确实在站点上留下了重复对象（issue "404 for many URLs" 四份，间隔 25 秒），
但**它几乎不伤害分数**，因为创建/追加类任务的 evaluator 有 78.4% 用 `must_include`——
建三个副本仍然满足"必须包含 X"。真正受伤的只有 `exact_match` 检查累积值的相对量任务
（10 题，重放回收 +20%）。净影响 4 题。

replay 低于 inline 的 8 个百分点全部来自 64 个未产出可评产物的任务，
那是**脚本的可重现性问题，不是评测缺陷**，属于另一个研究问题。

### A6b. 相对量任务：硬编码的方向与直觉相反 —— 不加引导，如实计入
12 题形如"把价格降 5 美元"。原本担心 agent 会把探索时读到的值写死。实测相反：

- **硬编码绝对目标值反而使脚本幂等**（`fill("47.00")` 重跑仍是 47）
- **运行时计算才非幂等**（`original * 0.9` 重跑变成 0.81 倍），而 agent 以 7:1 压倒性使用运行时计算
- 生成前的 reset 使 agent 首次读到的就是真实原价，硬编码的值本身是对的

因此**未在 prompt 中加入"运行时读取当前值"一条**，这类损失（重放可回收 +20%，即 2 题）如实计入。

### A7. 部署环境
- 实例 2 的 `shopping_2` / `shopping_admin_2` 设 `web/url/redirect_to_base = 0`（改前该行未设置，默认 1）。
  不改任何 URL；不改则任何 host ≠ base_url 字面量时 302 死循环（并发+缓存穿透下必现）。
  回滚：`/data/ww_official/revert_redirect_to_base.sh`。
  **该设置已焊进 `/data/webarena/replica.sh` 的 `up` 流程**，否则每次 reset 都会退回默认值 1 并重新触发死循环；
  实例 1 / 2 / 3 现在都带此设置。
- 全链路 host 小写（Chromium 强制 `page.url` 小写）。
- 单实例承载全部并发。

### A8. 登录
与官方一致：使用任务自带的 `storage_state` 字段，由官方 `browser_env/auto_login.py` 生成。
注入严格跟随该字段——task8（map，`require_login=True` 但官方未给 `storage_state`）不注入。
机制差异：官方一次性交出已登录 context；我们在每次创建 context 时注入（见 B3）。

### A9. 纯 import 兼容替身（不影响判分）
`beartype` → 恒等装饰器（关闭运行时类型检查）；`browser_env.actions/utils` → `dict`。
`nltk` 已改用真库（`word_tokenize('11.5') == ['11.5']`）。

---

## B. 与 webwright 原生的偏离

### B1. 模型配置（`model_gateway_54.yaml` + `model.eval.yaml`）
| 项 | 原生 base.yaml | 实际生效 |
|---|---|---|
| `model.model_name` | 未设 | `gpt-5.4` |
| `model.openai_endpoint` | 未设 | `https://gateway.phyagi.net/api/responses` |
| `model.max_output_tokens` | 4000 | **16000** |
| `model.request_timeout_seconds` | 120 | **600** |
网关响应的 `model` 字段为 `gpt-5.4-endpoint-10`（疑为路由后缀，未与网关方确认）。

### B2. `environment.env` 注入
`PYTHONPATH=/data/ww_official/shim`、`WEBARENA_STORAGE_STATE=<该任务的 .auth 文件>`。

### B3. Playwright 运行时 shim（本次新增，webwright 无此机制）
`shim/sitecustomize.py` 经 PYTHONPATH 自动导入，为 `Browser.new_context` / `Browser.new_page`
的 `storage_state` 设默认值。agent 代码中无任何 `storage_state` 字样，登录动作计数为 0。
副作用：影响 agent 启动的**所有** Python 进程；`python -E` / `-S` 可绕过（未见发生）。

### B4. webwright venv 新增包
`nltk 3.10.3`、`openai 3.3.1`、`requests 2.34.2`、`text_generation 0.6.0`、`aiolimiter 1.2.1`。
均为 evaluator 依赖，webwright 自身不使用。**该 venv 与 `~/webwright` 主工作区共享。**

### B5. 分支本地改动（相对 e6fed17，182 增 / 72 删，两文件）
`official_webarena.py`：删任务类型泄露行、删凭据注入、删 `agent_response.json` 产物与其完成判定、
删 `normalize_not_found`、改产物标题与 answer 措辞、新增 `auth_state_for` / `auth_shim_config`。
`webarena_final_state_eval.py`：真 nltk 优先、官方 judge 逐字复刻、新增 `_load_official_helpers`
（当前加载失败见 A2）、`evaluate_saved_state` 接受 `auth_state_path`、结果记录 judge 模型。
官方 checkout 本身 **0 改动**（`git status` 干净，HEAD = `dce04686`）。

### B6. 调度
自建 `run_official.py`：64 workers / 每站点 12 lane / 单任务 900s 超时 / 可断点续跑。
`agent.step_limit` 保持原生 100。

---

## 需要你拍板的三处

1. **A1 judge 模型** —— 接受 gpt-4o 并在报告中注明，还是等网关上 `gpt-4-1106-preview`。
2. **A2 站点辅助函数** —— 跑 mutate 前是否投入修复（需解决 openai v0/v3 API 冲突）。
3. **A7 实例 3** —— 是否回滚其 `redirect_to_base`（当时仅作测试台）。
