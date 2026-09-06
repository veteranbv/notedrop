# CI and Codex review

The repository includes two independent merge checks:

- `ci`: Python 3.11 and 3.14 tests on macOS and Linux, review-gate regression
  tests, Ruff lint and formatting, action pinning, and workflow syntax checks. All component jobs must
  succeed, including every matrix entry.
- `review-gate`: an owner-authorized Codex review of the exact PR head commit.
  Unresolved P0/P1 findings block it. P2/P3 findings remain visible but do
  not block merging. An emoji reaction alone does not count as a review.

The gate and its regression tests come from the owner's `homelab.codes`
workflow; the action-reference checker comes from `henrysowell.com`.
The gate runs the script from the PR's base commit, so changes to the script
in that PR do not replace the established evaluator. Maintainers must still
review workflow changes themselves: workflow files and repository settings
are part of the trust boundary, not an unchangeable security service.

This automation is separate from the product. Using notedrop requires no
GitHub account, review integration, or network connection. CI uses GitHub's
token, `gh`, and hosted runner tools. External actions use full commit SHAs;
Ruff and actionlint use versions and SHA-256-verified archives. Dependabot
proposes action updates. Review tool versions and checksums together.
Ruff checks Python errors, imports, and common bug patterns (`E4`, `E7`,
`E9`, `F`, `I`, `B`), plus formatting. These are not static type checks.

## Activate on GitHub

These files do not create a remote repository or enable branch protection.
Bootstrap them onto `main` before opening the first gated PR, since the gate
script and event-driven retrigger workflow must exist on the base branch.

1. Enable GitHub Actions and connect Codex code review to the repository.
2. Open a PR and let the workflows register their check names.
3. In the rule protecting `main`, require PRs and successful `ci` and
   `review-gate` checks. Require branches to be current before merging.
   Apply the rule to administrators too if direct bypass is not wanted.
4. Protect workflow changes through maintainer review. Do not mark
   `review-gate-retrigger` as a required check; it only refreshes the gate.

The authorization policy currently expects a personally owned repository:
the GitHub repository owner must post the review request. An organization
needs an explicit trusted-maintainer policy before enabling this gate.

## Request and refresh a review

As the repository owner, post a standalone PR comment replacing the
placeholder with the full current 40-character head SHA:

```text
@codex review FULL_CURRENT_HEAD_SHA
```

A short SHA, another user's request, or a review of a previous head does
not satisfy the gate. Request again after pushing new commits. Automation
does not post this comment for you: a workflow bot cannot supply the owner's
authorization. The gate polls for up to 30 minutes and fails closed if review
evidence is missing, stale, incomplete, or unavailable.

Codex review events and owner comment changes refresh the existing gate job,
avoiding duplicate required checks. After resolving a review thread, rerun
the existing gate from Actions; thread resolution alone does not trigger it.
For a delayed fork review, rerun the gate manually or post a new exact-head
owner request. The latter requires a fresh review after the new request.

The retrigger has permission to rerun Actions jobs and never checks out PR
code. The gate itself has read-only permissions. A missing Codex integration
will leave this required check failing; local unit tests cannot verify the
live integration.

## Local checks

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
python3 .github/scripts/check_workflow_pinning.py
actionlint
ruff check notedrop tests .github/scripts
ruff format --check notedrop tests .github/scripts
```

The gate tests use synthetic GitHub responses and require `jq` for the
retrigger selection regression. They never contact GitHub. Product tests
use temporary mailboxes and never read personal sessions. The pinning
checker is a lightweight check for the workflow syntax used here, not a
general YAML parser; actionlint supplies the full workflow syntax check.
