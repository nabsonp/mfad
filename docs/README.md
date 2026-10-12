# DAMFE documentation

| | |
|---|---|
| [decisions.md](decisions.md) | every design decision and why, including the ones that were reversed |
| [requirements.md](requirements.md) | the user stories, done and pending |
| [catalogue.md](catalogue.md) | the anti-pattern catalogue the rules implement |
| [metamodel.mmd](metamodel.mmd) | the conceptual metamodel: what the tool models, without its own plumbing |
| [domain-model.mmd](domain-model.mmd) | the domain classes as the code has them today |
| [extraction/common.md](extraction/common.md) | navigation, external calls, global state and communication — the rules every technology gets for free |
| [extraction/single-spa.md](extraction/single-spa.md) | discovery, composition and screens under single-spa |
| [extraction/module-federation.md](extraction/module-federation.md) | discovery, composition and screens under Module Federation |
| [extraction/angular-router.md](extraction/angular-router.md) | screens declared through the Angular Router, read by both reconstructors |

Two axes live in `extraction/`. **Integration** — single-spa, Module Federation — says how units become a system. **Routing** — Angular Router, and React Router still inside each reconstructor — says how one unit declares its screens. Any combination exists, so a routing document is used by every integration document.

Start with `architecture.md` to change the tool, with `extraction/` to check what it reads, and with `decisions.md` before reversing anything.
