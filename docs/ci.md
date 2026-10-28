# Checks and pull requests

Changes to notedrop go through a pull request. Keep changes focused, include
regression tests for behavior changes, and run the relevant checks below.
Using the CLI does not require GitHub or a Codex account.

## Local checks

Run from the repository root with Python 3.11+, Git, Ruff 0.12.7, actionlint
1.7.12, and ShellCheck available:

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
python3 .github/scripts/check_workflow_pinning.py
ruff check notedrop tests .github/scripts
ruff format --check notedrop tests .github/scripts
actionlint
```

Product tests use temporary mailboxes and fictional data. Review-gate tests
evaluate recorded, redacted review evidence and the workflow files; they do
not contact GitHub. Never use personal mailboxes or credentials as test
fixtures.

Ruff checks Python errors, import ordering, common bug patterns, and formatting.
It does not perform static type checking. Actionlint validates workflows and
uses ShellCheck for embedded shell. The action-reference checker enforces
full commit SHAs for the external actions used in these workflows.

## Required checks

- `ci` combines Python 3.11 and 3.14 tests on macOS and Linux with lint,
  formatting, review-gate regression tests, and workflow validation. Every
  component job and matrix entry must succeed.
- `review-gate` is a short, one-shot check of the current PR head. It never
  waits for a model. It passes only when the repository owner's
  `@codex review` request names the exact current head commit, Codex has
  posted a typed code-review completion and receipt for that commit after the
  request, and every review thread is resolved. Security review is advisory:
  it is not required, but findings it reports on the current head block.
  Reactions and clean-sounding prose do not count as review evidence.

The gate also rejects AI attribution lines (such as `Co-Authored-By` or
"Generated with" naming an AI tool) in commits, the PR title, and the PR
description, and commits authored or committed by an app or bot account
(Dependabot excepted).

The main branch also requires all review conversations to be resolved,
including advisory findings, and the PR branch to be up to date. These
requirements apply to administrators too. Address review feedback before
merging; do not bypass failed checks.

Contributors do not need to configure Codex. The repository owner requests
review by posting a standalone comment that names the full current
40-character head SHA:

```text
@codex review FULL_CURRENT_HEAD_SHA
```

A short SHA, another user's request, an edited request, or a review of a
previous head does not satisfy the gate. Marking a draft ready, reopening,
force-pushing, or changing the base starts a new review generation, so earlier
requests and reviews no longer count. After pushing changes, ask the owner for
a fresh review.

## Maintaining the workflows

External actions use full commit SHAs. Dependabot proposes action updates;
Ruff and actionlint downloads use pinned versions and SHA-256 checksums.
Update each tool's version and checksum together, and verify the release.

The gate checks out only its two evaluator files
(`.github/scripts/review_qualification.py` and `review_contract.py`) from the
PR's base commit, without persisted credentials, and runs them with
`python3 -I` and a read-only token. It never checks out PR code, so a proposed
evaluator change cannot replace the established evaluator for that PR.
Workflow changes still require careful maintainer review.

`review-gate-retrigger` re-runs the existing gate job in place when Codex
posts a review receipt, records code-review completion in its summary, or
submits or dismisses a review, rather than creating a duplicate required
check. Only the Codex bot's events start it, and it never checks out PR code
or interpolates comment bodies into shell. Resolving a thread, marking ready,
reopening, and fork-PR reviews do not trigger it; the maintainer's tooling
re-runs the existing gate job afterward.

`review-gate-retrigger` is not a required check. Branch protection lives in
GitHub settings, separately from these workflow files. Fork maintainers must
choose their own required checks and configure Codex if retaining this gate.
The current authorization policy uses the repository owner's login; an
organization-owned fork needs an explicit trusted-maintainer policy.
