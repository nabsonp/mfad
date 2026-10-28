# MFAD

Static analysis of micro frontend architectures. It extracts from the
source code the artefacts that describe the architecture, detects
anti-patterns over them and generates visualizations.

It currently recognises **single-spa** and **Module Federation**. Other
technologies are added as extensions, without changing the other
modules. Platforms with their own integration built on top of these two
— OpenMRS 3 (`@openmrs/esm-framework`) and Open edX
(`@edx/frontend-platform`) — are outside the analysis: the packages
built on them are skipped, with a warning, and a repository that is
only that is refused instead of being reconstructed wrongly.

No step of the analysis uses a language model, the network or execution
of the analysed code.

## Installation

```bash
cd mfad
pipx install -e .
```

The `-e` makes the installation editable: changes to the code take
effect immediately. The `mfad` command becomes available globally.

### Tests

```bash
cd mfad
python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest
```

Each test builds a minimal repository in a temporary folder and runs the
whole reconstruction over it. The examples are written from each
technology's documentation, not copied from the study's systems: the
test proves the rule, not the shape of one project.

## Five-minute usage

```bash
mfad analyze /path/to/repo --prefix @your-org/
```

Reconstructs, detects and visualizes in one pass, writing to
`artifacts/`. The three steps also exist separately, for those who need
them:

```bash
mfad reconstruct /path/to/repo --prefix @your-org/ --out artifacts
mfad detect artifacts --out artifacts
mfad visualize artifacts --detections artifacts
```

To debug an extractor, `--only` restricts the run to one collection:

```bash
mfad reconstruct /path/to/repo --prefix @your-org/ --only navigations
```

Typical output (abridged):

```
4 micro frontends, 4 fragments, 12 screens, 4 imports and 18 navigations
  and 0 communications between micro frontends · 16 external calls
  · 8 global state accesses

nano-frontend  [size]
  monolito has 1 screens and 0 fragments, 1 in total, at most 5 (absolute floor), …
```

## The three modules

| module | command | what it does |
|---|---|---|
| reconstruction | `reconstruct` (and `reconstruct --only`) | reads the code, produces artefacts |
| detection | `detect` | applies rules over the artefacts |
| visualization | `visualize` | draws artefacts and detections |

`analyze` chains the three. Detection and visualization never read
source code. They work only on the artefact model, and are therefore
independent of the source technology.

---

## Commands

```bash
mfad {reconstruct,analyze,setup-communication,detect,visualize} ...
mfad --version
```

### `reconstruct` — extracts every artefact

```bash
mfad reconstruct <repo> [--prefix PREFIX] [--framework FRAMEWORK] [--out DIR]
                        [--only COLLECTION] [--spec PATH]
```

| option | default | description |
|---|---|---|
| `--prefix` | none | filters the micro frontends by the organization prefix, e.g. `@nabstore/` |
| `--framework` | detected | forces a reconstructor: `single-spa` or `module-federation` |
| `--out` | `artifacts` | output directory |
| `--only` | all | extracts a single collection — `microfrontends`, `compositions`, `navigations`, `api-calls`, `global-state` or `communications` — and prints it to the terminal without writing. A cut of the same process, useful to debug an extractor |
| `--spec` | `<repo>/.mfad/` | path of the communication declaration |

### `analyze` — reconstructs, detects and visualizes in one pass

```bash
mfad analyze <repo> [--prefix PREFIX] [--framework FRAMEWORK] [--out DIR]
                    [--spec PATH] [--rule NAME] [--format FORMAT]
```

Same options as `reconstruct` (except `--only`), plus `--rule` and
`--format` from `detect` and `visualize`. Everything is written to
`--out` (`artifacts` by default); the `html` report goes to
`<out>/architecture.html`.

### `detect` — applies the rules

```bash
mfad detect [artifacts] [--rule NAME] [--out DIR]
```

| option | default | description |
|---|---|---|
| `artifacts` | `artifacts` | directory with the artefacts |
| `--rule` | all | applies only this rule. Can be repeated |
| `--out` | none | writes `detections.json` |

### `visualize` — draws

```bash
mfad visualize [artifacts] [--format FORMAT] [--detections DIR] [--out FILE]
```

| format | output |
|---|---|
| `html` (default) | a single, self-contained report, no CDN; written to `<artifacts>/architecture.html` unless `--out` is given |
| `features` | Markdown summary of the system, on standard output |

The numbers in the `html` header are also the tabs of the page. The
first box, **Dashboard**, opens the graphs; each number opens the full
table of what it counts — micro frontends, screens, navigations,
compositions (with the fragments, in a single table), communications,
API endpoints and anti-patterns —, with a text filter and sorting by
column. The slices of shared global state have no tab: they are in the
detail of the `global-state-communication` detection, with who reads,
who writes and where.
A row shows only what identifies the item; clicking it opens the rest —
files and lines, screens, mechanism — and a shortcut to the item in the
graph.

The dashboard has one graph per question, each in its own card, one
below the other, and only those that have something to show:

| graph | what it draws |
|---|---|
| Overview | micro frontends and the relations between pairs: mounting, composition, navigation, communication |
| Composition, Navigation, Communication | one relation at a time, only with those taking part in it |
| Global state | each shared slice as a node, linked to whoever reads or writes it |
| Backend | each endpoint called by more than one micro frontend, linked to whoever calls it |
| Screens | on which screen each composition, communication and navigation happens, with a cut per micro frontend |

The search and the filters at the top apply to every graph. Hovering a
node highlights its relations in every graph; clicking pins the
highlight and opens the details in a sidebar on the right, which closes
with ×, Esc or another click on the same node. In the sidebar, the name
of another micro frontend opens it right there (← goes back), and the ↗
next to each item leads to the tab that details it, with its row open.
Each card has its own zoom (Ctrl/⌘ + wheel or the buttons), and
**enlarge** makes it taller; dragging the background pans.
`#view=screens&mfe=<id>&lang=pt` at the end of the address leads
straight to a graph, in a cut and a language; `#page=navigations` opens
straight on a table.

The page is in English by default, with a PT/EN switch in the header.
All of its text — and the detection messages — comes from
`src/mfad/adapters/driven/i18n/texts.json`, with each key in both
languages side by side. The title is `<architecture name> - MFAD`.

### `setup-communication`

```bash
mfad setup-communication <repo> [--out DIR]   # generates .mfad/communication.yml
```

---

## Artefacts produced

| file | content |
|---|---|
| `manifest.json` | the envelope: schema version, provenance and index |
| `microfrontends.json` | the nodes: routes, role, screens, fragments, size |
| `compositions.json` | component consumption between micro frontends |
| `navigations.json` | user navigation between micro frontends |
| `communications.json` | message exchange |
| `api_calls.json` | calls to external services, with the screens that reach them |
| `state_accesses.json` | global state reads and writes |
| `detections.json` | written by `detect` |

Every collection is written on each run, including the empty ones —
otherwise the file from the previous run would remain and the next step
would read data that no longer matches the code.

### The envelope

`manifest.json` is what makes the set self-describing and the result
reproducible:

```json
{
  "mfad": "1.0.0",
  "tool_version": "0.1.0",
  "generated_at": "2026-10-03T14:22:10Z",
  "project": "mfe-hands-on",
  "reconstructor": "single-spa",
  "sources": [
    {
      "path": "mfe-checkout",
      "remote": "https://github.com/org/mfe-checkout.git",
      "commit": "a1b2c3d...",
      "dirty": false
    }
  ],
  "artifacts": {
    "microfrontends": { "file": "microfrontends.json", "count": 6 }
  }
}
```

`mfad` is the version of the artefacts' **schema** and goes up when the
shape of the files breaks whoever reads them; `tool_version` is the
**tool**'s version. They are separate because fixing a bug in an
extractor changes the second and not the first — and a long data
collection must be able to state that all results follow the same
schema.

`sources[]` lists the repositories read, searched up to two levels
below the root — which is how the tool is used, on a folder with several
clones. The `commit` is what allows repeating the analysis on exactly
the same code; `dirty` warns that there were uncommitted changes and
that, therefore, the `commit` does *not* identify what was read.
Credentials embedded in the origin URL are removed before writing.

Without git installed, or outside a repository, `sources` is empty and
the analysis proceeds normally.

The output is JSON and the input is YAML, on purpose: `.mfad/*.yml` is
written by hand and benefits from comments; `artifacts/*.json` is
generated and consumed by machines. The reason is in
[docs/decisions.md](docs/decisions.md), section 9.

### How the artefacts are discovered

The full rules, one *given / when / then* each, are in
`docs/extraction/` (index in [docs/README.md](docs/README.md)): what
every technology shares in [common.md](docs/extraction/common.md), and
discovery and composition in
[single-spa.md](docs/extraction/single-spa.md) and
[module-federation.md](docs/extraction/module-federation.md). In short —
micro frontends, routes and fragments as single-spa declares them, the
rest common to every technology:

**Micro frontends** come from the orchestrator's `registerApplication`
— the single-spa contract. This also finds applications without a
package of their own. Those not registered with a literal name are
found by the lifecycles they export (`bootstrap`, `mount`, `unmount`).

**Routes** come from `activeWhen`; from **single-spa-layout**, both in
the page's `<template id="single-spa-layout">` and in the
`microfrontend-layout.html` file that `create-single-spa` generates;
and, in Angular, from the `APP_BASE_HREF` that single-spa-angular asks
to declare. The name in the layout is linked to the package when the
two are equal or equal without the scope (`@org/catalog` ↔ `catalog`).
The package that declares the layout is the orchestrator.

**Fragments** are the entrypoint's exports that are not part of the
lifecycle contract.

**Screens** come from each unit's router: React Router v6/v7 in JSX
(`element`), in objects (`createBrowserRouter`, `useRoutes`, `lazy`)
and v5 (`component`, `render`, child); @reach/router; and the Angular
Router. Nested routes add the parent's path. Without a router, the
screen is the root component.

**Size** is measured during the same scan, with comment lines
discounted through the syntax tree — not by text prefix.

**Navigations** use an inversion: instead of looking for navigation
calls, which vary by router, the extractor looks for expressions that
resolve to a route of ANOTHER micro frontend. The route's owner comes
from `activeWhen`, which is standardized. The target of a React Router
link (`<Link to>`, `<NavLink to>`, `<Navigate to>`, `navigate()`,
`history.push()`) starts from the `basename` of the unit's router, as
React Router resolves it: under `basename="/shop"`, `to="/"` is
`/shop`.

**External calls** are recognised in layers: `fetch` and
`XMLHttpRequest`, which are web platform API; known clients — axios,
ky, got, superagent — identified by the import specifier, including
`axios.create()` instances, even when created in another module of the
project; Angular's `HttpClient`, identified by the type it is injected
with (`constructor(private http: HttpClient)` or `inject(HttpClient)`);
and the **project's functions that forward one of their parameters as
the URL** to one of those clients — `fetchApi(url)`,
`this.request.get(endpoint)` —, followed in layers, with the verb coming
from the options the caller passes. The parameter may be at any
position of the function's signature, and more path may follow it in
the URL (`` `${base}${endpoint}/${id}` ``); a ternary between two URL
forms counts for what the two have in common. A URL that starts with an
unknown base — `` `${API_URL}/users` ``, `API_URL + "/users"` — counts
as the path after it; a runtime segment in the middle becomes `{param}`
(`/account/{param}/statement`), and the query (`?page=2`) is not part of
the path. A URL held in a variable or returned by a function of the
project (`const url = statementUrl(id)`) is followed. Each call records
the screens that reach it by following internal imports — and, in
Angular, the components the template uses by selector, which the screen
renders without importing.

**Imports** follow the bundler's resolution — implicit extension and
`/index` — and, for a specifier without a leading dot, the `baseUrl`
and `paths` of the nearest `tsconfig.json` or `jsconfig.json`, with
`extends`. An alias pointing to another package is a boundary, like a
package import.

**Global state** comes from libraries known by their import —
react-redux, zustand, jotai, recoil, mobx, pinia — and from browser
storage, `localStorage` and `sessionStorage`. In the libraries, only
**reads**: the selector walks the path explicitly, while a write reveals
only the action's name. In storage, reads and writes, because both
name the key. A key with runtime segments is recorded with `{param}` in
their place (`` `${user.handle}_provider` `` is `{param}_provider`):
the contract is the key's format, like the path of a URL. A Redux store
created inside the unit itself is that unit's local state and is not
included. A project function that forwards one of its parameters as
the key — `setLocalStorageItem(key, value)`, a `LocalStorageService`
injected in Angular — becomes a storage access, with the key read at
the caller, and the access belongs to the caller: the utility may live
in a common package. An access in an unused function does not count.

**Test files are not read**: `*.spec.*`, `*.test.*` and the folders
`__tests__`, `__mocks__`, `cypress` and `e2e`.

**Communication** has three layers: platform primitives (`CustomEvent`
with `dispatchEvent`/`addEventListener` — also when the event is created
in a variable before being dispatched —, rxjs `fromEvent(window, …)`,
`BroadcastChannel`), buses known by their import, and the mechanism
declared by the user. An end inside an unused function does not count:
a non-exported function that nothing in the file references, or an
exported function from a file the project imports without bringing that
name.

**Code owner** is the unit whose directory contains the file, the
longest that matches. Code of a shared package that is not a unit — the
monorepo's common library, an organization's `common` repository — runs
inside each micro frontend that imports it, so the external calls and
storage accesses in it count for each of those micro frontends (the
recorded location stays the package's file). Code that no unit imports
belongs to no one and produces no edge.

---

## Per-project declarations

They live in `.mfad/`, at the root of the analysed repository —
versioned with it, and immune to cleaning of the output folder.

### `.mfad/communication.yml`

Routes and fragments are extracted without configuration because the
technology standardizes those contracts. Communication through a
mechanism of the project's own has no standard, and is declared:

```yaml
mechanisms:
  - name: events
    kind: pubsub
    produce:
      module: "@your-org/utils"   # import specifier, literal
      export: publishEvent        # EXPORTED name, not the local name
      channel_argument: 0         # channel position, 0-based
    consume:
      module: "@your-org/utils"
      export: subscribeToTopic
      channel_argument: 0
```

Producer and consumer are paired by the **channel value**.

> Zero communications with a filled-in declaration almost always means
> a `module` that does not match the real import specifier.

---

## Anti-pattern rules

Seven, out of the catalogue's 27. The full triage is in
[docs/catalogue.md](docs/catalogue.md).

### `cyclic-dependency`

Micro frontends that depend on one another in a cycle **within the same
screen**. Being on the screen means being reached by it: the code the
screen's component imports and the fragments it renders, at any depth.
In a graph of the whole system, edges from different screens chained
together and, in a large system, cycles exploded without any of them
actually being mounted.

It evaluates composition and communication **separately**, because a
cycle means different things in each. Navigation is not included: it
links one screen to another, and going back and forth between screens
is product flow. One occurrence per cycle, with the screens in which it
appears.

### `hub-like-dependency`

A screen that instantiates many fragments. The signal is the number of
**distinct fragments**, not of providers nor of instantiations: five
fragments from a single provider concentrate as much contract change as
five from five, and the same fragment repeated in a list is just one.
Default 5.

### `one-for-all`

A micro frontend linked to almost all the others. It counts undirected
neighbours, but records separately whom it depends on and who depends
on it — a shared bottleneck and excessive knowledge are distinct
problems. It excludes the orchestrator, abstains in small systems and
ignores the symmetric global state edges, which would link everyone to
everyone — that coupling belongs to `global-state-communication`.

### `hammering-apis`

A service route consumed by more than one micro frontend. It groups by
**path**, not by path plus method: whoever reads and whoever writes the
same resource share the same contract.

### `global-state-communication`

Global state accessed by more than one micro frontend — a store slice or
a `localStorage`/`sessionStorage` key. A **single, binary** occurrence:
the system either uses state as a channel or it does not.

### `mega-frontend`

A micro frontend whose screens **and** lines of code are both above the
upper Tukey fence of the system, `Q3 + 1.5·IQR`. Both together, not
either one: many screens with little code is a menu, a lot of code with
one screen is a library. The rule abstains in systems with fewer than
eight micro frontends, where there is no distribution to speak of. It
indicates a concentration of responsibilities, but does not prove it: a
large, cohesive unit is not a Mega Frontend.

### `nano-frontend`

A micro frontend with few screens plus fragments — at most 5, or below
the system's lower Tukey fence — **and** less code than the system
median. The second condition is the same double requirement as
`mega-frontend`: few screens with a lot of code is a dense screen, not
a small unit. It indicates excessive fragmentation, but does not prove
it: a small unit is legitimate when it makes up a whole capability on
its own.

### No severity scale

Assigning "high" or "low" would require a defined and justified
criterion. Instead, each occurrence reports the **dimension** — which
architectural relation produced it.

---

## Known limitations

**Constant propagation** is indexed by the identifier's name, globally.
Two files with a different `const routes` collide. For a simple
constant (`const KEY = "x"`), a name with two values in the repository
does not resolve.

**A layout name different from the package** is only linked when it
differs by the scope. `@org/argo-gestao` and a package `gestao` remain
unlinked.

**Vue Router and `.vue` files** are not read.

**Bundler import aliases** (webpack's `resolve.alias` and
`resolve.modules`, Vite's `alias`) are not read; only the
`tsconfig`/`jsconfig` one.

**Dead code** is discarded for communication ends, global state
accesses and API calls, only at the function level. A file no one
imports counts as live — it may be the application's entry point or an
exposed module —, and so does a class method.

**A storage key through a wrapper** is only followed when it is the
parameter, with at most fixed text before and after it. A key inside an
object (`storage.get({ key })`), a method chosen at runtime
(`storage[op](key)`) and a utility imported by the workspace package
name (`@org/utils`, without `paths` in `tsconfig`) are left out.

**The router's `basename`** applies to all of the unit's links when it
declares a single value. With two routers of different bases, the
target stays as written.

**`activeWhen` as a function** cannot be resolved statically.

**A dynamic navigation target** (`navigate(variable)`) does not
resolve. Literals, constants, templates and `.replace(":id", …)`
resolve.

**Navigation inside a fragment** is attributed to the micro frontend
that defines the fragment, not to the one that renders it.

**Units mounted side by side** by the orchestrator, without one
rendering the other, are not on the same screen for
`cyclic-dependency` — nor is `customProps`, which is emitted at
registration. It is left out by definition.

**Writes to library-managed global state** (Redux `dispatch` and the
like) are not extracted: the call reveals the action's name, not the
slice that changes. Writes to `localStorage`/`sessionStorage` are.

**`baseURL` does not resolve**, because it comes from an environment
variable. The paths stay relative, and two micro frontends talking to
different services on the same path look the same.

**A function wrapping a client** is not followed when the text before
the parameter is already a path (`"/api/" + endpoint`): the call stays
where it is, as `/api/{param}`, because what the parameter completes is
unknown. A function held in a variable, a service object assembled at
runtime and injection without a written type have no target.

**GraphQL does not fit the model** of an external call: everything goes
to a single endpoint, and the real unit is the operation.

**Changing a declaration requires re-running `reconstruct`.** Editing
`communication.yml` and running only `detect` uses the previous
resolution, without warning.

**tree-sitter versions are pinned to a closed range.** The core and the
language bindings share an ABI, and mixing families silently corrupts
memory — the process dies with a segmentation fault at random places,
without an exception.
