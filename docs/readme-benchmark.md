# README benchmark: local agent operations patterns

Ten high-traction GitHub repositories were sampled for README patterns that can
inform a generic, local agent-operations and configuration-auditing toolkit.
Traction is a discovery signal, not a security or suitability endorsement.

**Method.** Counts are GitHub REST API values retrieved on **2026-11-04**;
README observations are paraphrases of the linked repository README at that
time. Sources below are first-party GitHub repository pages and GitHub API
endpoints only.

| Repository | Observable traction | Relevant README pattern to borrow | Sources |
| --- | ---: | --- | --- |
| [openai/codex](https://github.com/openai/codex) | 133,104 stars; 21,075 forks | Keep the front page short: separate install paths and route deeper operational material to a documentation hub. | [README](https://github.com/openai/codex/blob/main/README.md) · [API snapshot](https://api.github.com/repos/openai/codex) |
| [anthropics/claude-code](https://github.com/anthropics/claude-code) | 154,499 stars; 25,561 forks | Expose an extension/plugin boundary and make data handling, session retention, and privacy safeguards visible at top level. | [README](https://github.com/anthropics/claude-code/blob/main/README.md) · [API snapshot](https://api.github.com/repos/anthropics/claude-code) |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | 30,491 stars; 4,983 forks | Document the agent contract as instructions, tools, guardrails, and handoffs; pair it with human review, sessions, and tracing. | [README](https://github.com/openai/openai-agents-python/blob/main/README.md) · [API snapshot](https://api.github.com/repos/openai/openai-agents-python) |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 44,448 stars; 7,644 forks | Treat human oversight, persistent/working memory, and execution tracing as first-class operational surfaces. | [README](https://github.com/langchain-ai/langgraph/blob/main/README.md) · [API snapshot](https://api.github.com/repos/langchain-ai/langgraph) |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 60,484 stars; 9,033 forks | Make agent, task, tool, model, memory, guardrail, and human-review settings inspectable; distinguish project definitions from a control plane's observability and governance. | [README](https://github.com/crewAIInc/crewAI/blob/main/README.md) · [API snapshot](https://api.github.com/repos/crewAIInc/crewAI) |
| [microsoft/autogen](https://github.com/microsoft/autogen) | 61,699 stars; 9,361 forks | Flag lifecycle state prominently and warn that MCP integrations can execute local commands or expose sensitive data; an auditor should inventory and trust-gate them. | [README](https://github.com/microsoft/autogen/blob/main/README.md) · [API snapshot](https://api.github.com/repos/microsoft/autogen) |
| [microsoft/semantic-kernel](https://github.com/microsoft/semantic-kernel) | 28,731 stars; 4,851 forks | Present plugins, prompt/template settings, provider environment variables, structured output, and observability/security as separate configuration concerns. | [README](https://github.com/microsoft/semantic-kernel/blob/main/README.md) · [API snapshot](https://api.github.com/repos/microsoft/semantic-kernel) |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 91,784 stars; 11,907 forks | Label reference versus production status; enumerate tool classes and require configurable access controls for local resources such as the filesystem. | [README](https://github.com/modelcontextprotocol/servers/blob/main/README.md) · [API snapshot](https://api.github.com/repos/modelcontextprotocol/servers) |
| [Aider-AI/aider](https://github.com/Aider-AI/aider) | 49,939 stars; 5,134 forks | Connect local-agent actions to existing Git review/undo workflows, and give configuration its own discoverable entry point. | [README](https://github.com/Aider-AI/aider/blob/main/README.md) · [API snapshot](https://api.github.com/repos/Aider-AI/aider) |
| [aaif-goose/goose](https://github.com/aaif-goose/goose) | 56,212 stars; 6,558 forks | Audit provider selection, credential source, and MCP extensions independently; support a preconfigured distribution as a reviewable deployment unit. | [README](https://github.com/aaif-goose/goose/blob/main/README.md) · [API snapshot](https://api.github.com/repos/aaif-goose/goose) |

## Synthesis for this toolkit

The smallest useful manifest/audit model is:

1. **Identity and model:** agent role, provider, endpoint, model, and how credentials are referenced—never their values.
2. **Capabilities:** tools, plugins, MCP servers, filesystem or command scope, and an explicit trusted/untrusted classification.
3. **Controls:** destructive-action approvals, input/output guardrails, and human-review gates.
4. **State and evidence:** session/memory locations and retention, plus tracing/logging configuration and Git change-review expectations.
5. **Deployment posture:** local/reference/production designation, configuration source, and an explicit warning when a configuration is unsuitable to share.

This supports a static audit without adding remote control, secret collection, or runtime monitoring.
