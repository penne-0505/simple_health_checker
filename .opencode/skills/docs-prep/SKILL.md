---
name: docs-prep
description: Use when preparing documentation for large implementations (Size >= M) following the _docs/ hierarchy and lifecycle rules.
---

# Documentation Preparation

This skill focuses on creating documentation before large implementations, following the project's documentation protocol and lifecycle rules.

## When to Use

Use this skill for **large changes (Size >= M)** or when design decisions need to be recorded:
- New features requiring architecture decisions
- Breaking changes or migrations
- Complex refactors affecting multiple components
- Features requiring formal specification

For small changes (Size < M), use **implementation-prep** alone and skip this skill.

## Documentation Workflow

### 1. Determine Documentation Scope

Based on the implementation size and complexity:

| Change Type | Required Documents |
|-------------|-------------------|
| Large feature (Size >= M) | draft/ → plan/ → intent/ → guide/ + reference/ |
| Breaking change | plan/ + intent/ (migration guide) |
| Architecture decision | intent/ (ADR-style) |
| Research-heavy feature | survey/ → plan/ → intent/ |

### 2. Create Draft Documentation

**Location**: `_docs/draft/(feature-name)/`

Create initial notes and hypotheses:

```markdown
---
title: "Feature X Draft Notes"
status: proposed
draft_status: exploring
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
references: []
related_issues: []
related_prs: []
---

## Hypothesis
- What we're trying to solve
- Expected outcomes

## Options / Alternatives
- Approach A: Pros/Cons
- Approach B: Pros/Cons

## Open Questions
- Technical constraints to investigate
- Design decisions pending
```

**Key Points**:
- Use `draft_status: exploring` while investigating
- Update `updated_at` regularly (30-day stale limit)
- Link to related TODO.md entries

### 3. Elevate to Plan (if needed)

**Location**: `_docs/plan/(feature-name)/plan.md`

When scope is clear, create formal plan:

```markdown
---
title: "Feature X Implementation Plan"
status: proposed
draft_status: n/a
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
references: ["../draft/feature-x/"]
related_issues: []
related_prs: []
---

## Overview
Brief description of the feature.

## Scope
- Features to implement
- Impact areas

## Non-Goals
- Out of scope items

## Requirements
- **Functional**: Feature requirements
- **Non-Functional**: Performance, security, etc.

## Tasks
Implementation task breakdown.

## Test Plan
Testing strategy and verification points.

## Deployment / Rollout
Deployment procedures and rollback strategy.
```

**Key Points**:
- Must include Scope, Non-Goals, Requirements
- Define Test Plan and Rollback strategy
- Link related issues/PRs in front-matter

### 4. Create Intent (ADR-style)

**Location**: `_docs/intent/(feature-name)/decision.md`

Record design decisions and rationale:

```markdown
---
title: "Feature X Design Decision"
status: active
draft_status: n/a
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
references: ["../../plan/feature-x/plan.md"]
related_issues: []
related_prs: []
---

## Context
Background and problem statement.

## Decision
The chosen approach.

## Consequences
Impact of this decision.

## Alternatives Considered
Other options and why they were rejected.
```

**Key Points**:
- Focus on "why" not "what"
- Reference the plan document
- Record trade-offs explicitly

## Document Hierarchy Rules

### Naming Convention
Directory name `(対象)` must match TODO.md **Area** field:
- If renaming directory, update TODO.md Area simultaneously
- Use kebab-case for multi-word names

### Status Transitions

| From | To | Condition |
|------|-----|-----------|
| draft/ | plan/ | Scope and requirements are clear |
| plan/ | intent/ | Design decisions are finalized |
| intent/ | archives/ | Approved and implementation complete |
| draft/ | survey/ | Research findings need formalization |
| survey/ | plan/ | Research complete, ready to plan |

### Stale Management
- Drafts: 30-day TTL from `updated_at`
- Extensions: Add `stale_exempt_until`, `stale_exempt_reason`, `stale_extensions`
- Never archive draft/plan/survey without intent approval

## Integration with Implementation

1. **Before coding**: Have draft/ or plan/ ready
2. **During implementation**: Update documents as decisions change
3. **After implementation**: Use **docs-cleanup** skill to finalize

## Deliverables

Before starting implementation:
- [ ] Draft notes in `_docs/draft/(feature)/` (exploring phase)
- [ ] Plan document in `_docs/plan/(feature)/` (if Size >= M)
- [ ] Intent document in `_docs/intent/(feature)/` (if design decisions needed)
- [ ] All documents linked in TODO.md references
- [ ] Front-matter complete with dates and relationships

## References

- `_docs/standards/documentation_guidelines.md` - Full documentation guidelines
- `_docs/standards/documentation_operations.md` - Operations and lifecycle rules
