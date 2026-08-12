"""The check that answers "would this actually run", not "does this parse".

Calibrated against real libraries: six true positives on the GitLab batch that invented
`self.base_url`, zero on the four scripted packages and on the clean Map batch.
"""
from __future__ import annotations

import pytest

from skill_agent.soundness import (
    check_hardcoded_hosts,
    check_method_code,
    check_package,
    check_primitives,
    hardcoded_hosts,
)

CLEAN = """
def list_commits(self, base_url, project_id):
    import json
    from urllib.request import urlopen
    with urlopen(f"{base_url}/api/v4/projects/{project_id}/repository/commits") as response:
        return {"commits": json.load(response)}
"""

INVENTED_STATE = """
def list_commits(self, project_id):
    from urllib.request import urlopen
    with urlopen(f"{self.base_url}/api/v4/projects/{project_id}") as response:
        return {"raw": response.read()}
"""

UNDEFINED_NAME = """
def get_issue_state(self, issue_url):
    self.page.goto(f"{base_url}{issue_url}")
    return {"body": self.page.locator("body").inner_text()}
"""


def test_accepts_a_method_that_resolves_everything():
    assert check_method_code(CLEAN, where="p") == []


def test_rejects_invented_constructor_state():
    errors = check_method_code(INVENTED_STATE, where="gitlab/list_commits")
    assert len(errors) == 1
    assert "self.base_url" in errors[0]
    assert "only stores `page`" in errors[0]


def test_rejects_an_undefined_bare_name():
    """The scripted pipeline derives base_url locally; forgetting to is a NameError."""
    errors = check_method_code(UNDEFINED_NAME, where="p")
    assert len(errors) == 1 and "`base_url`" in errors[0] and "NameError" in errors[0]


def test_accepts_the_derived_form_the_rules_ask_for():
    code = """
def get_issue_state(self, issue_url):
    from urllib.parse import urlparse
    parsed = urlparse(self.page.url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    self.page.goto(f"{base_url}{issue_url}")
    return {"ok": True}
"""
    assert check_method_code(code, where="p") == []


def test_self_page_and_private_helpers_are_available():
    code = """
def list_rows(self):
    return {"rows": self._parse(self.page.locator("table").inner_text())}

def _parse(self, text):
    return [line for line in text.splitlines() if line]
"""
    assert check_method_code(code, where="p") == []


def test_a_sibling_public_method_is_available():
    code = "def a(self):\n    return self.b()\n"
    assert check_method_code(code, where="p", known_methods=frozenset({"b"})) == []


@pytest.mark.parametrize("snippet", [
    "def f(self):\n    return [x for x in self.page.items()]\n",          # comprehension target
    "def f(self):\n    try:\n        pass\n    except ValueError as exc:\n        return exc\n",
    "def f(self):\n    with open('x') as handle:\n        return handle.read()\n",
    "def f(self, *args, **kwargs):\n    return (args, kwargs)\n",
])
def test_ordinary_binding_forms_are_not_false_positives(snippet):
    assert check_method_code(snippet, where="p") == []


def test_syntax_errors_are_reported_not_raised():
    assert "does not parse" in check_method_code("def f(self:\n", where="p")[0]


def test_check_primitives_labels_each_offender(tmp_path):
    errors = check_primitives([
        {"primitive_id": "gitlab/a", "method": "a", "method_code": INVENTED_STATE},
        {"primitive_id": "gitlab/b", "method": "b", "method_code": CLEAN},
    ])
    assert len(errors) == 1 and errors[0].startswith("gitlab/a:")


def test_check_package_resolves_classes_defined_later(tmp_path):
    """The root site class constructs feature classes declared further down the file."""
    package = tmp_path / "package.py"
    package.write_text('''
class GitLabCommits:

    def __init__(self, page):
        self.page = page

    def list_commits(self, base_url):
        return base_url

class GitLabSite:

    def __init__(self, page):
        self.commits = GitLabCommits(page)
''', encoding="utf-8")
    assert check_package(package) == []


class TestHardcodedHosts:
    """Decision A: the site address arrives from outside, so a literal one is a defect.

    Calibrated on real libraries: it flags the two scripted Map primitives and one scripted
    Shopping primitive that bake in a WebArena address, and nothing in either GitLab library,
    which take the address as a parameter or derive it from `self.page.url`.
    """

    def test_flags_a_baked_in_address(self):
        code = 'def geocode(self, query):\n    return "http://18.208.187.221:8085/search?q=" + query\n'
        errors = hardcoded_hosts(code, where="map/geocode")
        assert len(errors) == 1 and "18.208.187.221:8085" in errors[0]

    def test_flags_it_inside_an_f_string(self):
        code = 'def route(self, a):\n    return f"http://18.208.187.221:5000/route/v1/driving/{a}"\n'
        assert len(hardcoded_hosts(code, where="p")) == 1

    def test_a_parameterized_base_url_is_clean(self):
        code = 'def commits(self, base_url, pid):\n    return f"{base_url}/api/v4/projects/{pid}"\n'
        assert hardcoded_hosts(code, where="p") == []

    def test_a_derived_base_url_is_clean(self):
        code = ('def issue(self, path):\n'
                '    from urllib.parse import urlparse\n'
                '    p = urlparse(self.page.url)\n'
                '    return f"{p.scheme}://{p.netloc}{path}"\n')
        assert hardcoded_hosts(code, where="p") == []

    def test_relative_paths_are_clean(self):
        code = 'def issues(self):\n    self.page.goto("/dashboard/issues")\n'
        assert hardcoded_hosts(code, where="p") == []

    def test_check_hardcoded_hosts_labels_the_primitive(self):
        errors = check_hardcoded_hosts([
            {"primitive_id": "map/geocode", "method_code":
             'def geocode(self):\n    return "http://10.0.0.1:80/x"\n'},
            {"primitive_id": "map/clean", "method_code":
             'def clean(self, base):\n    return f"{base}/x"\n'}])
        assert len(errors) == 1 and errors[0].startswith("map/geocode:")
