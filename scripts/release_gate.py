"""Decide whether a Release run publishes, and publish only when it may.

    python scripts/release_gate.py decide
    python scripts/release_gate.py publish --tag vX.Y.Z --sha <commit> --title "MellowDLP X.Y.Z" \\
        --notes-file notes.md FILE...

Both run inside .github/workflows/release.yml, from the repository root:
- decide: the version job. Reads APP_VERSION and the event, writes version, tag,
  publish, build and sha to $GITHUB_OUTPUT. Only a push can publish: a push to
  main whose version has no tag yet, or a pushed tag that equals APP_VERSION,
  is on main and has no release. Never at or below the highest stable release.
- publish: the last step of the publish job. Checks again that the tag is
  absent or on the tested commit, that no release (draft included) has the
  tag, and that the version is still above every stable release (one may have
  been published while this run was testing and building), then runs gh
  release create, once.

Version order: tags are vX.Y.Z (stable) or vX.Y.Z-label (pre-release). Only
stable, published releases set the bar: a candidate's X.Y.Z must be above the
highest of them, whether the candidate is stable or a pre-release. Pre-release
labels are never compared with each other or with stable versions, and an
existing pre-release never blocks anything. A stable release whose tag isn't
vX.Y.Z makes the order unknown, which stops the run.

Every check fails closed: a GitHub or git answer that isn't a clear yes or no
stops the run (exit 1, ::error:: annotation). tests/test_release_gate.py runs
this file against a throwaway git repository with GitHub mocked.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mellow import changelog  # noqa: E402

_SHA = re.compile(r"[0-9a-f]{40}")
_VERSION = re.compile(r"\d+\.\d+\.\d+")
_TAG = re.compile(r"v(\d+\.\d+\.\d+)(?:-([0-9A-Za-z][0-9A-Za-z.-]*))?")
_APP_VERSION = re.compile(r"""^APP_VERSION\s*(?::\s*str\s*)?=\s*["']([^"']+)["']""", re.MULTILINE)


class GateError(Exception):
    """A reason not to release; the run stops with it."""


def _gh(args: list[str]) -> tuple[bool, str]:
    """Run the GitHub CLI: (exit code 0, stdout + stderr)."""
    try:
        res = subprocess.run(["gh", *args], capture_output=True, text=True)
    except OSError as exc:   # no gh: an answer that is neither yes nor no
        return False, str(exc)
    return res.returncode == 0, (res.stdout + res.stderr).strip()


def _create_release(args: list[str]) -> None:
    """The one place a release is made."""
    subprocess.run(["gh", "release", "create", *args], check=True)


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _version_tuple(version: str) -> tuple[int, int, int]:
    if not _VERSION.fullmatch(version):
        raise GateError(f"not an X.Y.Z version: {version}")
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def parse_tag(tag: str) -> tuple[str, str | None]:
    """vX.Y.Z -> ("X.Y.Z", None); vX.Y.Z-label -> ("X.Y.Z", "label")."""
    match = _TAG.fullmatch(tag)
    if not match:
        raise GateError(f"not a release tag (vX.Y.Z or vX.Y.Z-label): {tag}")
    return match.group(1), match.group(2)


def app_version(root: Path) -> str:
    match = _APP_VERSION.search((root / "mellow" / "version.py").read_text(encoding="utf-8"))
    if not match or not _VERSION.fullmatch(match.group(1)):
        raise GateError("can't read APP_VERSION from mellow/version.py")
    return match.group(1)


def has_release_notes(root: Path, version: str) -> bool:
    entries = changelog.parse((root / "CHANGELOG.md").read_text(encoding="utf-8"))
    return any(e["version"] == version and e["items"] for e in entries)


def list_releases(repo: str) -> list[tuple[str, bool, bool]]:
    """Every release as (tag, draft, prerelease). Drafts are listed when the token may see them."""
    ok, out = _gh(["api", "--paginate", f"repos/{repo}/releases",
                   "--jq", ".[] | [.tag_name, .draft, .prerelease] | @tsv"])
    if not ok:
        raise GateError(f"could not list the releases: {out}")
    releases = []
    for line in out.splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or not fields[0] or {fields[1], fields[2]} - {"true", "false"}:
            raise GateError(f"unexpected answer listing the releases: {line!r}")
        releases.append((fields[0], fields[1] == "true", fields[2] == "true"))
    return releases


def highest_stable(releases: list[tuple[str, bool, bool]]) -> tuple[int, int, int] | None:
    stable = [tag for tag, draft, prerelease in releases if not draft and not prerelease]
    versions = []
    for tag in stable:
        version, label = parse_tag(tag)   # a stable release we can't order stops the run
        if label is not None:
            raise GateError(f"stable release {tag} has a pre-release tag: can't order the releases")
        versions.append(_version_tuple(version))
    return max(versions, default=None)


def check_order(releases: list[tuple[str, bool, bool]], tag: str) -> None:
    """The candidate's X.Y.Z must be above every stable release (see the module docstring)."""
    version, _label = parse_tag(tag)
    highest = highest_stable(releases)
    if highest is not None and _version_tuple(version) <= highest:
        raise GateError(f"{tag} is not above the latest stable release v{'.'.join(map(str, highest))}")


def remote_tag_commit(tag: str) -> str | None:
    """The commit tag points at on origin (annotated or lightweight), None if no such tag."""
    res = _git(["ls-remote", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"])
    if res.returncode != 0:
        raise GateError(f"could not list the tags (git exit {res.returncode}): {res.stderr.strip()}")
    refs = dict(reversed(line.split("\t", 1)) for line in res.stdout.splitlines() if "\t" in line)
    return refs.get(f"refs/tags/{tag}^{{}}") or refs.get(f"refs/tags/{tag}")


def on_main(sha: str) -> bool:
    res = _git(["merge-base", "--is-ancestor", sha, "origin/main"])
    if res.returncode in (0, 1):
        return res.returncode == 0
    raise GateError(f"could not check {sha} against main (git exit {res.returncode}): {res.stderr.strip()}")


def decide(env: dict, root: Path) -> dict:
    event, ref = env.get("GITHUB_EVENT_NAME", ""), env.get("GITHUB_REF", "")
    sha, repo = env.get("GITHUB_SHA", ""), env.get("GITHUB_REPOSITORY", "")
    if not _SHA.fullmatch(sha):
        raise GateError(f"not a full commit SHA: {sha!r}")
    version = app_version(root)
    out = {"version": version, "tag": "", "publish": "false", "build": "true", "sha": sha}

    # Only a pushed tag or a push to main can publish; a manual run (even on a tag) never does
    if event == "push" and ref.startswith("refs/tags/"):
        tag = ref.removeprefix("refs/tags/")
        if not _TAG.fullmatch(tag) or parse_tag(tag)[0] != version:
            raise GateError(f"Tag {tag} doesn't match APP_VERSION {version} in mellow/version.py")
        if not on_main(sha):
            raise GateError(f"Tag {tag} points at {sha}, which is not on main: only commits on main are released")
        out.update(tag=tag, publish="true")
    elif event == "push" and ref == "refs/heads/main":
        tag = f"v{version}"
        out["tag"] = tag
        if remote_tag_commit(tag) is not None:
            print(f"::notice::{tag} already exists: nothing to release")
            out["build"] = "false"
        else:
            out["publish"] = "true"

    if out["publish"] == "true":
        if not has_release_notes(root, version):
            raise GateError(f"CHANGELOG.md has no '## {version}' section: add the release notes")
        releases = list_releases(repo)
        if any(tag == out["tag"] for tag, _draft, _pre in releases):
            raise GateError(f"Release {out['tag']} already exists: a tag is never released twice")
        # Installed copies only move up: never at or below a stable release
        check_order(releases, out["tag"])
    return out


def publish(repo: str, tag: str, sha: str, title: str, notes_file: str, files: list[str]) -> None:
    if not _SHA.fullmatch(sha):
        raise GateError(f"not a full commit SHA: {sha!r}")
    if not files or not all(Path(f).is_file() for f in files):
        raise GateError(f"missing release files: {files}")
    _version, label = parse_tag(tag)
    # Last checks before anything is published. The tag either doesn't exist (a
    # release from main creates it) or already points at the commit that was tested
    # and built. Then, from one listing taken right before creating the release: no
    # release (not even a draft) has this tag, and no stable release at or above this
    # version appeared while this run was testing and building. Publishing runs share
    # one concurrency group, so only a release made outside this workflow could still
    # slip in between this listing and gh release create.
    tagged = remote_tag_commit(tag)
    if tagged and tagged != sha:
        raise GateError(f"Tag {tag} points at {tagged}, not the tested commit {sha}")
    releases = list_releases(repo)
    if any(existing == tag for existing, _draft, _pre in releases):
        raise GateError(f"Release {tag} already exists (it may be a draft): nothing is published twice")
    check_order(releases, tag)
    args = [tag, *files, "--repo", repo, "--target", sha, "--title", title,
            "--notes-file", notes_file, "--generate-notes"]
    if label is not None:
        args.append("--prerelease")
    _create_release(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("decide")
    pub = sub.add_parser("publish")
    pub.add_argument("--tag", required=True)
    pub.add_argument("--sha", required=True)
    pub.add_argument("--title", required=True)
    pub.add_argument("--notes-file", required=True)
    pub.add_argument("files", nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.command == "decide":
            out = decide(dict(os.environ), Path.cwd())
            lines = "".join(f"{key}={value}\n" for key, value in out.items())
            output = os.environ.get("GITHUB_OUTPUT")
            if output:
                with open(output, "a", encoding="utf-8") as fh:
                    fh.write(lines)
            print(f"APP_VERSION {out['version']}, tag '{out['tag']}', publish={out['publish']}, build={out['build']}")
        else:
            publish(os.environ.get("GITHUB_REPOSITORY", ""), args.tag, args.sha, args.title,
                    args.notes_file, args.files)
    except GateError as exc:
        print(f"::error::{exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
