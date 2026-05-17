<!--
Vendored from mattpocock/skills @ e74f0061bb67222181640effa98c675bdb2fdaa7
Upstream path: skills/engineering/tdd/deep-modules.md
License: MIT — Copyright (c) 2026 Matt Pocock
Source: https://github.com/mattpocock/skills/blob/e74f0061bb67222181640effa98c675bdb2fdaa7/skills/engineering/tdd/deep-modules.md
Do not edit in place — re-vendor from upstream and bump the SHA.
-->

# Deep Modules

From "A Philosophy of Software Design":

**Deep module** = small interface + lots of implementation

```
┌─────────────────────┐
│   Small Interface   │  ← Few methods, simple params
├─────────────────────┤
│                     │
│                     │
│  Deep Implementation│  ← Complex logic hidden
│                     │
│                     │
└─────────────────────┘
```

**Shallow module** = large interface + little implementation (avoid)

```
┌─────────────────────────────────┐
│       Large Interface           │  ← Many methods, complex params
├─────────────────────────────────┤
│  Thin Implementation            │  ← Just passes through
└─────────────────────────────────┘
```

When designing interfaces, ask:

- Can I reduce the number of methods?
- Can I simplify the parameters?
- Can I hide more complexity inside?
