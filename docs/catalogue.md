# Anti-pattern catalogue — feasibility and specification

Triage of the 27 anti-patterns in the [micro frontends anti-pattern
catalogue](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/)
(ICOMP/UFAM) against what MFAD can observe through static analysis,
with the input, detection and output specification of each one.

| band | meaning | count |
|---|---|---|
| **A** | already implemented | 8 |
| **B** | feasible with the artefacts that already exist | 5 |
| **C** | needs new extraction | 11 |
| **D** | out of reach of static code analysis | 3 |

## The available artefacts

The *Input* column of each rule refers to these:

| artefact | fields |
|---|---|
| `MicroFrontend` | id, directory, entrypoint, routes, role, screens, fragments, size |
| `Screen` | component, route, file, line |
| `Fragment` | name, file, line |
| `Composition` | consumer, provider, fragment, import location, instantiation locations, props |
| `Navigation` | source, target, expression, resolved URL, confidence |
| `Communication` | source, target, mechanism, channel, locations on both sides |
| `ApiCall` | micro frontend, method, path, client |
| `StateAccess` | micro frontend, library, path of the slice read |
| `AntiPattern` | name, description, category and reference of an entry in this catalogue |

The anti-pattern and its occurrence are distinct entities. `AntiPattern`
is the entry in this catalogue — it exists whether or not it has been
found in any system; the `Rule` is how to look for it in the artefacts,
and the same entry admits more than one operationalization.

Every detection returns an `AntiPatternDetection`, with the anti-pattern,
dimension, explanation, message, elements involved, code locations and
metadata specific to the rule. The *Output* column describes what is
specific to each one.

---

# A — already implemented

## [Cyclic Dependency](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Cyclic%20Dependency)
> Two or more MFEs depend on each other, directly or indirectly.

| | |
|---|---|
| **Input** | `Composition` (with `RenderLocation.screens` and `.fragments`), `Communication` (with `produced_on` and `consumed_on`) |
| **Detection** | For each screen, gathers the fragments mounted on it — the ones it renders and, at any depth, the ones those render. Builds a directed graph per relation **and per screen**: it includes the instantiations reached by the screen, and the communication whose two ends are both live on it. Enumerates the elementary cycles of each graph. Capped at 200 distinct cycles per relation, because enumeration grows with the number of cycles, not with the size of the graph. |
| **Output** | One occurrence per cycle, merging the screens on which it appears. `dimension` says which relation produced it; `chain` holds the ordered sequence; `through` lists what goes through each edge — fragments or channels; `screens`, the screens. |

Composition and communication are evaluated separately because a cycle
means different things in each: composition is build coupling;
communication is contract coupling.

The per-screen cut exists because, in the graph of the whole system,
edges that never coexist get chained together — the composition of one
screen with that of another — and in a large system the number of cycles
explodes without any of them actually being mounted. Navigation was left
out for the same reason: it links one screen to another, and going back
and forth between screens is product flow.

Micro frontends mounted side by side by the orchestrator, without the
screen rendering them, are not on the screen — and a unit without a
`<Route>` has no screen at all.

## [Hub-like Dependency](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Hub-like%20Dependency)
> A screen of one MFE integrates fragments from several other MFEs.

| | |
|---|---|
| **Input** | `MicroFrontend.screens`, `Composition.renders` |
| **Detection** | Groups fragment instantiations by screen, using the screens recorded by the render site. Flags a screen when it instantiates `min_fragments` fragments. Default 5. |
| **Output** | One occurrence per screen. Metadata: screen, providers, instantiated fragments. |

The signal is the number of **distinct fragments**, not of providers
nor of instantiations: it is the number of pieces the screen has to
assemble that makes it a convergence point, and five fragments from a
single provider concentrate as much contract change as five from five.
The same card repeated in a list is one piece.

Counting distinct providers, as was done before, penalized normal
design: with a shared component library, any screen that used one of
its components plus any fragment already added up to two providers.

The fragment↔screen link is no longer by file: the render site records
which screens it appears on, following relative imports from the
screen's component. A fragment instantiated in a helper component is
attributed correctly, and when the fragment is the route component
itself, the screen is that one and only that one.

## [Hammering APIs](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Hammering%20APIs)
> Several MFEs call the same endpoint independently.

| | |
|---|---|
| **Input** | `ApiCall` |
| **Detection** | Groups calls by **path**, not by path plus method: one MFE that reads and another that writes the same resource share the same contract. Flags from `min_callers` consumers. Default 2. |
| **Output** | One occurrence per shared route. Metadata: route, observed methods, consumers. |

## [Global state communication](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Global%20state%20communication)
> Shared state violates segregation and increases coupling.

| | |
|---|---|
| **Input** | `StateAccess` |
| **Detection** | Groups who accesses each slice — library and path together — and checks whether any is accessed by `min_microfrontends` or more. Default 2. Includes `localStorage` and `sessionStorage` keys. |
| **Output** | A **single, binary** occurrence — the system either uses global state as a channel or it does not. Metadata: the shared slices with who accesses each one, and the libraries involved. |

One per slice would say the same thing several times. What matters is
whether the practice exists and who takes part.

## [One Micro Frontend for all](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/One%20Micro%20Frontend%20for%20all)
> A single MFE is created and imported by all the others.

| | |
|---|---|
| **Input** | `Composition`, `Navigation`, `Communication` (directed ones only) |
| **Detection** | Counts the distinct neighbours of each MFE, summed over the relations, and flags whoever reaches `ratio` of the others. Excludes the orchestrator from the computation and abstains below `min_microfrontends`. Defaults 0.9 and 5. |
| **Output** | One occurrence per MFE. Metadata: coverage, neighbours, and the split between what it depends on and what depends on it. |

**Divergence to resolve.** The catalogue specifically describes
*imported by all* — in-degree. The current implementation counts
**undirected** neighbourhood, which also flags the MFE that depends on
all the others. These are distinct problems: one is a shared bottleneck,
the other knows too much about the system. Both go into the metadata,
but the rule should either restrict itself to in-degree, to adhere to
the catalogue, or state explicitly that it widens the definition.

The orchestrator is excluded because reaching everyone is its job, and
keeping it in the computation would inflate the degree of all the
others. The size floor exists because in a small system being connected
to everyone is the norm, not the deviation. Symmetric communication
(global state) does not count: it connects everyone who touches the
slice to everyone, with no centre, and is already flagged by
`global-state-communication`.

## [Mega Frontend](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Mega%20Frontend)
> One MFE takes on several responsibilities that should be separate.

| | |
|---|---|
| **Input** | `MicroFrontend.screens`, `.fragments`, `.size` |
| **Detection** | Screens **and** lines of code above the **upper Tukey fence** (`Q3 + 1.5 × IQR`) of the system's own distribution, with the orchestrator left out. |
| **Output** | One occurrence per micro frontend, with the three counts, the fences it exceeded and the medians it was compared against. |

**The cut is Tukey's fence, not a multiple of the median.** The
previous values — `2.0` for mega and `0.4` for nano — were chosen for
symmetry with each other, and never had an empirical origin. The fence
has a name, a reference and a property that a multiple of the median
does not: on a homogeneous set it flags nobody, instead of flagging a
fixed fraction as P25 and P75 would.

Two design consequences. The rule **abstains with fewer than 8
units**, because with four points interpolation invents fractional
values over a sample of integers and the quartile becomes fiction.
And the comparison is **strict**: when the IQR is zero both fences
collapse onto the same point, and then only units that deviate from it
are flagged — which is consistent, because with zero dispersion any
difference is infinitely many IQRs away.

Without a domain map there is no way to state WHICH responsibilities
the unit accumulates, so v0 measures the observable consequence: it
grew far above its peers. It is evidence, not proof — a large, cohesive
micro frontend is not a Mega Frontend —, and that is why the output
carries the medians, so that the reader can disagree.

Both measures are required together. Many screens and little code is a
menu; a lot of code and one screen is a library.

## [Nano Frontend](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Nano%20Frontend)
> An MFE created with only a few screens or fragments.

| | |
|---|---|
| **Input** | `MicroFrontend.screens`, `.fragments`, `.size` |
| **Detection** | Screens plus fragments below the **absolute floor** `floor` **or** the **lower Tukey fence** (`Q1 - 1.5 × IQR`), **and** lines of code below the system median. The orchestrator is left out. |
| **Output** | One occurrence per micro frontend, with the counts and the medians it was compared against. |

Screens and fragments are summed because both ways of delivering an
interface count: a unit with no screen that publishes many fragments is
not nano.

**The floor exists because relative comparison is blind in a uniform
system.** In a public seven-unit Vite system every unit has one screen
and one fragment: the median follows along, and none would be flagged,
by construction. The premise of the floor is that below it the unit is
too small to be a micro frontend, regardless of its neighbours.

**The value of `floor` is a declared choice, not a measurement.** At
`5`, it flagged **9 of the 10 units** of the two reference systems —
all of that system and three of the four units of `nabstore`. Since it
is combined with the relative criterion by OR, it dominates whenever it
is looser than the median.

**That is why the count does not decide alone.** Screens and fragments
say where the unit is seen from, not how much it does: an Angular
application with two routes and dozens of tabs has few screens and is
among the largest in the system — in udistrital, the largest unit by
code was flagged as nano. The unit must also have less code than the
median of its peers. It is the double requirement of `mega-frontend`,
from the opposite side, and it uses no new number: the median is the
system's own.

The rule assumes that **everything it receives is a micro frontend**.
Telling a library apart from a unit is the decision of whoever points
the tool, and does not belong here: the remedy for nano is to absorb the
unit into another, the remedy for a library is not to count it.

A unit whose entrypoint did not resolve is left out of both criteria.
Extraction that could not read it returns zero for everything, and
flagging that would be calling a read failure an anti-pattern.

Evidence, not a verdict. A small micro frontend is legitimate when it
alone constitutes a whole capability, and the rule cannot tell that
case apart — which is why the output says what the unit was compared
against.

## [Micro Frontends Greedy](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Micro%20Frontends%20Greedy)
> Explosion in the number of MFEs.

| | |
|---|---|
| **Input** | `MicroFrontend` (count and sizes) |
| **Detection** | Ratio between the number of MFEs and the median size of each. Flags a system with many small MFEs. |
| **Output** | A single occurrence, about the system. Metadata: count, median, size distribution. |

Overlaps with `Nano Frontend` — one looks at the unit, the other at the
system. Implement both only if the distinction is defended in the text.

## [Knot Micro Frontend](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Knot%20Micro%20Frontend)
> Three or more MFEs communicate directly through specific interfaces.

| | |
|---|---|
| **Input** | `Communication`, `Composition` |
| **Detection** | Looks for cliques of three or more nodes — sets in which everyone communicates with everyone. `networkx.find_cliques` solves it. |
| **Output** | One occurrence per clique. Metadata: the MFEs in the knot and the channels or fragments that connect them. |

## [Bidirectional Data Flow](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Bidirectional%20Data%20Flow)
> Bidirectional communication between the host application and the remote MFEs.

| | |
|---|---|
| **Input** | `MicroFrontend.role`, `Communication`, `Composition`, `Navigation` |
| **Detection** | The `shell` role already identifies the host. Flags a pair with edges in both directions involving the shell, in any relation. |
| **Output** | One occurrence per pair. Metadata: the relations in each direction. |

## [Chatty Micro Frontends](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Chatty%20Micro%20Frontends)
> Excessive communication between fragments, broadcasting an event on every action.

| | |
|---|---|
| **Input** | `Communication` |
| **Detection** | Counts publication points per pair of MFEs and flags above a threshold. |
| **Output** | One occurrence per pair. Metadata: channels, count of publication points. |

**Caveat about its nature.** The catalogue describes **execution
frequency**; static analysis sees **points in the code**. A `publish`
inside a loop counts as one. It is a weak proxy, and the rule should not
be published without this caveat attached — otherwise it promises to
measure something it does not.

## [Spaghetti Architecture](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Spaghetti%20Architecture)
> MFEs structured in a disorganized way, with tangled dependencies.

| | |
|---|---|
| **Input** | all edges |
| **Detection** | Graph metrics: density, strongly connected components, absence of a layered structure. |
| **Output** | A single occurrence, about the system. Metadata: the computed metrics. |

The concept is diffuse. The rule is worth whatever the chosen
operationalization is worth, and that choice must be justified in the
text.


---

# C — needs new extraction

Ordered by increasing effort.

## [No CI&CD](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/No%20CI%26CD)
> No automated integration and delivery pipeline.

| | |
|---|---|
| **New extraction** | Presence of `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml` per MFE |
| **Input** | the extraction above |
| **Detection** | Absence of all of these files, per MFE and in the repository. |
| **Output** | One occurrence per MFE without a pipeline, or a single one if none has any. |

This is not code analysis, it is repository inspection. `SourceTree`
already walks the tree.

## [No Versioning](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/No%20Versioning)
> The MFEs are not versioned.

| | |
|---|---|
| **New extraction** | The `version` field of `package.json`; presence of git tags |
| **Input** | the extraction above |
| **Detection** | Flags an MFE without `version`, or with a fixed version that never changes in the history. |
| **Output** | One occurrence per MFE. |

## [Framework Frenzy](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Framework%20Frenzy) · [Golden Hammer](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Golden%20Hammer)
> Several frameworks with no real need · all with the same technology,
> even when it does not fit.

| | |
|---|---|
| **New extraction** | Dependencies declared in each MFE's `package.json`, classified by family: react, vue, angular, svelte |
| **Input** | the extraction above |
| **Detection** | `Framework Frenzy`: more than N families in the system. `Golden Hammer`: a single one, in all of them. |
| **Output** | A single occurrence in each case. Metadata: the family of each MFE. |

They are the same data read in opposite directions. **Golden Hammer is
the most delicate in the catalogue**: homogeneity is a problem only when
some unit needed a different technology — and the code does not say
that. The detection identifies homogeneity, not unsuitability.

## [Dependency hell](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Dependency%20hell)
> MFEs share external libraries without consistent version management.

| | |
|---|---|
| **New extraction** | Dependencies and version ranges per MFE |
| **Input** | the extraction above |
| **Detection** | The same library with incompatible ranges across MFEs. |
| **Output** | One occurrence per divergent library. Metadata: the ranges and who declares each one. |

**One manifest extraction solves four rules** — this one,
`Framework Frenzy`, `Golden Hammer` and `No Versioning`. It is the best
return on effort of the whole C band, and it opens the *Development*
category, which today has no coverage at all.

## [Avoiding observability](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Avoiding%20observability)
> No observability implemented.

| | |
|---|---|
| **New extraction** | Imports of observability libraries — Sentry, Datadog, OpenTelemetry, LogRocket — per MFE |
| **Input** | the extraction above |
| **Detection** | Absence of signal in one or in all MFEs. |
| **Output** | One occurrence per MFE without signal. |

Same technique as the HTTP client catalogue: recognition by the import
specifier.

An **absence** rule, which is more fragile than a presence rule: not
finding it may mean instrumentation in a shared package. The output must
say "no signal found", not "does not exist".

## [Lack of Skeleton](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Lack%20of%20Skeleton)
> There is no standard skeleton or boilerplate for creating new MFEs.

| | |
|---|---|
| **New extraction** | Directory structure and configuration files of each MFE |
| **Input** | the extraction above |
| **Detection** | Structural similarity between the MFEs. Projects generated from the same skeleton look alike. |
| **Output** | A single occurrence. Metadata: the similarity matrix. |

Delicate operationalization: low similarity may mean absence of a
skeleton or legitimate divergence over time.

## [Dependent deployment](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Dependent%20deployment)
> MFEs so coupled that deployment requires coordination between teams.

| | |
|---|---|
| **New extraction** | Release signals: versions pinned between MFEs, a pipeline that publishes several together |
| **Input** | existing coupling + the extraction above |
| **Detection** | Strong coupling between MFEs combined with a joint-release signal. |
| **Output** | One occurrence per group that has to be deployed together. |

Without the release extraction, it can be treated as a **composite**
rule over the existing detections — but then it has to be named as an
inferred risk, not as an observed fact.

## [Partial UI Migration](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Partial%20UI%20Migration)
> Extracting part of the UI into an MFE and re-embedding it in the legacy monolith.

| | |
|---|---|
| **New extraction** | Identification of the monolith and of the embedding direction |
| **Input** | the extraction above + `Composition` |
| **Detection** | An MFE whose fragment is instantiated back inside the legacy application. |
| **Output** | One occurrence per re-embedded fragment. |

Recognizing an application **as legacy** requires a signal the code
does not give on its own. It probably needs a declaration from the user.

## [Unmediated Legacy Integration](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Unmediated%20Legacy%20Integration)
> Integrating a legacy system without proper isolation.

Same difficulty as the previous one, made worse: it requires identifying
the legacy system **and** assessing the quality of the isolation. It is
the furthest away in band C.

## [Distributed Data Inconsistency](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Distributed%20Data%20Inconsistency)
> Data replicated across MFEs without change propagation.

| | |
|---|---|
| **New extraction** | Data models defined in each MFE — type or object shapes |
| **Input** | the extraction above |
| **Detection** | Equivalent models defined in more than one MFE. |
| **Output** | One occurrence per duplicated model. |

A much heavier analysis than anything that exists today, and with a
high false-positive rate — two MFEs may legitimately have similar types.
**I would leave it out of scope.**

---

# D — out of reach

These are not properties of the code. No static analysis of source code
determines them, and approximating them would produce a number with no
meaning.

## [Common Ownership](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Common%20Ownership)
> A single team manages all the MFEs.

Organizational structure. An approximation is possible — `CODEOWNERS` and
authorship in the git history —, but that is repository metadata, not
code, and it measures **who committed**, not who owns.

If it were included, it would be a declared scope extension: repository
analysis, not code analysis.

## [Dismissing human factors](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Dismissing%20human%20factors)
> Teams pursue technical goals without considering well-being and morale.

Not detectable by any automatic means.

## [Micro Frontend as the goal](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Micro%20Frontend%20as%20the%20goal)
> Adopting the MFE architecture in an unsuitable context.

Requires judging whether the context justified the decision —
information that is not in the artefact. `Nano Frontend` and
`Micro Frontends Greedy` capture related symptoms, but not the cause.

---

# Summary for the scope

**Current coverage:** 8 of 27. The Intra-frontend category is almost
closed: `Micro Frontends Greedy` is missing alongside
the two already implemented.

**Reach without new extraction:** 13 of 27 — almost half the catalogue.

**Best return on effort:** the manifest extraction — dependencies and
versions per MFE — enables four rules at once and opens the
*Development* category, which today has no coverage.

**Smallest remaining effort:** `Micro Frontends Greedy` is the
system-level reading of what `nano-frontend` does per unit. It depends
on a notion of business capability, which v0 does not have.

**Realistic ceiling:** 24 of 27. Three are about people and process, and
stating that explicitly is a result: it delimits what static code
analysis can claim about architecture.

| category | total | A | B | C | D |
|---|---|---|---|---|---|
| Inter-frontend | 15 | 6 | 4 | 5 | 0 |
| Intra-frontend | 3 | 2 | 1 | 0 | 0 |
| Operations | 4 | 0 | 0 | 4 | 0 |
| Development | 5 | 0 | 0 | 2 | 3 |

## Three rules that require a methodological statement

These measure concepts that **are not in the artefact**. Implementing
them is possible; publishing them without stating the
operationalization is not.

| rule | what the catalogue describes | what can be observed |
|---|---|---|
| `Chatty Micro Frontends` | execution frequency | publication points in the code |
| `Golden Hammer` | technology unsuited to the need | technological homogeneity |

In all of them, the detection identifies the observable symptom, not
the described cause. The distance between the two is a threat to
validity, and it is worth stating.
