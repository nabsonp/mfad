# damfe — requirements

Two kinds of requirement, told in the form each one deserves.

**Behaviour requirements (RF)** say what the tool does to code and to artefacts, as *given / when / then*. Nobody is interacting in them: they hold whether the analysis was started from a terminal, from a script or from a page, and they are what a test asserts.

**User stories (US)** say what someone wants from the tool and why. There is one per command, plus one for reading the report — they document the surface a person touches, and nothing beyond it.

Behaviour numbers are carried over from the previous revision, so `RF-25` here was `US-25` there. The user stories were renumbered, because the set is no longer the same: they now follow the commands.

| status | meaning |
|---|---|
| **Done** | exists and has been exercised on a real system |
| **Partial** | exists with a recorded limitation |
| **Pending** | identified, not built |

---

# Part 1 · Behaviour

## Discovery

### RF-01 · Micro frontend inventory

> **Given** a repository
> **when** the reconstructor recognises the technology
> **then** every deployable unit is listed, each with its identity, its routes and its role.

For single-spa the units come from `registerApplication`, in both the object and the positional form; for Module Federation, from the federation declaration in each build config. A unit whose entrypoint does not resolve still appears, carrying the fields that could be determined — disappearing is worse than showing up incomplete.

**Done.**

### RF-02 · The orchestrator as a node

> **Given** the registrations of a system
> **when** the package that declares them is identified
> **then** it becomes a node with `role = "shell"`, listing the units it mounts.

One node per orchestrator, because a repository may hold more than one system. Living in the orchestrator's package does not make an application the shell: a monolith loaded by relative path from `root-config` is a registered application like any other.

**Done.**

### RF-03 · Screens and routes

> **Given** a micro frontend
> **when** any of its files declares a route
> **then** each declaration becomes a screen, with the component and the resolved route.

The route resolves through constants and one level of indirection; when it does not resolve, the original expression is kept. A screen declared in a file no import reaches is extracted all the same and marked unreachable — it exists in the code and not at runtime, and both facts matter.

**Done.**

### RF-04 · Exposed fragments

> **Given** a micro frontend's entrypoint
> **when** it exports something that is not a lifecycle, or declares `exposes`
> **then** each name is a fragment, pointing at the file that defines it.

**Done.**

### RF-05 · Fragment consumption

> **Given** the fragment catalogue of every unit
> **when** one unit imports, from another, a name in that catalogue
> **then** the consumption is recorded, with where it was imported, where it was instantiated, and in which screens it appears.

Only names in the catalogue count, so shared libraries stay out. Import aliases resolve. An import with no instantiation is recorded as such. A fragment instantiated inside a helper component is attributed through relative-import reachability, and when the fragment is itself the route's component, that screen alone is recorded.

**Done.**

### RF-06 · Navigation between micro frontends

> **Given** an expression that produces a URL
> **when** that URL belongs to another micro frontend
> **then** a navigation is recorded from the origin to the route's owner.

The detection knows no router and no navigation library: it recognises the destination, not the call. Ownership is by longest matching prefix on a segment boundary, so the shell's catch-all does not swallow every route, and `/` matches only itself. Destinations expressed as a literal, a constant, a template or a `.replace(":param", …)` resolve, each carrying whether the match is exact or a prefix. Navigation inside a single unit is not reported.

**Done.**

### RF-08 · Communication between micro frontends

> **Given** the source of a system
> **when** a platform primitive, a known bus or a declared mechanism publishes or subscribes to a channel
> **then** producer and consumer are paired by channel name.

Three tiers with one result. Platform primitives — `CustomEvent`, `BroadcastChannel`, `postMessage` — hold anywhere with no configuration. Known buses are recognised by import specifier, never by variable name. The declared mechanism covers the project's own wrapper. Without a declaration the result is not empty: the first two tiers still apply, and the absence of a declaration is reported as a distinct state from the absence of communication.

**Done.**

### RF-11 · Technology recognition

> **Given** a repository
> **when** more than one reconstructor is registered
> **then** the one that recognises it is chosen, and when none does the tool says so rather than returning an empty result.

**Done.**

## Measurement

### RF-24 · Global state reads

> **Given** an import of a known state library
> **when** a read walks a path into the state
> **then** the access is recorded, with the library and the path.

Libraries are recognised by import specifier. A selector that assembles an object counts every slice it walks. Access inside a shared package is not coupling between units and stays out. Writes are deliberately excluded: the call site names the dispatched action, not the slice it changes, and recording both would mix two vocabularies.

When two or more units read the same slice, undirected communication edges are derived between them — the coupling is real, and leaving it out of the graph made the rules that walk it undercount.

**Done.**

### RF-29 · External service calls

> **Given** the code of a micro frontend
> **when** it calls the platform's HTTP API or a recognised client
> **then** the call is recorded, with the path resolved and the screens and fragments that reach it.

`fetch` and `XMLHttpRequest` need no configuration, being platform rather than framework. Known clients are identified by import specifier, including instances built by a factory such as `axios.create()`. An empty reachability list is information: the call sits in code no screen reaches.

**Done.**

### RF-30 · Size of each unit

> **Given** the scan already under way
> **then** each unit's files and lines of code are counted, without a second read of the disk.

A comment line is identified through the syntax tree, never by text prefix, so `//` inside a string does not count, and a line with code followed by a comment is still code.

**Done.**

### RF-31 · Declared business domains

> **Given** a `.damfe/domains.yml` in the analysed repository
> **when** routes and endpoints are matched against it
> **then** each domain resolves to its members and to the units that serve it.

Routes and endpoints are separate fields, being separate vocabularies. A subdomain is a record, not a division: its routes and endpoints fold into the domain containing it, and rules operate at the top level, so the granularity chosen by whoever declares does not change the verdict. Matching is by prefix on a segment boundary, and `/` matches only the exact path.

**Done.**

## Detection

### RF-13 · Rules over artefacts

> **Given** the artefacts
> **when** the rules run
> **then** each occurrence names the elements involved and, where applicable, the places in the code.

Detection reads only the artefact model, never source. Rules can be applied in full or selected by name. Having no rules registered is reported, and not confused with having no problems.

**Done.**

### RF-14 · Dependency cycle

> **Given** the composition, navigation and communication graphs, each on its own
> **when** an elementary cycle exists in one of them
> **then** it is reported with the chain in the order it closes and the relation that produced it.

One cycle per relation rather than one per pair: importing a fragment and navigating are different couplings with different remedies. Symmetric edges are excluded — coupling through shared state has no direction, and looking for cycles in it finds one in every pair. The enumeration is capped so a dense graph cannot stall the run.

**Done.**

### RF-15 · Screen concentrating fragments

> **Given** the screens and the render sites
> **when** a screen instantiates five or more fragments
> **then** it is reported with the fragments and where they come from.

The count is of fragments, not of distinct providers: five from one provider concentrate as much contract change as five from five. Counting providers punished the normal design — with a shared component library, any screen using one of its components plus any other fragment became a hub.

**Done.**

### RF-16 · Unit connected to nearly all others

> **Given** every relation summed
> **when** one unit touches 90% or more of the others, in a system of at least five
> **then** it is reported, separating how many it depends on from how many depend on it.

Connection is counted without direction: being the centre is a problem either way. The orchestrator is excluded, reaching everything by definition. Systems below the minimum size are not assessed, because being connected to everyone is normal in them.

**Done.**

### RF-32 · Domain and unit out of alignment

> **Given** the screens, the API calls and the declared domain map
> **when** a unit serves more than one domain, or covers part of a domain another unit dominates, or calls services from more than one domain
> **then** it is reported, naming **which screens differ and where they would go**.

Size is not the condition: it disambiguates which of the two is the fragment, and corroborates the evidence. Without a declared map the rules fall back to size relative to the system median and say which criterion they used. A unit whose screens fall in no domain is undetermined and the rule abstains. When the median is zero the rules abstain too: a zero median means nothing was measured, not that everything is small.

**Done.**

---

# Part 2 · User stories

One per command. Each says who runs it, what they want and why, followed by what the command does today.

### US-01 · `damfe analyze`

> As an **analyst**, I want one command that takes a repository and gives me the report, so that I need not learn how the stages fit together.

Runs reconstruction, detection and visualisation in one pass, writing the artefacts, the detections and `architecture.html` into `artifacts/`. Takes `--prefix` to restrict the analysis to one organisation, `--out` to change the destination, `--rule` to select rules and `--format` to change the renderer.

The chaining it hides is real: `detect` reads what `reconstruct` wrote, and `visualize` needs to be told where the detections are. That is a fact about the tool, not a decision the person should have to make.

**Done.**

### US-02 · `damfe reconstruct`

> As an **analyst**, I want to extract the artefacts and stop there, so that I can inspect the model or feed it to something other than the report.

Recognises the technology, extracts every collection and writes one JSON file per collection. `--only <collection>` narrows it to a single extraction, which is what makes debugging one extractor cheap. `--prefix` restricts to one organisation, `--framework` forces a reconstructor when detection is wrong, `--spec` points at a communication declaration elsewhere.

**Done.**

### US-03 · `damfe detect`

> As an **analyst**, I want to run the rules over artefacts I already have, so that I can change a threshold or a domain map without reading the code again.

Reads the artefacts, applies every registered rule or those named with `--rule`, prints each occurrence with the elements involved and the places in the code, and writes `detections.json` with `--out`.

**Done.**

### US-04 · `damfe visualize`

> As an **analyst**, I want the report on its own, so that I can regenerate it after editing a declaration without redoing the extraction.

Writes `architecture.html` into the artefacts directory. `--detections` overlays the occurrences on the drawing; without it the report shows the architecture alone. `--format features` prints a Markdown summary of the system to standard output instead, which is the input the domain-mapping prompt expects. `--out` chooses another destination.

**Done.**

### US-05 · `damfe setup`

> As an **analyst**, I want a page that asks what the tool cannot infer and shows me straight away what my answers produced, so that I can tell a wrong declaration from a right one.

Serves a page on `127.0.0.1` and opens the browser. Three steps: the model credential, four fields describing how the system discovers, composes, routes and communicates, and a run whose counts are shown on the same screen. The agent's declaration is written to `.damfe/` and read back immediately, so invalid YAML fails at once.

Runs in the directory of one system. Pointed at a folder holding several, it reads them as one.

**Partial** — the interview produces `discovery`, `composition` and `routing` sections that no extractor reads yet. Only `mechanisms` takes effect.

### US-06 · `damfe setup-llm`

> As an **analyst**, I want to store a credential once, so that the authoring steps stop asking for it.

Takes `--key`, `--model` and `--url`, and writes them to the user's config directory — **never** to `.damfe/`, which is versioned with the analysed project. The file is created readable only by its owner, with no window in which others could read it. An environment variable takes precedence over the file. The credential is never printed in full, and no analysis command reads it.

**Done.**

### US-07 · `damfe setup-communication`

> As an **analyst**, I want a template of the declaration, so that I can fill it in by hand without learning the schema from documentation.

Writes a commented template to `.damfe/` in the analysed repository — input to the analysis, not output, which is why it does not live among the artefacts and survives deleting them.

**Done.**

### US-08 · Reading the report

> As an **analyst**, I want to move between the finding and the drawing, so that the picture is evidence rather than illustration.

`architecture.html` is one file with no network dependency: it opens offline and can be archived next to the text citing it. The drawing is produced by the tool rather than the browser, so the same artefacts always give the same image. Relations can be switched on and off one at a time; elements named in a detection are highlighted, distinguishably from the orchestrator's own mark; and each occurrence links back to the nodes and edges that produced it.

**Done.**

---

# Pending

### RF-25 · Report what could not be resolved

> **Given** an analysis that has run
> **then** the report states what the tool could not determine.

There is already plenty to report: an opaque activity function, an entrypoint that did not resolve, a screen no import reaches, a URL resolved only as a prefix. None of it reaches the reader today, so "found nothing" and "could not look" are indistinguishable — which is precisely what produced six false detections on a system whose extraction had come back empty.

**Pending.** Without it the method's recall cannot be stated.

### RF-35 · Warn when the artefacts are stale

> **Given** a declaration changed after the last reconstruction
> **when** detection runs over the old artefacts
> **then** the staleness is reported.

**Pending.** Editing `domains.yml` or `communication.yml` and running only `detect` produces a plausible, outdated result.

### RF-36 · Extract communication through `customProps`

> **Given** an orchestrator that injects state or actions into a unit
> **then** that channel is extracted.

The keys are already read; the channel is not. It is standardised by the technology and needs no declaration.

**Pending.**

### US-09 · Generate the communication declaration from prose

> As an **analyst**, I want to describe in prose how the system works and get the declaration ready, so that I need not learn the format.

This is `damfe setup` finished: the proposal validated against the schema and checked against the repository before being written, and the sections for discovery, composition and routing actually read by an extractor. Non-determinism stays confined to the setup step, whose result is reviewed and versioned; the analysis stays reproducible.

**Pending.** A setup page exists with the interview, but what it generates for composition and routing is not yet read by any extractor.

### RF-28 · Automated test suite

> **Given** the extraction, the rules and the persistence
> **when** the suite runs
> **then** a regression fails the build instead of reaching a repository.

**Pending.** The architecture was built to allow it — injected ports, use cases without side effects — and the possibility sits unused. Every regression found so far was found by rerunning two real repositories by hand.
