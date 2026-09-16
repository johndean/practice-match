"""The migration ledger's own check must be able to SEE a claim on an unmerged branch.

`docs/MIGRATIONS.md` exists because two branches took `092` on 2026-09-15. It shipped with a
command that could not have found that collision: `git ls-tree` takes exactly ONE tree-ish, so
every ref after the first was swallowed as a pathspec and only `main`'s files were reported.
Nothing exercised it, so nobody knew.

These cases run the command THE DOCUMENT ACTUALLY PRINTS against a repository built to contain
the failure the document names, so the two cannot drift and the broken form cannot come back.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

LEDGER = Path(__file__).resolve().parents[1] / "docs" / "MIGRATIONS.md"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")


def documented_command() -> str:
    """The first fenced shell block in the ledger — the command it tells a reader to run."""
    blocks = re.findall(r"```\n(.*?)```", LEDGER.read_text(), re.DOTALL)
    assert blocks, f"{LEDGER.name} prints no command at all"
    return blocks[0]


def _git(repo: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t", "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(repo), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env).stdout


@pytest.fixture()
def repo_with_an_unmerged_claim(tmp_path: Path) -> Path:
    """`main` holds 090. An UNMERGED branch holds 092. That is the shape that collides.

    The branch is named to sort AFTER `main`, deliberately: `git for-each-ref` returns refnames in
    lexical order, so a branch sorting FIRST would be the one tree-ish the broken single-command
    form happens to read, and the broken form would pass this case by luck. `zz-unmerged` puts the
    claim where only a per-ref walk can reach it.
    """
    repo = tmp_path / "r"
    (repo / "migrations").mkdir(parents=True)
    _git(repo.parent, "init", "-q", "-b", "main", str(repo))
    (repo / "migrations" / "090_on_main.sql").write_text("-- 090\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "090")
    _git(repo, "checkout", "-q", "-b", "zz-unmerged")
    (repo / "migrations" / "092_only_on_a_branch.sql").write_text("-- 092\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "092")
    _git(repo, "checkout", "-q", "main")
    return repo


def run_documented_command(repo: Path) -> list[str]:
    out = subprocess.run(["bash", "-c", documented_command()], check=False, cwd=repo, capture_output=True,
                         text=True, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(repo),
                                         "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"})
    return [line for line in out.stdout.splitlines() if line.strip()]


def test_the_documented_command_finds_a_claim_that_exists_only_on_an_unmerged_branch(
    repo_with_an_unmerged_claim: Path,
) -> None:
    """The one case the ledger exists for. The published single-command form FAILS this."""
    found = run_documented_command(repo_with_an_unmerged_claim)
    assert any("092_only_on_a_branch.sql" in line for line in found), (
        "the command `docs/MIGRATIONS.md` prints did not see a migration claimed on an unmerged "
        f"branch — which is the only kind of claim that collides. It returned: {found}"
    )


def test_the_documented_command_still_sees_main_s_own_files(
    repo_with_an_unmerged_claim: Path,
) -> None:
    found = run_documented_command(repo_with_an_unmerged_claim)
    assert any("090_on_main.sql" in line for line in found), found


def test_the_ledger_does_not_carry_the_broken_single_tree_form() -> None:
    """`git ls-tree <many refs>` reads the first as the tree and the rest as paths, silently."""
    command = documented_command()
    assert not re.search(r"git ls-tree[^\n|]*\$\(git for-each-ref", command), (
        "docs/MIGRATIONS.md has been 'simplified' back to passing every ref to one `git ls-tree`. "
        "That form reports only the first ref's files and answers nothing about unmerged branches."
    )


def test_every_row_in_the_ledger_names_a_number_a_file_and_a_branch() -> None:
    rows = re.findall(r"^\| (\d{3}) \| (.+?) \| (.+?) \|", LEDGER.read_text(), re.MULTILINE)
    assert rows, "the ledger has no rows"
    numbers = [int(n) for n, _, _ in rows]
    assert numbers == sorted(numbers), f"rows are out of order: {numbers}"
    assert len(numbers) == len(set(numbers)), f"a number is claimed twice in the ledger: {numbers}"
    for number, filename, branch in rows:
        assert filename.strip("`*_ "), f"row {number} names no file"
        assert branch.strip("`*_ "), f"row {number} names no branch"
        assert number in filename, f"row {number}'s file name does not carry its own number: {filename}"
