"""Router judgment eval: a small multi-skill library + a table of tasks with expected verdicts.
Runs recommend() live (decision only, no browser) and reports verdict vs expected per case."""
import os, sys, tempfile
sys.path.insert(0, os.path.expanduser("~/project/Code-Web-Skills/external/webwright/src"))
from webwright.skill_factory.library import Library, Skill
from webwright.tools.skill_use import recommend

STUB = "def run(x):\n    return None\n"   # not executed — recommend only decides


def build_library(root):
    lib = Library(root)
    def add(sid, template, summary, params, grade):
        lib.add(Skill(sid, STUB, {
            "template": template, "summary": summary,
            "signature": {"params": params}, "grade": grade,
            "output_schema": {"type": "array", "items": {"type": "string"}}}))
    add("nonstop_flight",
        "What is the earliest nonstop flight from {origin_city} ({origin_code}) to "
        "{destination_city} ({destination_code}) on {date}",
        "earliest nonstop flight between two airports on a date (Google Flights)",
        ["origin_city", "origin_code", "destination_city", "destination_code", "date"], "executable")
    add("cheapest_flight",
        "What is the cheapest flight from {origin_city} ({origin_code}) to "
        "{destination_city} ({destination_code}) on {date}",
        "cheapest flight between two airports on a date (Google Flights)",
        ["origin_city", "origin_code", "destination_city", "destination_code", "date"], "executable")
    add("bestsellers",
        "Get the top {n} best-selling {entity} in {period}",
        "top-N best-selling products/brands in a period (store admin dashboard)",
        ["n", "entity", "period"], "reference")     # NOT executable -> should be adapt, never run
    add("product_reviews",
        "Get the reviewers who mention {description} for the product on the current page",
        "reviewers mentioning a description for the product on the current page",
        ["description"], "executable")
    add("repo_clone_url",
        "Get the URL to clone {repo} with SSH",
        "SSH clone URL for a GitHub repository",
        ["repo"], "executable")
    return lib


# (task, expected_verdict, note)
CASES = [
    ("What is the earliest nonstop flight from Seattle (SEA) to Denver (DEN) on 2026-08-26?",
     "run", "exact match, executable, fits, fillable"),
    ("What is the earliest 1-stop flight from Seattle (SEA) to Denver (DEN) on 2026-08-26?",
     "adapt", "nonstop skill, only the stop filter differs"),
    ("What is the cheapest flight from San Francisco (SFO) to Boston (BOS) on 2026-08-26?",
     "run", "matches the cheapest skill"),
    ("What is the cheapest nonstop flight under $300 from SEA to DEN on 2026-08-26?",
     "adapt", "3a: 'under $300' + 'nonstop' not expressible by cheapest template"),
    ("Get the top 5 best-selling products last month.",
     "adapt", "bestsellers is grade=reference -> not runnable, must adapt"),
    ("Get the reviewers who mention battery life for the product on the current page.",
     "run", "reviews skill, executable, fits, description fillable"),
    ("Get the SSH clone URL for the vercel/next.js repository.",
     "run", "repo clone skill, executable"),
    ("How many commits did torvalds make to torvalds/linux on 2024-07-29?",
     "skip", "no commits skill in this library"),
    ("Book the cheapest hotel in Paris for next weekend.",
     "skip", "no travel-lodging skill; flights are a different task"),
    ("What is the weather in Tokyo tomorrow?",
     "skip", "nothing relevant"),
]


def main():
    with tempfile.TemporaryDirectory() as d:
        build_library(d)
        ok = 0
        print(f"{'exp':5} {'got':6} {'✓':2} skill / reason")
        print("-" * 100)
        for task, expected, note in CASES:
            r = recommend(task, d)
            got = r["verdict"]
            hit = "✓" if got == expected else "✗"
            ok += got == expected
            print(f"{expected:5} {got:6} {hit:2} {str(r.get('skill_id')):26} | {note}")
            if got != expected:
                print(f'        └─ reason: {r.get("reason","")[:110]}')
        print("-" * 100)
        print(f"agreement: {ok}/{len(CASES)}")


if __name__ == "__main__":
    main()
