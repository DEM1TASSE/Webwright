# 并行 / 串行两条 lane

跑全量 812 题的调度约束、命令、和实测踩过的坑。这是唯一出处——
脚本 docstring 只讲各自的实现，不重复这里的运维流程。

---

## 1. 为什么要分两条

只读任务之间互不影响，可以随便并行。写任务不行：一个任务在改商品价格、
另一个在读同一个商品的价格，读到的就是被污染的状态，而且**不会报错，只会让分数变低**。

但也不能因此把全部 374 个写任务串成一条链——那要跑十几个小时。
真正的约束是「两个任务不能同时写同一个对象」，而不是「写任务不能并发」。
所以按**写入作用域**切链：链内串行，链间并发。

| lane | 任务 | 调度 |
|---|--:|---|
| 并行（只读） | 432 | 每站点一个线程池，池内多 worker |
| 串行（写） | 380 | 每个写入作用域一条链，链内单 worker，链间并发 |

（432/380 是修正后的数字。Verified 原始标注是 438/374，写动词守卫补回 6 条——见 §2。）

---

## 2. 划分：`scripts/partition_tasks.py`

```
:99   mutates = annotated_type(...) == "mutate" or writes_despite_annotation(...)
:101  (serial if mutates else parallel).append(task_id)
:105  groups[write_scope(official[task_id])].append(task_id)
```

三个判据：

**`annotated_type`** 读 WebArena-Verified 的 `eval[].expected.task_type`。

**`writes_despite_annotation`** 按 intent 起始动词独立判定。必须有这一层，因为
**Verified 的标注是按「怎么评」分的，不是按「做什么」**：`Create an issue asking ...`、
`Add the following users ... as maintainer`、`Like/DisLike all submissions ...`、
`Buy the highest rated product ...` 这六条都真的写，但 evaluator 只做 `string_match`，
于是被标成只读，会被调度进所有只读任务共用的实例。

实测后果：task789 建了 3 个 issue（门禁重跑三次），而同 lane 有三个「列出所有未关闭 issue」
的任务。按时间戳核对那次 0 个受影响——**是运气，不是调度保证**。

`checkout` 故意不在词表里：WebArena 用它表示「看一下」（`Checkout merge requests
assigned to me`），不是结账。加进去会误伤两条只读任务。

**`write_scope`** 从 eval config 的 `reference_url` / `program_html[].url` 推出写入目标，
推不出的落 `<site>:*` 兜底。宁可多串不可少串。

产物：`partition/{parallel_ids,serial_ids,serial_groups,replay_ids}.json`。

---

## 3. 调度：`scripts/run_official.py`

```
:464  grouped   = jobs_by_scope(...) if args.serial_groups else jobs_by_site(...)
:489  per_group = 1 if args.serial_groups else args.per_site_workers
:498  pools     = {group: ThreadPoolExecutor(max_workers=size) ...}
:469  gate      = threading.Semaphore(args.workers)
```

`--serial-groups` 这一个开关切换两种模式：

| | 分组 | 池内 worker |
|---|---|---|
| 不给 | `jobs_by_site` 每站点一组 | `--per-site-workers` |
| 给 | `jobs_by_scope` 每个写入作用域一组 | 固定 1 |

`--workers` 是**跨所有池的全局上限**。串行模式下有 100+ 条链，每条一个池，
不设闸会同时开 100+ 个 agent 压垮单实例。链内串行由 `per_group = 1` 保证，
和全局上限是两个独立的旋钮。

用每站点线程池而不是「一个全局池 + 每站点信号量」，是因为后者会让某个繁忙站点的
排队任务占满所有线程、饿死其他站点。

---

## 4. 两条 lane 必须落在不同实例

同实例并跑会让串行 lane 的写污染并行 lane 的读。本机有实例 0/1/2/3 四套：

```
并行 lane → 实例 2   deployment_inst2.json   7970 / 7980 / 8223 / 10199 / 9088 / 4599
串行 lane → 实例 1   deployment_inst1.json   7870 / 7880 / 8123 / 10099 / 8988 / 4499
```

分实例是免费的（容器共享镜像），不必为此串行两条 lane 多花一倍墙钟。

---

## 5. 命令

并行 lane：

```bash
python run_official.py \
  --webarena-root  $WA_ROOT \
  --deployment-config deployment_inst2.json \
  --task-ids partition/parallel_ids.json \
  --output-root nonmutate_runs --results-root nonmutate_results \
  --model-config $MODEL_CFG \
  --workers 64 --per-site-workers 12 --timeout 900 \
  --progress nonmutate_progress.jsonl
```

串行 lane（注意：**不要给 `--replay-eval`**，见 §7）：

```bash
python run_official.py \
  --webarena-root  $WA_ROOT \
  --deployment-config deployment_inst1.json \
  --task-ids       partition/serial_ids.json \
  --serial-groups  partition/serial_groups.json \
  --output-root mutate_runs --results-root mutate_results \
  --model-config $MODEL_CFG \
  --workers 24 --timeout 900 \
  --progress mutate_progress.jsonl
```

---

## 6. 重置 → 开跑的固定顺序

每一步都是因为踩过才加的，不要跳。

```bash
bash /data/webarena/replica.sh reset <k>          # 1 重建容器
python scripts/deployment_state.py --instance <k> \
    --deployment-config deployment_inst<k>.json --wait 2400   # 2 等站点真的在服务
until docker exec forum_<k> psql -U postgres -d postmill -c 'SELECT 1'; do sleep 30; done  # 3
#                                                  4 重新生成 auth（reset 清掉了服务端 session）
python -c "from browser_env.auto_login import renew_comb; ..."
python scripts/deployment_state.py --instance <k> \
    --verify pristine_fingerprint.json            # 5 指纹校验，漂移则拒绝开跑
```

**第 2 步不能省。** Postmill 的 Postgres 在容器起来后还要重放 WAL，
nginx 已经返回 200 而 psql 仍拒连。空载约 1 分钟，**有 60 个 agent 抢 CPU 时实测 13 分钟**。
`replica.sh` 里固定的 `sleep 300` 在有负载时远远不够。

**第 4 步不能省。** reset 清掉服务端 session，但 `storage_state` 文件还在、格式合法，
失效表现为「元素找不到超时」而不是鉴权错误。第一次踩这个坑查了四个错误方向。

**第 5 步是为了挡住静默失败。** reset 没生效不会报错，只会让分数整体变低。
指纹比对 15 个「写任务会动的计数器」（orders / submissions / notes / issues / price_sum …），
参照来自一个刚重置的实例。它抓到过真东西：只读 lane 的实例比纯净态多 3 个 GitLab issue，
顺藤查出 task789 被误划进了并行 lane。

`replica.sh up` 里必须有 `web/url/redirect_to_base = 0`，否则 Magento 在任何 host
不匹配时 302 死循环（Chromium 会把 host 小写）。已焊进 `/data/webarena/replica.sh`。

---

## 7. 重放是独立阶段，不是内联开关

`--replay-eval` 在任务跑完当场重放，对只读任务无害，对写任务会**在它自己刚写过的状态上再写一次**。
所以它和 `--serial-groups` 同时给会被直接拒绝。

写任务的重放必须是 reset 之后的独立阶段：

```bash
python run_official.py ... --replay-only \
  --serial-groups partition/serial_groups.json \
  --replay-results-root mutate_results_replay --workers 6 --replay-timeout 900
```

`--replay-only` 不生成，只把每个任务留下的 `final_script.py` 在干净态执行一次并计分，
写到独立的 results root，生成阶段的分数保持不变。

---

## 8. 实测踩过的坑

**并发争抢会冒充任务超时。** 在三条独立 lane 上各自证实过：只读 lane 5 个任务在 64 并发下
打满 900s 上限，降到 8 并发后**全部通过且只用了 172–512 秒**；写 lane 10 个在 24→6 并发后零超时；
重放阶段 11 个同样如此。**看到超时先降并发重跑，再下「任务太难」的结论。**

**墙钟由最长的那条链决定，而它未必是兜底链。** 实测 Phase 1 墙钟 3.81 小时，其中 95%
由 `shopping_admin:catalog/product` 一条链（31 题，都改同一份商品目录）决定。
把 `reddit:*`、`shopping:*` 这些兜底链拆到无穷细，新下界仍是它，**收益只有 4.5%**。
所以保守划分的代价接近于零；想缩短批次要先看第二长的链是不是可拆的。

**`pkill -f <pattern>` 会杀掉自己。** 当前 shell 的命令行里含有那个 pattern，
`pkill -f 'run_official'` 会把执行它的 shell 一起干掉。用精确 pid。

**重放需要 auth。** `program_html` 里 `url != "last"` 的目标由 evaluator 实地导航获取，
登出状态下拿到的是登录页，`must_include` 必然失败。inline 路径一直传了，
重放路径曾经漏传，导致整批重放看起来像脚本全面失效（`shopping_admin` 从 59% 崩到 4.9%）。
现在 `replay_and_score` 会自动解析并传 `--auth-state`。
