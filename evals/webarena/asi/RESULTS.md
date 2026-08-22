# 结果数字

WebArena 官方 cross-template 留出集，实例 4，gpt-5.4，2026-08-21。
**完成 220 / 399 题** —— 只读 lane 211 题全部完成，写 lane（188 题 mutate）跑了 9 题后中止。

数字由 `analysis/per_task.json` 与 `results/` 生成；逐题明细见文末。

## 判分状态

| 状态 | 数 |
|---|--:|
| `scored_correct` | 129 |
| `scored_incorrect` | 90 |
| `agent_timeout_or_incomplete` | 1 |
| **合计** | **220** |


## 库的使用（**主结果，不依赖对照臂**）

| 指标 | 值 |
|---|--:|
| 注入了库的题数 | 220 |
| **引用过任一诱导函数的题数** | **0** |
| 照抄 bid 序列的题数 | 0 |
| 尝试 `get_by_test_id` 的题数 | 0 |

检测方式：扫描每题的 `final_script.py` 与全部 `steps/*.sh`，匹配 28 个诱导函数名。
不用 marker 注释，因为 prompt 未要求保留 marker——要求记录用法会预设会用，而使用率正是被测量。

## 准确率（**不可单独引用：配对的 scratch 对照臂未跑**）

### 按站点

| | n | 正确 | 通过率 | 用过库 |
|---|--:|--:|--:|--:|
| shopping | 61 | 33 | 54.1% | 0 |
| map | 53 | 35 | 66.0% | 0 |
| shopping_admin | 51 | 34 | 66.7% | 0 |
| gitlab | 36 | 19 | 52.8% | 0 |
| gitlab+reddit | 6 | 1 | 16.7% | 0 |
| wikipedia+map | 5 | 4 | 80.0% | 0 |
| reddit | 4 | 2 | 50.0% | 0 |
| map+shopping_admin | 2 | 0 | 0.0% | 0 |
| map+wikipedia | 1 | 1 | 100.0% | 0 |
| **合计** | **219** | **129** | **58.9%** | **0** |

### 按 lane 与 task_type

| | n | 正确 | 通过率 | 用过库 |
|---|--:|--:|--:|--:|
| read / retrieve | 156 | 98 | 62.8% | 0 |
| read / navigate | 54 | 27 | 50.0% | 0 |
| write / mutate | 9 | 4 | 44.4% | 0 |
| **合计** | **219** | **129** | **58.9%** | **0** |


## 与旧基线的临时对比（**不要引用**）

对照是 2026-08-20 的 full812 scratch，跑在不同实例、旧 prompt spec、不同 harness 上，
三个差异混在一起。且库引用为 0，任何 delta 都不可能是库效应。

| | n | asi | scratch | delta |
|---|--:|--:|--:|--:|
| 合计（可配对） | 209 | 59.8% | 58.9% | +1.0% |

赢 20 / 输 18 / 净 +2。splits/README §5 实测同批题重跑翻转率 21%，399 题 MDE 6.5%——在噪声内。

## 逐题

| task | site | lane | type | 结果 | 步数 | 用库 |
|---|---|---|---|---|--:|---|
| 0 | shopping_admin | read | retrieve | ✓ scored_correct | 9 | 否 |
| 1 | shopping_admin | read | retrieve | ✗ scored_incorrect | 10 | 否 |
| 2 | shopping_admin | read | retrieve | ✗ scored_incorrect | 14 | 否 |
| 3 | shopping_admin | read | retrieve | ✗ scored_incorrect | 7 | 否 |
| 4 | shopping_admin | read | retrieve | ✗ scored_incorrect | 8 | 否 |
| 5 | shopping_admin | read | retrieve | ✗ scored_incorrect | 11 | 否 |
| 6 | shopping_admin | read | retrieve | ✗ scored_incorrect | 8 | 否 |
| 7 | map | read | retrieve | ✗ scored_incorrect | 13 | 否 |
| 8 | map | read | retrieve | ✓ scored_correct | 12 | 否 |
| 9 | map | read | retrieve | ✗ scored_incorrect | 10 | 否 |
| 10 | map | read | retrieve | ✗ scored_incorrect | 9 | 否 |
| 11 | shopping_admin | read | retrieve | ✓ scored_correct | 12 | 否 |
| 12 | shopping_admin | read | retrieve | ✗ scored_incorrect | 9 | 否 |
| 13 | shopping_admin | read | retrieve | ✓ scored_correct | 11 | 否 |
| 14 | shopping_admin | read | retrieve | ✓ scored_correct | 12 | 否 |
| 15 | shopping_admin | read | retrieve | ✓ scored_correct | 10 | 否 |
| 16 | map | read | retrieve | ✗ scored_incorrect | 7 | 否 |
| 17 | map | read | retrieve | ✗ scored_incorrect | 8 | 否 |
| 18 | map | read | retrieve | ✗ scored_incorrect | 7 | 否 |
| 19 | map | read | retrieve | ✗ scored_incorrect | 11 | 否 |
| 20 | map | read | retrieve | ✓ scored_correct | 8 | 否 |
| 36 | map | read | retrieve | ✓ scored_correct | 8 | 否 |
| 37 | map | read | retrieve | ✓ scored_correct | 20 | 否 |
| 38 | map | read | retrieve | ✓ scored_correct | 10 | 否 |
| 39 | map | read | retrieve | ✓ scored_correct | 8 | 否 |
| 40 | map | read | retrieve | ✗ scored_incorrect | 12 | 否 |
| 44 | gitlab | read | navigate | ✓ scored_correct | 7 | 否 |
| 52 | map | read | retrieve | ✓ scored_correct | 12 | 否 |
| 53 | map | read | retrieve | ✓ scored_correct | 23 | 否 |
| 54 | map | read | retrieve | ✓ scored_correct | 9 | 否 |
| 55 | map | read | retrieve | ✗ scored_incorrect | 12 | 否 |
| 56 | map | read | retrieve | ✓ scored_correct | 7 | 否 |
| 62 | shopping_admin | read | retrieve | ✓ scored_correct | 15 | 否 |
| 63 | shopping_admin | read | retrieve | ✓ scored_correct | 15 | 否 |
| 64 | shopping_admin | read | retrieve | ✗ scored_incorrect | 11 | 否 |
| 65 | shopping_admin | read | retrieve | ✗ scored_incorrect | 11 | 否 |
| 66 | reddit | read | retrieve | ✗ scored_incorrect | 10 | 否 |
| 67 | reddit | read | retrieve | ✓ scored_correct | 12 | 否 |
| 68 | reddit | read | retrieve | ✗ scored_incorrect | 11 | 否 |
| 69 | reddit | read | retrieve | ✓ scored_correct | 10 | 否 |
| 70 | map | read | retrieve | ✓ scored_correct | 12 | 否 |
| 71 | map | read | retrieve | ✓ scored_correct | 11 | 否 |
| 72 | map | read | retrieve | ✓ scored_correct | 18 | 否 |
| 73 | map | read | retrieve | ✓ scored_correct | 11 | 否 |
| 74 | map | read | retrieve | ✗ scored_incorrect | 13 | 否 |
| 75 | map | read | retrieve | ✓ scored_correct | 11 | 否 |
| 76 | map | read | retrieve | ✗ scored_incorrect | 8 | 否 |
| 80 | map | read | retrieve | ✓ scored_correct | 13 | 否 |
| 81 | map | read | retrieve | ✓ scored_correct | 16 | 否 |
| 82 | map | read | retrieve | ✗ scored_incorrect | 9 | 否 |
| 83 | map | read | retrieve | ✓ scored_correct | 7 | 否 |
| 84 | map | read | retrieve | ✓ scored_correct | 8 | 否 |
| 85 | map | read | retrieve | ✓ scored_correct | 14 | 否 |
| 86 | map | read | retrieve | ✓ scored_correct | 7 | 否 |
| 87 | map | read | retrieve | ✗ scored_incorrect | 8 | 否 |
| 88 | map | read | retrieve | ✓ scored_correct | 11 | 否 |
| 94 | shopping_admin | read | retrieve | ✓ scored_correct | 11 | 否 |
| 95 | shopping_admin | read | retrieve | ✓ scored_correct | 9 | 否 |
| 97 | map+wikipedia | read | retrieve | ✓ scored_correct | 10 | 否 |
| 112 | shopping_admin | read | retrieve | ✓ scored_correct | 10 | 否 |
| 113 | shopping_admin | read | retrieve | ✗ scored_incorrect | 15 | 否 |
| 114 | shopping_admin | read | retrieve | ✗ scored_incorrect | 9 | 否 |
| 115 | shopping_admin | read | retrieve | ✗ scored_incorrect | 18 | 否 |
| 116 | shopping_admin | read | retrieve | ✗ scored_incorrect | 10 | 否 |
| 117 | shopping | read | retrieve | ✓ scored_correct | 7 | 否 |
| 118 | shopping | read | navigate | ✗ scored_incorrect | 4 | 否 |
| 127 | shopping_admin | read | retrieve | ✓ scored_correct | 8 | 否 |
| 128 | shopping_admin | read | retrieve | ✓ scored_correct | 12 | 否 |
| 129 | shopping_admin | read | retrieve | ✓ scored_correct | 8 | 否 |
| 130 | shopping_admin | read | retrieve | ✓ scored_correct | 9 | 否 |
| 131 | shopping_admin | read | retrieve | ✓ scored_correct | 13 | 否 |
| 132 | gitlab | read | retrieve | ✓ scored_correct | 6 | 否 |
| 133 | gitlab | read | retrieve | ✗ scored_incorrect | 12 | 否 |
| 134 | gitlab | read | retrieve | ✓ scored_correct | 11 | 否 |
| 135 | gitlab | read | retrieve | ✓ scored_correct | 9 | 否 |
| 136 | gitlab | read | retrieve | ✓ scored_correct | 6 | 否 |
| 156 | gitlab | read | navigate | ✓ scored_correct | 8 | 否 |
| 157 | shopping_admin | read | navigate | ✓ scored_correct | 10 | 否 |
| 163 | shopping | read | retrieve | ✗ scored_incorrect | 10 | 否 |
| 164 | shopping | read | retrieve | ✓ scored_correct | 11 | 否 |
| 165 | shopping | read | retrieve | ✗ scored_incorrect | 7 | 否 |
| 166 | shopping | read | retrieve | ✗ scored_incorrect | 10 | 否 |
| 167 | shopping | read | retrieve | ✗ scored_incorrect | 8 | 否 |
| 178 | gitlab | read | retrieve | ✗ scored_incorrect | 6 | 否 |
| 179 | gitlab | read | retrieve | ✗ scored_incorrect | 8 | 否 |
| 180 | gitlab | read | retrieve | ✗ scored_incorrect | 5 | 否 |
| 181 | gitlab | read | retrieve | ✗ scored_incorrect | 9 | 否 |
| 182 | gitlab | read | retrieve | ✗ scored_incorrect | 9 | 否 |
| 188 | shopping | read | retrieve | ✓ scored_correct | 8 | 否 |
| 189 | shopping | read | retrieve | ✓ scored_correct | 11 | 否 |
| 190 | shopping | read | retrieve | ✓ scored_correct | 12 | 否 |
| 191 | shopping | read | retrieve | ✗ scored_incorrect | 7 | 否 |
| 192 | shopping | read | retrieve | ✓ scored_correct | 9 | 否 |
| 205 | gitlab | read | retrieve | ✓ scored_correct | 9 | 否 |
| 206 | gitlab | read | retrieve | ✓ scored_correct | 9 | 否 |
| 207 | gitlab | read | retrieve | ✓ scored_correct | 9 | 否 |
| 208 | shopping_admin | read | retrieve | ✓ scored_correct | 11 | 否 |
| 209 | shopping_admin | read | retrieve | ✓ scored_correct | 17 | 否 |
| 210 | shopping_admin | read | retrieve | ✓ scored_correct | 14 | 否 |
| 211 | shopping_admin | read | retrieve | ✓ scored_correct | 14 | 否 |
| 212 | shopping_admin | read | retrieve | ✓ scored_correct | 19 | 否 |
| 218 | map | read | retrieve | ✓ scored_correct | 15 | 否 |
| 219 | map | read | retrieve | ✓ scored_correct | 16 | 否 |
| 220 | map | read | retrieve | ✓ scored_correct | 13 | 否 |
| 226 | shopping | read | retrieve | ✗ scored_incorrect | 14 | 否 |
| 227 | shopping | read | retrieve | ✓ scored_correct | 5 | 否 |
| 228 | shopping | read | retrieve | ✓ scored_correct | 5 | 否 |
| 229 | shopping | read | retrieve | ✓ scored_correct | 5 | 否 |
| 230 | shopping | read | retrieve | ✓ scored_correct | 9 | 否 |
| 231 | shopping | read | retrieve | ✓ scored_correct | 7 | 否 |
| 232 | shopping | read | retrieve | ✓ scored_correct | 9 | 否 |
| 233 | shopping | read | retrieve | ✓ scored_correct | 7 | 否 |
| 234 | shopping | read | retrieve | ✓ scored_correct | 11 | 否 |
| 235 | shopping | read | retrieve | ✓ scored_correct | 9 | 否 |
| 238 | shopping | read | navigate | ✗ scored_incorrect | 12 | 否 |
| 239 | shopping | read | navigate | ✗ scored_incorrect | 9 | 否 |
| 240 | shopping | read | navigate | ✗ scored_incorrect | 10 | 否 |
| 241 | shopping | read | navigate | ✗ scored_incorrect | 12 | 否 |
| 242 | shopping | read | navigate | ✗ scored_incorrect | 8 | 否 |
| 243 | shopping_admin | read | retrieve | ✓ scored_correct | 10 | 否 |
| 244 | shopping_admin | read | retrieve | ✓ scored_correct | 13 | 否 |
| 245 | shopping_admin | read | retrieve | ✓ scored_correct | 14 | 否 |
| 246 | shopping_admin | read | retrieve | ✓ scored_correct | 12 | 否 |
| 247 | shopping_admin | read | retrieve | ✓ scored_correct | 11 | 否 |
| 253 | map | read | retrieve | ✓ scored_correct | 16 | 否 |
| 254 | map | read | retrieve | ✗ scored_incorrect | 15 | 否 |
| 255 | map | read | retrieve | ✓ scored_correct | 11 | 否 |
| 256 | map | read | retrieve | ✓ scored_correct | 14 | 否 |
| 257 | map | read | retrieve | ✓ scored_correct | 11 | 否 |
| 258 | gitlab | read | navigate | ✓ scored_correct | 6 | 否 |
| 260 | shopping | read | navigate | ✓ scored_correct | 6 | 否 |
| 261 | shopping | read | navigate | ✗ scored_incorrect | 5 | 否 |
| 262 | shopping | read | navigate | ✗ scored_incorrect | 12 | 否 |
| 263 | shopping | read | navigate | ✓ scored_correct | 4 | 否 |
| 264 | shopping | read | navigate | ✓ scored_correct | 10 | 否 |
| 269 | shopping | read | navigate | ✗ scored_incorrect | 12 | 否 |
| 270 | shopping | read | navigate | ✓ scored_correct | 9 | 否 |
| 271 | shopping | read | navigate | ✓ scored_correct | 10 | 否 |
| 272 | shopping | read | navigate | ✗ scored_incorrect | 8 | 否 |
| 273 | shopping | read | navigate | ✗ scored_incorrect | 14 | 否 |
| 274 | shopping | read | navigate | ✓ scored_correct | 6 | 否 |
| 275 | shopping | read | navigate | ✓ scored_correct | 4 | 否 |
| 276 | shopping | read | navigate | ✓ scored_correct | 5 | 否 |
| 277 | shopping | read | navigate | ✗ scored_incorrect | 4 | 否 |
| 278 | shopping | read | navigate | ✓ scored_correct | 5 | 否 |
| 279 | shopping | read | retrieve | ✗ scored_incorrect | 11 | 否 |
| 280 | shopping | read | retrieve | ✗ scored_incorrect | 10 | 否 |
| 281 | shopping | read | retrieve | ✗ scored_incorrect | 10 | 否 |
| 282 | shopping | read | retrieve | ✗ scored_incorrect | 8 | 否 |
| 283 | shopping | read | navigate | ✓ scored_correct | 7 | 否 |
| 293 | gitlab | read | retrieve | ✗ scored_incorrect | 6 | 否 |
| 294 | gitlab | read | retrieve | ✗ scored_incorrect | 11 | 否 |
| 295 | gitlab | read | retrieve | ✗ scored_incorrect | 17 | 否 |
| 296 | gitlab | read | retrieve | ✗ scored_incorrect | 10 | 否 |
| 297 | gitlab | read | retrieve | ✗ scored_incorrect | 13 | 否 |
| 303 | gitlab | read | retrieve | ✓ scored_correct | 10 | 否 |
| 304 | gitlab | read | retrieve | ✓ scored_correct | 8 | 否 |
| 305 | gitlab | read | retrieve | ✓ scored_correct | 12 | 否 |
| 306 | gitlab | read | retrieve | ✓ scored_correct | 12 | 否 |
| 307 | gitlab | read | retrieve | ✗ scored_incorrect | 13 | 否 |
| 313 | shopping | read | retrieve | ✓ scored_correct | 11 | 否 |
| 319 | shopping | read | retrieve | ✗ scored_incorrect | 9 | 否 |
| 320 | shopping | read | retrieve | ✗ scored_incorrect | 5 | 否 |
| 321 | shopping | read | retrieve | ✗ scored_incorrect | 9 | 否 |
| 322 | shopping | read | retrieve | ✓ scored_correct | 6 | 否 |
| 323 | shopping | read | retrieve | ✗ scored_incorrect | 8 | 否 |
| 339 | gitlab | read | navigate | ✗ scored_incorrect | 8 | 否 |
| 340 | gitlab | read | navigate | ✗ scored_incorrect | 5 | 否 |
| 341 | gitlab | read | navigate | ✗ scored_incorrect | 8 | 否 |
| 342 | gitlab | read | navigate | ✗ scored_incorrect | 5 | 否 |
| 343 | gitlab | read | navigate | ✗ scored_incorrect | 10 | 否 |
| 344 | shopping_admin | read | retrieve | ✓ scored_correct | 12 | 否 |
| 345 | shopping_admin | read | retrieve | ✓ scored_correct | 9 | 否 |
| 346 | shopping_admin | read | retrieve | ✓ scored_correct | 8 | 否 |
| 347 | shopping_admin | read | retrieve | ✓ scored_correct | 8 | 否 |
| 348 | shopping_admin | read | retrieve | ✓ scored_correct | 12 | 否 |
| 349 | gitlab | read | retrieve | ✓ scored_correct | 8 | 否 |
| 350 | gitlab | read | retrieve | ✓ scored_correct | 5 | 否 |
| 356 | map | read | navigate | ✗ scored_incorrect | 13 | 否 |
| 358 | shopping | read | retrieve | ✓ scored_correct | 5 | 否 |
| 359 | shopping | read | retrieve | ✓ scored_correct | 9 | 否 |
| 360 | shopping | read | retrieve | ✓ scored_correct | 13 | 否 |
| 361 | shopping | read | retrieve | ✗ scored_incorrect | 4 | 否 |
| 362 | shopping | read | retrieve | ✓ scored_correct | 6 | 否 |
| 368 | shopping | read | retrieve | ✗ scored_incorrect | 9 | 否 |
| 369 | map | read | navigate | ✗ scored_incorrect | 13 | 否 |
| 370 | map | read | navigate | ✓ scored_correct | 12 | 否 |
| 371 | map | read | navigate | ✗ agent_timeout_or_incomplete | 30 | 否 |
| 372 | map | read | navigate | ✓ scored_correct | 11 | 否 |
| 373 | map | read | navigate | ✓ scored_correct | 17 | 否 |
| 374 | shopping_admin | read | navigate | ✗ scored_incorrect | 16 | 否 |
| 375 | shopping_admin | read | navigate | ✗ scored_incorrect | 13 | 否 |
| 382 | map | read | retrieve | ✗ scored_incorrect | 17 | 否 |
| 387 | shopping | read | retrieve | ✓ scored_correct | 10 | 否 |
| 388 | shopping | read | retrieve | ✓ scored_correct | 11 | 否 |
| 480 | gitlab | write | mutate | ✓ scored_correct | 10 | 否 |
| 552 | gitlab+reddit | write | mutate | ✗ scored_incorrect | 15 | 否 |
| 562 | gitlab+reddit | write | mutate | ✗ scored_incorrect | 9 | 否 |
| 563 | gitlab+reddit | write | mutate | ✗ scored_incorrect | 11 | 否 |
| 565 | gitlab+reddit | write | mutate | ✗ scored_incorrect | 7 | 否 |
| 566 | gitlab+reddit | write | mutate | ✗ scored_incorrect | 9 | 否 |
| 568 | gitlab | write | mutate | ✓ scored_correct | 13 | 否 |
| 661 | gitlab | write | mutate | ✓ scored_correct | 11 | 否 |
| 704 | shopping_admin | read | navigate | ✓ scored_correct | 9 | 否 |
| 705 | shopping_admin | read | navigate | ✓ scored_correct | 10 | 否 |
| 706 | shopping_admin | read | navigate | ✓ scored_correct | 7 | 否 |
| 707 | shopping_admin | read | navigate | ✗ scored_incorrect | 7 | 否 |
| 708 | shopping_admin | read | navigate | ✗ scored_incorrect | 9 | 否 |
| 737 | wikipedia+map | read | navigate | ✓ scored_correct | 7 | 否 |
| 738 | wikipedia+map | read | navigate | ✗ scored_incorrect | 7 | 否 |
| 739 | wikipedia+map | read | navigate | ✓ scored_correct | 10 | 否 |
| 740 | wikipedia+map | read | navigate | ✓ scored_correct | 10 | 否 |
| 741 | wikipedia+map | read | navigate | ✓ scored_correct | 7 | 否 |
| 757 | map | read | navigate | ✗ scored_incorrect | 13 | 否 |
| 758 | map | read | navigate | ✓ scored_correct | 7 | 否 |
| 759 | map+shopping_admin | read | navigate | ✗ scored_incorrect | 16 | 否 |
| 760 | map+shopping_admin | read | navigate | ✗ scored_incorrect | 14 | 否 |
| 761 | map | read | navigate | ✓ scored_correct | 10 | 否 |
| 762 | map | read | navigate | ✓ scored_correct | 11 | 否 |
| 791 | gitlab+reddit | write | mutate | ✓ scored_correct | 14 | 否 |
