# Checks and pull requests

Changes to notedrop go through a pull request. Keep changes focused, include
regression tests for behavior changes, and run the relevant checks below.
Using the CLI does not require GitHub or a Codex account.

## Local checks

Run from the repository root with Python 3.11+, Git, Ruff 0.12.7, actionlint
1.7.12, ShellCheck, and jq available:

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
python3 .github/scripts/check_workflow_pinning.py
ruff check notedrop tests .github/scripts
ruff format --check notedrop tests .github/scripts
actionlint
```

Product tests use temporary mailboxes and fictional data. Review-gate tests
use synthetic GitHub responses and jq; they do not contact GitHub. Never use
personal mailboxes or credentials as test fixtures.

Ruff checks Python errors, import ordering, common bug patterns, and formatting.
It does not perform static type checking. Actionlint validates workflows and
uses ShellCheck for embedded shell. The action-reference checker enforces
full commit SHAs for the external actions used in these workflows.

## Required checks

- `ci` combines Python 3.11 and 3.14 tests on macOS and Linux with lint,
  formatting, review-gate regression tests, and workflow validation. Every
  component job and matrix entry must succeed.
- `review-gate` requires a Codex review of the current PR head commit,
  requested by the repository owner. Unresolved P0/P1 findings fail this
  check. A reaction alone does not count as a review.

The main branch also requires all review conversations to be resolved,
including advisory findings, and the PR branch to be up to date. These
requirements apply to administrators too. Address review feedback before
merging; do not bypass failed checks.

Contributors do not need to configure Codex. The repository owner requests
review by posting a standalone comment with the full current 40-character
head SHA:

```text
@codex review FULL_CURRENT_HEAD_SHA
```

A short SHA, another user's request, or a review of a previous head does not
satisfy the gate. After pushing changes, ask the owner for a fresh review.
Missing, stale, or incomplete review evidence cannot pass the gate; it polls
for up to 30 minutes before timing out.

## Maintaining the workflows

External actions use full commit SHAs. Dependabot proposes action updates;
Ruff and actionlint downloads use pinned versions and SHA-256 checksums.
Update each tool's version and checksum together, and verify the release.

The gate executes its script from the PR's base commit, so a proposed script
change cannot replace the established evaluator for that PR. Workflow changes
still require careful maintainer review. The gate has read-only permissions;
its retrigger workflow can rerun Actions jobs and never checks out PR code.

Review events refresh the existing gate job rather than creating duplicate
required checks. Resolving a thread alone does not trigger a refresh: rerun
the existing gate from Actions afterward. For a delayed fork review, rerun
that job or have the owner request a fresh review. A new request requires
review evidence newer than the request.

`review-gate-retrigger` is not a required check. Branch protection lives in
GitHub settings, separately from these workflow files. Fork maintainers must
choose their own required checks and configure Codex if retaining this gate.
The current authorization policy uses the repository owner's login; an
organization-owned fork needs an explicit trusted-maintainer policy.
