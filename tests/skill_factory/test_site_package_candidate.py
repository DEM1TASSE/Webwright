import json

from webwright.skill_factory.site_package_candidate import (
    generate_site_package_candidate,
    validate_site_package_candidate,
    write_candidate_bundle,
)


CODE = """class GitLabSite:
    def __init__(self, page):
        self.page = page

    def _parse_rows(self, rows):
        return [{\"title\": row} for row in rows]

    def list_commits(self, project):
        rows = self.page.locator(\".commit-row\").all_inner_texts()
        return self._parse_rows(rows)
"""

SOURCE = """page.goto(base + project + '/-/commits/main')
rows = page.locator('.commit-row').all_inner_texts()
commits = [{"title": row} for row in rows]
print(commits)
"""


def candidate(code=CODE, output_contract=None):
    return {
        "site": "gitlab",
        "class_name": "GitLabSite",
        "package_code": code,
        "methods": [{
            "primitive_id": "gitlab/repository/list_commits",
            "feature": "repository",
            "method": "list_commits",
            "capability": "Read typed commit records from a GitLab project.",
            "owns": ["GitLab commit-page selector and record parsing"],
            "does_not_own": ["task-specific filtering and final answer formatting"],
            "input_contract": {"project": "str project path"},
            "output_contract": output_contract or {
                "type": "list[CommitRecord]", "fields": {"title": "str"}
            },
            "requires": ["authenticated_session"],
            "provides": ["typed_commit_records"],
            "source_evidence": [{
                "workflow_id": "w1", "template_id": 10,
                "code_quote": SOURCE,
                "explanation": "The source navigates to GitLab commits and parses commit rows.",
            }],
        }],
    }


WORKFLOWS = [{"id": "w1", "task_id": 1, "template_id": 10, "code": SOURCE}]


def test_generate_returns_raw_model_object_without_repair():
    raw = {"site": "wrong", "package_code": "broken"}
    result = generate_site_package_candidate(
        "gitlab", WORKFLOWS, llm_fn=lambda system, user: raw
    )
    assert result is raw


def test_retry_feedback_is_explicitly_passed_to_generator():
    captured = {}

    def fake(system, user):
        captured.update(json.loads(user))
        return {}

    generate_site_package_candidate(
        "gitlab", WORKFLOWS, prior_candidate={"bad": True},
        validation_feedback=["bad evidence"], llm_fn=fake,
    )
    assert captured["previous_rejected_candidate"] == {"bad": True}
    assert captured["validation_feedback"] == ["bad evidence"]


def test_valid_candidate_has_clear_workflow_primitive_boundary():
    result = validate_site_package_candidate(candidate(), site="gitlab", workflows=WORKFLOWS)
    assert result.accepted, result.errors


def test_rejects_raw_dom_contract_and_public_primitive_dependency():
    code = CODE.replace(
        "rows = self.page.locator", "rows = self.list_projects()\n        rows = self.page.locator"
    ).replace(
        "    def list_commits(self, project):",
        "    def list_projects(self):\n        return []\n\n    def list_commits(self, project):",
    )
    value = candidate(code, {"type": "Locator", "fields": {}})
    value["methods"].append({**value["methods"][0],
                             "primitive_id": "gitlab/repository/list_projects",
                             "method": "list_projects"})
    result = validate_site_package_candidate(value, site="gitlab", workflows=WORKFLOWS)
    assert not result.accepted
    assert any("untyped site output" in error for error in result.errors)
    assert any("calls public method" in error for error in result.errors)


def test_rejects_non_verbatim_evidence_and_index_code_mismatch():
    value = candidate()
    value["methods"][0]["source_evidence"][0]["code_quote"] = "x" * 100
    value["methods"][0]["method"] = "get_commits"
    result = validate_site_package_candidate(value, site="gitlab", workflows=WORKFLOWS)
    assert not result.accepted
    assert any("not a verbatim" in error for error in result.errors)
    assert any("do not match" in error for error in result.errors)


def test_bundle_is_candidate_only_and_preserves_exact_code(tmp_path):
    value = candidate()
    validation = validate_site_package_candidate(value, site="gitlab", workflows=WORKFLOWS)
    path = write_candidate_bundle(tmp_path, value, validation, site="gitlab", workflows=WORKFLOWS)
    assert (path / "package.py").read_text() == CODE
    index = json.loads((path / "index.json").read_text())
    assert index["status"] == "candidate"
    assert index["approved"] is False
    assert "not promoted" in (path / "review.md").read_text()
