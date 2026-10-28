# MFAD design decisions

Living document. One entry per decision, with the reason. A reversed
decision stays recorded as reversed; it does not disappear.

Last updated: 03/10/2026.

---

## 1. Scope and architecture

**Three independent modules** — reconstruction, detection, visualization.
Reconstruction is extensible per technology; detection is agnostic and
operates only on artifacts.

**Hexagonal architecture per module**, not one for the whole. This allows
using reconstruction alone without dragging the rest along.

**`composition.py` is the only composition point.** No adapter
instantiates another.

**Use cases separated by extraction**, grouped in subfolders per
module. A monolithic `reconstruct` killed single responsibility; today
it only composes the others.

**One artifact file per collection.** ~~No index or manifest: there
was no consumer for it.~~ **Reversed on 03/10/2026** — the consumer
appeared: the empirical evaluation over hundreds of repositories needs
to say which revision of which repository each result refers to. See
section 9.

**No unrequested code.** Skeleton first, implementation on demand.

---

## 2. Domain model

**`MicroFrontend`**, not `Application`. **`AntiPatternDetection`**, not
`Finding`. The vocabulary is the domain's, not the tool's.

**Severity removed.** The anti-pattern catalogue does not define it;
inventing a scale would smuggle judgement into the data.

**Domains are an artifact**, with a hierarchy of subdomains. The rules
operate at the top level, so the granularity of the map does not change
the result.

**Global state: reads only.** Writes also couple, but the call site
reveals the name of the dispatched action, not the changed slice —
finding the slice would require following the reducer. Mixing state
path with action name would mix two vocabularies. This applies to the
libraries; for browser storage, writes are included (see below).

**`localStorage` and `sessionStorage` are global state.** ~~Directed
communication channel: `setItem` produces, `getItem` consumes.~~
**Reversed on 08/10/2026.** Whoever writes sends nothing to anyone; it
leaves the data for whoever comes next, and the coupling is the format
of the value under the key — the same as a store slice. As a directed
channel, the authentication token written by one and read by all closed
a cycle between almost any pair: in udistrital there were 844
`localStorage` edges, and the 200 cycles that blew past the
`cyclic-dependency` cap. Writes are included because here they name the
key; `StateAccess.access` separates `read` from `write`. Schema 3.1.0 →
3.2.0: the keys leave `communications.json` and go into
`state_accesses.json`.

**The slice is library and path together.** The `user` key of
`localStorage` and the `user` slice of a store are different data.

**Global-state coupling goes into the communication graph**, as an edge
with `mechanism: "global-state"`. It used to be a separate collection,
and the graph rules undercounted the real coupling.

**`Communication.directed`** distinguishes a directed edge from a
symmetric one. Shared state has no origin; symmetry is represented by a
pair of opposite edges, and whoever traverses the graph needs to know
that.

---

## 3. Determinism

**No analysis step uses an LLM, the network, or execution of the
analyzed code.** That is what makes the result reproducible and
auditable.

**LLM confined to authoring steps.** It helps *write* a file — domain
map, communication spec — that is reviewed and versioned. MFAD reads
the file, not the model.

**LLM-generated artifact rejected as input.** A `features.md` produced
by a model is not an artifact MFAD generates, so it cannot be part of
the analysis path.

**API key in `~/.config/mfad/`, never in `.mfad/`.** The latter is
versioned together with the analyzed project. The file is created with
mode `0600`; the key is never displayed in full.

---

## 4. Reconstruction

**Discovery starts from `registerApplication`**, not from `package.json`.
In single-spa the orchestrator declares every micro frontend; starting
from it found one that the package scan did not see.

**`--prefix` is mandatory.** Without it the fragment filter opened up
(returned true for everything) and captured every import.

**`activeWhen` matches by prefix with a segment boundary.** `/` is
always mounted, but does not own every URL.

**Navigation by target-directed inversion.** Instead of recognizing the
navigation call — which changes with each router — MFAD recognizes the
expression that resolves to a route belonging to another micro
frontend. It is library-independent.

**Layered detection**: platform primitives (universal) → known
libraries by import specifier → declared spec. It works with no
declaration at all; the declaration only increases coverage.

**Partial string evaluation** with constant propagation, templates and
concatenation. The result carries its confidence: `exact` when the URL
was fully resolved, `prefix` when only the beginning was.

**Attribution by reachability** — transitive closure of relative
imports starting from screen and fragment. It revealed that
`services/api.js` is dead code in all three micro frontends of the
reference repository.

**An implicit extension is appended, not substituted.** `./x.component`
resolves to `x.component.ts`. Resolution used to replace the suffix and
try `x.ts`, which left the whole Angular naming convention (`.component`,
`.service`, `.module`) and the `root.component.tsx` root of the
single-spa template without a file. Fixed on 08/10/2026: in udistrital,
screens without a file dropped from 241 to 0 (out of 251), and files
reached by some screen rose from 10 to 232. Grupo-10, LBHackney and
Insta-Graph gained the root screen, which was not found before.

**In Angular, the template is an import.** The screen writes
`<app-tabela>`, and what binds the selector to the class is the
`NgModule`: the screen's `.ts` does not import the child. Reachability
now follows the selector to the file that declares it, in the same
package. This is the fix that holds for any Angular application.
Reading `baseUrl`/`paths` from `tsconfig` (`src/app/...` imports) was
left out because it is per-project configuration. Decided on
08/10/2026.

**Test code is not read.** `*.spec.*`, `*.test.*`, `__tests__`,
`__mocks__`, `cypress` and `e2e` are removed from the scan, which is a
single one for all extractors. Tests are not mounted at runtime: in
udistrital, an `auth.guard.spec.ts` writing to `localStorage` became a
communication.

**Generic fixes, tested by examples written from the documentation.**
An audit on 08/10/2026 compared the output with the code of 13 systems.
The fixes follow each technology's documented API or the language
semantics, never a project's convention; each one has a test in
`tests/` with a minimal repository written from the documentation. Left
out, because they are the convention of a single system: the route
`data: { app }` that an Angular orchestrator uses to mount parcels, and
the `src/test/` folder as test code.

**The owner of code is the longest directory containing it.** Looking
only at the first folder of the path gave, in a monorepo with the units
one level below, the monorepo folder as owner. Code outside any unit
belongs to no one and produces no edge — including external calls,
which used to create a consumer outside the inventory.

**A URL after an unknown base counts as its path.** `${API_URL}/users`
used to be discarded entirely, and nearly every service call is written
like that. Navigation still requires a URL starting at the path itself:
an unknown base may be another origin. Storage keys and channel names
require the whole value — `"cart_" + id` does not say which slice it is.

**single-spa layout in both forms, and the orchestrator comes from it.**
The `microfrontend-layout.html` of `create-single-spa`, with a
`<single-spa-router>` root, was not read — only the `<template>` in the
page. The package that declares the layout becomes the shell, mounting
what the layout names. `<route default>` gives no prefix. The layout
name binds to the package when it is equal, or equal without the scope;
any similarity beyond that would be guessing.

**`APP_BASE_HREF` is a route in Angular.** single-spa-angular instructs
declaring it with the mount prefix. It applies when neither the
registration nor the layout gives a route, and covers a unit whose
orchestrator is not in the repository.

**React routes in every documented form**, in a dedicated reader
(`routers/react.py`) used by both extractors: v6 in JSX with relative
nesting, v6.4+ as objects (`createBrowserRouter`, `lazy`), v5
(`component`, `render`, child) and @reach/router.

**A simple constant resolves by name, if the name has a single value.**
`const CART_KEY = "cart"` — including when imported from another
module, without following the import: if the name has only one value in
the repository, that is it.

**An event created before being dispatched** is followed to its
declaration in scope, and rxjs's `fromEvent(window, …)` is a listener.
Only global targets count: `fromEvent(botao, "click")` is an element
event.

**A route declaration is not navigation.** `path` and `from` in
`<Route>`, `<Redirect>` or a direct child of `<Router>`/`<Routes>`/`<Switch>`,
and `basename` on a `*Router`, are the router saying what answers
there — but `path` on a project component (`<Voltar path={routes.HOME}>`)
leads somewhere, and stays. `fetch(url)` fetches data, and an argument
of a string method (`url.endsWith("/")`, `split("/")`) is text.

**An application outside `<route>` in the layout has no route.** It is
always mounted and owns no URL; with the route `/`, every `"/"` in the
code became navigation to it — 191 in udistrital.

**A service path needs one literal segment.** `/` alone, from
`${base}/${rota}`, names no service and would merge everything into a
single route.

**`registerApplication` name only as a literal.** The text of an
identifier became the application name (`appName`).

**A Redux store created in the unit itself is local.** Two units, each
with `createStore` and the same slice, share nothing.

**An import made only by a remote's standalone entry is not
composition.** The host loads what the remote publishes; the remote's
`main.tsx` only runs when it is opened on its own. It made a component
library, used only there, look depended upon by everyone in
`one-for-all`.

**Platform packages with their own integration are removed from the
scan.** OpenMRS 3 and Open edX use single-spa/MF underneath and register
applications at runtime, through their own manifests. The extractor
recognized them and returned a misleading inventory. The cut is per
package, like the test one: whatever depends on the platform, or is the
platform (`@openmrs/esm-*`), is left out, with a warning in the CLI, and
the rest proceeds — Bahmni has an OpenMRS module next to two Module
Federation units. When nothing is left, the answer is "not supported".

**Pruned scan, not `rglob`.** Descending into `node_modules` took
minutes; pruning brought it to 3.3s.

**A function that forwards the URL is an HTTP client.** The most common
pattern of service calls is the project's own function — `fetchApi(url)`,
a `RequestManager` in Angular — and the URL only appears in its caller.
The criterion is data flow, not name: the function becomes a client when
it passes one of its parameters as the URL of a known client, and this
propagates through layers. Only when the URL ENDS at the parameter, with
at most a base and text before it; `"/api/" + endpoint` is already a
path and stays where it is — there is no way to know what the parameter
completes, and the old rule loses nothing.

**Angular `HttpClient` by injected type.** The module import is not
enough — `@angular/common/http` also exports `HttpHeaders` and
`HttpParams` —, and the call is always on the instance (`this.http`).
The type written on the constructor parameter or in `inject(HttpClient)`
is what the compiler itself uses to know what `http` is.

**A runtime segment in the path becomes `{param}`, and the query string
is dropped.** Cutting at the first `${}` merged `/account/${id}/statement`
and `/account/${id}/transfers` into `/account/` in `hammering-apis`. The
path keeps what comes after; `?page=2` does not change the contract.

**`paths` and `baseUrl` from `tsconfig`.** They are the compiler's rule,
and TypeScript projects import almost everything through aliases
(`@/utils/x`). Without them reachability stopped at the screen and dead
code could not be decided. An alias pointing to another package is a
boundary, like a package import. Bundler aliases (`resolve.alias`, Vite)
are left out: they live in configuration code, not in data.

**A communication endpoint in an unused function does not count.**
Three Grupo-10 units had a copy of `setAccountId` that dispatches the
event, and none called it — the file was imported only for
`getAccountId`. The rule is the linters' "unused symbol" rule,
conservative: a file nobody imports and a class method count as alive,
because the consumer may be the framework.

**A function that forwards the key is a storage access.** It is the same
pattern as `fetchApi`: `setLocalStorageItem(key, value)` in Grupo-10, a
`LocalStorageService` in gematik, a `LocalStorageUtil` in Bahmni. The
key only appears in the caller, and without following the function the
access disappeared. The access is attributed to the CALLER, not to the
function's file: the utility usually lives in a common package that
belongs to no unit, and it is the units that use it that couple through
the key. Recognition of layered wrappers is the same as for HTTP calls,
in a common module (`forwarding.py`). The key still has to be whole —
`` save(`cart_${id}`) `` does not become a slice.

**Global-state access in an unused function does not count**, by the
same criterion as communication endpoints. Grupo-10's unused
`setAccountId` wrote to `localStorage` and counted as an access.

**An API call in an unused function does not count either**, by the
same criterion. A call that never leaves the browser does not couple the
unit to the service and cannot make up a `hammering-apis`.

**A React Router link starts from `basename`.** `<Link to="/">` under
`basename="/loja"` goes to `/loja`; read as absolute, it became
navigation to the owner of `/`. It applies when the unit declares a
single base: with two, it is unknown which router each link belongs to.

---

## 5. Per-technology extension — decided, not implemented

**Setup by interview.** An agent asks the user how composition, routing
and communication between the micro frontends are done, asking for code
examples or a text description.

**The agent generates data, not code.** The output is a declarative
spec, not an extractor. The analysis path reads a versioned file instead
of running model-generated code; thirty lines of YAML are genuinely
reviewable, three hundred lines of extractor are not; and whoever
replicates the research reads the spec.

**The spec lives in `.mfad/`**, versioned with the analyzed project,
next to `domains.yml`. Whoever clones the repository reconstructs
without redoing the interview.

**The algorithms stay in the engine.** Partial evaluation,
reachability and target-directed inversion are already agnostic. The
spec covers only recognition: which call declares a unit, where the name
and the route are. The surface is small on purpose.

**Coexisting mechanisms: apply all and merge.** A repository may use
single-spa and Module Federation at the same time. No precedence and no
conditionals — the spec does not become a programming language.

**An unresolved value returns empty.** The spec only sees what is in
the call itself; `registerApplication(config)` with the object built
elsewhere is left out. Start small: no coverage report, no warning. If
it becomes a problem in practice, RF-25 handles it.

**A technology detector is missing.** Today MFAD assumes single-spa
instead of discovering it. The reconstructor registry exists, but
nothing chooses between them.

---

## 6. Detection

**Technology-agnostic rules**, operating only on artifacts. A new rule
does not know single-spa.

**Rules added one by one**, with verification on real code for each.

**Size as evidence**, and as a decision criterion only when there is no
domain map.

**`cyclic-dependency` ignores symmetric edges.** Looking for a cycle in
an undirected relation finds one in every pair of readers — the cycle
would be the encoding, not the system. The test is `directed`, not the
mechanism name, so that any future symmetric medium is already handled
correctly.

**`nano-frontend` also requires code below the median.** The floor of
5 screens and fragments, alone, flagged the largest unit in udistrital.
Decided on 08/10/2026.

**`hub-like-dependency` counts distinct fragments**, not render sites:
the same card in a list is a single dependency.

**`one-for-all` also ignores symmetric edges.** With browser storage
becoming global state, the token key linked almost every micro frontend
to all the others, and in udistrital the rule went from 6 to 43
detections. The coupling is real, but it has no center, and it already
belongs to `global-state-communication`. Decided on 08/10/2026.

**`cyclic-dependency` looks for cycles within a screen.** ~~One graph
per relation, for the whole system.~~ **Reversed on 07/10/2026** — in a
large system, edges from different screens chained together and the
number of cycles exploded without any of them actually being mounted.
Now there is one graph per relation and per screen, and the same cycle
on several screens is a single occurrence, with the screens listed.

**Being on the screen means being reached by it.** What counts is the
code the screen component imports and the fragments it renders, at any
depth. Micro frontends co-mounted through `activeWhen` were left out on
purpose, as the strictest cut. The price is known: a unit without
`<Route>` has no screen, and event exchange between units mounted side
by side — the Grupo-10 case, which had 5 communication cycles — no
longer shows up.

**Navigation removed from `cyclic-dependency`.** It links one screen to
another; going back and forth between screens is product flow.

**Reconstruction records where each thing happens.** `RenderLocation`
gained `fragments` — the nesting, which `screens` did not see because
reachability does not cross the package boundary — and `Communication`
gained `produced_on` and `consumed_on`. Schema 3.0.0 → 3.1.0: only new
fields, but an old artifact, read with them empty, silently flags no
cycle at all.

---

## 7. Visualization

**Self-contained HTML report**, with four reading levels.

**One view per question, not one graph with everything.** The circle
with every relation stopped being readable from about twenty units on:
in udistrital, 53 overlapping nodes and 4,468 edges. Most of them were
global-state pairs — a key read by N units becomes N² edges —, and the
shared-endpoint edges had the same defect. Both became bipartite
drawings, with what is shared as a node: one link per participant. The
pairwise relations stay in the overview and in one graph per relation,
each with only its participants.

**Force-directed per component, in Python, with no seed.** The initial
position comes from the order of the identifiers and the number of
iterations is fixed: the same artifact gives the same drawing.
Components are laid out separately and packed; whoever has no relation
in the cut goes to a band of its own instead of pushing the others.
Label overlap is removed afterwards, along the axis of least conflict.

**Screens as the place of relations.** Composition already knew on
which screen the fragment is instantiated and communication on which
screen each endpoint is; navigation now knows which screen it starts
from (`on`, schema 3.3.0), and the target is the screen whose route
receives the URL. The screens view arranges the micro frontends in
layers along the flow — whoever publishes or navigates to the left of
whoever receives —, so the edges do not cross frames. An endpoint in
code that no screen reaches stays as "off-screen": the relation exists,
it just has no place in the interface.

**Per-micro-frontend cut precomputed.** With dozens of units, the full
screens view is too long to answer "who does this one talk to, and from
where". Each cut is laid out again and goes into a `<template>`, which
the browser only draws when it is chosen.

**The header numbers are tabs.** A number that cannot be opened asks
for trust; one that leads to the list that adds up to it can be checked.
Each box opens the table of what it counts, with file and line for each
item, and the first box goes back to the map. The tables, which used to
be stacked below the map — detections, endpoints, inventory —, moved to
the tabs, and the home page kept only the map and the panel. Fragments
and compositions are a single table, opened by a single box, the
compositions one: a composition is the fragment seen from whoever
mounts it, and the fragment's row already says who mounts it and on
which screens. With two boxes for the same table, both were selected
together.

**Dashboard with every graph.** With the tables in the tabs, the home
page kept only the map, and its views were another row of tabs, one at
a time. It became a dashboard: one card per graph, one below the other,
at full width. Two per row was tried and discarded: the narrow card
shrank the large graphs too much. Search and filters apply to all of
them, and highlighting a micro frontend lights it up in every graph at
the same time — comparing relations, which used to require switching
tabs, is how the page is read. Zoom is per card: collapsed, the graph
shrinks until it fits entirely, to see its shape; **expand** makes the
card taller, where the text becomes readable again.

**Details in a sidebar that opens on click.** The panel was always next
to the dashboard, taking width with help text while nothing was
selected. It became a bar that slides in from the right only when a
node, an edge or a shortcut is clicked, and closes with ×, Esc or by
clicking the same node again. Hovering still only highlights. The help
moved to the search bar at the top.

**The sidebar leads to the tabs.** Each item in the bar has a ↗ to the
tab that details it: the screen, the fragment, the endpoint, the
detection, the pair of a dependency. Table rows carry keys (`data-key`:
the micro frontend, the screen, the `origin>target` pair, the detection
index), and the link opens the right row without relying on text
search, which matched extra rows. The numbers at the top of the bar
(screens, fragments, anti-patterns) show only that micro frontend's
rows. "Routes" became "Base URL": it is the path where the orchestrator
mounts the micro frontend, not the routes of the screens.

**Paths grouped by micro frontend.** In a row's detail, the locations
(where the slice is read, where the message is published, where the
endpoint is called from, where the fragment is imported) come in groups:
the micro frontend once, with its directory, and below it the files
without that directory. Repeating `mfe · mfe/src/...` on every line hid
what changes between them, which is the rest of the path. The full path
is still in each one's `title`.

**Detection as fields, not a sentence.** Each rule declares, besides
the message, the data supporting it as labeled fields
(`metadata.text.facts`: screens, fragments, threshold, lines, median…).
The anti-patterns tab is a table like the others: the row states the
anti-pattern and who is involved, and the detail shows one field per
datum, the why, and the code. The all-in-one sentence forced reading the
whole sentence to find a number. The message stays in the artifact and
in the map's warning; the dimension also stays in the artifact, but
leaves the page, where it only repeated the anti-pattern's name.

**Shared global state without its own tab.** The slices touched by more
than one micro frontend are exactly the evidence of
`global-state-communication`; in a separate tab, the page said the same
thing twice, and the detection only gave the count. Now the detection
detail shows each slice — library, key, who reads, who writes and
where —, and the header number was removed. The map's global-state view
remains.

**Per-route detections on a single row.** `hammering-apis` emits one
occurrence per shared route, and systems with dozens of them filled the
table with identical rows. The page merges route detections
(`metadata.path`) of the same anti-pattern into one row, with a
collapsed block per route — methods, callers and the calls per micro
frontend and file —, like the global-state slices. It is presentation
only: the artifact still has one occurrence per route, and the counts
do not change. "Show in graph" focuses all routes together.

**External calls in a single table.** The tab had the endpoints table
and, below it, one row per call. The endpoint detail already had each
call — micro frontend, file, line, method and screen —, and the second
table repeated it; only the HTTP client was missing, and it was added to
the detail. The call's code snippet was removed: the file and line lead
to it.

**Texts in a single JSON, in two languages.** The page and the rules
read from `i18n/texts.json`, with `pt` and `en` side by side under each
key. The HTML is produced in English, the default language, with each
text tagged by its key and values, and the header switch rebuilds the
sentences in Portuguese without going back to Python — including inside
the SVGs and the stored cuts. The rule writes the message in the default
language, and the
reference in `metadata` (`text`), which is what the page translates; an
old artifact, without the reference, appears as it was written. The
drawing's boxes are sized by the longer of the two versions.

**Badge, not border, for anti-patterns.** In a system where almost
every unit appears in some detection, a red border on all of them
distinguished no one; the badge says how many.

**`visualize` writes a file.** The default is `html` at
`<artifacts>/architecture.html`. Dumping hundreds of kilobytes to the
terminal forced the user to copy from the screen what the command
already had ready. `features` (markdown) stays on standard output,
which is where it is useful.

**One command for the common case.** `analyze` does reconstruction,
detection and visualization in one pass. The chaining — `detect` reads
what `reconstruct` wrote, `visualize` needs `--detections` — is a tool
detail, not a user decision.

**Six subcommands became `reconstruct --only`.** `microfrontends`,
`compositions`, `navigations`, `api-calls`, `global-state` and
`communications` were slices of the same process exposed as separate
commands, and made the help list eleven entries for a three-step flow.
From 11 commands to 6.

---

## 8. Operation

**Installation with `pipx install -e`.** Editable, global command.

**tree-sitter pinned to the 0.23 family.** Core and bindings share an
ABI; mixing families silently corrupts memory and the process dies with
a segmentation fault in random places, with no exception.

**`AstReader.walk` is iterative, with a tree cache.** Recursion over a
large file overflowed; the tree must be kept alive because the nodes
point into its memory.

**`save` always writes every collection**, including empty ones.
Skipping an empty collection left a stale file from a previous run, and
the next detection read wrong data with no warning at all.

---

## 9. Artifact format and versioning

**The output stays JSON; only the input is YAML.** `.mfad/*.yml`
(`communication.yml`, `domains.yml`) is handwritten and gets comments.
`artifacts/*.json` is generated and consumed by machines. Converting the
output to YAML was considered and rejected for three reasons. The `code`
field carries arbitrary source-code snippets — `:`, `#`, `{`, backtick,
quotes, line breaks — which every YAML emitter handles by quoting, but
the result is fragile precisely for whoever edits it by hand, and the
temptation to edit exists because it is YAML. Determinism:
`json.dumps(indent=2)` produces byte-for-byte identical output across
versions, while a YAML emitter varies with library version, line width
and quoting style — and the empirical evaluation must be reproducible.
Tooling: `jq` over the artifacts is the daily use in the analysis.
Readability, the only argument in favor, is already handled by
`mfad visualize`.

**`manifest.json` is a versioned envelope.** It was
`{"project": "..."}`. It now carries the schema version, the tool
version, the generation instant, the extractor used, the revision of
each repository read, and the collection index with the count of each.

**Schema version separate from tool version.** The `mfad` key is the
artifacts' schema and is bumped when the shape of the files breaks
whoever reads them; `tool_version` is the tool's. They are separate
because fixing a bug in an extractor changes the latter and not the
former, and a long collection run must be able to state that all
results follow the same schema even if the version changed halfway
through.

**`sources[]` records `commit` and `dirty` per repository.** This is
what makes the result reproducible: without the revision, a set of
artifacts does not say which version of the code it describes, and it
stops being verifiable as soon as the repository receives a commit.
`dirty` exists because with uncommitted changes the `commit` does *not*
identify what was read — omitting that would produce false provenance,
which is worse than missing provenance.

**The origin URL is recorded without credentials.** Cloning with a token
in the URL is common and the remote stays in `.git/config`; copying it
into the artifact would publish the credential, because the output is
versioned. The probe strips `user:password@` before recording.

**Provenance comes from a port, `SourceProbe`.** Reading git state is
I/O and cannot live in the use case. The `GitSourceProbe` implementation
looks for repositories up to two levels below the root — that is how
`mfad setup` is used, in a folder with several clones — and stops
descending when it finds one. Nothing there fails the analysis: without
git, provenance is poorer and the rest proceeds.

**The collection index lives in the adapter, not in the domain.** A file
name is a detail of whoever persists. The domain has `Provenance` and
`SourceRepository`; `JsonArtifactRepository` is what knows that
microfrontends go into `microfrontends.json`.

**A manifest without the `mfad` key is accepted on read.** An artifact
predating schema 1.0.0 loads with empty provenance instead of being
rejected — whoever needs the exact revision checks the field and finds
it empty.

**Open Microfrontends was evaluated as a source of inspiration, not as a
foundation.** It is a declarative, prescriptive spec — the server
declares by hand the MFEs it exposes, so that a host knows how to load
them — whereas MFAD describes what was recovered from the code. From it
came the versioned envelope and the idea of a published schema. From it
does *not* come the conceptual model: it has no routing, no composition,
no concept of screen, and declares no edge between MFEs (messages are
host-mediated pub/sub), so none of the catalogue's anti-patterns is
detectable over one of its descriptors. A single maintainer's project,
not an industry standard: it enters as related work and a possible
export target.

---

## 10. Routing is an axis of its own

**The route reader belongs to no reconstructor.** Integration and routing are orthogonal: single-spa and Module Federation say how units become a system, React Router and Angular Router say how ONE unit declares its screens, and any combination exists. Until now the second was hard-wired inside the first — React's `<Route>`, duplicated in two files —, and that is why "route outside React Router" looked like a Module Federation limitation when it was a missing dimension.

**An Angular unit came out with zero screens.** In single-spa the unit's route comes from `activeWhen`, so the symptom was not a missing route, it was a missing screen. And a screen is not an accessory artifact: three rules depend on it — `hub-like-dependency` counts fragments per screen, `access-to-different-domains` resolves the domain per screen, and the fragment→screen attribution is built on top of it.

**The rules come from the framework's documentation, not from an analyzed repository.** The systems selected for the study are the evaluation set; developing against them would turn them into training data and contaminate any accuracy reported later. The Angular reader was written from the `Route` interface published by the project and validated on a fixture built with the documented forms. The public seven-unit Vite system used to build the Module Federation reconstructor belongs to a personal account and is not among the 14 included organizations.

**Angular's `path` is relative and must be concatenated.** `path: 'info'` inside `path: 'product/:id'` answers for `/product/:id/info`. This is the most consequential difference from React Router, where the nested path is usually written as absolute — reading the isolated segment would report a route the application does not have.

**React Router stays where it is, for now.** The two copies diverged: the Module Federation one unwraps `<Suspense>` and resolves the provider, the single-spa one does not. Unifying them in the same step would risk regressing two extractors that work, with no immediate gain. It is left as a separate refactoring.

---

## 11. Names

**`ArtifactSet` became `MicroFrontendArchitecture`.** The old name described the FORMAT OF THE CONTAINER — "a set of artifacts" — and not the thing. It is the same family as `DataManager` and `InfoHolder`: the domain should not know that it is a collection.

The object is the reconstructed architecture, which is literally what the tool sets out to produce. And it does not belong to reconstruction: it is produced by it and also consumed by detection and visualization, so naming it after the producer — `Reconstruction` — would read wrong in the other two, as if the rule evaluated the process instead of the architecture.

The variable followed: `artifacts` became `architecture` everywhere it holds this type. Left out, on purpose, are the uses where `artifacts` really means the output FOLDER — `arguments.artifacts`, `Path("artifacts")` and the manifest's `"artifacts"` key. Having both meanings under the same name was part of the confusion.

---

## 12. v0: no AI and no domain

**No language model, at any step.** Removed: `mfad setup` with the web page, `mfad setup-llm`, the credentials repository in `~/.config/mfad/` and the authoring prompts. Determinism stops being a property defended by convention and becomes structural: there is no code path that calls a model.

**The business domain was removed entirely.** Gone are `Domain`, `DomainMap`, `DomainDeclaration`, `.mfad/domains.yml`, `domains.json` and the resolution that crossed them with the artifacts. It was the only input requiring knowledge external to the repository, and sustaining it cost an entire authoring step.

**`access-to-different-domains` was removed.** It was the only rule that depended solely on the map and, without it, returned nothing. Seven of the eight remain.

**`mega-frontend` and `nano-frontend` become pure counts** — screens, fragments and lines against the system median, with the orchestrator excluded from the comparison. Both already had this mode as a fallback when the map was missing; now it is the only one. What is lost is the ability to say WHICH responsibilities the unit accumulates; what remains is the observable consequence, and the output carries the medians so the reader can disagree.

Mega requires screens **and** lines above the threshold, not either one: many screens with little code is a menu, a lot of code with one screen is a library. Nano adds screens and fragments, because both ways of delivering interface count.

**Measured effect:** nabstore went from 3 to 4 occurrences. The new one is `nano-frontend` on `monolito`, with 1 screen against a median of 3 — correct under the new rule, and previously suppressed by the per-domain mode.

**`.mfad/communication.yml` stays.** It is a deterministic declaration, written and reviewed by hand, and the `setup-communication` that generates the template uses no model at all.

---

## Known pending items

| | |
|---|---|
| RF-25 | report coverage and what was not resolved |
| RF-35 | warn when the artifacts are stale — cheap now: just compare the manifest's `sources[].commit` with the current HEAD |
| US-28 | automated test suite |
| — | `hub-like-dependency` counts a symmetric edge twice |
| — | presentation counts global state twice (edge and access) |
| — | reconstructor for Module Federation: 63% of the sampled population |
| — | published JSON schema of the artifacts, for external validation |
| — | move the React Router reader to `routers/`, unifying the two copies |
| — | Angular `loadChildren`: follow the other module's route table |
| — | `mfad export --format open-microfrontends` |
| — | calibrate `nano-frontend.floor` against the study base: at 5 it flags 9 of the 10 reference units |
| — | `MIN_SAMPLE = 8` for Tukey's fence is a convention, not a measurement |
