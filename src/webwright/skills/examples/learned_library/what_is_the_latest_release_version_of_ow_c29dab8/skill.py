import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


def find_workspace() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve().parent
    return Path(os.environ.get("WORKSPACE_DIR", Path.cwd())).resolve()


WORKSPACE = find_workspace()
TASKSPEC_PATH = Path(sys.argv[1]).resolve()
AGENT_RESPONSE_PATH = WORKSPACE / "agent_response.json"

FINAL_RUNS = WORKSPACE / "final_runs"
FINAL_RUNS.mkdir(parents=True, exist_ok=True)


def next_run_dir() -> Path:
    existing = []
    for p in FINAL_RUNS.glob("run_*"):
        try:
            existing.append(int(p.name.split("_")[1]))
        except Exception:
            pass
    run_id = max(existing, default=0) + 1
    run_dir = FINAL_RUNS / f"run_{run_id:03d}"
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    return run_dir


RUN_DIR = next_run_dir()
SCREENSHOTS_DIR = RUN_DIR / "screenshots"
LOG_PATH = RUN_DIR / "final_script_log.txt"
LOG_PATH.write_text("", encoding="utf-8")


def log(msg: str) -> None:
    print(msg)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def load_taskspec(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_repo_urls(taskspec: dict) -> Tuple[str, str, str]:
    params = taskspec.get("params", {})
    owner = params["owner"]
    repo = params["repo"]
    base = taskspec.get("start_url") or f"https://github.com/{owner}/{repo}"
    base = base.rstrip("/")
    releases_url = f"{base}/releases"
    latest_url = f"{base}/releases/latest"
    return base, releases_url, latest_url


def extract_version_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r"\bv?\d+(?:\.\d+){1,}\b",
        r"\b\d{4}\.\d+(?:\.\d+)*\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(0)
    return None


def extract_version_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"/releases/tag/([^/?#]+)", url)
    if m:
        return m.group(1)
    return None


async def screenshot(page, step: int, name: str) -> None:
    await page.screenshot(path=str(SCREENSHOTS_DIR / f"final_execution_{step}_{name}.png"), full_page=True)


async def open_page(page, url: str, step: int, label: str) -> None:
    log(f"step {step} action: open {label} {url}")
    await page.goto(url, wait_until="domcontentloaded")
    log(f"step {step} observed url: {page.url}")
    log(f"step {step} observed title: {await page.title()}")
    await screenshot(page, step, label.replace(" ", "_"))


async def try_repo_page_release(page) -> Optional[str]:
    link = page.locator('a[href*="/releases/tag/"]').first
    try:
        await link.wait_for(timeout=3000)
        raw_text = (await link.inner_text()).strip()
        href = await link.get_attribute("href")
        version = extract_version_from_text(raw_text) or extract_version_from_url(href or "")
        log(f"repo page release candidate text={raw_text!r} href={href!r} parsed={version!r}")
        return version
    except PlaywrightTimeoutError:
        log("repo page did not expose a visible release tag link quickly")
        return None


async def open_latest_release_and_extract(page, latest_url: str) -> Optional[str]:
    await page.goto(latest_url, wait_until="domcontentloaded")
    current_url = page.url
    title = await page.title()
    body_text = await page.locator("main").inner_text() if await page.locator("main").count() > 0 else await page.locator("body").inner_text()
    version = (
        extract_version_from_url(current_url)
        or extract_version_from_text(title)
        or extract_version_from_text(body_text)
    )
    log(f"latest release page url={current_url}")
    log(f"latest release page title={title}")
    log(f"latest release extracted version={version!r}")
    return version


async def open_releases_page_and_extract(page, releases_url: str) -> Optional[str]:
    await page.goto(releases_url, wait_until="domcontentloaded")
    tag_link = page.locator('a[href*="/releases/tag/"]').first
    try:
        await tag_link.wait_for(timeout=5000)
    except PlaywrightTimeoutError:
        log("releases page did not show a tag link")
        return None
    raw_text = (await tag_link.inner_text()).strip()
    href = await tag_link.get_attribute("href")
    version = extract_version_from_text(raw_text) or extract_version_from_url(href or "")
    log(f"releases page first tag text={raw_text!r} href={href!r} parsed={version!r}")
    return version


def validate_version(version: Optional[str]) -> str:
    if not version or not isinstance(version, str):
        raise RuntimeError("Could not extract latest release version")
    return version.strip()


def write_response(data):
    AGENT_RESPONSE_PATH.write_text(json.dumps({"retrieved_data": data}, ensure_ascii=False), encoding="utf-8")


async def main():
    taskspec = load_taskspec(TASKSPEC_PATH)
    repo_url, releases_url, latest_url = build_repo_urls(taskspec)

    log(f"loaded taskspec from {TASKSPEC_PATH}")
    log(f"repo_url={repo_url}")
    log(f"releases_url={releases_url}")
    log(f"latest_url={latest_url}")

    step = 1
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await context.new_page()

        await open_page(page, repo_url, step, "repo_page")
        repo_candidate = await try_repo_page_release(page)
        step += 1

        version = None
        log(f"step {step} action: open latest release redirect page and extract version")
        version = await open_latest_release_and_extract(page, latest_url)
        await screenshot(page, step, "latest_release_page")
        step += 1

        if not version:
            log(f"step {step} action: fallback to releases page")
            version = await open_releases_page_and_extract(page, releases_url)
            await screenshot(page, step, "releases_page")
            step += 1

        if not version and repo_candidate:
            log(f"step {step} action: fallback to repo page candidate")
            version = repo_candidate
            step += 1

        version = validate_version(version)

        response_data = [version]
        write_response(response_data)
        log(f"final extracted version={version}")
        log(f"wrote {AGENT_RESPONSE_PATH} with retrieved_data matching output schema")
        await screenshot(page, step, "final_state")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
