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

### RF-37 · Provenance of the artefacts

> **Given** a reconstruction that has run
> **then** the artefacts record the schema version, the tool version, the instant of generation, the reconstructor used, the revision of every repository read, and the count of every collection
> **and** a repository with uncommitted changes is marked as such
> **and** no credential embedded in a remote URL is written out.

Without it a set of artefacts is anonymous: it does not say which version of the tool produced it, nor which revision of which repository it describes. For an evaluation over hundreds of systems that is fatal — the result stops being verifiable the moment the analysed repository takes a commit. The schema version is separate from the tool version because fixing an extractor bug changes the second and not the first, and a long collection has to be able to state that every result follows the same schema.

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

> **Given** the screens, the fragments and the size of each unit
> **when** a unit's screens **and** lines of code both sit above **twice** the system median, with the orchestrator left out of the comparison
> **then** it is reported, with its counts and the medians it was compared against.

With no declared map of business capabilities there is no way to state *which* responsibilities a unit accumulates, so what is measured is the observable consequence: it grew far beyond its peers. Both measures are required together — many screens and little code is a menu, much code and one screen is a library. The rule abstains when the median is zero: zero means nothing was measured, not that everything is small.

**Done.**

### RF-20 · Nano frontend

> **Given** the screens, the fragments and the size of each unit
> **when** a unit's screens plus fragments sit below **0.4×** the system median, with the orchestrator left out of the comparison
> **then** it is reported, with its counts and the medians it was compared against.

Screens and fragments are summed because both are ways of delivering interface: a unit with no screen that publishes five fragments is not nano. An indication rather than a verdict — a small micro frontend is legitimate when it is a whole capability on its own, and the rule cannot tell that case apart, which is why the output carries what it compared against.

**Done.**

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

> As an **analyst**, I want to run the rules over artefacts I already have, so that I can change a threshold without reading the code again.

Reads the artefacts, applies every registered rule or those named with `--rule`, prints each occurrence with the elements involved and the places in the code, and writes `detections.json` with `--out`.

**Done.**

### US-04 · `damfe visualize`

> As an **analyst**, I want the report on its own, so that I can regenerate it after editing a declaration without redoing the extraction.

Writes `architecture.html` into the artefacts directory. `--detections` overlays the occurrences on the drawing; without it the report shows the architecture alone. `--format features` prints a Markdown summary of the system to standard output instead. `--out` chooses another destination.

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

**Pending.** Editing `communication.yml` and running only `detect` produces a plausible, outdated result. Cheap now that RF-37 records `sources[].commit`: comparing it against the current HEAD covers the code; the declarations still need their own marker.

### RF-36 · Extract communication through `customProps`

> **Given** an orchestrator that injects state or actions into a unit
> **then** that channel is extracted.

The keys are already read; the channel is not. It is standardised by the technology and needs no declaration.

**Pending.**

### RF-28 · Automated test suite

> **Given** the extraction, the rules and the persistence
> **when** the suite runs
> **then** a regression fails the build instead of reaching a repository.

**Pending.** The architecture was built to allow it — injected ports, use cases without side effects — and the possibility sits unused. Every regression found so far was found by rerunning two real repositories by hand.
