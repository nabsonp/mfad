# damfe documentation

| | |
|---|---|
| [architecture.md](architecture.md) | how the tool is put together: three modules, hexagonal, where to plug a new piece in |
| [decisions.md](decisions.md) | every design decision and why, including the ones that were reversed |
| [requirements.md](requirements.md) | the user stories, done and pending |
| [catalogue.md](catalogue.md) | the anti-pattern catalogue the rules implement |
| [extraction/single-spa.md](extraction/single-spa.md) | what the single-spa reconstructor reads, rule by rule |
| [extraction/module-federation.md](extraction/module-federation.md) | the same for Module Federation |
| [prompts/](prompts/) | portable prompts for the authoring steps — declaring communication, writing a reconstructor, mapping domains |

Start with `architecture.md` to change the tool, with `extraction/` to check what it reads, and with `decisions.md` before reversing anything.
