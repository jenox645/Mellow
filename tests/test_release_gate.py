"""The release gate: scripts/release_gate.py (what release.yml runs) and the workflow wiring.

Each test builds a throwaway git repository with its own bare "origin"; GitHub is a
fake release store and the publisher only records what it would have created.
"""
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / '.github' / 'workflows'

_spec = importlib.util.spec_from_file_location('release_gate', ROOT / 'scripts' / 'release_gate.py')
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _git(cwd, *args):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def _commit(work, version, notes, message):
    (work / 'mellow').mkdir(exist_ok=True)
    (work / 'mellow' / 'version.py').write_text(f'APP_VERSION = "{version}"\n', encoding='utf-8')
    (work / 'CHANGELOG.md').write_text(notes, encoding='utf-8')
    _git(work, 'add', '-A')
    _git(work, 'commit', '-q', '-m', message)
    return _git(work, 'rev-parse', 'HEAD')


class FakeGitHub:
    """Answers the script's one GitHub call, the release listing.

    `releases`: tags (a "-" makes a pre-release) or (tag, draft, prerelease) tuples.
    `fail` answers with an error, `raw` with that text instead of the listing.
    """

    def __init__(self, releases=(), fail=None, raw=None):
        self.releases, self.fail, self.raw, self.calls = list(releases), fail, raw, 0

    def __call__(self, args):
        self.calls += 1
        assert args[:3] == ['api', '--paginate', 'repos/owner/repo/releases'], args
        if self.fail is not None:
            return False, self.fail
        if self.raw is not None:
            return True, self.raw
        rows = [r if isinstance(r, tuple) else (r, False, '-' in r) for r in self.releases]
        return True, '\n'.join(f'{tag}\t{str(draft).lower()}\t{str(pre).lower()}' for tag, draft, pre in rows)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """main: 2.12.0 (tagged v2.12.0) then a bump to 2.13.0; `side`: a 2.13.0 commit off main."""
    origin, work = tmp_path / 'origin.git', tmp_path / 'work'
    _git(tmp_path, 'init', '-q', '--bare', str(origin))
    _git(origin, 'symbolic-ref', 'HEAD', 'refs/heads/main')
    _git(tmp_path, 'init', '-q', str(work))
    _git(work, 'symbolic-ref', 'HEAD', 'refs/heads/main')
    for key, value in (('user.name', 'Test'), ('user.email', 'test@example.invalid'),
                       ('commit.gpgsign', 'false'), ('tag.gpgsign', 'false'), ('core.autocrlf', 'false')):
        _git(work, 'config', key, value)
    old_notes = '## 2.12.0\n\n- **Old**: the previous release.\n'
    old = _commit(work, '2.12.0', old_notes, '2.12.0')
    _git(work, 'tag', 'v2.12.0')
    bump = _commit(work, '2.13.0', '## 2.13.0\n\n- **New**: this release.\n\n' + old_notes, '2.13.0')
    _git(work, 'checkout', '-q', '-b', 'side')
    side = _commit(work, '2.13.0', '## 2.13.0\n\n- **Side**: not on main.\n\n' + old_notes, 'side')
    _git(work, 'checkout', '-q', 'main')
    _git(work, 'remote', 'add', 'origin', str(origin))
    _git(work, 'push', '-q', 'origin', 'main', 'side', 'v2.12.0')
    _git(work, 'fetch', '-q', 'origin')
    monkeypatch.chdir(work)
    published = []
    monkeypatch.setattr(gate, '_gh', FakeGitHub(['v2.12.0']))
    monkeypatch.setattr(gate, '_create_release', published.append)   # the intercepted publisher
    return SimpleNamespace(work=work, origin=origin, old=old, bump=bump, side=side, published=published)


def _decide(repo, event, ref, sha):
    _git(repo.work, 'checkout', '-q', sha)
    env = {'GITHUB_EVENT_NAME': event, 'GITHUB_REF': ref, 'GITHUB_SHA': sha,
           'GITHUB_REPOSITORY': 'owner/repo'}
    return gate.decide(env, repo.work)


def _publish(repo, tag, sha):
    files = []
    for name in ('MellowDLP-2.13.0-linux-x86_64', 'SHA256SUMS.txt'):
        path = repo.work / name
        path.write_text('x', encoding='utf-8')
        files.append(str(path))
    gate.publish('owner/repo', tag, sha, 'MellowDLP 2.13.0', 'notes.md', files)
    return files


def _use_github(monkeypatch, *releases, fail=None, raw=None):
    github = FakeGitHub(releases, fail=fail, raw=raw)
    monkeypatch.setattr(gate, '_gh', github)
    return github


# --- decide: what may publish ---

def test_push_to_main_with_a_new_version_publishes(repo):
    out = _decide(repo, 'push', 'refs/heads/main', repo.bump)
    assert out == {'version': '2.13.0', 'tag': 'v2.13.0', 'publish': 'true', 'build': 'true',
                   'sha': repo.bump}


def test_push_to_main_of_a_tagged_version_builds_nothing(repo):
    # Also what a revert to the previous version looks like
    out = _decide(repo, 'push', 'refs/heads/main', repo.old)
    assert (out['publish'], out['build']) == ('false', 'false')


def test_a_tag_on_main_that_matches_publishes(repo):
    out = _decide(repo, 'push', 'refs/tags/v2.13.0', repo.bump)
    assert (out['tag'], out['publish']) == ('v2.13.0', 'true')


def test_a_suffix_tag_is_a_prerelease_of_that_version(repo):
    out = _decide(repo, 'push', 'refs/tags/v2.13.0-rc1', repo.bump)
    assert (out['tag'], out['publish']) == ('v2.13.0-rc1', 'true')


@pytest.mark.parametrize('event, ref', [
    ('workflow_dispatch', 'refs/tags/v2.13.0'),   # a manual run on a tag
    ('workflow_dispatch', 'refs/heads/main'),
    ('pull_request', 'refs/pull/1/merge'),
    ('push', 'refs/heads/side'),
])
def test_only_a_push_to_main_or_of_a_tag_can_publish(repo, event, ref):
    out = _decide(repo, event, ref, repo.bump)
    assert (out['publish'], out['build']) == ('false', 'true')


# --- decide: what is refused ---

def test_a_tag_off_main_is_refused(repo):
    with pytest.raises(gate.GateError, match='not on main'):
        _decide(repo, 'push', 'refs/tags/v2.13.0', repo.side)


def test_a_tag_that_isnt_app_version_is_refused(repo):
    with pytest.raises(gate.GateError, match="doesn't match APP_VERSION 2.13.0"):
        _decide(repo, 'push', 'refs/tags/v9.9.9', repo.bump)


def test_a_tag_whose_release_exists_is_refused(repo, monkeypatch):
    _use_github(monkeypatch, 'v2.13.0', 'v2.12.0')
    with pytest.raises(gate.GateError, match='already exists'):
        _decide(repo, 'push', 'refs/tags/v2.13.0', repo.bump)


@pytest.mark.parametrize('ref', ['refs/heads/main', 'refs/tags/v2.13.0'])
def test_a_version_below_the_latest_release_is_refused(repo, monkeypatch, ref):
    _use_github(monkeypatch, 'v2.14.0', 'v2.12.0')
    with pytest.raises(gate.GateError, match='not above the latest stable release v2.14.0'):
        _decide(repo, 'push', ref, repo.bump)


def test_a_version_without_release_notes_is_refused(repo):
    _git(repo.work, 'checkout', '-q', 'main')
    sha = _commit(repo.work, '2.14.0', '## 2.13.0\n\n- **New**: this release.\n', 'no notes')
    with pytest.raises(gate.GateError, match="no '## 2.14.0' section"):
        _decide(repo, 'push', 'refs/heads/main', sha)


@pytest.mark.parametrize('ref', ['refs/heads/main', 'refs/tags/v2.13.0'])
def test_a_github_error_stops_the_run(repo, monkeypatch, ref):
    _use_github(monkeypatch, fail='gh: Bad Gateway (HTTP 502)')
    with pytest.raises(gate.GateError, match=r'could not list the releases: gh: Bad Gateway \(HTTP 502\)'):
        _decide(repo, 'push', ref, repo.bump)


def test_an_unreachable_origin_stops_the_run(repo):
    _git(repo.work, 'remote', 'set-url', 'origin', str(repo.work.parent / 'gone.git'))
    with pytest.raises(gate.GateError, match='could not list the tags'):
        _decide(repo, 'push', 'refs/heads/main', repo.bump)


def test_a_sha_that_isnt_a_full_commit_is_refused(repo):
    env = {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': 'main',
           'GITHUB_REPOSITORY': 'owner/repo'}
    with pytest.raises(gate.GateError, match='full commit SHA'):
        gate.decide(env, repo.work)


# --- publish: the last check, then the (intercepted) publisher ---

def test_publish_creates_the_release_on_the_tested_commit(repo):
    files = _publish(repo, 'v2.13.0', repo.bump)
    assert repo.published == [['v2.13.0', *files, '--repo', 'owner/repo', '--target', repo.bump,
                               '--title', 'MellowDLP 2.13.0', '--notes-file', 'notes.md',
                               '--generate-notes']]


def test_publish_marks_a_suffix_tag_as_prerelease(repo):
    _publish(repo, 'v2.13.0-rc1', repo.bump)
    assert repo.published[0][-1] == '--prerelease'


@pytest.mark.parametrize('annotated', [False, True])
def test_publish_accepts_a_tag_already_on_the_tested_commit(repo, annotated):
    # A pushed tag, or a run that created the tag and failed before the release
    _git(repo.work, 'tag', *(['-a', '-m', 'v2.13.0'] if annotated else []), 'v2.13.0', repo.bump)
    _git(repo.work, 'push', '-q', 'origin', 'v2.13.0')
    _publish(repo, 'v2.13.0', repo.bump)
    assert len(repo.published) == 1


def test_publish_refuses_a_tag_on_another_commit(repo):
    _git(repo.work, 'push', '-q', 'origin', f'{repo.old}:refs/tags/v2.13.0')
    with pytest.raises(gate.GateError, match='not the tested commit'):
        _publish(repo, 'v2.13.0', repo.bump)
    assert repo.published == []


def test_publish_refuses_when_the_release_exists(repo, monkeypatch):
    _use_github(monkeypatch, 'v2.13.0', 'v2.12.0')
    with pytest.raises(gate.GateError, match='already exists'):
        _publish(repo, 'v2.13.0', repo.bump)
    assert repo.published == []


def test_publish_refuses_on_a_github_error(repo, monkeypatch):
    _use_github(monkeypatch, fail='gh: Bad Gateway (HTTP 502)')
    with pytest.raises(gate.GateError, match=r'could not list the releases: gh: Bad Gateway \(HTTP 502\)'):
        _publish(repo, 'v2.13.0', repo.bump)
    assert repo.published == []


def test_a_failed_call_with_no_output_is_not_an_empty_listing(repo, monkeypatch):
    # gh exiting non-zero with nothing on stdout must not read as "no releases yet"
    _use_github(monkeypatch, fail='')
    with pytest.raises(gate.GateError, match='could not list the releases'):
        _publish(repo, 'v2.13.0', repo.bump)
    assert repo.published == []


def test_publish_refuses_when_origin_is_unreachable(repo):
    _git(repo.work, 'remote', 'set-url', 'origin', str(repo.work.parent / 'gone.git'))
    with pytest.raises(gate.GateError, match='could not list the tags'):
        _publish(repo, 'v2.13.0', repo.bump)
    assert repo.published == []


# --- version order, checked again right before publishing ---

@pytest.mark.parametrize('newer', ['v2.13.1', 'v2.14.0', 'v3.0.0'])
def test_publish_refuses_a_version_overtaken_while_the_run_was_building(repo, monkeypatch, newer):
    # decide() sees 2.12.0 as the latest and lets 2.13.0 through; while this run tests
    # and builds, another run publishes something newer
    github = _use_github(monkeypatch, 'v2.12.0')
    assert _decide(repo, 'push', 'refs/heads/main', repo.bump)['publish'] == 'true'
    github.releases.insert(0, newer)
    with pytest.raises(gate.GateError, match=f'not above the latest stable release {newer}'):
        _publish(repo, 'v2.13.0', repo.bump)
    assert repo.published == []


def test_publish_lists_the_releases_once_right_before_creating(repo, monkeypatch):
    github = _use_github(monkeypatch, 'v2.12.0')
    _publish(repo, 'v2.13.0', repo.bump)
    assert github.calls == 1 and len(repo.published) == 1


@pytest.mark.parametrize('release', [
    'v2.14.0-rc1',                    # a pre-release never raises the bar
    ('v2.14.0', True, False),         # nor does a draft of another version
])
def test_only_published_stable_releases_set_the_bar(repo, monkeypatch, release):
    _use_github(monkeypatch, release, 'v2.12.0')
    _publish(repo, 'v2.13.0', repo.bump)
    assert len(repo.published) == 1


def test_a_draft_with_the_same_tag_blocks_publishing(repo, monkeypatch):
    # A publish step that failed half way can leave one: an owner decides what to do with it
    _use_github(monkeypatch, ('v2.13.0', True, False), 'v2.12.0')
    with pytest.raises(gate.GateError, match='already exists'):
        _publish(repo, 'v2.13.0', repo.bump)
    assert repo.published == []


@pytest.mark.parametrize('stage', ['decide', 'publish'])
def test_a_prerelease_of_a_released_version_is_refused(repo, monkeypatch, stage):
    _use_github(monkeypatch, 'v2.13.0', 'v2.12.0')
    with pytest.raises(gate.GateError, match='not above the latest stable release v2.13.0'):
        if stage == 'decide':
            _decide(repo, 'push', 'refs/tags/v2.13.0-rc1', repo.bump)
        else:
            _publish(repo, 'v2.13.0-rc1', repo.bump)
    assert repo.published == []


def test_prerelease_labels_are_not_ordered(repo, monkeypatch):
    # rc2 after rc3 is fine: only the X.Y.Z part is compared, and only with stable releases
    _use_github(monkeypatch, 'v2.13.0-rc3', 'v2.13.0-rc1', 'v2.12.0')
    assert _decide(repo, 'push', 'refs/tags/v2.13.0-rc2', repo.bump)['publish'] == 'true'
    _publish(repo, 'v2.13.0-rc2', repo.bump)
    assert repo.published[0][-1] == '--prerelease'


@pytest.mark.parametrize('release, message', [
    ('nightly', 'not a release tag'),
    ('v2.13', 'not a release tag'),
    (('v2.14.0-rc1', False, False), 'has a pre-release tag'),   # marked stable
])
def test_a_stable_release_that_cant_be_ordered_stops_publishing(repo, monkeypatch, release, message):
    _use_github(monkeypatch, release, 'v2.12.0')
    with pytest.raises(gate.GateError, match=message):
        _publish(repo, 'v2.13.0', repo.bump)
    assert repo.published == []


@pytest.mark.parametrize('raw', ['v2.12.0\tmaybe\tfalse', 'v2.12.0\tfalse', '\tfalse\tfalse'])
def test_an_unexpected_listing_stops_publishing(repo, monkeypatch, raw):
    _use_github(monkeypatch, raw=raw)
    with pytest.raises(gate.GateError, match='unexpected answer'):
        _publish(repo, 'v2.13.0', repo.bump)
    assert repo.published == []


@pytest.mark.parametrize('tag', ['v2.13.0-', 'v2.13.0.1', 'V2.13.0', 'v2.13.0+build'])
def test_a_malformed_tag_is_refused(repo, tag):
    with pytest.raises(gate.GateError, match="doesn't match APP_VERSION"):
        _decide(repo, 'push', f'refs/tags/{tag}', repo.bump)
    with pytest.raises(gate.GateError, match='not a release tag'):
        _publish(repo, tag, repo.bump)
    assert repo.published == []


def test_a_second_attempt_at_the_same_version_is_refused(repo, monkeypatch):
    # Two runs for one version (a push to main and a tag push): once the first has
    # published, the second decides nothing to release or is refused
    _publish(repo, 'v2.13.0', repo.bump)
    _git(repo.work, 'push', '-q', 'origin', f'{repo.bump}:refs/tags/v2.13.0')   # what gh release created
    _use_github(monkeypatch, 'v2.13.0', 'v2.12.0')
    assert _decide(repo, 'push', 'refs/heads/main', repo.bump)['publish'] == 'false'
    with pytest.raises(gate.GateError, match='already exists'):
        _decide(repo, 'push', 'refs/tags/v2.13.0', repo.bump)
    with pytest.raises(gate.GateError, match='already exists'):
        _publish(repo, 'v2.13.0', repo.bump)
    assert len(repo.published) == 1


# --- the command line, as the workflow calls it ---

def test_decide_writes_the_step_outputs(repo, monkeypatch, tmp_path):
    _git(repo.work, 'checkout', '-q', repo.bump)
    output = tmp_path / 'github_output'
    for key, value in {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': repo.bump,
                       'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_OUTPUT': str(output)}.items():
        monkeypatch.setenv(key, value)
    assert gate.main(['decide']) == 0
    assert output.read_text(encoding='utf-8').splitlines() == [
        'version=2.13.0', 'tag=v2.13.0', 'publish=true', 'build=true', f'sha={repo.bump}']


def test_a_refusal_exits_non_zero_with_an_annotation(repo, monkeypatch, capsys):
    _git(repo.work, 'checkout', '-q', repo.side)
    for key, value in {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/tags/v2.13.0', 'GITHUB_SHA': repo.side,
                       'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_OUTPUT': ''}.items():
        monkeypatch.setenv(key, value)
    assert gate.main(['decide']) == 1
    assert capsys.readouterr().out.startswith('::error::Tag v2.13.0 points at')


@pytest.mark.skipif(sys.platform == 'win32', reason='a fake gh on PATH is a shell script')
def test_the_real_gh_boundary_fails_closed(repo, tmp_path):
    # The script as the workflow starts it, with a gh that answers every call with an error
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    fake = bin_dir / 'gh'
    fake.write_text('#!/bin/sh\necho "gh: Service Unavailable (HTTP 503)" >&2\nexit 1\n', encoding='utf-8')
    fake.chmod(0o755)
    _git(repo.work, 'checkout', '-q', repo.bump)
    env = {**os.environ, 'PATH': f'{bin_dir}{os.pathsep}{os.environ["PATH"]}', 'GITHUB_EVENT_NAME': 'push',
           'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': repo.bump, 'GITHUB_REPOSITORY': 'owner/repo',
           'GITHUB_OUTPUT': str(tmp_path / 'out')}
    res = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'release_gate.py'), 'decide'],
                         cwd=repo.work, env=env, capture_output=True, text=True)
    assert res.returncode == 1
    assert 'HTTP 503' in res.stdout
    assert not (tmp_path / 'out').exists()


# --- the workflow wiring around the script ---

def _jobs(path):
    """{job name: its block of text} for a workflow file."""
    text = path.read_text(encoding='utf-8')
    body = text[text.index('\njobs:\n'):]
    parts = re.split(r'^  ([\w-]+):\n', body, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2]))


def test_release_builds_and_publishes_only_after_validating_that_commit():
    jobs = _jobs(WORKFLOWS / 'release.yml')
    tested = "needs.validate.result == 'success'"
    same = 'needs.validate.outputs.sha == needs.version.outputs.sha'
    assert 'uses: ./.github/workflows/validate.yml' in jobs['validate']
    assert 'sha: ${{ needs.version.outputs.sha }}' in jobs['validate']
    for name in ('windows', 'linux'):
        assert 'needs: [version, validate]' in jobs[name]
        assert tested in jobs[name] and same in jobs[name]
        assert 'ref: ${{ needs.version.outputs.sha }}' in jobs[name]   # builds the validated commit
    publish = jobs['publish']
    assert 'needs: [version, validate, windows, linux]' in publish
    for condition in (tested, same, "needs.windows.result == 'success'", "needs.linux.result == 'success'",
                      "needs.version.outputs.publish == 'true'"):
        assert condition in publish


def test_release_decisions_are_the_scripts():
    jobs = _jobs(WORKFLOWS / 'release.yml')
    assert 'run: python3 scripts/release_gate.py decide' in jobs['version']
    assert 'python3 scripts/release_gate.py publish' in jobs['publish']
    workflow = (WORKFLOWS / 'release.yml').read_text(encoding='utf-8')
    commands = [line for line in workflow.splitlines() if not line.strip().startswith('#')]
    assert not [line for line in commands if 'gh release' in line or 'gh api' in line]   # only through the script
    assert re.search(r"group: \$\{\{ github\.event_name == 'push' && 'release-publish'", workflow)


def test_only_the_publish_job_can_write():
    jobs = _jobs(WORKFLOWS / 'release.yml')
    assert [name for name, block in jobs.items() if 'contents: write' in block] == ['publish']
    downloads = re.findall(r'download-artifact@\S+(?: #[^\n]*)?\n\s+with:\n\s+(\w+):', jobs['publish'])
    assert downloads and set(downloads) == {'name'}   # this run's two builds, by name


def test_validation_passes_only_when_every_job_passed_on_the_commit_asked_for():
    jobs = _jobs(WORKFLOWS / 'validate.yml')
    for name in ('test', 'frontend', 'browser'):
        assert 'ref: ${{ inputs.sha }}' in jobs[name]
        assert 'git rev-parse HEAD' in jobs[name]
    assert 'needs: [test, frontend, browser]' in jobs['gate']
    assert 'if: always()' in jobs['gate']
    ci = _jobs(WORKFLOWS / 'ci.yml')
    assert 'uses: ./.github/workflows/validate.yml' in ci['validate']
    assert 'needs: validate' in ci['build-linux']


def test_every_action_is_pinned_to_a_full_commit():
    pins = {}
    for path in WORKFLOWS.glob('*.yml'):
        for use in re.findall(r'uses: (\S+(?: # \S+)?)', path.read_text(encoding='utf-8')):
            if use == './.github/workflows/validate.yml':
                continue
            match = re.fullmatch(r'([\w-]+/[\w-]+)@([0-9a-f]{40}) # (v\d+\.\d+\.\d+)', use)
            assert match, f'{path.name}: {use}'
            pins.setdefault(match.group(1), set()).add(match.group(2, 3))
    assert all(len(versions) == 1 for versions in pins.values()), pins   # one pin per action
