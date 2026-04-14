# Architecture Decision Records

Numbered, dated, durable. One ADR per material choice.

## Format

Every ADR uses this template:

```
# NNNN — <slug>

**Status:** Proposed | Accepted | Superseded-by-NNNN
**Date:** YYYY-MM-DD
**Deciders:** <who>

## Context
<what forced the decision>

## Decision
<what we chose, in one paragraph>

## Alternatives considered
- <option>: <why not>

## Consequences
### Positive
- ...
### Negative
- ...
### Neutral
- ...
```

## What gets an ADR

- Algorithm switches, new dependencies, data-flow changes, trust-boundary changes, runtime choices, cost tradeoffs, retry/timeout policies, protocol choices

## What does not

- Bug fixes, refactors, renames, test additions, dependency version bumps, typo fixes — these go in commit messages
