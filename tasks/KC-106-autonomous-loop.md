# KC-106: Autonomous Agent Execution Loop

Status: IMPLEMENTATION
Implementer: local-codex-KC-106
Reviewer: local-claude-KC-106
Branch: agent/KC-106-autonomous-loop

## Goal
Implement a bounded, auditable, single-task agent execution loop
using the existing KC-104 scheduler and KC-105 adapters.

## Allowed paths
- .gitignore
- orchestrator/models.py
- orchestrator/scheduler.py
- orchestrator/worktree.py
- orchestrator/runloop.py
- orchestrator/cli.py
- orchestrator/README.md
- orchestrator/tests/**
- tasks/KC-106-autonomous-loop.md

## Requirements
- Atomic claim and strict lease ownership.
- Verified isolated Git worktree and branch.
- Fake-agent end-to-end operation without API calls.
- Sandboxed implementation and quality checks.
- Independent structured review.
- At most two correction rounds.
- Bounded execution, logging and retries.
- Safe handling of failures and interrupted execution.
- Structured attempt history and handover.
- No automatic push, PR merge or deployment.
- No inherited personal credential access.
- No live execution without explicit authorization.

## Safety boundaries
- No changes to main or unrelated worktrees.
- No direct host execution of agent-controlled code.
- Review must include uncommitted and untracked changes.
- Dry-run must not modify persistent state.
- No silent fallback from sandbox to direct execution.
- Failure to safely implement a boundary means BLOCKED.

## Implementation handover

Task: KC-106 — Autonomous Agent Execution Loop
Owner / branch / commit: local-codex-KC-106 / agent/KC-106-autonomous-loop / uncommitted by instruction
Agent status: READY_FOR_REVIEW
Task status requested: REVIEW
Changed paths: orchestrator models, scheduler, strict worktree verifier, run loop, CLI, README, and focused tests; this task card
Implemented behavior: atomic run claim; token-bound attempts; verified branch/worktree/scope; isolated Codex and Claude phases; Bubblewrap-only allowlisted quality checks; complete bounded review input; strict verdicts; initial attempt plus at most two corrections; durable outcomes/evidence paths; final handover
Contracts / migrations changed: task transition policy now supports RUNNING, bounded REVIEW-to-RUNNING corrections, and READY_FOR_PR; schema remains v1 with no migration
Reproduction steps: run the two commands in Verification below from this worktree
Checks (with actual environment):
  PASS: python3 -B -m unittest discover -s orchestrator/tests -v — 77 tests passed, 1 pre-existing opt-in real-Bubblewrap class skipped
  PASS: python3 -m orchestrator --help — exit 0; run and attempts commands listed
  PASS: SandboxedQualityRunner orchestrator-tests + orchestrator-help smoke — real /usr/bin/bwrap filesystem boundary, both exit 0; nested suite 77 passed / 1 opt-in skipped
  NOT RUN: real Codex/Claude execution — no credential provisioning authorized or available; automated tests use deterministic fakes
Yocto evidence: none
Security, licensing, network and data impacts: no new dependencies or schema migration; model workers inherit no personal credentials; quality checks have no host fallback; no push/merge/publish/deploy behavior; KC-105's lack of kernel-enforced network egress filtering remains unchanged
Known gaps / risks: real unattended model authentication is intentionally unresolved; the pre-existing opt-in adapter Bubblewrap test class remained skipped in the required suite, while the new quality runner was separately exercised through real Bubblewrap
Next action and owner: local-claude-KC-106 independently reviews the uncommitted diff and evidence; maintainer controls any PR/integration
PR / issue / artifact links: none; no commit, push, or PR authorized
