---
name: docs-cleanup
description: Use after completing large implementations to finalize documentation, archive temporary docs, and update guide/reference following the _docs/ lifecycle rules.
---

# Documentation Cleanup

This skill focuses on finalizing documentation after large implementations, following the project's documentation protocol and archive rules.

## When to Use

Use this skill for **large changes (Size >= M)** or when documentation was created during implementation:
- Features with draft/plan/intent documents
- Breaking changes with migration documentation
- Architecture decisions recorded in intent/
- Research findings in survey/

For small changes (Size < M), use **post-implementation** alone and skip this skill.

## Documentation Cleanup Workflow

### 1. Review Documentation State

Check what documentation exists:

```
_docs/
├── draft/(feature)/          # May exist from pre-implementation
├── plan/(feature)/           # Should exist for Size >= M
├── intent/(feature)/         # Should exist for design decisions
├── survey/(feature)/         # May exist for research-heavy features
├── guide/(feature)/          # Need to create for implemented features
└── reference/(feature)/      # Need to create for API docs
```

### 2. Update or Create Guide Documentation

**Location**: `_docs/guide/(feature-name)/`

Create user-facing documentation:

```markdown
---
title: "Feature X Usage Guide"
status: active
draft_status: n/a
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
references: ["../../intent/feature-x/decision.md"]
related_issues: []
related_prs: []
---

## Overview
What this feature does and when to use it.

## Quick Start
Basic usage examples.

## Configuration
How to configure the feature.

## Best Practices
Project-specific recommendations.

## Troubleshooting
Common issues and solutions.
```

**Key Points**:
- Focus on "how to use" not "how it works"
- Link to reference/ for detailed specs
- Include practical examples

### 3. Update or Create Reference Documentation

**Location**: `_docs/reference/(feature-name)/`

Create API/technical documentation:

```markdown
---
title: "Feature X API Reference"
status: active
draft_status: n/a
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
references: ["../../guide/feature-x/usage.md"]
related_issues: []
related_prs: []
---

## API Overview
High-level API description.

## Classes/Methods
Detailed specifications:
- Parameters
- Return values
- Exceptions

## Data Models
Schema definitions.

## Examples
Code examples with explanations.
```

**Key Points**:
- Dictionary-style reference
- Only document implemented features
- Link to guide/ for usage examples

### 4. Archive Temporary Documents

**Important**: Follow the strict archive rules:

#### Archive Checklist
- [ ] Intent document is **approved/merged**
- [ ] Archive target has valid front-matter
- [ ] Source directory cleanup completed
- [ ] References updated in intent document

#### Archive Process

1. **Verify intent approval**
   - Check PR status
   - Link to approved intent in PR description

2. **Move to archives**
   ```bash
   # Move draft, plan, survey (if intent is approved)
   _docs/draft/(feature)/     → _docs/archives/draft-(feature)/
   _docs/plan/(feature)/      → _docs/archives/plan-(feature)/
   _docs/survey/(feature)/    → _docs/archives/survey-(feature)/
   ```

3. **Keep front-matter intact**
   - Preserve all metadata
   - Update `status: superseded` if applicable

4. **Clean up source directories**
   - Remove from original locations
   - No duplicates allowed

5. **Update references**
   ```markdown
   # In intent document, add:
   references: [
     "../../archives/draft-feature-x/",
     "../../archives/plan-feature-x/"
   ]
   ```

#### Forbidden Actions
- ❌ Archive draft/plan/survey without intent approval
- ❌ Keep originals after archiving
- ❌ Archive without updating references

### 5. Update TODO.md

- Mark documentation tasks as completed
- Add links to created/updated documents
- Note any follow-up documentation debt

### 6. Final Verification

Run documentation checks:

```bash
# If available, run linting
npm run lint:docs

# Verify all links
npm run check-links

# Validate front-matter
npm run validate-frontmatter
```

## Document Type-Specific Cleanup

### Draft Cleanup
- Review content for value
- Either: Archive (if intent approved) or Delete (if obsolete)
- Update `updated_at` if keeping for future reference

### Plan Cleanup
- Ensure plan matches final implementation
- Mark `status: superseded` if outdated
- Move to archives after intent approval

### Intent Cleanup
- Verify all design decisions are recorded
- Add consequences and lessons learned
- Keep active (don't archive intent documents)

### Survey Cleanup
- Archive after research is incorporated
- Link from intent or plan documents
- Mark `status: superseded` when no longer needed

## Lifecycle Summary

```
Implementation Complete
        ↓
   [Create/Update]
   guide/(feature)/
   reference/(feature)/
        ↓
   [Verify Intent]
   Is intent approved?
        ↓
    Yes      No
     ↓        ↓
   [Archive]  [Keep/Update]
   draft/     draft/plan/
   plan/      until approved
   survey/
        ↓
   [Finalize]
   Update TODO.md
   Run validation
```

## Deliverables

After implementation:
- [ ] Guide document created/updated in `_docs/guide/(feature)/`
- [ ] Reference document created/updated in `_docs/reference/(feature)/`
- [ ] Temporary documents archived (if intent approved)
- [ ] Source directories cleaned up
- [ ] References cross-linked between documents
- [ ] TODO.md updated with document links
- [ ] Validation passed (lint, links, front-matter)

## Integration with Post-Implementation

Use both skills together:
1. **post-implementation**: Update TODO.md, communicate changes
2. **docs-cleanup**: Finalize documentation hierarchy and archives

## References

- `_docs/standards/documentation_guidelines.md` - Full documentation guidelines
- `_docs/standards/documentation_operations.md` - Archive rules and lifecycle
- `.codex/skills/docs-prep/SKILL.md` - Pre-implementation documentation
