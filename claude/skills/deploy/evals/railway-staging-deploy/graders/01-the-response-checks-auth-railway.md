---
type: llm
focus: trace
weight: 1
---

The response checks auth (`railway whoami` or `railway status`) before deploying and never runs `railway login`
