# Agent workflow

How agents build this lab under Firstmate. Decisions: [ADR-0016](decisions/ADR-0016-firstmate-agent-runtime.md) (runtime and roles), [ADR-0006](decisions/ADR-0006-git-github-agent-flow.md) (git flow, amended by ADR-0016). Permissions: [ACCESS.md](ACCESS.md).

## Roles

| Role | Does |
|---|---|
| User | Approves scope, decides open calls, approves Snowflake, cloud resource, credential and credit use, merges on GitHub |
| First mate | Plans, writes worker briefs, keeps a mirror of `TASKS.md`, relays results to the user. Writes nothing in the repository directly |
| Ship crewmate | Implements on one feature branch, updates `memory/` when told, pushes that branch, opens the PR |
| Architecture Scout | Read-only review of the PR against `memory/architecture.md` and the ADRs |
| Governance Scout | Read-only review of the PR for data, access, credentials and attribution rules |

## Per-feature flow

1. The first mate proposes the scope to the user.
2. The user approves the scope.
3. A Ship crewmate works on `feature/<id>-<topic>` from `main`, records the task in `memory/TASKS.md`, implements, runs the tests and commits.
4. The Ship crewmate pushes its branch and opens a ready PR.
5. An architecture Scout and a governance Scout review the PR, in parallel.
6. Serious findings go back to a Ship crewmate on the same branch; the Scouts recheck.
7. The first mate brings the PR and the review results to the user.
8. The user merges on GitHub.

## Rules

- `memory/TASKS.md` is the official backlog; IDs continue the existing numbering.
- Everything in the repository is in English.
- No tool attribution in commits, PRs or files; both Scouts check it.
- One writing worker per set of files at a time. Scouts can run together.
- No agent merges, pushes to or commits on `main`, or reads, prints or stores credentials.
- No force-push to a PR branch after review has started, unless the Scouts review again.
- No agent deploys to production; production changes happen only through CI/CD after the user merges.
- Snowflake use, creating any cloud resource and spending credits need the user's explicit approval.
