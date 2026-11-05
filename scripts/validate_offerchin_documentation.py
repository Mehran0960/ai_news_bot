#!/usr/bin/env python3
"""Enforce OfferChin documentation updates for implementation changes.

Generated runtime ledgers are deliberately excluded: documenting every scheduled
cursor/state write would create noise and encourage unsafe edits to live state.
Manual edits to those files still require a handbook and changelog entry.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import PurePosixPath
from typing import Iterable

HANDBOOK = "docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md"
CHANGELOG = "docs/CHANGELOG_FA.md"
REQUIRED_CHANGELOG_FIELDS = (
    "**هدف:**",
    "**تغییر/اقدام:**",
    "**فایل‌ها/سامانه‌ها:**",
    "**آزمون و نتیجه:**",
    "**شواهد/شناسه:**",
    "**ریسک/بازگشت:**",
    "**وضعیت:**",
)

RUNTIME_GENERATED_NAMES = {
    "state.json",
    "catalog_sweep_state.json",
    "catalog_sweep_candidates.json",
    "candidates.json",
    "diversity_report.json",
    "integrity_audit_state.json",
    "video_upload_dispatch_state.json",
    "campaign_publication_state.json",
}


def is_runtime_generated(path: str) -> bool:
    name = PurePosixPath(path).name
    return (
        name in RUNTIME_GENERATED_NAMES
        or name.endswith("_state.json")
        or name.endswith("_report.json")
    )


def is_offerchin_implementation_file(path: str) -> bool:
    """Return True for OfferChin source/config/workflow files, not runtime ledgers."""
    normalized = path.replace("\\", "/").lstrip("./")
    if is_runtime_generated(normalized):
        return False

    if normalized.startswith("affilio_radar/"):
        return True
    if normalized == "cloudflare/affilio-minute-dispatcher.js":
        return True
    if normalized.startswith("offerchin-site/"):
        return True
    if normalized.startswith("scripts/"):
        return True
    if normalized.startswith(".github/workflows/"):
        name = PurePosixPath(normalized).name.lower()
        return name.startswith(("offerchin-", "affilio-"))
    return False


def added_changelog_entries(previous: str, current: str) -> list[str]:
    """Return newly introduced dated sections, preserving append-only semantics."""
    old = set(re.findall(r"^##\\s+\\d{4}-\\d{2}-\\d{2}[^\\n]*$", previous, re.M))
    new = re.findall(r"^##\\s+\\d{4}-\\d{2}-\\d{2}[^\\n]*$", current, re.M)
    return [heading for heading in new if heading not in old]


def validate_change(
    changed_paths: Iterable[str],
    handbook_changed: bool,
    changelog_changed: bool,
    previous_changelog: str,
    current_changelog: str,
) -> list[str]:
    implementation_changes = [
        p for p in changed_paths if is_offerchin_implementation_file(p)
    ]
    if not implementation_changes:
        return []

    errors: list[str] = []
    if not handbook_changed:
        errors.append(f"Implementation changes require updating {HANDBOOK}.")
    if not changelog_changed:
        errors.append(f"Implementation changes require updating {CHANGELOG}.")
        return errors

    entries = added_changelog_entries(previous_changelog, current_changelog)
    if not entries:
        errors.append("CHANGELOG_FA.md must contain a new dated section (## YYYY-MM-DD — ...).")
        return errors

    latest_heading = entries[-1]
    start = current_changelog.find(latest_heading)
    next_heading = re.search(r"^##\\s+", current_changelog[start + len(latest_heading):], re.M)
    end = start + len(latest_heading) + next_heading.start() if next_heading else len(current_changelog)
    entry_body = current_changelog[start:end]

    missing = [field for field in REQUIRED_CHANGELOG_FIELDS if field not in entry_body]
    if missing:
        errors.append("Newest changelog entry is missing required fields: " + ", ".join(missing))
    return errors


def git_text(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def run(base: str, head: str) -> int:
    changed = [
        line.strip()
        for line in git_text("diff", "--name-only", "--diff-filter=ACMR", f"{base}...{head}").splitlines()
        if line.strip()
    ]
    handbook_changed = HANDBOOK in changed
    changelog_changed = CHANGELOG in changed
    previous = git_text("show", f"{base}:{CHANGELOG}") if _git_path_exists(base, CHANGELOG) else ""
    current = git_text("show", f"{head}:{CHANGELOG}") if _git_path_exists(head, CHANGELOG) else ""

    errors = validate_change(
        changed, handbook_changed, changelog_changed, previous, current
    )
    implementation_changes = [
        p for p in changed if is_offerchin_implementation_file(p)
    ]
    if errors:
        print("OFFERCHIN_DOCUMENTATION_GATE_FAILED")
        for error in errors:
            print(f"- {error}")
        print("Update both the technical handbook and append a fully structured changelog entry.")
        return 1

    if implementation_changes:
        print("OFFERCHIN_DOCUMENTATION_GATE_PASSED")
        print(f"implementation_files={len(implementation_changes)}")
        print(f"handbook_updated={handbook_changed} changelog_updated={changelog_changed}")
    else:
        print("OFFERCHIN_DOCUMENTATION_GATE_NOT_REQUIRED: no OfferChin implementation files changed.")
    return 0


def _git_path_exists(ref: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Base commit/ref")
    parser.add_argument("--head", required=True, help="Head commit/ref")
    args = parser.parse_args()
    try:
        return run(args.base, args.head)
    except subprocess.CalledProcessError as exc:
        print("Could not compute the documentation diff from Git refs.", file=sys.stderr)
        print(exc.stderr, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
