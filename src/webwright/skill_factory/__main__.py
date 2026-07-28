"""python -m webwright.skill_factory <init|build|learn|update> — friendly entry points."""
import sys

CMDS = {
    "init": "webwright.skill_factory.init",
    "build": "webwright.skill_factory.build",
    "learn": "webwright.skill_factory.learn",
    "update": "webwright.skill_factory.update",
    "route": "webwright.skill_factory.route",
}

def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in CMDS:
        import importlib
        mod = importlib.import_module(CMDS[sys.argv[1]])
        return mod.main(sys.argv[2:])
    print("usage: python -m webwright.skill_factory <init|build|learn|update|route> …\n"
          "  init    draft a skill.yaml skeleton from a one-line need (you fill the values)\n"
          "  build   solve a spec's instances, then learn — for a task you haven't solved yet\n"
          "  learn   distill a folder of finished runs into skills (no manifest needed)\n"
          "  update  manual mode: distill from an explicit batch.json manifest\n"
          "  route   route a task: run a matching skill directly, or hand it to the agent")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
