# Amazon cheapest:闸的模式必须匹配任务真值(以及 cheapest 在电商上 ill-posed)

**日期:** 2026-07-16 ｜ 触发:用户亲手走 init → build 闭环,选了
"Find the cheapest {product} on Amazon and return its brand and price"。

## 一句话

**skill 一直是好的;那次拒收 100% 是 `verify` 模式选错了。** 同一批 runs:
strict 拒 1 次,shape **两次都一抽落库**。

## 因果链(完整)

1. `init` 给 skill.yaml 写了 `verify: strict` —— **当时它对所有任务都默认 strict**;
2. 任务答案是**价格**(会自己漂);
3. trash bags 那条训练答案抓到了 **`$0.01` 的垃圾链接**(转瞬即逝的假真值);
4. 重放时该链接已消失,读到 `$5.99`;
5. strict 要求逐字等于训练答案 → `$5.99 ≠ $0.01` → **拒收,库空,一小时白跑**。

**关键证据:另外两条(卸妆水 `Golf Professional $1.39`、鼠标 `Lovskoo $1.99`)在
重放时精确复现。** 即闸没冤枉 skill,它忠实报告了"第 3 条的训练答案漂走了"。

## 结论:模式 × 真值 必须匹配

| 答案会不会自己变 | 例子 | 该用 |
|---|---|---|
| 会 | 价格、库存、榜单、"今日热销" | **`--verify shape`**(非空 + 形状) |
| 不会 | 时刻表、规格、ID、评分、历史计数 | **`--verify strict`**(复现原答案) |

**已修**:`init` 现在自己判断 drift 并写对模式(commit `37bceb6`),yaml 里附理由、
可覆盖。实测三条全对(卸妆水→shape;最早直飞→strict;Best Seller→shape ——
第三条模型比我准,榜单确实每天重排)。

## 更深一层:cheapest 在电商上 ill-posed(本轮不修)

即使 shape 过了,这个 skill 会**忠实返回 Amazon `price-asc-rank` 第一名**。实测:

| product | 答案 |
|---|---|
| trash bags | `Acoolstore $0.01` |
| **phone case**(held-out,无模型 18s) | **`Hyprest $0.00`** |

**字面正确、意图垃圾。** agent 的方法是对的(用站点自己的排序,不是自己猜),
但"最便宜"在电商上根本没有有意义的唯一真值:$0.00/$0.01 的占位、诈骗、配件、
变体起价会稳定占据第一名。这与 flights 的 cheapest 是**同一个病**:

- **flights cheapest**:真值漂 + 有歧义(Best vs Cheapest)+ 随客户端;
- **amazon cheapest**:真值漂 + **排序第一名 ≠ 用户要的东西**。

→ 任务选型判据再加一条:不只问"页面是否声明、是否稳定、能否可靠提取",
还要问 **"站点声明的那个值,是不是用户真正想要的那个值"**。声明性锚点解决
"从哪读",解决不了"读的是不是对的东西"。

## 本轮顺带修掉的三个真 bug(都是用户手动体验逼出来的)

| bug | 症状 | commit |
|---|---|---|
| `pool.map` 按提交序返回 | 已完成的实例被慢的挡住不显示,像挂死 | `23cd7d5` |
| 用退出码判 solve 成败 | 杀掉的 run 明明写了答案,build 报 failed 而 learn 报 3/3 admitted | `04521fc` |
| `init` 一律默认 strict | 价格任务必拒,烧完一小时空手 | `37bceb6` |
| solve 期间零输出 | 10-60 分钟静默,读起来像卡死 | `0850179`(每 30s 报步数) |
