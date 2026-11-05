#!/usr/bin/env python3
"""Enforce OfferChin documentation updates for implementation changes."""
from __future__ import annotations

import argparse
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
DIGITS = set("0123456789۰۱۲۳۴۵۶۷۸۹")


def is_dated_heading(line: str) -> bool:
    """Accept ISO-style dates written with Latin or Persian numerals."""
    if not line.startswith("## "):
        return False
    date = line[3:13]
    return (
        len(date) == 10
        and date[4] == "-"
        and date[7] == "-"
        and all(ch in DIGITS for i, ch in enumerate(date) if i not in (4, 7))
    )


def is_offerchin_implementation_file(path: str) -> bool:
    """Return True for OfferChin source/config/workflow files, not generated ledgers."""
    normalized = path.replace("\\", "/").lstrip("./")
    name = PurePosixPath(normalized).name
    if (
        name in {
            "state.json",
            "catalog_sweep_state.json",
            "catalog_sweep_candidates.json",
            "candidates.json",
            "diversity_report.json",
            "integrity_audit_state.json",
            "video_upload_dispatch_state.json",
            "campaign_publication_state.json",
        }
        or name.endswith("_state.json")
        or name.endswith("_report.json")
    ):
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
        workflow = PurePosixPath(normalized).name.lower()
        return workflow.startswith(("offerchin-", "affilio-"))
    return False


def added_changelog_entries(previous: str, current: str) -> list[str]:
    """Return newly introduced dated sections, preserving append-only semantics."""
    old = {
        line.rstrip()
        for line in previous.splitlines()
        if is_dated_heading(line.rstrip())
    }
    new = [
        line.rstrip()
        for line in current.splitlines()
        if is_dated_heading(line.rstrip())
    ]
    return [heading for heading in new if heading not in old]


def _section_for_heading(content: str, heading: str) -> str:
    """Return a heading and its body up to the next level-two heading."""
    lines = content.splitlines(keepends=True)
    start = None
    offset = 0
    for index, line in enumerate(lines):
        if line.rstrip("\n\r") == heading:
            start = index
            break
        offset += len(line)
    if start is None:
        return ""

    end = len(content)
    running = offset + len(lines[start])
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            end = running
            break
        running += len(line)
    return content[offset:end]


def validate_change(
    changed_paths: Iterable[str],
    handbook_changed: bool,
    changelog_changed: bool,
    previous_changelog: str,
    current_changelog: str,
) -> list[str]:
    implementation_changes = [
        path for path in changed_paths if is_offerchin_implementation_file(path)
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
        errors.append(
            "CHANGELOG_FA.md must append a new dated section (## YYYY-MM-DD — ...)."
        )
        return errors

    latest_entry = _section_for_heading(current_changelog, entries[-1])
    missing = [
        field for field in REQUIRED_CHANGELOG_FIELDS if field not in latest_entry
    ]
    if missing:
        errors.append(
            "Newest changelog entry is missing required fields: "
            + ", ".join(missing)
        )
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


def _git_path_exists(ref: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def run(base: str, head: str) -> int:
    changed = [
        line.strip()
        for line in git_text(
            "diff", "--name-only", "--diff-filter=ACMR", f"{base}...{head}"
        ).splitlines()
        if line.strip()
    ]
    handbook_changed = HANDBOOK in changed
    changelog_changed = CHANGELOG in changed
    previous = (
        git_text("show", f"{base}:{CHANGELOG}")
        if _git_path_exists(base, CHANGELOG)
        else ""
    )
    current = (
        git_text("show", f"{head}:{CHANGELOG}")
        if _git_path_exists(head, CHANGELOG)
        else ""
    )

    implementation_changes = [
        path for path in changed if is_offerchin_implementation_file(path)
    ]
    errors = validate_change(
        changed,
        handbook_changed,
        changelog_changed,
        previous,
        current,
    )
    if errors:
        print("OFFERCHIN_DOCUMENTATION_GATE_FAILED")
        for error in errors:
            print(f"- {error}")
        print(
            "Update the technical handbook and append a complete structured changelog entry."
        )
        return 1

    if implementation_changes:
        print("OFFERCHIN_DOCUMENTATION_GATE_PASSED")
        print(f"implementation_files={len(implementation_changes)}")
        print(
            f"handbook_updated={handbook_changed} changelog_updated={changelog_changed}"
        )
    else:
        print(
            "OFFERCHIN_DOCUMENTATION_GATE_NOT_REQUIRED: "
            "no OfferChin implementation files changed."
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Base commit/ref")
    parser.add_argument("--head", required=True, help="Head commit/ref")
    args = parser.parse_args()
    try:
        return run(args.base, args.head)
    except subprocess.CalledProcessError as exc:
        print(
            "Could not compute the documentation diff from Git refs.",
            file=sys.stderr,
        )
        print(exc.stderr, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
