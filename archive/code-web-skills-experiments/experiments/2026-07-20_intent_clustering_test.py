"""Basic intent-clustering test for skill_factory's template aggregation (group_chunk).

Goal (kept minimal on purpose): does grouping cluster by INTENT?
- paraphrases / background noise / synonyms  -> SAME template  (merge)
- different action / different site / different intent (search vs compare vs recommend) -> SPLIT

Scoring is partition-based and naming-agnostic: for every task pair we check
(same group in the model's output) == (same group in the gold labels). A case PASSES a
draw only if ALL pairs agree with gold. Runs BASELINE (shipped prompt) vs HARDENED
(intent+site+output, paraphrases=same, prefer-fewest) A/B, K draws each.

Run (needs the webwright venv + gateway env OPENAI_API_KEY/OPENAI_ENDPOINT/OPENAI_MODEL):
    python 2026-07-20_intent_clustering_test.py 3
"""
import sys
import webwright.skill_factory.learn as L

# ---- the shipped ("baseline") prompt, kept here so we can A/B against the hardened one ----
BASELINE = (
    "You organize solved web tasks into task TEMPLATES. Tasks are instances of the same "
    "template when they differ only in parameter values (names, dates, places, counts).\n"
    "You are given existing template strings and a numbered task list. Return STRICT JSON:\n"
    '{"groups": [{"template": "sentence with {{param}} placeholders", '
    '"members": [{"i": <task index>, "params": {"<name>": "<value>", ...}}]}]}\n'
    "Rules: if a task matches an EXISTING template, use that exact template string verbatim. "
    "Every task index appears in exactly one group. A group may have a single member. "
    "Params must be the concrete values from the task text."
)
HARDENED = L._GROUP_SYS   # the current (hardened) prompt already in learn.py

# ---- cases: (name, kind, tasks, gold_labels) ; gold_labels[i] = which cluster task i belongs to ----
CASES = [
    ("paraphrase_merge", "merge", [
        "Find the cheapest laptop stand on Amazon. Return the answer as [brand, price].",
        "Search for the lowest-priced laptop stand on Amazon. Return the answer as [brand, price].",
        "What is the least expensive laptop stand on Amazon? Return the answer as [brand, price].",
    ], [0, 0, 0]),

    ("background_noise_merge", "merge", [
        "Find flights from Seattle to San Francisco on 2026-08-15. Return [airline, price].",
        "Show me flights from SEA to SFO on 2026-08-15. Return [airline, price].",
        "I'm visiting SF for Startup School and need to arrive Friday 2026-08-15. Can you see what "
        "flights leave from Seattle? Return [airline, price].",
    ], [0, 0, 0]),

    # DECISION (2026-07-20): a different optimization objective is INTENT-defining, not a param —
    # cheapest reads/sorts price, fastest reads/sorts duration, fewest-stops reads/sorts stops:
    # different extraction => different code => different skill. So these SPLIT.
    ("objective_split", "split", [
        "Find the cheapest flight from SEA to SFO on 2026-08-15. Return [airline, price].",
        "Find the fastest flight from SEA to SFO on 2026-08-15. Return [airline, price].",
        "Find the flight with the fewest stops from SEA to SFO on 2026-08-15. Return [airline, price].",
    ], [0, 1, 2]),

    ("constraint_as_param_merge", "merge", [
        "Find a hotel in San Francisco. Return [name, price].",
        "Find a hotel with a private bathroom in San Francisco. Return [name, price].",
        "Find a hotel near Moscone Center in San Francisco. Return [name, price].",
    ], [0, 0, 0]),

    ("verb_object_split", "split", [
        "Find the cheapest laptop stand on Amazon. Return [brand, price].",
        "Find the best-rated laptop stand on Amazon. Return [brand, price].",
    ], [0, 1]),

    ("action_split", "split", [
        "Search for flights from SEA to SFO on 2026-08-15. Return [airline, price].",
        "Book a flight from SEA to SFO on 2026-08-15.",
        "Cancel my flight from SEA to SFO.",
    ], [0, 1, 2]),

    ("cross_site_split", "split", [
        "Find the cheapest wireless mouse on Amazon. Return [brand, price].",
        "Find the cheapest wireless mouse on eBay. Return [brand, price].",
    ], [0, 1]),

    ("search_compare_recommend_split", "split", [
        "Find flights from SEA to SFO on 2026-08-15. Return a list of [airline, price].",
        "Compare these three SEA->SFO flights and return which has the lowest price.",
        "Recommend which SEA->SFO flight I should take given I prefer mornings. Return a recommendation.",
    ], [0, 1, 2]),
]


def partition_from_groups(groups, n):
    """map task index -> group id (or -1 if the model dropped it)."""
    lab = [-1] * n
    for gid, g in enumerate(groups):
        for m in g.get("members", []):
            i = m.get("i")
            if isinstance(i, int) and 0 <= i < n:
                lab[i] = gid
    return lab


def pairs_ok(pred, gold):
    n = len(gold)
    if any(x == -1 for x in pred):
        return False  # a dropped/duplicated index is a contract failure -> case fails
    for i in range(n):
        for j in range(i + 1, n):
            if (pred[i] == pred[j]) != (gold[i] == gold[j]):
                return False
    return True


def run(label, prompt, draws):
    L._GROUP_SYS = prompt
    print(f"\n================= {label} ({draws} draws) =================")
    total_pass = total = 0
    for name, kind, tasks, gold in CASES:
        runs = [{"task": t} for t in tasks]
        oks = 0
        got_counts = []
        for _ in range(draws):
            groups = L.group_chunk(runs, existing_templates=[])
            got_counts.append(len(groups))
            if pairs_ok(partition_from_groups(groups, len(tasks)), gold):
                oks += 1
        total_pass += oks
        total += draws
        print(f"  [{kind:5s}] {name:32s} {oks}/{draws} pass   (n_templates seen: {got_counts})")
    print(f"  ---- {label}: {total_pass}/{total} draw-cases passed ----")
    return total_pass, total


if __name__ == "__main__":
    draws = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    bp, bt = run("BASELINE", BASELINE, draws)
    hp, ht = run("HARDENED", HARDENED, draws)
    print(f"\n##### SUMMARY (gpt-5.x) #####")
    print(f"BASELINE {bp}/{bt}   HARDENED {hp}/{ht}")
