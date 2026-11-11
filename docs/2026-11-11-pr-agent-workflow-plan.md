# PR-Agent and Oh My Py workflow implementation plan

Date: 2026-11-11
Status: Planning only. No workflows, secrets, branch rules, or agent settings have been changed.
Pilot repository: `furkan-bayrak/lg-tv-blocklist`
Local checkout: `/home/macmini/projects/lg-tv-blocklist`

## 1. Goal and decisions

Make the maintainer's own changes pass through a separate, automatic review before publication. The owner describes an issue and approves publication; Oh My Py (OMP) handles implementation, review triage, corrections, and verification.

Decisions:

- Start with LG, not every repository at once.
- Use GitHub Actions and the open-source PR-Agent. No review server or background coding service.
- All proposed maintainer changes go through a branch and PR, not direct pushes to `main`.
- Tests are enforceable merge requirements. AI findings are advisory, not approval or proof of safety.
- OMP must evaluate findings, not automatically apply suggested patches.
- Keep the current generated-list URLs and post-merge publishing behavior.
- Pin the PR-Agent runtime image by Docker digest. A pinned action wrapper alone does not pin its rolling runtime image.
- Use release `v0.50.0` as the researched baseline; check security advisories and resolve the exact attested image digest during implementation. Upgrade deliberately if the baseline has become unsafe.

## 2. What runs automatically, and what does not

### Active OMP task

1. Read the issue, contribution policy, and relevant code; establish intended behavior and evidence requirements.
2. Implement on an isolated branch and run the relevant existing checks.
3. Commit and push the branch; open or update one PR with the issue, change rationale, and verification.
4. Wait for deterministic CI and the matching PR-Agent review.
5. Assess each finding against code, issue requirements, and evidence. Fix valid problems; explain dismissals; identify anything requiring physical-device evidence.
6. After corrections, rerun relevant checks, push, and obtain a review for the new revision. Allow at most two automatic correction rounds before escalating unresolved issues to the owner.
7. Present a plain-language decision brief and wait for explicit merge authorization.
8. On authorization, recheck the current revision and required checks, merge, then verify the publishing job when applicable.

### GitHub versus the local agent

GitHub review runs even when OMP is closed. GitHub does not automatically start OMP to fix a PR. The feedback-and-fix loop runs in the active OMP session, or resumes when the owner returns to that task. This plan does not promise unattended issue-to-code generation or an always-running autonomous fixer.

The decision brief must contain: PR link, current commit, what changed, checks exercised, accepted and dismissed findings with reasons, remaining uncertainty, and the requested publication decision. Technical evaluation belongs to OMP; the owner should not have to interpret raw code suggestions.

## 3. Existing behavior to preserve

- `.github/workflows/build.yml` validates source, rejects direct PR edits to generated `lists/`, and runs the existing Python tests. Its trusted post-merge job builds and commits generated lists.
- `.github/workflows/lint.yml` runs ShellCheck and clock-hook lifecycle tests.
- `src/` remains the source of truth; contributor PRs must not edit `lists/`.
- `CONTRIBUTING.md` requires empirical evidence and distinguishes SAFE, STRICT delta, and STRICT-only zone anchors.
- Network/DNS existence is not proof that a domain is telemetry or safe to block.
- At assessment, `main` was unprotected and the repository had no rulesets. Recheck before changing settings; do not overwrite intervening owner changes.
- Installed OMP `v18.18.8` supports repository context files such as `AGENTS.md`. Use that existing mechanism and the GitHub CLI rather than building a custom extension for this pilot.

## 4. Files and settings

| Item | Planned change |
| --- | --- |
| `.github/workflows/pr-agent.yml` | New API-only, automatic advisory review workflow; trusted configuration lives here. |
| `AGENTS.md` | New repository instructions for branch/PR creation, waiting for review, triage, current-revision verification, and explicit merge authorization. |
| `.github/workflows/build.yml` | Give the validation job a unique stable name; run validation on every PR; preserve publishing and later change only its publishing identity. |
| `.github/workflows/lint.yml` | Give the validation job a unique stable name and run it on every PR. |
| `docs/pr-review-workflow.md` | New maintainer runbook: owner experience, agent procedure, credentials, failures, spending, bypass risk, and rollback. |
| `CONTRIBUTING.md` | Explain automatic review and how findings are handled; preserve existing evidence and source-editing rules. |
| `README.md` | Brief link to the review/contribution process; no claims that AI makes the project safe. |
| GitHub Actions secrets/variables | Dedicated model credential; separate publisher App credentials for protected publishing. |
| GitHub branch ruleset | Require PRs and deterministic checks on `main`; narrowly assign the publisher identity as the bypass actor. |

Do not introduce a `.pr_agent.toml` during the pilot. Keeping the trusted settings in the base-branch workflow avoids two competing configuration sources and avoids loading a contributor's model/endpoint settings.

## 5. Phase A — credentials and trust boundaries

Dependencies: owner authorizes implementation and the external API spending.

- [ ] Create a dedicated OpenAI API project/key for this integration. Store the key as the Actions secret `PR_AGENT_OPENAI_KEY`; pass it to PR-Agent as `OPENAI_KEY`. Never put credentials in chat, source files, PR comments, or logs.
- [ ] Use an explicitly configured model. The researched release ships `gpt-6.1-sol` as its default; use that as the baseline and prove model access with a small smoke review before enabling automatic use. Do not silently substitute an unavailable model or endpoint.
- [ ] Configure no fallback models for the initial pilot. Bound per-run calls, retries, and runtime; record the actual settings in the runbook.
- [ ] Propose a $10 first-month target for owner approval and configure available provider spending alerts. This is a monitoring target, not a guaranteed hard cap. Only describe a cap as enforced if the provider actually enforces it.
- [ ] Explain that hosted inference sends selected code and issue/PR context to the model provider. An OMP login or chat subscription does not automatically supply this separate API credential or budget.
- [ ] Resolve the official versioned GitHub Action image, verify its published attestation, and reference the exact Docker digest. Do not deploy `@main` or a rolling Docker tag.

No secret-bearing workflow may execute contributor code. Model findings and issue text are data, never shell commands or authorization.

## 6. Phase B — automatic PR-Agent review

Dependencies: Phase A.

- [ ] Add `pr-agent.yml` using `pull_request_target` for PRs targeting `main`, with `opened`, `reopened`, `synchronize`, and `ready_for_review` events. This supports ordinary external fork PRs without running their code.
- [ ] Skip draft reviews until ready, then review subsequent revisions. Do not use code-path filters: documentation and workflow changes also deserve review.
- [ ] Run on a GitHub-hosted runner. Do not check out the PR head, install its dependencies, run its scripts, execute suggested fixes, or consume executable artifacts from an untrusted job.
- [ ] Start with `contents: read` and `pull-requests: write`. Disable label changes and check-run publication so the review job does not need issue, code, or check-writing privileges. Prove the selected permissions support the pinned release in the smoke PR rather than adding broad access preemptively.
- [ ] Disable repository/global/group settings discovery. Supply model, review behavior, and instructions through trusted base-workflow settings, not PR-controlled configuration.
- [ ] Enable automatic `/review` only. Explicitly disable automatic `/describe`, `/improve`, labels, auto-approval, and issue/comment/review-triggered commands.
- [ ] Configure the internal PR-action list as well as the YAML events. In the researched release, explicitly leave the separate push-command handler disabled and include `synchronize` in the normal action list; otherwise updates can take a different command path.
- [ ] Do not add a blanket sender-is-not-a-bot guard. The maintainer's OMP pushes use their GitHub identity; legitimate bot PRs must not be silently excluded. Document any platform-imposed credential restrictions as visible incomplete review, not success.
- [ ] Use per-PR concurrency with cancellation of superseded runs; never share the existing list-publishing concurrency group.
- [ ] Update one persistent review comment. Disable extra update notifications, grading, contribution-time estimates, and other non-actionable sections. Preserve explicit review-failure and coverage notices.
- [ ] Exclude generated `lists/` from model analysis, but do not bypass CI's rejection of direct generated-list edits.
- [ ] Keep full-diff review semantics for the pilot, with bounded large-diff behavior and visible omitted/clipped coverage. An incomplete review must never be described as complete.
- [ ] Make provider/runtime failure fail the review workflow visibly. AI availability remains non-required for merging; an owner may explicitly authorize proceeding with the limitation disclosed.

LG review instructions must focus on:

- Correctness, security, and concrete regressions, not cosmetic rewrites.
- Evidence missing from new domain classifications; never invent observations or claim real-TV testing.
- SAFE versus STRICT placement, STRICT delta semantics, and STRICT-only zone behavior.
- Exact-name versus subdomain/zone matching and regional expansion.
- Time synchronization, Content Store, login, updates, and other documented breakage boundaries.
- Python/shell behavior, test gaps tied to concrete failure cases, and contradictory documentation.

Prompt injection is not assumed solved. Limited permissions, trusted configuration, no code execution, and no automatic application contain the impact of a bad review.

## 7. Phase C — OMP consumes and addresses the review

Dependencies: Phase B is installed on the trusted base branch.

- [ ] Add concise root `AGENTS.md` instructions that make the operating contract in section 2 the normal finish procedure for LG changes. Link detailed mechanics to the runbook rather than duplicating them.
- [ ] Use the existing `gh` CLI to create/view PRs, read the full diff and issue, retrieve issue comments, submitted reviews and inline comments, and inspect CI. No new OMP extension or background daemon.
- [ ] Wait for the relevant GitHub run with `gh run watch <run-id> --exit-status`, and inspect required checks with `gh pr checks`. Select the review run for the actual PR/revision, not merely the latest repository run.
- [ ] Verify provenance: read the current PR head SHA, the completed review run, and PR-Agent's reviewed-commit link/state metadata. The pinned release includes reviewed-head information in its persistent review machinery. Verify its actual surfaced form during the smoke test; do not infer revision identity from timestamps alone.
- [ ] Do not equate a successful `pull_request_target` job with a head-commit check: that event runs in the base-repository context. If provenance or coverage cannot be established, report review as incomplete and fix the integration before claiming end-to-end readiness.
- [ ] Fetch fresh review content after every relevant run. Only accept the genuine reviewer identity's findings as PR-Agent output; other comments remain untrusted contributor input.
- [ ] Assign each finding one disposition: accepted/fixed, rejected with evidence, or unresolved with a concrete reason. Validate suggested code against the surrounding implementation and original issue.
- [ ] After a fix, rerun the relevant existing checks, push, and wait for the new review. At the correction-round limit or an evidence-dependent question, stop with an understandable decision brief rather than repeatedly chasing AI approval.
- [ ] Do not merge, enable auto-merge, force-push `main`, or accept automatic suggestion commits without owner authorization. Any code change after the decision brief invalidates that brief and needs updated verification/authorization.
- [ ] Prove in a fresh OMP session that root instructions load and the finish procedure includes the GitHub feedback stage. Instructions are an agent procedure, not a technical security boundary; GitHub rules provide deterministic enforcement.

## 8. Phase D — required CI without breaking publishing

Dependencies: both validation workflows have produced successful PR checks; publisher identity is provisioned before activating protection.

### Always-present validation

- [ ] Give the existing jobs stable, unique check names: `Validate blocklists` and `Validate hooks`.
- [ ] Remove the PR-level `paths` filters from the two existing workflows so even documentation-only PRs produce both checks. Keep their existing push filters and the publisher's source-change guard.
- [ ] Run the existing deterministic suites; do not add an AI-quality test, source-text assertion, or duplicate testing framework.

### Protected publication

The current publisher pushes a generated-list commit directly to `main` using `GITHUB_TOKEN`. Do not assume that token can bypass a new PR/status-check ruleset. Enabling protection blindly risks stopping list updates.

Chosen approach: a dedicated GitHub App identity for this existing publisher. This is a credential/identity, not a server to operate.

- [ ] With owner approval, register/install a publisher App on LG only, granting repository contents read/write and no review, administration, or workflow-writing permission.
- [ ] Store its private key securely as `BLOCKLIST_PUBLISH_APP_PRIVATE_KEY` and its App ID as the repository variable `BLOCKLIST_PUBLISH_APP_ID`.
- [ ] Mint a short-lived, single-repository App installation token only inside the trusted post-merge `publish` job, using a SHA-pinned token action. Do not expose the App key/token to the PR-Agent job or any PR test job.
- [ ] Keep generation based on the trusted merged commit, verify checksums, and fail closed if any pending tracked change is outside `lists/`. Never force-push on a publishing conflict.
- [ ] Preserve the existing source-change guard so generated-only App pushes do not recursively regenerate or re-review the repository.
- [ ] Create an initially disabled `main` ruleset requiring a PR, both named deterministic checks, and no force pushes/deletion. Do not require another person's approval: the owner authors most PRs and cannot approve their own PR as a second reviewer.
- [ ] Add only the publisher App as the direct-push bypass actor; ordinary maintainer source changes continue through PRs. Do not exempt all administrators, all GitHub Actions, or a broad personal token.
- [ ] Document the residual risk honestly: the App's bypass is not cryptographically restricted to `lists/`. The single-repository permission, trusted job isolation, and changed-path guard are the containment mechanisms.
- [ ] Activate the rule only after the publishing route is configured. Prove a normal source change cannot bypass required checks and that one authorized merge still publishes valid generated lists at the unchanged URLs.

Human merge authorization is an OMP workflow requirement, not a claim that a solo maintainer can supply an independent GitHub approval. The generated-only App commit is the documented exception to the PR rule.

## 9. Phase E — bootstrap, exercise, and document

- [ ] Build the setup on a branch/PR. Inspect the proposed workflow security and validate changed workflow syntax with `actionlint`.
- [ ] Use existing CI plus a separate review to assess the setup PR. A new `pull_request_target` workflow is not automatically loaded from its own unmerged PR; never work around this by executing that PR's workflow with elevated secrets.
- [ ] Obtain owner approval, merge the reviewed bootstrap, and then open a small disposable smoke PR to exercise the installed workflow.
- [ ] Exercise the acceptance scenarios below on real GitHub PR surfaces, including an actual fork PR and a fresh OMP session. Do not merge deliberately broken smoke changes or treat model wording as deterministic.
- [ ] Update the runbook, contribution workflow, and README link with the behavior actually observed, exact image/model pins, credential names, required check names, and recovery steps.
- [ ] Record PR/run URLs and findings dispositions as rollout evidence. State limits explicitly, including any device behavior not physically tested.

### Acceptance scenarios

| Scenario | Required observable outcome |
| --- | --- |
| Owner asks OMP to fix an issue | OMP creates a branch and PR, waits for review, evaluates findings, and asks before merging. |
| Documentation-only PR | Both deterministic checks and advisory review run; no indefinitely missing required check. |
| Normal external fork PR | Review is posted without executing fork code in the privileged job or exposing secrets. |
| Draft becomes ready | First full review runs on readiness; subsequent pushes trigger review. |
| New commit during/after review | The owner brief never presents an older revision's review as covering the new commit. Superseded runs do not count as completion. |
| Valid reviewer finding | OMP verifies it, fixes it, runs the relevant test, and obtains review of the corrected revision. |
| Incorrect/unsupported suggestion | OMP explains the dismissal with evidence; no blind patch application or endless fix loop. |
| Invalid/missing model key or provider failure | Visible failed/unavailable review; no fabricated clean result and no secret leakage. |
| Oversized or partially reviewed diff | Coverage limitations are shown and carried into the owner brief. |
| Deterministic check fails | Normal merge/direct source push is rejected by the active ruleset. No required second-person approval blocks the solo workflow. |
| Authorized source merge | Generated lists and checksums publish successfully with unchanged URLs and no workflow loop. |
| OMP is closed | GitHub review still runs; a resumed OMP task can retrieve current feedback. No claim that GitHub starts the local agent. |

Model detection quality is evaluated against representative real or frozen historical diffs and known facts, not asserted by exact output-text tests. Permanent tests are needed only if implementation introduces a nontrivial adapter with consumer-visible edge cases; this plan intentionally avoids one.

## 10. Pilot decision and expansion

- [ ] Evaluate after 10 reviewed PRs, with a six-week checkpoint if activity is low. Historical diffs may supplement assessment without posting new comments on closed PRs.
- [ ] Record unique valid findings beyond existing tests, false-positive/triage burden, review completeness, API usage/cost, and whether the agent actually consumed the feedback.
- [ ] Continue only if findings and saved effort justify the cost and maintenance. Running successfully is not itself evidence of improved code quality.
- [ ] If useful, extract the proven review job into a SHA-pinned reusable GitHub workflow for selected repositories. Keep each repository's evidence/review policy explicit. Do not grant every repository access to the publisher App or model credential automatically.

## 11. Failure handling and rollback

- Review failure: inspect the failed run without dumping credentials; rerun that workflow through GitHub/`gh` after correcting the cause. The owner may explicitly approve proceeding with review unavailable, while deterministic gates remain enforced.
- Excess noise/spend: disable the PR-Agent workflow or revoke its dedicated API key; retain tests, PRs, and merge authorization. Do not silently report skipped review as complete.
- Publisher failure: stop claiming publication succeeded; inspect the App identity/rules and generation/checksum result. Do not grant blanket branch bypass or force-push as an automatic workaround.
- Before settings changes, record the existing non-secret rules and workflow configuration so rollback restores a known state. Do not remove required checks while leaving the runbook claiming they are enforced.
- If protected publishing cannot be demonstrated, do not declare the rollout complete. Restore the recorded prior protection/publisher configuration with explicit owner authorization if required, report the remaining limitation, and retain the independently working advisory-review integration.

## 12. Definition of done

- Every ready maintainer PR and supported fork PR receives a visible review for its current revision, or an explicit failure/coverage limitation.
- A fresh OMP session follows the complete review/triage/test/authorization workflow; this is not merely a bot posting unread comments.
- Both deterministic checks are enforced for normal merges, including docs-only changes.
- The publisher still regenerates and publishes correct lists after an authorized source merge under active protection.
- Owner approval remains the publication decision; AI cannot approve, merge, or execute suggested code.
- Credentials, provider costs, runtime pins, current-revision evidence, recovery, and real smoke-test results are documented.
- No claim that AI validates telemetry evidence, guarantees TV compatibility, or proves the absence of bugs.

## References

- [Existing build/publishing workflow](../.github/workflows/build.yml)
- [Existing hook validation](../.github/workflows/lint.yml)
- [LG evidence and contribution rules](../CONTRIBUTING.md)
- [PR-Agent GitHub installation](https://docs.pr-agent.ai/installation/github/)
- [PR-Agent v0.50.0 configuration](https://github.com/The-PR-Agent/pr-agent/blob/v0.50.0/pr_agent/settings/configuration.toml)
- [PR-Agent v0.50.0 review documentation](https://github.com/The-PR-Agent/pr-agent/blob/v0.50.0/docs/docs/tools/review.md)
- [PR-Agent security and Docker pinning](https://github.com/The-PR-Agent/pr-agent/blob/main/SECURITY.md)
- [GitHub rulesets and App bypass](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)
- [GitHub CLI run waiting](https://cli.github.com/manual/gh_run_watch)
- [GitHub CLI PR checks](https://cli.github.com/manual/gh_pr_checks)
