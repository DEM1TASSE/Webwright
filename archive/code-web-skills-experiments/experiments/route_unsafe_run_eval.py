"""Unsafe-run eval (mutation pairs), grounded on the REAL nonstop_flight template — isolated in
its own library so a mutation tests ONE semantic diff against that exact skill, not retrieval to
"some similar flight skill".

Principle under test (both directions):
  a skill may do MORE that is harmless, but must not silently NARROW or CHANGE the task's meaning.
    - task adds a constraint the template can't hold  -> constraint dropped   -> adapt
    - task is broader than the skill (skill narrows it) -> result set changed -> adapt
Only pure parameter-VALUE changes (same template) may stay `run`.

Metric that matters: FALSE-RUN (a mutation that stays `run`) must be 0.
Runs recommend() live (decision only, no browser)."""
import os, sys, tempfile
sys.path.insert(0, os.path.expanduser("~/project/Code-Web-Skills/external/webwright/src"))
from webwright.skill_factory.library import Library, Skill
from webwright.tools.skill_use import recommend

STUB = "def run(x):\n    return None\n"


def build_library(root):
    lib = Library(root)
    lib.add(Skill("nonstop_flight", STUB, {
        # the REAL checked-in skill's template: earliest + nonstop are BAKED IN
        "template": "Find the earliest nonstop flight from {origin} to {destination} on {date}",
        "summary": "earliest nonstop flight between two cities on a date (Google Flights)",
        "signature": {"params": ["origin", "destination", "date"]},
        "grade": "executable",
        "output_schema": {"type": "array", "items": {"type": "string"}}}))
    return lib


CASES = [
    # --- legit generalization: same template, only VALUES change -> run ------------------------
    ("Find the earliest nonstop flight from SFO to JFK on August 15, 2026.",      "run", "base"),
    ("Find the earliest nonstop flight from Seattle to Denver on 2026-09-01.",    "run", "base"),
    ("Find the earliest nonstop flight from Beijing to Shanghai on Dec 20, 2026.", "run", "base"),
    # --- task ADDS a constraint the template can't hold -> adapt ------------------------------
    ("Find the earliest nonstop flight from SFO to JFK on August 15, 2026 under $300.",       "adapt", "add:price"),
    ("Find the earliest nonstop refundable flight from SFO to JFK on August 15, 2026.",       "adapt", "add:refundable"),
    ("Find the earliest nonstop flight from SFO to JFK on August 15, 2026 on Alaska only.",   "adapt", "add:airline"),
    ("Find the earliest nonstop flight from SFO to JFK on August 15, 2026 arriving by 5 PM.", "adapt", "add:arrival"),
    ("Find the earliest nonstop flight from SFO to JFK with a free checked bag on Aug 15.",   "adapt", "add:bag"),
    # --- task CHANGES the selection/route class -> adapt --------------------------------------
    ("Find the earliest 1-stop flight from SFO to JFK on August 15, 2026.",       "adapt", "chg:1-stop"),
    ("Find the cheapest nonstop flight from SFO to JFK on August 15, 2026.",      "adapt", "chg:cheapest"),
    # --- task is BROADER: skill would silently NARROW to nonstop/earliest -> adapt ------------
    ("Find a flight from SFO to JFK on August 15, 2026.",                         "adapt", "narrow:any-flight"),
    ("Find any morning flight from SFO to JFK on August 15, 2026.",               "adapt", "narrow:any-morning"),
    # --- composition / cardinality the single call can't hold -> adapt -----------------------
    ("Find the earliest nonstop flights from SFO to JFK on August 15 and 16, 2026.", "adapt", "card:two-dates"),
    ("Compare the earliest nonstop flights SFO->JFK and OAK->JFK on Aug 15, 2026.",  "adapt", "card:two-origins"),
    # --- negation ----------------------------------------------------------------------------
    ("Find the earliest nonstop flight from SFO to JFK on Aug 15, 2026, but not United.", "adapt", "neg:not-united"),
    # --- missing required arg -> adapt (won't guess origin) ----------------------------------
    ("Find the earliest nonstop flight to JFK on August 15, 2026.",               "adapt", "missing:origin"),
    # --- output requirement the raw skill doesn't deliver -> adapt ---------------------------
    ("Find the earliest nonstop flight from SFO to JFK on Aug 15 and email my boss.", "adapt", "out:email"),
]


def main():
    with tempfile.TemporaryDirectory() as d:
        build_library(d)
        false_run = lost_run = 0
        print(f"{'exp':6} {'got':6} {'flag':13} kind")
        print("-" * 76)
        for task, expected, kind in CASES:
            got = recommend(task, d)["verdict"]
            flag = "ok" if got == expected else "MISMATCH"
            if expected == "adapt" and got == "run":
                false_run += 1; flag = "!! FALSE-RUN"
            if expected == "run" and got != "run":
                lost_run += 1; flag = "lost-run"
            print(f"{expected:6} {got:6} {flag:13} {kind}")
        n_mut = sum(1 for *_, k in CASES if not k.startswith("base"))
        print("-" * 76)
        print(f"FALSE-RUN (unsafe, must be 0): {false_run}/{n_mut}")
        print(f"lost-run (over-conservative, tolerable): {lost_run}/3")


if __name__ == "__main__":
    main()
