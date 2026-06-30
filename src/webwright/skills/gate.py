"""准入闸：只有"对的"解/技能才准进库，防 correct-but-narrow / regression 污染。
gate 是【独立第二只眼】，与解题 agent 自己的 self_reflection 不同（后者是解题完成条件）。

接口稳定（实现可换），method 可配置：
    gate(result, *, gold=None, output_schema=None, method="auto") -> GateResult

- method="gold"        : 与 gold 比对（WebArena 等有标准答案；真独立、能挡住抽错的解）。★推荐
- method="self_verify" : 不变量（result 非空 + shape 合 output_schema）。无 gold 时的弱占位。
                         ⚠️ 局限：只查"有没有/形状对不对"，不查"对不对"——抽错但非空的答案照样放行。
                         （注：webwright 的 self_reflection 因 require_self_reflection_success 而恒为
                         predicted_label==1，故不能用它当 gate；那是解题完成条件，非独立准入。）
- method="none"        : 不把关（纯演示复用，不防污染）。
- method="auto"        : 有 gold 用 gold，否则 self_verify。
升级路径（next step）：真实站用 WebJudge（OM2W 官方 judge）或跨源一致核验，做真独立把关。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class GateResult:
    admit: bool
    reason: str


def _shape_ok(result, output_schema) -> bool:
    if not output_schema:
        return True
    t = output_schema.get("type")
    if t == "array":
        return isinstance(result, list)
    if t == "object":
        return isinstance(result, dict)
    if t in ("string",):
        return isinstance(result, str)
    if t in ("number", "integer"):
        return isinstance(result, (int, float)) and not isinstance(result, bool)
    return True


def _self_verify(result, output_schema) -> GateResult:
    if result is None:
        return GateResult(False, "result is null")
    if isinstance(result, (list, dict, str)) and len(result) == 0:
        return GateResult(False, "result is empty")
    if not _shape_ok(result, output_schema):
        return GateResult(False, f"shape != output_schema ({output_schema.get('type')})")
    return GateResult(True, "self-verify passed (non-empty, shape ok)")


def _gold(result, gold) -> GateResult:
    if result == gold:
        return GateResult(True, "matches gold")
    return GateResult(False, "differs from gold")


def gate(result, *, gold=None, output_schema=None, method: str = "auto") -> GateResult:
    if method == "none":
        return GateResult(True, "no gate (admit all)")
    if method == "gold" or (method == "auto" and gold is not None):
        return _gold(result, gold)
    return _self_verify(result, output_schema)
