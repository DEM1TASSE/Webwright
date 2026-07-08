"""python -m webwright.skills <learn|update> — friendly entry points."""
import sys

CMDS = {"learn": "webwright.skills.learn", "update": "webwright.skills.update"}

def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in CMDS:
        import importlib
        mod = importlib.import_module(CMDS[sys.argv[1]])
        return mod.main(sys.argv[2:])
    print("usage: python -m webwright.skills <learn|update> …\n"
          "  learn   distill a folder of finished runs into skills (no manifest needed)\n"
          "  update  manual mode: distill from an explicit batch.json manifest")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
