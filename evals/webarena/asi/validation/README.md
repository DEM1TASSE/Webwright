# 验证证据

跑正式批次之前和之中做的验证，保留原始产物。

## smoke/
开跑前的 2 题冒烟（gitlab task44、map task7），两题均 `scored_correct`。
核对了三件事：实发 prompt 与冻结版本**逐字节一致**；`format_errors: 0`
（确认注入块末尾那句 `Multiple actions can be provided at once` 没有破坏
Webwright 的 JSON+bash 输出协议）；库引用 0。

## verify/
harness 被并发修改并修复之后，拿两道原先崩溃的题（shopping_admin task0、shopping task360）
验证修复：两题恢复正常判分而非 `process_error`，且 prompt 与重新冻结的版本逐字节一致。

## PAUSE_NOTES.md
harness 被并发修改时的暂停记录：当时的判断、损失清单、恢复条件。
其中"计分缺口需要补 patch"的结论后来被推翻——修复其实已经完整，
崩溃全部落在编辑窗口内。最终结论以 FINDINGS.md §6.1 为准。
