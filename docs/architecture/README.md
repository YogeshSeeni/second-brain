# Architecture — brain-v1

Entry point for developers onboarding to the brain-v1 codebase.

**Start here, then read in this order:**

1. [../design/brain-v1.md](../design/brain-v1.md) — the canonical design doc (spec)
2. [modules.md](modules.md) — living module map: what lives where and why
3. [decisions/](decisions/) — every material technical choice, one ADR per decision

## Top-level layout

```
apps/brain-core/     FastAPI orchestrator (Python 3.12)
apps/brain-web/      Next.js 16 + Tailwind v4 control panel
bench/               benchmark harness + weekly reports
docs/architecture/   this directory — the map
docs/design/         design docs (mirror of docs/superpowers/specs/)
infra/terraform/     AWS resources
infra/ec2/           cloud-init + systemd units + cron
infra/docker/        container images
jobs/                job prompts (markdown)
wiki/                LLM-maintained knowledge base
raw/                 immutable ingested sources
```

## How to add a feature

1. Read the design doc section covering the area
2. Read the relevant ADR(s) in `decisions/`
3. Find the module in `modules.md`; open its file
4. If the change introduces a new material decision, write a new dated ADR
5. Update `modules.md` if boundaries changed
