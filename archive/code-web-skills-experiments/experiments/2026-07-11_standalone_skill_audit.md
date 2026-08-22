# WebArena skill 裸跑审计:3/10

**日期:** 2026-07-11 ｜ 对象:eval_webarena_54 的 10 个 skill ｜ 方法:每个 skill 用自己
gold 通过的训练实例 taskspec 独立重放(无模型),答案与录得的 gold 答案精确比对。

## 一句话

**裸跑正确率 3/10。** eval 里 held-out 70% 的好数字是 agent+库的联合能力:agent 把 skill
当源码读、坏了就 adapt,7 个带病 skill 全被兜住,数字上零痕迹。"库对 agent 有用" 和
"库里的 skill 本身对" 是两个命题,之前只测过前者。

## 明细

| skill | 裸跑 | 死因 |
|---|---|---|
| route_time(demo 主角) | 2/2 ✓ | |
| top_n_bestseller | 1/1 ✓ | |
| total_reviews | 2/2 ✓ | |
| coordinates | 0/3 | 无视参数:三个地点返回同一坐标 |
| reviews_by_rating (t213) | 0/3 | 崩溃:goto 相对 URL,没从 taskspec.start_url 建基址 |
| ssh_clone_url | 0/3 | 提取选择器空 → RuntimeError |
| min_car_travel_time | 0/2 | 找不到 origin 输入框 |
| commits_by_date | 0/3 | 静默无产出(rc=0,异常被吞) |
| commits_by_period | 0/2 | 一个空、一个 [5] vs ["5"] 类型不一致 |
| order_attribute | 0/2 | 无产出 ×1;另一个疑似站点状态漂移 |

t213 最典型:agent-in-loop 是 held-out 功臣(13 步救活),裸跑第一步就崩。

## 含义

1. evolve 的输出侧以前没有任何验证(连 syntax check 都没有),gate 只看输入。这次坐实。
2. 修复已上线(fork commit 9786424):_refine 生成后在训练 taskspec 上重放,失败带反馈
   重炼一次,再失败不入库。learn 默认 shape 档(抓崩溃/空/形状错,容忍实时数据漂移),
   strict 档精确比对。这 7 个如果当时有 strict 关,多数会被打回。
3. 对叙事的影响:凡是宣传 standalone/cron 的地方,必须依赖重放关;agent-in-loop 数字
   (WebArena 表)不受影响,但不能拿它证明"skill 本身是对的"。

## 复现

脚本:scratchpad/audit_skills.py(库 + evals_webarena_backup/results.json +
Code-Web-Agent 数据集/config;站点需活着)。

## 追加:evolve+verify 的真实效果(同日)

拿这 7 个坏模板的原始训练 solve 重新 evolve(verify=strict,真 LLM + 活站点):

| 模板 | 结果 | 说明 |
|---|---|---|
| t213 评论≤3星 | **落库**(重炼救回) | 相对 URL 崩溃被失败反馈修好 |
| t293 ssh URL | **落库**(重炼救回) | 空提取被修好 |
| t303 按时段数提交 | **落库**(一次过) | 原拒收是比较器类型假阴性([5] vs ["5"]),加标量归一化后一次过 |
| t248 坐标 | 拒收 | 无视参数,重炼也没救回 |
| t151 车程 | 拒收 | origin 输入框选择器,重炼没救回 |
| t132 按日期数提交 | 拒收 | null×2 + 数值错 |
| t198 订单属性 | 拒收 | 站点状态漂移(答案随店铺数据变,strict 对它天然不公) |

结论:**防污染 100%(0 坏 skill 入库,旧版是 7/7 带病入库);修复救回 3/7;拒收 4 个里
1 个是答案不稳定(t198),3 个是蒸馏真难。** 比较器已加标量归一化并入 fork(0c29b9f)。
