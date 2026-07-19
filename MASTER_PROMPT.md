
# MASTER OBJECTIVE: BUILD A COMPLETE, DATA-READY DEUTSCHE BANK LASR RESEARCH AND IMPLEMENTATION FRAMEWORK

You are the lead orchestrator for a multi-agent quantitative research and engineering project.

Your responsibility is not merely to summarize research papers, produce pseudocode, or create an incomplete repository skeleton. You must coordinate specialized research, architecture, implementation, verification, and red-team agents to build a rigorous, executable, production-quality framework for reconstructing, validating, and modernizing Deutsche Bank’s machine-learning-based stock-selection models.

The completed system must support:

1. Historical data ingestion.
2. Point-in-time data processing.
3. Feature construction and feature injection.
4. Target and label construction.
5. Representation preparation or pre-training where technically meaningful.
6. Base-model training.
7. Rolling retraining and adaptation.
8. Validation and walk-forward evaluation.
9. Post-training calibration.
10. Fine-tuning or model updating where technically meaningful.
11. Signal generation.
12. Portfolio construction.
13. Transaction-cost-aware backtesting.
14. Paper trading and eventual live inference.
15. Complete reproducibility, testing, documentation, auditability, and source-control history.

Actual historical data and production API credentials are not currently available.

You will receive:

- Four Deutsche Bank research papers describing successive generations of the model.
- Two Excel workbooks describing expected data templates, available fields, fundamental metrics, technical metrics, consensus fields, and related provider data structures.

Build the entire framework so that the principal missing external dependency at completion is the actual historical data feed or API credentials.

The system must work end-to-end using schema-compliant synthetic data and mock provider adapters. Once real data becomes available, connecting it should require implementing or configuring a provider adapter rather than rewriting the research, modelling, validation, portfolio, or reporting stack.

---

# 1. SOURCE MATERIALS

The project contains the following papers:

1. `20120605_Rise of the Machines.pdf`
   - Foundational N-LASR model.
   - Primary source for the original AdaBoost-inspired learner, target formulation, temporal ensemble, factor aggregation, technical-factor extension, and early portfolio implementation.

2. `20130123_Rise of the Machines II.pdf`
   - Second-generation N-LASR2 model.
   - Primary source for signal-level neutralization, sector/country/size/beta controls, adverse-environment or hedge learning, and expanded institutional portfolio considerations.

3. `20140101_Rise of the Machines III.pdf`
   - Third-generation LASR model.
   - Verify the actual publication date from the report rather than trusting the filename.
   - Primary source for Linearized AdaBoost Style Rotation, LASR-HC, LASR-HF, turnover reduction, capacity, portfolio construction, and comparison with alternative machine-learning methods.

4. `20200423_Return of the Machines.pdf`
   - Later reassessment and reimplementation of N-LASR.
   - Primary source for the later feature universe, weekly operation, four-week targets, monotonic constraints, explicit validation periods, execution-delay tests, implementation-cost tests, and modern challenger algorithms.

The project also contains two Excel workbooks.

Discover their actual filenames automatically. Do not assume their structure before opening them.

Treat the workbooks as evidence about:

- Available provider fields.
- Data templates.
- Fundamental metrics.
- Technical metrics.
- Analyst-estimate and consensus metrics.
- Market-data fields.
- Identifier columns.
- Time dimensions.
- Frequency and reporting structure.
- Units and currencies.
- Historical versus current values.
- Potentially derivable fields.
- Missing fields required by the Deutsche Bank methodology.

Do not fabricate fields, APIs, endpoints, update frequencies, history lengths, availability timestamps, or provider capabilities not established by the workbooks or another documented source.

---

# 2. GITHUB REPOSITORY AS THE DURABLE SOURCE OF TRUTH

The complete project must be maintained in a private GitHub repository.

The GitHub repository is not merely a final publishing destination. It is the durable project memory, coordination mechanism, engineering record, and recovery mechanism for the entire multi-agent process.

Use Git to preserve:

- The master objective.
- Source-material manifests.
- Research evidence.
- Architectural decisions.
- Assumptions.
- Goal definitions.
- Agent assignments.
- Implementation history.
- Verification reports.
- Red-team findings.
- Test results.
- Milestones.
- Unresolved issues.

A long conversational context must never be the only place where important information exists.

## 2.1 Repository creation

At the beginning:

1. Inspect whether the current project directory is already a Git repository.
2. Inspect whether it already has an intentional GitHub remote.
3. Do not overwrite or recreate an existing legitimate repository.
4. If no repository exists:
   - Initialize Git with `main` as the default branch.
   - Create an initial `.gitignore`.
   - Create the initial project-control files.
   - Make a bootstrap commit.
5. Check whether the GitHub CLI is installed and authenticated:
   - Run `gh --version`.
   - Run `gh auth status`.
6. If GitHub CLI authentication is available, create a new private GitHub repository.
7. Use the current directory name as the repository name when appropriate; otherwise use:
   - `db-lasr-reconstruction`
8. Configure the GitHub remote using SSH.
9. Push the bootstrap commit to `origin/main`.

An appropriate creation sequence may resemble:

```bash
git init -b main
git add .
git commit -m "chore(repo): bootstrap LASR reconstruction project"
gh repo create db-lasr-reconstruction \
  --private \
  --source=. \
  --remote=origin \
  --push
```

Adapt commands to the actual environment.

SSH is already configured for the user, but do not assume that GitHub CLI authentication is also configured.

If `gh` is unavailable or unauthenticated:

* Initialize and maintain the local Git repository immediately.
* Continue productive local work.
* Record remote-repository creation as a clearly identified infrastructure blocker.
* Ask for GitHub CLI authorization or an empty private repository URL only when remote creation is actually blocked.
* Do not abandon the engineering work merely because the remote cannot yet be created.

## 2.2 Repository privacy and protected materials

The repository must be private by default.

Do not create a public repository without explicit user approval.

Do not commit or push:

* Licensed research PDFs.
* Proprietary Excel workbooks.
* Confidential provider templates.
* API credentials.
* SSH keys.
* Access tokens.
* Raw production data.
* Proprietary data extracts.
* Secret configuration.
* Large generated datasets.
* Model artifacts containing confidential data.

By default, add source inputs to `.gitignore`, for example:

```gitignore
inputs/papers/*
inputs/data_templates/*
data/raw/*
data/interim/*
data/processed/*
artifacts/*
models/*
reports/generated/*
.env
.env.*
!.env.example
```

Preserve reproducibility by committing:

* Input filenames.
* File hashes.
* File sizes.
* Page counts.
* Workbook sheet inventories.
* Schema summaries.
* Field mappings.
* Parsing status.
* Processing code.
* Synthetic fixtures.
* Non-confidential examples.

Create placeholder files such as:

```text
inputs/papers/README.md
inputs/data_templates/README.md
```

These should explain where the local source files must be placed.

Do not use Git LFS for proprietary inputs unless explicitly authorized.

---

# 3. GIT BRANCH AND WORKTREE OPERATING MODEL

Use Git branches and Git worktrees to isolate agents and prevent overlapping edits.

The orchestrator owns integration.

Subagents must not all edit the same working directory.

## 3.1 Main branch

`main` represents the latest integrated and independently verified project state.

After the initial bootstrap:

* Do not perform substantial implementation directly on `main`.
* Do not leave experimental or partially working changes on `main`.
* Do not merge failed or unverified goals into `main`.
* The orchestrator is the only agent authorized to integrate feature branches into `main`.
* Every merged goal must have an associated verification report.
* Blocking red-team findings must be resolved before merge.

Small control-plane updates may be made by the orchestrator on `main`, but they must still be committed and pushed.

## 3.2 Branch naming

Every implementation or research goal must have its own branch.

Use a predictable pattern:

```text
agent/<agent-role>/<goal-id>-<short-description>
```

Examples:

```text
agent/paper-researcher/G003-paper-evidence
agent/data-researcher/G004-workbook-schema
agent/architect/G007-canonical-data-design
agent/implementer/G017-nlasr-weak-learner
agent/verifier/G017-nlasr-verification
agent/red-team/G030-leakage-audit
```

Use lowercase Git-safe names where required.

Every branch must map to exactly one primary goal.

Do not create generic branches such as:

```text
work
changes
updates
agent-task
misc
```

## 3.3 Worktrees

Create a separate Git worktree for each concurrently active agent goal.

Use a structure such as:

```text
.worktrees/
├── G003-paper-researcher/
├── G004-data-researcher/
├── G007-architect/
└── G017-implementer/
```

A typical sequence is:

```bash
git fetch origin
git branch agent/paper-researcher/G003-paper-evidence main
git worktree add \
  .worktrees/G003-paper-researcher \
  agent/paper-researcher/G003-paper-evidence
```

Every subagent must:

* Work only in its assigned worktree.
* Work only on its assigned branch.
* Respect the assigned file scope.
* Commit its own meaningful changes.
* Push its branch after each meaningful commit.
* Leave the worktree clean before handoff.
* Record its latest commit SHA in the assignment registry.

Do not allow two active agents to use the same branch or worktree.

## 3.4 Agent ownership and overlap prevention

Create:

```text
coordination/agent_assignments.yaml
```

The orchestrator is the sole normal writer to this file.

Each active assignment must contain:

```yaml
goal_id:
agent_role:
objective:
github_issue:
branch:
worktree:
status:
dependencies:
owned_paths:
read_only_paths:
shared_interfaces:
started_at:
last_updated_at:
latest_commit:
verification_required:
red_team_required:
notes:
```

Before assigning a goal, the orchestrator must define:

* The goal.
* Acceptance criteria.
* Dependencies.
* Owned files and directories.
* Read-only dependencies.
* Shared interfaces.
* Potential conflicts.
* Integration order.

No two active goals may have overlapping write ownership unless the orchestrator explicitly documents:

* Why the overlap is necessary.
* Which agent has priority.
* How edits will be sequenced.
* How conflicts will be resolved.

If two goals require changes to the same module:

1. Create and verify the shared interface first; or
2. Sequence the goals rather than executing them concurrently; or
3. Assign one integration owner for the shared module.

Do not rely on agents informally noticing conflicts.

## 3.5 Shared files

The following should normally be modified only by the orchestrator or by a dedicated integration goal:

* `MASTER_PROMPT.md`
* `goals.md`
* `progress.md`
* `coordination/agent_assignments.yaml`
* `pyproject.toml`
* `.github/workflows/*`
* Root `README.md`
* Central configuration registries
* Shared public interfaces used by several modules

Subagents may propose changes to shared files in their reports. The orchestrator should integrate those changes centrally.

## 3.6 Worktree cleanup

After a branch has been verified and merged:

1. Push the final branch state.
2. Merge through a pull request.
3. Update `main`.
4. Remove the completed local worktree.
5. Delete the merged remote branch where appropriate.
6. Prune stale worktree references.

Example:

```bash
git worktree remove .worktrees/G017-implementer
git worktree prune
```

Do not delete an unmerged worktree containing uncommitted work.

---

# 4. GITHUB ISSUES, PULL REQUESTS, AND PROJECT COORDINATION

Use GitHub Issues as durable goal records.

Use pull requests as review and integration records.

## 4.1 GitHub Issues

Create one issue for each major goal.

Every issue should contain:

* Goal ID.
* Objective.
* Motivation.
* Inputs.
* Dependencies.
* Owned file scope.
* Acceptance criteria.
* Required tests.
* Required verifier.
* Required red-team review.
* Assumptions.
* Evidence sources.
* Branch name.
* Worktree name.
* Current status.

Create useful labels, for example:

```text
type:research
type:architecture
type:implementation
type:verification
type:red-team
type:documentation
status:blocked
status:ready
status:in-progress
status:verification
status:failed
status:verified
agent:orchestrator
agent:paper-researcher
agent:data-researcher
agent:architect
agent:implementer
agent:verifier
agent:red-team
priority:critical
priority:high
priority:normal
```

GitHub issues do not replace `goals.md`; the two must remain synchronized.

`goals.md` is the repository-level dependency map.

GitHub Issues are the durable execution and discussion records.

## 4.2 Pull requests

Every goal that changes repository content should be integrated through a pull request.

The pull request must reference its goal and issue.

The pull request description should contain:

* Goal ID.
* Summary.
* Evidence used.
* Files changed.
* Assumptions introduced.
* Commands executed.
* Tests executed.
* Test results.
* Known limitations.
* Verification status.
* Red-team status.
* Follow-up issues.

Do not merge a pull request merely because CI passes.

Merge only when:

* Acceptance criteria pass.
* Independent verification passes.
* Required red-team review passes.
* Documentation is updated.
* The branch is synchronized sufficiently with `main`.
* No unresolved blocking finding remains.

Prefer a normal merge commit rather than a squash merge when preserving the branch’s meaningful engineering history is valuable.

A suitable command may be:

```bash
gh pr merge <PR_NUMBER> --merge --delete-branch
```

Do not force-push branches after they have entered verification unless necessary and explicitly documented.

## 4.3 Pull-request review separation

The implementer must not be the sole approver of its own pull request.

The verifier must review from fresh context.

The red-team agent must review quantitatively sensitive goals, including:

* Point-in-time data.
* Targets and labels.
* Neutralization.
* Model fitting.
* Walk-forward validation.
* Portfolio accounting.
* Costs.
* Borrow.
* Performance reports.

Verification reports must be stored under:

```text
docs/verification/<goal-id>.md
```

Red-team reports must be stored under:

```text
docs/red_team/<goal-id>.md
```

These reports must be committed.

---

# 5. COMMIT AND PUSH DISCIPLINE

Commit continuously so that no important work depends on an uncommitted local state.

Do not make one enormous final commit.

Do not commit every trivial keystroke.

Commit after each meaningful, internally coherent unit of work.

Examples include:

* Repository bootstrap.
* Input manifest.
* Paper evidence extraction for one version.
* Canonical schema implementation.
* Provider interface implementation.
* Synthetic-data generator.
* One historical weak learner.
* One test suite.
* One documentation milestone.
* One verifier remediation cycle.

Use commit messages containing the goal ID and a clear conventional prefix.

Examples:

```text
docs(research): extract N-LASR 2012 algorithm evidence [G003]
feat(data): add bitemporal fundamental schema [G008]
feat(model): implement hard-bin N-LASR weak learner [G017]
test(model): add formula-level boosting fixtures [G017]
fix(validation): purge overlapping forward labels [G026]
docs(verification): record N-LASR verification results [G017]
```

Every active agent must:

1. Check `git status` before starting.
2. Confirm the expected branch.
3. Pull or fetch required updates.
4. Commit meaningful work.
5. Push after each meaningful commit.
6. Record the latest commit SHA.
7. Leave no unexplained untracked files.
8. Leave a clean worktree before handoff.

Do not use:

* `git push --force` on shared branches.
* Destructive resets on other agents’ branches.
* History rewriting after verification has begun.
* Commits containing secrets or proprietary source files.
* Vague commit messages such as `update`, `fix`, or `changes`.

---

# 6. SESSION RESUMPTION AND CONTEXT RECOVERY

At the beginning of every new orchestrator session:

1. Run:

```bash
git fetch --all --prune
git status
git branch --all
git worktree list
git log --oneline --decorate -n 30
```

2. Read:

```text
MASTER_PROMPT.md
progress.md
goals.md
decisions.md
assumptions_register.md
evidence_matrix.md
coordination/agent_assignments.yaml
```

3. Inspect:

* Open GitHub issues.
* Open pull requests.
* CI status.
* Active branches.
* Active worktrees.
* Latest commits.
* Failed verification reports.
* Red-team findings.
* Current blockers.

4. Reconcile any discrepancy between:

   * Local state.
   * GitHub state.
   * `goals.md`.
   * Agent assignment registry.
   * Pull-request status.

5. Update `progress.md` before assigning new work if the durable state is stale.

The orchestrator must be able to recover the project state from GitHub and committed repository files without needing the previous conversation transcript.

At the end of every session:

* Commit all durable project-state updates.
* Push all active branches.
* Update `progress.md`.
* Update agent assignments.
* Record blockers.
* Record the next dependency-ready goals.
* Ensure no important decision exists only in conversational context.

---

# 7. END STATE

The following command sequence, or an equivalently simple documented sequence, must work from a clean checkout:

1. Clone the private GitHub repository.
2. Install the project.
3. Validate configuration.
4. Generate schema-compliant synthetic data.
5. Ingest synthetic data through the same interfaces intended for real data.
6. Build a canonical point-in-time dataset.
7. Construct features.
8. Construct targets and labels.
9. Train at least one historical N-LASR/LASR model variant.
10. Generate predictions.
11. Construct a portfolio.
12. Run a walk-forward backtest.
13. Produce evaluation reports.
14. Save model, dataset, configuration, and lineage artifacts.
15. Reproduce the same outputs from the same configuration and random seed.

The completed repository must include working implementations rather than only interfaces or placeholder functions.

Placeholders are acceptable only for genuinely unavailable external dependencies such as:

* Provider credentials.
* Undocumented API endpoints.
* Proprietary vendor-specific request formats.
* Commercial risk-model data.
* Actual historical datasets.

Every unavailable dependency must have:

* A clearly defined interface.
* A mock implementation.
* Contract tests.
* Configuration examples.
* Documentation describing exactly what a real implementation must provide.
* No fabricated behaviour presented as real.

The final architecture must allow real data to replace synthetic data without changing model logic.

---

# 8. TECHNICAL MEANING OF PRE-TRAINING, TRAINING, POST-TRAINING, AND FINE-TUNING

Do not mechanically impose an LLM training lifecycle on a classical tabular quantitative model.

First determine what these terms mean for this system.

## 8.1 Data and representation preparation

This may include:

* Raw-data ingestion.
* Schema validation.
* Identifier reconciliation.
* Point-in-time alignment.
* Publication-lag application.
* Corporate-action adjustment.
* Cross-sectional normalization.
* Feature ranking.
* Residualization and neutralization.
* Feature eligibility and coverage analysis.
* Optional unsupervised representation learning.
* Optional feature compression or denoising.

Call this pre-training only where that terminology is technically defensible.

## 8.2 Base-model training

Fit the stock-selection learner using historical features and targets under a strictly point-in-time, walk-forward protocol.

## 8.3 Post-training

This may include:

* Probability or score calibration.
* Cross-sectional score standardization.
* Ensemble weighting.
* Risk residualization.
* Alpha scaling.
* Portfolio mapping.
* Cost-aware calibration.
* Model-card generation.
* Stability and exposure diagnostics.

## 8.4 Fine-tuning or model updating

For LASR-style models, this is naturally represented by:

* Rolling-window refitting.
* Periodic recalibration.
* Recent-history adaptation.
* Seasonal-model updating.
* Hedge-model updating.
* Region-specific adaptation.
* Universe-specific adaptation.
* Hyperparameter updates conducted only through valid nested validation.

Do not call ordinary monthly or weekly refitting “fine-tuning” without explaining the distinction.

## 8.5 Optional representation pre-training

Architect an optional module for pre-training representations from large historical datasets, panel data, text, or alternative data.

However:

* Keep it disabled by default.
* Do not make it a prerequisite for faithful LASR reconstruction.
* Do not claim Deutsche Bank used it unless the papers establish that.
* Require it to demonstrate incremental walk-forward value after costs before retaining it.

---

# 9. MULTI-AGENT RESEARCH, IMPLEMENTATION, AND VERIFICATION LOOP

Before implementing the quantitative system, create the agent operating framework.

Create Claude Code agent definitions under:

```text
.claude/agents/
```

Create reusable project skills using `SKILL.md` files.

Adapt frontmatter, tool declarations, hooks, and command syntax to the installed Claude Code version. Inspect local Claude Code documentation or help output rather than assuming unsupported syntax.

The operating loop must follow this sequence:

1. Identify the next dependency-ready objective.
2. Collect evidence from papers, workbooks, code, tests, and relevant primary sources.
3. Define a concrete goal.
4. Define acceptance criteria before implementation begins.
5. Define branch, worktree, agent owner, and file ownership.
6. Create or update the corresponding GitHub issue.
7. Record assumptions, dependencies, risks, and ambiguities.
8. Design the smallest complete vertical slice.
9. Implement it on the assigned branch and worktree.
10. Commit and push meaningful increments.
11. Run deterministic tests.
12. Open or update the pull request.
13. Send the branch to a fresh-context verifier.
14. Send quantitatively sensitive components to a red-team reviewer.
15. Record failures and required remediation.
16. Return failed goals to the implementer.
17. Repeat implementation and verification until the goal passes.
18. Merge only after verification.
19. Update durable project state.
20. Remove completed worktrees.
21. Proceed to the next dependency-ready goal.
22. Perform a repository-wide final audit after all goals pass.

An implementer may not be the sole approver of its own work.

A plan, issue, document, interface, or scaffold is not sufficient evidence that an implementation goal is complete.

---

# 10. REQUIRED SUBAGENTS

Create at least the following agents.

Names may be refined, but responsibilities must remain separated.

## 10.1 Orchestrator

Responsibilities:

* Own the global objective.
* Maintain the goal dependency graph.
* Maintain GitHub issues and pull-request flow.
* Assign branches, worktrees, and file ownership.
* Prevent overlapping edits.
* Resolve dependencies and integration order.
* Delegate work.
* Prevent duplicated work.
* Enforce acceptance criteria.
* Keep the project moving from research to executable implementation.
* Prevent endless literature review or architecture discussion.
* Decide when a goal is ready for verification.
* Merge only verified work.
* Keep durable project-control files synchronized.
* Never mark its own implementation work as independently verified.

The orchestrator is the sole normal writer to:

```text
goals.md
progress.md
coordination/agent_assignments.yaml
```

## 10.2 Paper Researcher

Responsibilities:

* Read all four papers thoroughly.
* Extract formulas, algorithms, hyperparameters, training windows, labels, portfolio rules, execution assumptions, and implementation details.
* Cite paper, page, section, figure, or table for every material extracted claim.
* Distinguish:

  * `EXPLICIT`
  * `INFERRED`
  * `ASSUMED`
  * `MODERNIZED`
* Identify contradictions and changes across papers.
* Produce an implementation-oriented evidence matrix rather than a prose-only summary.
* Avoid importing later-paper design choices into earlier-paper reconstructions without labelling the change.

## 10.3 Data and Workbook Researcher

Responsibilities:

* Inspect both Excel workbooks sheet by sheet.
* Produce a canonical data dictionary.
* Map provider fields to model features and canonical tables.
* Determine which required inputs are:

  * directly available,
  * available under a different name,
  * derivable,
  * ambiguously derivable,
  * unavailable,
  * dependent on additional data.
* Record units, frequencies, identifiers, nullability, date semantics, revision behaviour, and apparent point-in-time limitations.
* Identify every field whose template does not establish historical availability.
* Never assume that a metric’s presence implies point-in-time historical access.

## 10.4 Quantitative Methodology Reviewer

Responsibilities:

* Verify target definitions.
* Verify label formation.
* Verify ranking and neutralization.
* Verify boosting mathematics.
* Verify ensemble construction.
* Verify walk-forward protocol.
* Verify portfolio accounting.
* Verify costs and borrow assumptions.
* Identify leakage, survivorship bias, look-ahead bias, overlapping-label problems, multiple-testing risks, and false out-of-sample claims.
* Determine whether modernizations preserve or change the original economic objective.

## 10.5 Data and ML Systems Architect

Responsibilities:

* Design canonical schemas.
* Design provider interfaces.
* Design batch, backfill, incremental, and live paths.
* Design feature and label stores.
* Design model-training interfaces.
* Design artifact and experiment tracking.
* Define shared interfaces before parallel implementation.
* Prefer maintainable and testable architecture over unnecessary distributed-system complexity.
* Ensure synthetic, local-file, and future API sources use the same canonical contracts.

## 10.6 Implementer

Responsibilities:

* Write executable production-quality code.
* Work only in the assigned branch and worktree.
* Respect assigned file ownership.
* Follow the approved specification.
* Add unit, integration, and regression tests with each implementation.
* Avoid leaving core methods as `pass`, `TODO`, or unimplemented stubs.
* Use small, reviewable commits.
* Push after meaningful commits.
* Keep notebooks optional; production logic must live in importable modules.

## 10.7 Verifier

Responsibilities:

* Review each goal from fresh context.
* Review the objective and acceptance criteria before implementation explanations.
* Check out or inspect the assigned feature branch.
* Run required commands independently.
* Inspect code and tests.
* Attempt failure cases.
* Produce a pass/fail report with evidence.
* Reject goals supported only by mocked assertions, circular tests, or self-confirming fixtures.
* Avoid silently modifying production code.
* Add verification reports only after implementation pauses for review.

## 10.8 Red-Team Auditor

Responsibilities:

Search specifically for:

* Look-ahead bias.
* Point-in-time violations.
* Survivorship bias.
* Universe contamination.
* Incorrect return alignment.
* Feature/target overlap.
* Leakage through preprocessing.
* Leakage through neutralization.
* Leakage through model selection.
* Overlapping-label contamination.
* Unrealistic execution.
* Incorrect portfolio accounting.
* Cost underestimation.
* Short-borrow omissions.
* Hidden hardcoded assumptions.
* Non-reproducibility.
* Implausibly strong synthetic or historical performance.

Construct adversarial synthetic tests designed to reveal these failures.

Treat suspiciously strong performance as a potential bug until disproven.

A separate software-quality verifier may be created where useful.

---

# 11. PROJECT CONTROL FILES

Create and maintain:

## `goals.md`

Each goal must contain:

* Goal ID.
* GitHub issue number.
* Title.
* Objective.
* Why it matters.
* Inputs.
* Expected outputs.
* Dependencies.
* Assigned agent.
* Branch.
* Worktree.
* Owned file paths.
* Research evidence.
* Explicit assumptions.
* Acceptance criteria.
* Required tests.
* Required verifier.
* Required red-team review.
* Pull request.
* Latest commit.
* Status:

  * `BLOCKED`
  * `READY`
  * `ASSIGNED`
  * `IN_PROGRESS`
  * `IMPLEMENTED`
  * `IN_VERIFICATION`
  * `FAILED_VERIFICATION`
  * `VERIFIED`
  * `MERGED`
* Verification report.
* Remaining issues.

Do not use vague goals such as “implement model” or “improve tests.”

A goal must represent a verifiable vertical slice.

## `decisions.md`

Record:

* Decision ID.
* Decision.
* Alternatives considered.
* Evidence.
* Reasoning.
* Consequences.
* Reversibility.
* Date.
* Responsible agent.
* Related goal and pull request.

## `assumptions_register.md`

Every assumption must include:

* ID.
* Description.
* Why it is necessary.
* Whether it affects faithful reconstruction or modernization.
* Expected direction of bias.
* Configuration parameter controlling it.
* Required sensitivity test.
* Status once real data becomes available.
* Related goal.

## `evidence_matrix.md`

For every material implementation decision, record:

* Component.
* Paper or workbook source.
* Exact location.
* Extracted statement.
* Classification:

  * `EXPLICIT`
  * `INFERRED`
  * `ASSUMED`
  * `MODERNIZED`
* Implementation consequence.
* Open ambiguity.
* Related code path.
* Related test.
* Related goal.

## `progress.md`

Maintain a concise session-independent summary:

* Current milestone.
* Completed and merged goals.
* Verified but unmerged goals.
* Active assignments.
* Current blockers.
* Open pull requests.
* Failing CI jobs.
* Next dependency-ready goals.
* Major open risks.
* Last orchestrator update.
* Current `main` commit SHA.

## `input_manifest.md`

Record:

* Every source file.
* Hash or stable identifier.
* File type.
* File size.
* Relevant sheets or sections.
* Page or sheet count.
* Local expected path.
* Git tracking policy.
* Processing status.
* Parsing issues.

## `coordination/agent_assignments.yaml`

Maintain active ownership, branches, worktrees, and paths as described in the Git operating model.

## `coordination/integration_queue.md`

Track:

* Pull requests awaiting verification.
* Pull requests awaiting red-team review.
* Merge order.
* Shared-interface dependencies.
* Conflicts requiring orchestrator resolution.

---

# 12. SKILLS TO CREATE

Create project-specific `SKILL.md` files for at least:

1. GitHub repository and worktree coordination.
2. Goal decomposition and issue creation.
3. Paper evidence extraction.
4. Excel schema and field mapping.
5. Point-in-time data auditing.
6. Cross-sectional factor construction.
7. Target and label construction.
8. N-LASR weak-learner implementation.
9. LASR linearized weak-learner implementation.
10. Temporal ensemble construction.
11. Signal-level neutralization.
12. Walk-forward and purged validation.
13. Portfolio construction and accounting.
14. Transaction-cost and borrow modelling.
15. Synthetic financial-data generation.
16. Quantitative test design.
17. Leakage and survivorship red-teaming.
18. Pull-request verification.
19. Reproducibility verification.
20. Documentation and evidence traceability.

Each skill must define:

* Purpose.
* Preconditions.
* Inputs.
* Procedure.
* Expected artifacts.
* Common failure modes.
* Quantitative invariants.
* Required tests.
* Git branch and worktree expectations.
* Commit expectations.
* Exit criteria.

Skills must be specific enough that a fresh-context agent can execute them correctly.

---

# 13. RESEARCH PHASE

The research phase must produce an executable specification.

Do not stop after a conventional paper summary.

## 13.1 Paper-by-paper extraction

For every paper, extract:

* Model name and version.
* Investment universe.
* Eligibility criteria.
* Rebalance frequency.
* Model recalibration frequency.
* Feature categories.
* Feature formulas where disclosed.
* Feature preprocessing.
* Outlier treatment.
* Ranking method.
* Neutralization method.
* Target horizon.
* Return definition.
* Target residualization.
* Volatility scaling.
* Classification or regression formulation.
* Positive, negative, and discarded label groups.
* Training-window definitions.
* Seasonal samples.
* Recent-history samples.
* Hedge or adverse-environment samples.
* Weak-learner definition.
* Factor-selection objective.
* Observation-weight update.
* Smoothing constants.
* Number of boosting rounds.
* Stopping conditions.
* Ensemble weighting.
* Prediction normalization.
* Portfolio mapping.
* Risk-model usage.
* Portfolio constraints.
* Turnover limits.
* Transaction-cost assumptions.
* Borrow assumptions.
* Execution delay.
* Validation periods.
* Reported live or out-of-sample periods.
* Capacity analysis.
* Known limitations.

## 13.2 Resolve model versions independently

Create faithful, independently configurable specifications for:

1. N-LASR 2012.
2. N-LASR2 2013.
3. LASR 2014.
4. LASR-HC 2014.
5. LASR-HF 2014.
6. N-LASR 2020.
7. A separate modernized model.

Do not silently merge them.

The modernized model must be explicitly separate from historical reconstruction configurations.

## 13.3 Contradiction register

Document inconsistencies such as:

* Component weighting differences.
* Weak-feature-selection differences.
* Sample-window differences.
* Hedge-model differences.
* Target-preprocessing differences.
* Portfolio-construction differences.
* Prose-versus-appendix differences.
* Filename-versus-publication-date differences.

For every contradiction:

* State both or all versions.
* Identify exact sources.
* Choose a default only when necessary.
* Make alternatives configurable.
* Add an ablation or sensitivity test.

---

# 14. DATA ARCHITECTURE

Create a provider-independent data architecture.

At minimum, define canonical tables or typed datasets for:

## 14.1 Security master

Potential fields:

* Internal security ID.
* Provider identifiers.
* Ticker.
* Exchange.
* Country.
* Currency.
* Share class.
* Listing date.
* Delisting date.
* Active intervals.
* Security type.
* Primary-listing indicator.
* Industry and sector classifications with effective dates.

## 14.2 Market data

Potential fields:

* Event timestamp.
* Knowledge timestamp.
* Open, high, low, close.
* Adjusted and unadjusted prices.
* Volume.
* Shares outstanding.
* Market capitalization.
* VWAP where supplied.
* Bid, ask, spread, and liquidity measures where supplied.
* Corporate-action-adjustment metadata.

## 14.3 Fundamental data

Potential fields:

* Security or issuer ID.
* Fiscal period.
* Fiscal-period end.
* Report date.
* Publication timestamp.
* Provider-ingestion timestamp.
* Restatement or version identifier.
* Metric name.
* Value.
* Units.
* Currency.
* Consolidation basis.

## 14.4 Analyst estimates and consensus

Potential fields:

* Estimate timestamp.
* Forecast period.
* Metric.
* Mean, median, high, and low.
* Number of analysts.
* Revision history.
* Recommendation fields.
* Target-price fields.
* Provider vintage.

## 14.5 Corporate actions

Potential fields:

* Splits.
* Dividends.
* Mergers.
* Spin-offs.
* Rights issues.
* Symbol changes.
* Delistings.
* Announcement dates.
* Effective dates.

## 14.6 Risk, classification, and exposure data

Potential fields:

* Sector.
* Industry.
* Country.
* Region.
* Beta.
* Volatility.
* Size.
* Currency exposure.
* Style exposures.
* Effective dates.

## 14.7 Trading and implementation data

Potential fields:

* ADV.
* Spread.
* Borrow availability.
* Borrow rate.
* Hard-to-borrow indicator.
* Participation limits.
* Market-impact parameters.
* Trading calendar.

Only implement fields supported by the workbooks or clearly labelled future interfaces.

Do not claim unavailable fields are supplied by the provider.

---

# 15. DATA LAYERS

Implement clear layers.

## Raw layer

* Immutable source snapshots.
* Original field names and values.
* Ingestion metadata.
* Schema version.
* Provider metadata.
* File or request lineage.

## Canonical layer

* Standard identifiers.
* Standard units.
* Standard currencies where appropriate.
* Deduplicated records.
* Effective-time and knowledge-time semantics.
* Corporate-action-consistent data.
* Provider-independent schemas.

## Point-in-time layer

* Data available as of each model decision timestamp.
* Publication and ingestion lags.
* Vintage-aware values.
* No future revisions.
* Explicitly tested as-of joins.

## Feature layer

* Reusable feature values.
* Feature-definition version.
* Input lineage.
* Observation timestamp.
* Knowledge timestamp.
* Coverage and quality metadata.

## Training-example layer

* Feature snapshot.
* Target.
* Label.
* Universe membership.
* Comparison group.
* Eligibility metadata.
* Sample-window membership.
* Leakage-audit fields.

The system must support:

* Historical backfills.
* Incremental ingestion.
* Idempotent reruns.
* Partitioned storage.
* Dataset versioning.
* Schema evolution.
* Data-quality reports.
* Reconciliation.
* Local synthetic mode.
* Future provider/API mode.

---

# 16. DATA PROVIDER INTERFACE

Define a provider interface instead of hardcoding the unknown API.

The interface should expose capabilities such as:

* Load security master.
* Load historical prices.
* Load corporate actions.
* Load fundamentals.
* Load analyst estimates.
* Load classifications.
* Load technical or market metrics.
* Load borrow and liquidity information when available.
* Report available history.
* Report field coverage.
* Report revision and point-in-time support.

Provide at least:

1. A synthetic provider.
2. A local-file provider supporting the supplied workbook structures where appropriate.
3. A generic API-provider interface.
4. Contract tests every future provider must pass.

Never create fake production endpoints.

Credentials must come from environment variables or a secret manager.

Never commit credentials.

---

# 17. SYNTHETIC DATA GENERATOR

Build a realistic synthetic-data generator.

It must generate:

* Multiple securities.
* Multiple countries and sectors.
* Changing universe membership.
* Listings and delistings.
* Corporate actions.
* Fundamental publication lags.
* Restatements.
* Missing values.
* Analyst-estimate revisions.
* Cross-sectional factor structure.
* Time-varying factor efficacy.
* Seasonal effects.
* Regime changes.
* Market and sector components.
* Idiosyncratic returns.
* Liquidity variation.
* Borrow costs.
* Transaction costs.
* Technical metrics.
* Deliberate data errors that quality checks should detect.

Support controlled scenarios where correct behaviour is known.

Examples:

* A value factor predicts returns only in one regime.
* Momentum reverses in a crisis regime.
* Sector exposure appears predictive until sector neutralization is applied.
* A deliberately leaked feature creates unrealistic performance.
* A feature has stable monotonic efficacy.
* A feature has a nonlinear but non-monotonic payoff.
* Longer-horizon labels produce slower signal decay.
* Hard-bin N-LASR produces higher score turnover than continuous LASR.
* Delisted securities materially change historical results.
* Restated fundamentals cause leakage unless vintages are respected.

Synthetic tests verify correctness and plumbing, not real-world profitability.

---

# 18. FEATURE FRAMEWORK

Build a feature registry and feature-computation interface.

Every feature must specify:

* Name.
* Version.
* Economic category.
* Direction or orientation.
* Required source fields.
* Formula.
* Units.
* Frequency.
* Minimum coverage.
* Publication lag.
* Missing-value policy.
* Outlier policy.
* Ranking method.
* Neutralization method.
* Eligibility requirements.
* Expected monotonicity.
* Evidence source.
* Availability classification:

  * directly available,
  * derived,
  * proxy,
  * unavailable pending real data.

Support broad categories where data permits:

* Value.
* Profitability.
* Quality.
* Balance-sheet strength.
* Efficiency.
* Growth.
* Analyst revisions.
* Sentiment.
* Momentum.
* Reversal.
* Volatility and low risk.
* Liquidity.
* Technical indicators.

Do not implement dozens of weakly specified features before core point-in-time correctness is established.

Begin with a small audited feature library sufficient to exercise the complete framework.

---

# 19. TARGET AND LABEL ENGINE

Create configurable target definitions.

## 19.1 Original monthly target

* One-month forward return.
* Comparison against universe, sector, country, or another configured group.
* Top 30% labelled `+1`.
* Bottom 30% labelled `-1`.
* Middle 40% excluded.

## 19.2 LASR-HC target

* Three-month forward return.
* Correct treatment of overlapping labels.
* Purging or embargoing where required.

## 19.3 LASR-HF target

* Approximately one-week return.
* Configurable close-to-close, close-to-open, or open-to-open timing.
* Explicit decision and execution timestamps.

## 19.4 N-LASR 2020 target

* Four-week forward return.
* Sector-region adjustment.
* Historical-volatility scaling.
* Configurable operation order where the paper is ambiguous.
* Classification and regression forms.

Every target record must preserve:

* Feature observation time.
* Knowledge cutoff.
* Trade decision time.
* Execution time.
* Target start.
* Target end.
* Comparison group.
* Volatility-estimation window.
* Purge or embargo metadata.

---

# 20. MODEL IMPLEMENTATIONS

Implement historical kernels as separate tested modules.

## 20.1 N-LASR 2012 weak learner

Support:

* Cross-sectional ranked feature.
* Five bins.
* Weighted positive and negative class mass.
* Smoothing pseudocount.
* Bin-level log-ratio prediction.
* Factor-selection objective.
* AdaBoost observation-weight update.
* Configurable boosting rounds.
* Deterministic tie-breaking.
* Optional repeated feature selection.

Create formula-level tests using manually verifiable datasets.

## 20.2 N-LASR2

Add:

* Sector-relative learning.
* Country-relative learning.
* Size grouping.
* Beta grouping.
* Combined grouping.
* Hedge-model sample construction.
* Configurable hedge weighting.

## 20.3 LASR 2014

Implement:

* Continuous triangular membership in adjacent feature bins.
* Piecewise-linear factor-response functions.
* Boundary handling.
* Weighted class mass using fractional membership.
* Continuous weak predictions.
* Direct comparison with hard-bin N-LASR.

Test that:

* Predictions are continuous at internal boundaries.
* Tiny feature changes do not cause hard-bin jumps.
* The model is deterministic.
* Score autocorrelation is generally higher in controlled synthetic scenarios.

## 20.4 LASR-HC

Support:

* Longer target horizon.
* Lower-turnover feature subsets.
* Capacity-oriented configurations.
* Comparison under turnover and cost constraints.

## 20.5 LASR-HF

Keep modular and lower priority.

Support:

* Weekly targets.
* Technical factors.
* Execution-delay tests.
* Open-price training and testing where data permits.

## 20.6 N-LASR 2020

Support:

* Weekly feature snapshots.
* Four-week labels.
* Five-year long-term sample.
* One-year short-term sample.
* Ten-year seasonal sample.
* Hedge sample based on poor historical aggregate-model periods.
* Four-week model recalibration.
* Weekly portfolio updates.
* Equal-weight temporal aggregation.
* Monotonic factor orientation.
* Classification and regression alternatives.
* Beta residualization.
* Execution-delay and slippage testing.

Where Paper 4’s factor-selection description differs from earlier papers, implement both interpretations as separately configurable options.

Do not silently choose one.

---

# 21. TEMPORAL ENSEMBLE FRAMEWORK

Build a general temporal-expert interface.

Every expert must define:

* Name.
* Training-sample selector.
* Feature set.
* Target.
* Weak learner.
* Weighting rule.
* Refit schedule.
* Prediction schedule.
* Eligibility checks.

Support:

* Recent medium-term expert.
* Very-recent expert.
* Seasonal expert.
* Adverse-environment or hedge expert.
* Long-term expert.
* Optional multi-horizon experts.

Support aggregation rules including:

* Equal weighting.
* Historical rank-IC weighting.
* Published hedge-weight rule.
* Regularized non-negative weighting.
* Fixed pre-registered weighting.

Any learned ensemble weighting must be fitted inside the appropriate training or validation window and must never use test-period outcomes.

---

# 22. MODERN MODEL CHALLENGERS

Add modern alternatives only after faithful historical versions work.

Potential challengers:

* Equal-weight factor composite.
* Ridge regression.
* Elastic net.
* Non-negative least squares.
* Monotonic generalized additive model.
* Explainable Boosting Machine.
* Shallow gradient-boosted trees.
* Monotonic gradient boosting.
* Random forest.
* Learning-to-rank model.
* Carefully regularized neural network.
* Multi-task or multi-horizon model.

All challengers must use:

* The same universe.
* The same point-in-time features.
* The same target.
* The same walk-forward folds.
* The same execution assumptions.
* The same portfolio construction where possible.
* The same cost model.

Do not declare a complex model superior based only on:

* In-sample fit.
* Classification accuracy.
* Gross return.
* One favourable period.
* One favourable universe.

---

# 23. VALIDATION AND BACKTESTING

Build a rigorous event-time and walk-forward backtesting engine.

It must distinguish:

* Feature timestamp.
* Knowledge timestamp.
* Model-fit timestamp.
* Signal-generation timestamp.
* Order-decision timestamp.
* Execution timestamp.
* Holding period.
* Target period.

Support:

* Expanding windows.
* Rolling windows.
* Seasonal samples.
* Purged validation.
* Embargo periods.
* Nested hyperparameter selection.
* Fixed historical hyperparameters.
* Delayed execution.
* Rebalance calendars.
* Missing-market-day handling.
* Delistings.
* Corporate actions.
* Currency treatment.
* Long-only and long-short portfolios.

## Signal metrics

* Pearson IC.
* Spearman rank IC.
* IC mean.
* IC volatility.
* IC information ratio.
* Quantile return spreads.
* Quantile monotonicity.
* Hit rate.
* Score autocorrelation.
* Prediction decay.
* Turnover.
* Factor-selection stability.
* Feature-family exposure.
* Submodel contribution.

## Portfolio metrics

* Annualized return.
* Volatility.
* Sharpe ratio.
* Sortino ratio.
* Maximum drawdown.
* Gross and net exposure.
* Beta.
* Sector and country exposures.
* Turnover.
* Cost drag.
* Borrow drag.
* Capacity estimates.
* Participation rate.
* Tail losses.
* Performance by region, sector, regime, and period.

## Research-validity metrics

* Number of configurations tested.
* Validation-to-test degradation.
* Sensitivity to universe.
* Sensitivity to period.
* Sensitivity to costs.
* Sensitivity to execution delay.
* Confidence intervals.
* Bootstrap stability.
* Multiple-testing diagnostics where practical.

---

# 24. PORTFOLIO CONSTRUCTION

Implement portfolio construction progressively.

## Level 1: simple portfolio

* Equal-weight top and bottom quantiles.
* Dollar neutral.
* Deterministic tie handling.
* Explicit gross exposure.

## Level 2: signal-weighted portfolio

* Weight by normalized score.
* Position caps.
* Dollar neutrality.
* Optional beta residualization.

## Level 3: constrained optimizer

Support:

* Gross and net exposure.
* Target volatility.
* Beta limits.
* Sector limits.
* Country limits.
* Position limits.
* Turnover limits.
* ADV participation limits.
* Borrow availability.
* Borrow costs.
* Transaction costs.
* Optional risk-model covariance.

When the proprietary risk model used in the papers is unavailable:

* Define a generic risk-model interface.
* Implement a transparent substitute using shrinkage covariance and explicit factor exposures.
* Mark it as an assumption rather than an exact replication.
* Test and document it.

Separate:

* Raw alpha performance.
* Portfolio-construction improvement.
* Risk-control effects.
* Trading-cost effects.

---

# 25. TRANSACTION COSTS AND CAPACITY

Build a modular implementation-cost model supporting:

* Fixed commission.
* Half-spread.
* Slippage.
* Execution delay.
* Linear cost.
* Nonlinear market impact.
* ADV participation.
* Borrow fee.
* Hard-to-borrow exclusion.
* Short availability.
* Regional cost differences.
* Portfolio-size scaling.

Backtests must report:

* Gross performance.
* Performance after explicit trading costs.
* Performance after borrow costs.
* Performance under delayed execution.
* Capacity sensitivity.
* Break-even costs.

Do not use a single fixed basis-point assumption as the only cost analysis.

---

# 26. SOFTWARE ENGINEERING REQUIREMENTS

Prefer maintainable Python unless repository context strongly justifies another language.

Use:

* `pyproject.toml`.
* Typed interfaces.
* Clear module boundaries.
* Structured configuration.
* Deterministic random seeds.
* Structured logging.
* Explicit error handling.
* Unit tests.
* Integration tests.
* End-to-end tests.
* Static checks.
* Formatting and linting.
* Continuous integration.
* Reproducible environments.
* No committed secrets.

Set up GitHub Actions to run at minimum:

* Installation.
* Formatting check.
* Linting.
* Type checking.
* Unit tests.
* Integration tests that do not require proprietary inputs.
* Synthetic end-to-end smoke test.

Avoid:

* Notebook-only implementations.
* Hidden global state.
* Hardcoded paths.
* Hardcoded dates.
* Hardcoded provider assumptions.
* Silent fallback behaviour.
* Tests that only assert code execution.
* Monolithic scripts.
* Premature distributed computing.
* Premature deep-learning infrastructure.
* Over-abstraction without a concrete use case.

---

# 27. SUGGESTED REPOSITORY STRUCTURE

Refine this where justified, but preserve responsibility separation:

```text
.
├── .claude/
│   └── agents/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   ├── pull_request_template.md
│   └── workflows/
├── coordination/
│   ├── agent_assignments.yaml
│   └── integration_queue.md
├── skills/
├── configs/
│   ├── data/
│   ├── features/
│   ├── models/
│   ├── portfolios/
│   └── experiments/
├── docs/
│   ├── evidence/
│   ├── methodology/
│   ├── architecture/
│   ├── data/
│   ├── validation/
│   ├── verification/
│   ├── red_team/
│   └── runbooks/
├── inputs/
│   ├── papers/
│   │   └── README.md
│   └── data_templates/
│       └── README.md
├── src/
│   └── lasr/
│       ├── data/
│       │   ├── providers/
│       │   ├── schemas/
│       │   ├── ingestion/
│       │   ├── canonical/
│       │   ├── point_in_time/
│       │   └── quality/
│       ├── features/
│       ├── targets/
│       ├── models/
│       │   ├── nlasr/
│       │   ├── lasr/
│       │   ├── ensembles/
│       │   └── challengers/
│       ├── validation/
│       ├── portfolio/
│       ├── costs/
│       ├── backtesting/
│       ├── reporting/
│       ├── artifacts/
│       └── cli/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── end_to_end/
│   ├── leakage/
│   └── regression/
├── scripts/
├── examples/
├── MASTER_PROMPT.md
├── goals.md
├── decisions.md
├── assumptions_register.md
├── evidence_matrix.md
├── progress.md
├── input_manifest.md
├── README.md
├── .gitignore
└── pyproject.toml
```

Generated data, models, and reports must use ignored artifact directories.

Local worktrees should normally live under:

```text
.worktrees/
```

Add `.worktrees/` to `.gitignore`.

---

# 28. REQUIRED USER WORKFLOWS

Provide documented commands for:

* Cloning and environment setup.
* Input inspection.
* Workbook-schema extraction.
* Synthetic-data generation.
* Raw-data ingestion.
* Canonical-data construction.
* Point-in-time validation.
* Feature construction.
* Target construction.
* Model training.
* Walk-forward backtesting.
* Portfolio construction.
* Report generation.
* Running all tests.
* Running leakage tests.
* Reproducing a complete example experiment.
* Creating a new provider adapter.
* Creating a new feature.
* Creating a new model configuration.

A user should not need to edit source code to choose:

* Model version.
* Universe.
* Date range.
* Training windows.
* Target horizon.
* Feature set.
* Neutralization.
* Cost assumptions.
* Portfolio constraints.
* Provider.

These must be configuration-driven.

---

# 29. REQUIRED DOCUMENTATION

Produce:

## Research documentation

* Paper-by-paper implementation diagnosis.
* Model evolution map.
* Formula reference.
* Evidence matrix.
* Contradiction register.
* Assumptions register.
* Modernization rationale.

## Data documentation

* Workbook inventory.
* Canonical schema.
* Provider-field mapping.
* Data dictionary.
* Point-in-time policy.
* Identifier policy.
* Corporate-action policy.
* Missing-data policy.
* Real-data integration guide.

## Engineering documentation

* System architecture.
* Module responsibilities.
* Configuration guide.
* GitHub and worktree workflow.
* Agent coordination protocol.
* Testing strategy.
* Artifact lineage.
* Failure recovery.
* Development workflow.

## Quantitative documentation

* Feature definitions.
* Target definitions.
* Training windows.
* Model algorithms.
* Validation protocol.
* Portfolio accounting.
* Transaction-cost model.
* Metric definitions.
* Known limitations.

## Operational documentation

* Backfill runbook.
* Incremental-update runbook.
* Model-retraining runbook.
* Paper-trading runbook.
* Production-readiness checklist.
* Session-resumption runbook.

---

# 30. COMPLETE-PROJECT ACCEPTANCE CRITERIA

The project is complete only when all conditions below hold.

## GitHub and coordination

* A private GitHub repository exists.
* The SSH remote is configured.
* `main` contains only integrated verified work.
* Every major goal has a GitHub issue.
* Every implementation goal has a branch and worktree record.
* Every merged implementation has a pull request.
* Agent ownership and path ownership are documented.
* No active agents have unexplained overlapping write scopes.
* Important work is committed and pushed.
* No important decision exists only in conversational context.
* Repository state can be recovered from a clean clone.

## Agent framework

* Agent definitions exist with distinct responsibilities.
* Skills contain concrete procedures and exit criteria.
* `goals.md` accurately reflects work status.
* Every completed goal has independent verification.
* Blocking red-team findings are resolved or explicitly accepted with rationale.

## Research fidelity

* Every historical model variant has a documented specification.
* Material choices are traceable to papers or assumptions.
* Explicit statements, inferences, assumptions, and modernizations are distinguished.
* Contradictions across papers are documented.
* Later-paper choices are not silently imported into earlier versions.

## Data framework

* Both workbooks are fully inventoried.
* Field-level mappings exist.
* Direct, derived, ambiguous, missing, and future fields are distinguished.
* Canonical schemas are implemented and tested.
* Synthetic and local-file providers pass the same contract tests.
* Point-in-time semantics are implemented and tested.
* Real-data provider integration is documented.

## Model framework

* At least N-LASR 2012, N-LASR2, LASR 2014, and N-LASR 2020 have executable configurations.
* Historical weak learners have formula-level tests.
* Temporal ensembles are configurable.
* Training is deterministic under a fixed seed.
* Predictions and model artifacts are versioned.

## End-to-end execution

Using synthetic data, the framework can:

* Ingest data.
* Validate data.
* Build point-in-time features.
* Build targets.
* Train a model.
* Generate signals.
* Build a portfolio.
* Apply costs.
* Run a walk-forward backtest.
* Produce reports.
* Save lineage.
* Reproduce results.

## Quantitative correctness

Tests verify:

* No future data enters features.
* Labels align to the intended future horizon.
* Neutralization occurs at the intended stage.
* Training and testing do not overlap improperly.
* Overlapping labels are handled deliberately.
* Portfolio returns reconcile with positions and security returns.
* Turnover is calculated correctly.
* Costs and borrow are deducted correctly.
* Gross and net exposures reconcile.
* Corporate actions do not create false returns.
* Delistings are handled.
* Hard-bin and linearized learners behave differently in controlled scenarios.

## Software quality

* Test suite passes from a clean clone.
* GitHub Actions passes.
* No core implementation remains a placeholder.
* Static checks pass.
* Documentation commands work.
* No secrets or machine-specific paths exist.
* No proprietary source inputs have been accidentally committed.
* Dependencies and licences are recorded where appropriate.

---

# 31. INITIAL GOAL DECOMPOSITION

Create a dependency-aware goal queue.

A reasonable initial decomposition is:

1. Bootstrap local Git repository.
2. Create private GitHub repository and SSH remote.
3. Create GitHub labels, issue templates, and pull-request template.
4. Inventory all source files.
5. Build agent definitions and skills.
6. Create durable coordination files.
7. Extract paper evidence.
8. Extract workbook schemas.
9. Produce canonical data requirements.
10. Create assumptions and contradiction registers.
11. Design repository architecture.
12. Implement typed canonical schemas.
13. Implement provider interfaces.
14. Implement synthetic provider.
15. Implement workbook and local-file inspection.
16. Implement point-in-time data layer.
17. Implement data-quality checks.
18. Implement feature registry.
19. Implement a small audited feature library.
20. Implement target and label engine.
21. Implement N-LASR 2012 weak learner.
22. Implement temporal ensemble.
23. Implement N-LASR2 neutralization.
24. Implement hedge learner.
25. Implement LASR 2014 weak learner.
26. Implement LASR-HC configuration.
27. Implement N-LASR 2020 configuration.
28. Implement simple portfolio construction.
29. Implement transaction costs and borrow.
30. Implement walk-forward backtester.
31. Implement reporting and diagnostics.
32. Implement constrained portfolio layer.
33. Implement modern baseline challengers.
34. Run red-team leakage audit.
35. Run complete synthetic end-to-end experiment.
36. Produce real-data integration guide.
37. Perform final clean-clone and repository-wide verification.
38. Tag the first verified framework release.

The orchestrator may refine this after inspecting the inputs.

Do not begin with:

* Every possible feature.
* Every market.
* LASR-HF.
* Deep learning.
* Production brokerage integration.
* Distributed infrastructure.

First complete one audited vertical slice.

---

# 32. PRIORITY ORDER

## First priority

* GitHub-backed durable state.
* Clear ownership and non-overlapping worktrees.
* Point-in-time correctness.
* Data contracts.
* Reproducibility.
* Small synthetic vertical slice.
* N-LASR 2012 core learner.
* Walk-forward evaluation.
* Correct portfolio accounting.

## Second priority

* Temporal ensembles.
* N-LASR2 neutralization.
* LASR linearization.
* Transaction costs.
* Capacity and longer-horizon targets.

## Third priority

* N-LASR 2020 weekly implementation.
* Modern challenger models.
* Advanced risk optimization.
* Alternative-data interfaces.
* Optional representation pre-training.

## Lower priority

* LASR-HF.
* Large neural networks.
* Reinforcement learning.
* Live brokerage integration.
* Distributed training.
* Elaborate dashboards.

---

# 33. BEHAVIOURAL RULES

You must:

* Read supplied sources before defining implementation details.
* Cite evidence internally.
* State uncertainty explicitly.
* Prefer configurable assumptions over hidden guesses.
* Use synthetic data to prove plumbing and mathematical correctness.
* Keep faithful reconstruction and modernization separate.
* Use fresh-context verification.
* Escalate genuine blockers rather than fabricating resolutions.
* Implement incrementally.
* Commit and push meaningful progress continuously.
* Preserve a working integrated `main`.
* Keep branches and worktrees isolated.
* Define file ownership before parallel work.
* Keep GitHub issues and repository control files synchronized.
* Keep progress files current.
* Report exact commands and test results.
* Tag meaningful verified milestones.

You must not:

* Merely summarize the papers.
* Produce only a design document.
* Produce only pseudocode.
* Generate an impressive but non-executable scaffold.
* Claim mock data validates investment performance.
* Treat a currently available field as historically point-in-time by default.
* Use present-day index constituents for historical backtests.
* Select hyperparameters using the final test period.
* Fit preprocessing on future observations.
* Hide cost, borrow, or execution assumptions.
* Call ordinary rolling retraining “pre-training” or “fine-tuning” without defining the term.
* Combine historical model versions into an undocumented hybrid.
* Optimize endlessly against synthetic returns.
* Allow multiple agents to edit the same files without an ownership plan.
* Leave important work uncommitted.
* Keep important project knowledge only in chat.
* Commit licensed source papers, proprietary spreadsheets, secrets, or real data.
* Merge unverified work.
* Mark incomplete goals verified to satisfy a turn limit.
* Stop because the repository merely looks complete.

---

# 34. VERIFICATION OUTPUT FORMAT

For every goal, the verifier must produce:

* Goal ID.
* GitHub issue.
* Branch.
* Commit reviewed.
* Pull request.
* Verdict: `PASS` or `FAIL`.
* Acceptance criteria reviewed.
* Commands executed.
* Tests passed.
* Tests failed.
* Code paths inspected.
* Edge cases attempted.
* Leakage risks checked.
* Quantitative invariants checked.
* Blocking findings.
* Non-blocking recommendations.
* Evidence for the verdict.

A failed goal returns to implementation with the verifier’s report attached to the issue and pull request.

Do not mark it verified until a subsequent independent review passes.

---

# 35. FINAL AUDIT

After all individual goals are verified, perform a complete audit from fresh context and preferably from a clean clone.

The audit must answer:

1. Can the private repository be cloned from scratch?
2. Can the project be installed from a clean environment?
3. Can synthetic data flow through the real provider interfaces?
4. Can a complete experiment be reproduced?
5. Can each model version be configured separately?
6. Are all major assumptions documented?
7. Are paper-derived and modernized components distinguishable?
8. Are point-in-time safeguards tested?
9. Are portfolio returns and costs reconciled?
10. Are there hidden placeholders in core paths?
11. Is real-data integration limited primarily to provider access and mappings?
12. Are claimed capabilities supported by code and tests?
13. Are active branches and worktrees accounted for?
14. Are there stale or abandoned unmerged changes?
15. Are GitHub issues, pull requests, and local goal status consistent?
16. Are source papers, spreadsheets, secrets, and generated data absent from Git history?
17. Are there unresolved findings that would invalidate a genuine historical backtest?

Produce a final report containing:

* Completed architecture.
* Implemented model versions.
* Test summary.
* CI summary.
* Verification summary.
* GitHub issue and pull-request summary.
* Remaining external dependencies.
* Known methodological limitations.
* Exact steps for attaching real data.
* Exact steps for running the first genuine historical experiment.
* Current release tag and commit SHA.

Create a release tag after the final audit passes, for example:

```text
v0.1.0-framework-ready
```

Push the tag to GitHub.

---

# 36. LOOP TERMINATION CONDITION

Create a project-specific `/goal` condition or equivalent loop condition.

Continue working until:

1. Every required item in `goals.md` is `VERIFIED` or `MERGED`.
2. Every verified implementation is merged into `main`.
3. Every major goal has a synchronized GitHub issue.
4. Every merged implementation has an associated pull request and verification report.
5. All unit, integration, end-to-end, leakage, and regression tests pass.
6. GitHub Actions passes on `main`.
7. A complete synthetic-data experiment runs from ingestion through reporting.
8. The verifier reports contain no unresolved blocking findings.
9. The red-team audit contains no unresolved correctness or leakage findings.
10. Every material implementation decision is linked to evidence or a documented assumption.
11. The final clean-clone audit passes.
12. Actual provider data and credentials are the principal remaining external dependency.
13. The repository contains no unimplemented core paths disguised as future work.
14. No important project state remains only in conversational context.
15. All active branches and worktrees are either integrated, deliberately retained, or documented as blocked.
16. The repository has a final verified milestone tag.

Do not stop merely because:

* A plan has been written.
* Files have been scaffolded.
* GitHub issues have been created.
* Mock functions return plausible values.
* One model fits a static dataset.
* Tests were written but not executed.
* A pull request exists.
* The implementer believes the objective is complete.
* The codebase appears large or sophisticated.

Use a sensible maximum-turn safeguard.

If the limit is reached, stop with:

* Current goal statuses.
* Open issues and pull requests.
* Active branches and worktrees.
* Latest pushed commits.
* Exact unresolved blockers.
* Failed verification evidence.
* Recommended next actions.

Do not falsely mark incomplete goals verified.

---

# 37. FIRST ACTIONS

Begin with the following sequence:

1. Inspect the current directory.
2. Determine whether a Git repository and GitHub remote already exist.
3. Initialize Git if required.
4. Create a secure `.gitignore` before staging files.
5. Ensure the source PDFs and Excel workbooks will not be committed.
6. Create the private GitHub repository if GitHub CLI authentication permits.
7. Configure the SSH remote.
8. Create and push the bootstrap commit.
9. Inventory all supplied files.
10. Verify paper filenames, titles, publication dates, page counts, and hashes.
11. Inspect every workbook and sheet.
12. Create `input_manifest.md`.
13. Create the GitHub issue labels and templates.
14. Create agent definitions and core skills.
15. Create `goals.md`, `progress.md`, `decisions.md`, `assumptions_register.md`, and `evidence_matrix.md`.
16. Create `coordination/agent_assignments.yaml`.
17. Create the initial dependency-aware goals as GitHub issues.
18. Assign paper extraction and workbook extraction to separate branches and worktrees.
19. Define non-overlapping file ownership.
20. Delegate paper and workbook research to separate agents.
21. Require each agent to commit and push its work.
22. Ask the quantitative reviewer to define initial correctness and leakage criteria.
23. Produce the first architecture only after research outputs exist.
24. Select the smallest complete vertical slice.
25. Implement it in an isolated branch and worktree.
26. Open a pull request.
27. Independently verify it.
28. Merge it only after verification passes.
29. Update durable project state.
30. Continue through the goal loop until the full framework satisfies the termination condition.

Start now.

Do not wait for further direction unless a genuinely blocking ambiguity cannot be represented as a documented and configurable assumption.

````

A compact `/goal` condition to save separately as `goal_condition.txt` is:

```text
Continue until every required goal in goals.md is VERIFIED or MERGED; all verified implementation branches have been merged into main through documented pull requests; every goal has synchronized GitHub issue, agent, branch, worktree, ownership, and verification records; all unit, integration, end-to-end, leakage, regression, and clean-clone tests pass; GitHub Actions passes; the complete synthetic-data pipeline runs from ingestion through model training, portfolio construction, cost application, backtesting, and reporting; all blocking verifier and red-team findings are resolved; every material implementation decision is linked to paper/workbook evidence or a documented configurable assumption; no proprietary inputs, data, or secrets are committed; and the final audit confirms that actual provider data and credentials are the principal remaining external dependencies. Do not treat planning, scaffolding, issues, pull requests, mocks without contract tests, unexecuted tests, or unverified code as completion. Keep committing and pushing meaningful progress throughout the process. Stop at the maximum-turn limit only with an explicit report of open issues, pull requests, branches, worktrees, latest commits, failed checks, and unresolved blockers.
````
