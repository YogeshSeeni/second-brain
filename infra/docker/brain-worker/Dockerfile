# brain-worker:v1 — ARM64 sandbox image for per-run claude -p execution.
# Built for linux/arm64 (t4g.large host). See ADR 0001 + 0005.

FROM python:3.12-slim-bookworm

# System deps: git (reconciler reads the repo inside the sandbox for some
# job prompts), curl (local policy proxy calls in W2), ca-certs.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the Anthropic Claude CLI. Version pinned; update deliberately.
ENV CLAUDE_VERSION=1.0.0
RUN curl -fsSL "https://claude.ai/install.sh" | bash -s -- --yes \
    && /root/.local/bin/claude --version \
    && cp /root/.local/bin/claude /usr/local/bin/claude

# Python deps needed inside the sandbox (none for W1 beyond the Claude CLI).
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY run-agent.sh /usr/local/bin/run-agent.sh
RUN chmod +x /usr/local/bin/run-agent.sh

# The worktree is bind-mounted at /workspace; scratch at /scratch.
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/run-agent.sh"]
