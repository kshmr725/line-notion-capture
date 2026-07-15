# Editable Cloud Proposals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an invited user revise AI-suggested Cloud groupings per source before confirmation, without modifying canonical Notion or Obsidian content.

**Architecture:** A proposal retains source title/id pairs rather than samples only. A pure revision function validates a source-to-Cloud assignment map, supports canonical and safe custom keys, and produces a new proposal view with excluded items omitted. The confirmation route applies only the validated assignment map when it indexes the projection.

**Tech Stack:** Python dataclasses, Flask/Jinja forms, SQLite proposal JSON, pytest.

## Global Constraints

- No action may write to Notion or Obsidian.
- Every proposed source ID belongs to the authenticated tenant's proposal; unrecognized IDs are ignored.
- Excluded sources are not indexed; they are not deleted from the canonical source.
- Group rename, merge, split, and move are all represented as source-level assignment changes.
- Custom Cloud keys use a deterministic safe slug and remain visible as a label in projection/search results.

---

### Task 1: Source-level proposal revision domain model

**Files:**
- Modify: `brain_portal/models.py`, `brain_portal/onboarding.py`
- Test: `tests/portal/test_onboarding.py`

**Produces:** `ProposalSource`, `revise_proposal(proposal, assignments) -> tuple[CloudProposal, ...]`.

- [x] **Step 1:** Write RED tests proving that assigning two original groups to one target merges them, assigning one source to a new target splits it, and excluding one source removes it from the result only.
- [x] **Step 2:** Run `pytest -q tests/portal/test_onboarding.py -k revise` and confirm RED.
- [x] **Step 3:** Add source title/id pairs to proposal JSON and implement a pure revision function that rejects unknown source IDs and makes no source mutation.
- [x] **Step 4:** Run focused tests and commit `feat: add editable cloud proposal model`.

### Task 2: Confirm-time assignment validation

**Files:**
- Modify: `brain_portal/onboarding.py`, `brain_portal/auth.py`
- Test: `tests/portal/test_onboarding.py`, `tests/portal/test_auth.py`

**Produces:** `confirm_clouds(..., assignments=...)` indexes only the revised, non-excluded source set.

- [x] **Step 1:** Write RED tests for a custom Cloud label surviving confirmation, excluded source absent from projection, and foreign/unknown assignment unable to alter tenant data.
- [x] **Step 2:** Run focused tests and confirm RED.
- [x] **Step 3:** Parse form data only for sources from the current proposal, use the revision function, and pass revised assignments to the indexer.
- [x] **Step 4:** Run focused tests and commit `feat: apply edited cloud assignments on confirmation`.

### Task 3: Review UI

**Files:**
- Modify: `brain_portal/templates/portal/onboarding.html`, `brain_portal/static/portal.css`
- Test: `tests/portal/test_auth.py`, `tests/portal/test_accessibility.py`

- [x] **Step 1:** Write RED route/template tests for a labelled per-source destination selector, exclusion control, custom Cloud label input, and a clear source-backed warning.
- [x] **Step 2:** Run focused tests and confirm RED.
- [x] **Step 3:** Render accessible controls grouped by suggested Cloud; existing group names become editable labels and each source may select an existing or custom target.
- [x] **Step 4:** Run accessibility/full tests, inspect local HTML, commit `feat: let users edit cloud proposals before confirmation`.

### Task 4: Handoff and boundaries

**Files:**
- Modify: `README.md`, `docs/handoffs/2026-07-15/controlled-beta-webhook-queue.md`

- [x] **Step 1:** Document that edits change only the portal projection, not the source workspace.
- [x] **Step 2:** Run `pytest -q` and `git diff --check`.
- [x] **Step 3:** Record checkpoint including remaining dynamic custom-Cloud navigation work.
