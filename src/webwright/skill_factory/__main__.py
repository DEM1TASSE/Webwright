"""python -m webwright.skill_factory <init|build|learn|update> — friendly entry points."""
import sys

CMDS = {
    "init": "webwright.skill_factory.init",
    "build": "webwright.skill_factory.build",
    "learn": "webwright.skill_factory.learn",
    "update": "webwright.skill_factory.update",
    "route": "webwright.skill_factory.route",
    "om2w-eval": "webwright.skill_factory.om2w_eval",
    "webvoyager-eval": "webwright.skill_factory.webvoyager_eval",
}

def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in CMDS:
        import importlib
        mod = importlib.import_module(CMDS[sys.argv[1]])
        return mod.main(sys.argv[2:])
    print("usage: python -m webwright.skill_factory "
          "<init|build|learn|update|route|om2w-eval|webvoyager-eval> …\n"
          "  init    draft a skill.yaml skeleton from a one-line need (you fill the values)\n"
          "  build   solve a spec's instances, then learn — for a task you haven't solved yet\n"
          "  learn   distill a folder of finished runs into skills (no manifest needed)\n"
          "  update  manual mode: distill from an explicit batch.json manifest\n"
          "  route   route a task: run a matching skill directly, or hand it to the agent\n"
          "  om2w-eval  judge Webwright runs with an upstream Online-Mind2Web checkout\n"
          "  webvoyager-eval  judge Webwright runs with the WebVoyager protocol")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
