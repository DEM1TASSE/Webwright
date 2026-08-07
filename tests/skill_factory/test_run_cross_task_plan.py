import importlib.util
from pathlib import Path


_PATH = Path(__file__).parents[2] / "evals" / "webarena" / "run_cross_task_plan.py"
_SPEC = importlib.util.spec_from_file_location("run_cross_task_plan", _PATH)
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)


def test_planned_jobs_preserve_site_queues(tmp_path):
    (tmp_path / "a.json").write_text(
        '{"source":{"task_ids":[1,2]},"heldout":[]}'
    )
    (tmp_path / "b.json").write_text(
        '{"source":{"task_ids":[3,4]},"heldout":[]}'
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"sites":{"a":"a.json","b":"b.json"}}')
    assert R.planned_jobs(manifest, "train") == [
        ("a", tmp_path / "a.json", 1, "scratch"),
        ("a", tmp_path / "a.json", 2, "scratch"),
        ("b", tmp_path / "b.json", 3, "scratch"),
        ("b", tmp_path / "b.json", 4, "scratch"),
    ]


def test_partition_site_jobs_allows_bounded_parallel_lanes():
    jobs = [
        ("a", "split", 1, "scratch"),
        ("a", "split", 2, "scratch"),
        ("a", "split", 3, "scratch"),
        ("b", "split", 4, "scratch"),
        ("b", "split", 5, "scratch"),
    ]
    assert R.partition_site_jobs(jobs, 2) == [
        [jobs[0], jobs[2]], [jobs[1]], [jobs[3]], [jobs[4]],
    ]


def test_resume_requires_failure_aware_record(tmp_path):
    result = tmp_path / "result.json"
    result.write_text('{"correct": false}')
    assert R.resumable_result(result) is False
    result.write_text('{"correct": false, "process_returncode": -15}')
    assert R.resumable_result(result) is True


def test_library_for_site_prefers_independent_site_directory(tmp_path):
    assert R.library_for_site(tmp_path, "map") == tmp_path
    (tmp_path / "map").mkdir()
    assert R.library_for_site(tmp_path, "map") == tmp_path / "map"
