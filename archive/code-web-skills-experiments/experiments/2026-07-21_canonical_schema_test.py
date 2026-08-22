"""Test for feature ②: canonicalize_answers — one output_schema per template + each member's
answer reshaped to it (at aggregation).

Two paths:
- MECHANICAL (offline, no model): answers already share one structured shape -> schema inferred,
  answers unchanged. Runs always.
- MODEL (needs webwright venv + gateway env): prose / mixed answers -> one canonical schema is
  defined and each answer is reshaped to it, RESHAPE-ONLY (data preserved, nothing invented).

Run:  python 2026-07-21_canonical_schema_test.py
"""
import json
import os

from webwright.skill_factory.learn import canonicalize_answers

npass = ntot = 0
def check(name, cond, extra=""):
    global npass, ntot
    ntot += 1; npass += bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  ' + extra) if extra else ''}")

FLIGHT_TMPL = ("Find the cheapest one-way flight from {{origin}} to {{destination}} on {{date}} "
               "and return [airline, price].")

# ---------- MECHANICAL path (offline) ----------
schema, coerced = canonicalize_answers(FLIGHT_TMPL, [["Frontier", "$45"], ["Delta", "$80"]])
check("structured_consistent_schema", schema == {"type": "array", "items": {"type": "string"}}, str(schema))
check("structured_consistent_unchanged", coerced == [["Frontier", "$45"], ["Delta", "$80"]])

schema, coerced = canonicalize_answers(FLIGHT_TMPL, [["Frontier", "$45"]])
check("structured_single", schema == {"type": "array", "items": {"type": "string"}} and coerced == [["Frontier", "$45"]])

schema, coerced = canonicalize_answers("count", [5, 8])
check("numbers_mechanical", schema == {"type": "number"} and coerced == [5, 8], str(schema))

# ---------- MODEL path (gateway) ----------
if not os.environ.get("OPENAI_API_KEY"):
    print("  [SKIP] model-path cases (set OPENAI_API_KEY/OPENAI_ENDPOINT/OPENAI_MODEL to run)")
else:
    def faithful(obj, *needles):
        blob = json.dumps(obj, ensure_ascii=False).lower()
        return all(n.lower() in blob for n in needles)

    # prose answers -> one schema + reshaped, data preserved
    prose = ["The cheapest flight is Frontier at $45.", "Delta Air Lines for $80."]
    schema, coerced = canonicalize_answers(FLIGHT_TMPL, prose)
    check("prose_schema_is_object_or_array", isinstance(schema, dict) and schema.get("type") in ("array", "object"), str(schema))
    check("prose_len", len(coerced) == 2)
    check("prose_reshape_only_0", faithful(coerced[0], "frontier", "45"), str(coerced[0] if len(coerced) > 0 else None))
    check("prose_reshape_only_1", faithful(coerced[1], "delta", "80"), str(coerced[1] if len(coerced) > 1 else None))

    # mixed structured + prose -> aligned to one schema, both preserved
    mixed = [["Frontier", "$45"], "Delta costs $80"]
    schema, coerced = canonicalize_answers(FLIGHT_TMPL, mixed)
    check("mixed_len", len(coerced) == 2, str(schema))
    check("mixed_reshape_only_0", faithful(coerced[0], "frontier", "45"), str(coerced[0] if len(coerced) > 0 else None))
    check("mixed_reshape_only_1", faithful(coerced[1], "delta", "80"), str(coerced[1] if len(coerced) > 1 else None))

print(f"\n{npass}/{ntot} checks passed")
raise SystemExit(0 if npass == ntot else 1)
