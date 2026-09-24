# damfe — requirements

Two kinds of requirement, told in the form each one deserves.

**Behaviour requirements (RF)** say what the tool produces, as *given / when / then*. Nobody is interacting in them: they hold whether the analysis was started from a terminal, from a script or from a page, and they are what a test asserts.

They are also technology-agnostic. Which artefacts exist and what each must carry is settled here; **how** a given technology produces them belongs to [extraction/](extraction/), one document per reconstructor. A requirement that named `registerApplication` would have to be rewritten for the next technology, and that is the wrong place for it.

**User stories (US)** say what someone wants from the tool and why. There is one per command, plus one for reading the report — they document the surface a person touches, and nothing beyond it.

Behaviour numbers are carried over from the previous revision, so `RF-25` here was `US-25` there, except for the rules split out of the old `US-32`. The user stories were renumbered, because the set is no longer the same: they now follow the commands.

| status | meaning |
|---|---|
| **Done** | exists and has been exercised on a real system |
| **Partial** | exists with a recorded limitation |
| **Pending** | identified, not built |

---

# Part 1 · Behaviour

## The artefacts

What the reconstruction must produce, whatever the technology. **How** each technology produces it is in [extraction/](extraction/) — one document per reconstructor, plus the rules every technology shares.

### RF-01 · Inventory of units

> **Given** a repository whose technology is recognised
> **then** every separately deployable unit is listed, each with an identity, the routes it owns, its role and its size.

A unit whose entrypoint cannot be resolved still appears, carrying the fields that could be determined. Disappearing is worse than showing up incomplete.

**Done.**

### RF-02 · The orchestrator

> **Given** the units of a system
> **then** whatever composes them is a node too, marked as such and listing what it mounts.

Without it the graph shows units floating, with nothing explaining how they reach the page — the relation that defines the system. One node per orchestrator, because a repository may hold more than one.

**Done.**

### RF-03 · Screens

> **Given** a unit
> **then** every screen it declares is listed, with its component, its route and whether anything reaches it.

A route that cannot be resolved keeps its original expression, so the reader sees what the code said. A screen declared in a file no import reaches is extracted all the same and marked: it exists in the code and not at runtime, and both facts matter.

**Done.**

### RF-04 · Exposed fragments

> **Given** a unit
> **then** everything it publishes for others to consume is listed, each pointing at the file that defines it.

**Done.**

### RF-05 · Fragment consumption

> **Given** the fragments of every unit
> **when** one unit consumes another's
> **then** the consumption is recorded with where it was imported, where it was instantiated, and in which screens it appears.

Only what a unit actually publishes counts, so shared libraries stay out. An import with no instantiation is recorded as such — a dependency that costs a build and delivers nothing. A fragment instantiated inside a helper component belongs to the screens that reach it, not to none.

**Done.**

### RF-06 · Navigation between units

> **Given** an expression that produces a URL
> **when** that URL belongs to another unit
> **then** a navigation is recorded from the origin to the route's owner, carrying how certain the resolution is.

The detection recognises the destination, not the call: there is no standard navigation API to look for, and every technology declares who owns which route. Navigation inside a single unit is not reported.

**Done.**

### RF-08 · Communication between units

> **Given** the source of a system
> **when** one unit publishes on a channel another subscribes to
> **then** the two are paired by channel name, and the edge records whether its direction means anything.

Pairing is by channel because the channel is the contract between the ends, not the shape of the call. Direction matters to whoever walks the graph: a message has a side, shared state does not.

Platform primitives and known buses are recognised with no configuration; a project's own wrapper is declared once. The absence of a declaration is reported as a state distinct from the absence of communication.

**Done.**

### RF-24 · Global state

> **Given** a unit that reads a slice of shared state
> **then** the access is recorded, and when two or more units read the same slice, undirected edges are derived between them.

Writes are deliberately excluded: the call site names the dispatched action, not the slice it changes, and recording both would mix two vocabularies. The derived edges belong in the graph because the coupling is real — two units reading the same slice depend on the same data shape without knowing each other.

**Done.**

### RF-29 · External service calls

> **Given** a unit that calls an external service
> **then** the call is recorded with its path, how certain the resolution is, and the screens and fragments that reach it.

An empty reachability list is information: the call sits in code no screen reaches.

**Done.**

### RF-30 · Size of each unit

> **Given** the scan already under way
> **then** each unit's files and lines of code are counted, without a second read of the disk.

**Done.**

### RF-31 · Declared business domains

> **Given** a domain map declared in the analysed repository
> **then** each domain resolves to its routes, its endpoints, its screens and the units that serve it.

Business domains are not in the code and no static analysis determines them, which is why they are declared. A subdomain is a record, not a division: it folds into the domain containing it, and rules operate at the top level, so the granularity chosen by whoever declares does not change the verdict.

**Done.**

### RF-11 · Technology recognition

> **Given** a repository
> **when** more than one reconstructor is registered
> **then** the one that recognises it is chosen, and when none does the tool says so rather than returning an empty result.

**Done.**

### RF-10 · Persistence

> **Given** the artefacts of a run
> **then** each collection is written to its own file, stable between runs over the same code, and readable back without touching source again.

Stability is what makes a diff between two commits mean something: it shows coupling that appeared or vanished, not noise from the extraction order.

**Done.**

---

## Detection

Each rule reads artefacts and nothing else — never source, and never anything that says which technology produced them. That is what lets a rule written today hold for a technology supported tomorrow.

### RF-13 · Applying the rules

> **Given** the artefacts
> **when** the rules run
> **then** each occurrence names the rule, the elements involved, the relation that produced it and the places in the code.

Rules can be applied in full or selected by name. Having none registered is reported, and not confused with having no problems. There is no severity scale: assigning one would need a justified criterion the catalogue does not give, so each occurrence carries its **dimension** instead — which architectural relation produced it.

**Done.**

### RF-14 · Cyclic dependency

> **Given** the fragment consumptions, the navigations and the communications
> **when** an elementary cycle exists within **one** of those relations
> **then** it is reported with the chain in the order it closes.

One cycle per relation rather than one per pair: importing a fragment and navigating are different couplings with different remedies. Symmetric edges are excluded — coupling through shared state has no direction, and looking for cycles in it finds one in every pair. The enumeration is capped so a dense graph cannot stall the run.

**Done.**

### RF-15 · Hub-like dependency

> **Given** the screens and the render sites of the fragment consumptions
> **when** a screen instantiates **five or more** fragments
> **then** it is reported with the fragments and the units they come from.

The count is of fragments, not of distinct providers: five from one provider concentrate as much contract change as five from five. Counting providers punished the normal design — with a shared component library, any screen using one of its components plus any other fragment became a hub.

**Done.**

### RF-16 · One for all

> **Given** every relation summed, and the inventory
> **when** one unit touches **90% or more** of the others, in a system of at least **five**
> **then** it is reported, separating how many it depends on from how many depend on it.

Connection is counted without direction: being the centre is a problem either way. The orchestrator is excluded, reaching everything by definition. Systems below the minimum are not assessed, because being connected to everyone is normal in them.

**Done.**

### RF-17 · Hammering APIs

> **Given** the external service calls
> **when** **two or more** units call the same path
> **then** it is reported with the methods and the callers.

Grouping is by path, not by unit: it is the contract that is shared. This is the coupling no other graph shows — the units do not import one another, do not navigate to one another and exchange no messages, and still break together when the response format changes.

**Done.**

### RF-18 · Global state as a channel

> **Given** the global state accesses
> **when** a slice is read by **two or more** units
> **then** a single occurrence reports the practice, with the slices and who reads each.

One occurrence, not one per slice: what matters is whether the practice exists and who takes part, and emitting one per slice would say the same thing repeatedly.

**Done.**

### RF-19 · Mega frontend

> **Given** the screens and the declared domain map
> **when** a unit's screens fall into **more than one** domain
> **then** it is reported, naming **which screens differ and where they would go**.

A count does not say what to do; a screen name and a destination do. Without a declared map the rule falls back to size — **twice** the system median — and says which criterion it used. A unit whose screens fall in no domain is undetermined and the rule abstains, as it does when the median is zero: zero means nothing was measured, not that everything is small.

**Done.**

### RF-20 · Nano frontend

> **Given** the screens, the fragments and the declared domain map
> **when** a unit's screens all sit in a domain that another unit **dominates**
> **then** it is reported, naming the domain and who would absorb it.

The problem is not being small: it is not being a unit of a domain. A micro frontend with a single screen is legitimate when that screen is the domain. Without a map the fallback is **0.4×** the median, with the same abstentions as above.

**Done.**

### RF-21 · Access to different domains

> **Given** the external service calls and the declared domain map
> **when** a unit's calls fall into **two or more** domains
> **then** it is reported with the domains consumed.

Distinct from the mega frontend, and the difference changes the remedy: that one looks at what a unit **serves** — its screens; this one at what it **depends on** — its calls. A unit may serve one domain and consume three, and then the problem is API federation.

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
