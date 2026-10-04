# Extraction rules — single-spa

What the single-spa reconstructor reads from source, and under which conditions. Each rule as *given / when / then*.

Written from the implementation in `src/damfe/adapters/driven/reconstruction/singlespa/`. It exists so you can check what the tool does without rereading the code, and so you can write a reconstructor for another technology from a known baseline.

No rule executes the analysed code, reaches the network, or consults a language model.

---

## 0. Inputs

Every rule below consumes one of these. They are produced in this order, each from the one before it, so a rule can only use what an earlier rule has already resolved.

| input | what it is | example |
|---|---|---|
| **repository** | the directory handed to `damfe reconstruct`, minus `node_modules`, `dist`, `build` and other generated trees | `mfe-hands-on/` |
| **orchestrator file** | the source file containing calls to `registerApplication`. Found by scanning the repository; there is usually one | `root-config/src/nabstore-root-config.js` |
| **registration** | one `registerApplication` call, read into `name`, `activeWhen`, the loader's `specifier`, the file it was declared in, how `activeWhen` was written, and the keys of `customProps` | `{ name: "@nabstore/mfe-users", activeWhen: ["/users"], specifier: "@nabstore/mfe-users" }` |
| **entrypoint file** | the source file the registration's loader resolves to — the micro frontend's first module, the one exporting its lifecycles | `mfe-users/src/nabstore-mfe-users.js` |
| **micro frontend directory** | the directory whose `package.json` contains the entrypoint file | `mfe-users/` |
| **root component file** | the file holding the component passed as `rootComponent` to the single-spa adapter, resolved through the entrypoint's imports | `mfe-users/src/root.component.js` |
| **fragment catalogue** | every fragment of every micro frontend, gathered before any consumption is looked for. Cross-micro-frontend, so it needs all of §1 and §2.1 done first | `{ "@nabstore/mfe-products": ["BestOffersFragment", …] }` |
| **route table** | every micro frontend's `activeWhen`, sorted longest prefix first | `["/checkout", "/products", "/users", "/"]` |
| **communication spec** | `.damfe/communication.yml` in the analysed repository, when it exists | — |

---

## 1. Discovery

### 1.1 · Micro frontend inventory

> **Given** the repository
> **when** a source file contains calls to `registerApplication`, either in object form `({ name, app, activeWhen, customProps? })` or positional form `(name, loadingFn, activityFn, customProps?)`
> **then** each call is a micro frontend, with `name` as its identity and the string literals found inside `activeWhen` as its routes.

Reading string literals is what makes both forms work, but it is coarser than the API. single-spa accepts `activeWhen` as a string, as an activity function `(location) => boolean`, or as an array mixing the two. A function is not interpreted: whatever string literals appear inside it are taken as routes. `pathToActiveWhen("/users")` and `(l) => l.pathname.startsWith("/users")` both yield `/users` by coincidence, while a function holding no literal yields nothing, and one testing a literal negatively yields a route it does not own.

> **Given** a registration whose `activeWhen` is an activity function
> **when** the function has a recognised shape — `pathname.startsWith("/x")`, `pathname === "/x"`, `pathname.includes("/x")`, or `pathToActiveWhen("/x")`
> **then** the route is read from it and `metadata.active_when_form = "function"`.

> **Given** a registration whose `activeWhen` is an activity function
> **when** the shape is not recognised
> **then** any string literal inside it is taken as a route and `metadata.active_when_form = "opaque"`.

An arbitrary function does not resolve statically, but the ones written in practice are few and have fixed shapes. Recognising them is the difference between reading the right route and scanning literals hoping to hit it. `opaque` is the honest label for the rest: the routes there may be no routes at all, and the mark says so instead of letting them pass as equal to the others.

A literal `activeWhen` sets no mark, so its presence always means "look closer here".

> **Given** a registration
> **when** it carries `customProps` as an object literal
> **then** `metadata.custom_props` maps each key to its value when the value is a literal, and to an empty string otherwise.

A literal value is configuration written by hand and says something about the system. A value that is a function or a variable is assembled at runtime, and there only the key survives — knowing the key exists is already information.

`registerApplication` is single-spa's own source of truth about which applications exist — including those with no package of their own. Starting from `package.json` misses those.

### 1.2 · Entrypoint

> **Given** a registration
> **when** its loader carries a package specifier (`() => System.import("@org/mfe-x")`)
> **then** the entrypoint is looked up, in this order, in the directory whose `package.json` declares that name, by the convention `src/{org}-{project}.{js,jsx,ts,tsx}`, and then through the manifest's `module`, `main` or `source` fields.

> **Given** a registration
> **when** its loader carries a relative path (`() => import("./monolith")`)
> **then** the file is resolved against the file that declares the registration.

This is how a monolith under migration enters the graph: it is a registered application like any other, and it would vanish if we only looked at the import map.

> **Given** a registration
> **when** no entrypoint file resolves from its loader
> **then** it stays in the graph, flagged `metadata.entrypoint_resolved = false`.

Applications registered with inline lifecycles in the shell do exist. Disappearing is worse than showing up incomplete.

### 1.3 · Routes declared in a layout

> **Given** a registration with no routes, and the repository's HTML and template files
> **when** a `<template id="single-spa-layout">` names that application inside one or more `<route path=…>`
> **then** those paths become its routes, concatenated through nesting, and `metadata.routes_from = "single-spa-layout"`.

> **Given** a registration with no routes, and the repository's source files
> **when** `constructRoutes({ routes: [...] })` is called with an object literal naming that application under `{ type: "route", path: … }` entries
> **then** the same applies.

Only an object literal is read. `constructRoutes(myConfig)` stays out: resolving it would mean evaluating the module, and what looks like a route there may be assembled at runtime.

single-spa-layout moves route ownership out of the registration and into a template, and under it an application needs no `activeWhen` at all. Reading only the registration would return the application's name and no routes — a whole system with no route owners, no navigation and no screens, with nothing saying information was missing.

### 1.4 · Role in the system

> **Given** the entrypoint file
> **when** it exports `bootstrap`, `mount`, `unmount` or `update`
> **then** the names found go into `metadata.lifecycles`.

Those are single-spa's contract, and they are what confirms the thing is a micro frontend rather than any other package. `update` is optional and belongs to parcels; the other three are required of an application.

---

### 1.5 · The orchestrator as a node

> **Given** the registrations, grouped by the package that declares them
> **when** each group is read
> **then** that package becomes a node of its own, with `role = "shell"`, identified by the `name` in its `package.json`, and `mounts` listing the applications it registers.

The shell never appears in a `registerApplication` — it is the caller — so it used to be left out of the graph although it is what mounts everything else. What was missing with it is the relation that defines the system: micro frontends drawn loose, with nothing explaining how they reach the page.

It also answers a question that looks like composition and is not. A navigation bar registered at `/` shows up on every screen, and yet no micro frontend imports it — the shell puts it there. Modelling visual co-presence as imports between peers would invent edges that exist nowhere in the code, and would turn the navigation bar into a hub in the very report meant to reveal coupling.

One node per orchestrator, because a repository can hold more than one system, and merging their registrations would invent an orchestrator mounting applications across systems.

Being registered in the same package as the orchestrator does **not** make an application the shell. A monolith loaded through a relative path from `root-config` lives in that package and is still a registered application like any other.

---

## 2. Composition

### 2.1 · Exposed fragments

> **Given** the entrypoint file
> **when** it has a named `export` that is not a lifecycle
> **then** each exported name is a fragment of that micro frontend.

### 2.2 · Mount container

> **Given** the entrypoint file
> **when** it passes a `domElementGetter` resolving to `getElementById("x")` or `querySelector("#x")`
> **then** `metadata.container` receives the element's identifier.

Declaring a container means the shell reserved a slot in its layout: that micro frontend is fitted into a page alongside other things. One that declares nothing gets a `div` single-spa appends to the body, named `single-spa-application:{name}`.

Both `domElementGetter` and the direct `domElement` accepted by the framework adapters are read. An element arriving through `customProps` is not: there the value is assembled by the shell, and the entrypoint holds no trace of it.

### 2.3 · Fragment consumption

> **Given** the fragment catalogue and the source files of a micro frontend
> **when** one of those files imports, from another micro frontend's package, a name present in the catalogue
> **then** a `FragmentImport` is recorded between the two.

The catalogue is what buys precision here: without it there is no way to tell a fragment from any other export of the same package, nor to recognise a JSX instantiation without falling back on naming conventions.

The rule above finds the import. Where the fragment is then used is recorded as a render site, and single-spa offers two shapes for that.

> **Given** a fragment imported from another micro frontend
> **when** it is rendered as a JSX element, or passed as `config` to a `<Parcel>`, or handed as the first argument to `mountRootParcel` or to the `mountParcel` prop
> **then** each occurrence is a render site of that fragment.

> **Given** a render site and the screens of the consuming micro frontend
> **when** a screen reaches the render site's file through relative imports
> **then** that screen is recorded on the render site.

A fragment is rarely instantiated in a screen's own file. It usually sits in a component the screen uses, a layer or two down, so asking only about the file would return almost nothing. More than one screen is a common and correct answer — a fragment inside a shared component is seen from every screen that reaches it. None means no screen reaches that file: an instantiation in dead code, or in something only the shell mounts.

Knowing that `mfe-checkout` consumes `DeliveryEstimateFragment` answers who depends on whom. Knowing it shows up on the Cart screen answers where it is seen, which is the question someone about to change the system actually has.

A **parcel** is single-spa's framework-agnostic component: one application exports it, another mounts it by hand. It composes exactly like an imported component, but never appears as a JSX tag of its own — `<Parcel config={Modal} />` renders `Parcel`, and `mountRootParcel(Modal, …)` renders nothing at all. Looking only for JSX elements would return a system composed entirely of parcels as having no fragment consumption, which reads as a valid answer and is not one.

---

## 3. Screens and routes

### 3.1 · Declared screens

> **Given** the micro frontend directory
> **when** any source file under it has `<Route path=… element=… />`
> **then** each occurrence is a screen, taking the component from `element` and the route from `path`.

Every file is searched, not only the reachable ones: the question reconstruction answers is which screens the micro frontend **defines**.

### 3.2 · Screen wired or unwired

> **Given** a declared screen and the root component file
> **when** the file declaring the screen is reachable through imports from the root component
> **then** `reachable = true`; otherwise `false`.

A screen declared in a file nobody imports exists in the code and does not exist at runtime. Both facts matter, for different reasons.

### 3.3 · Micro frontend without its own router

> **Given** a micro frontend whose directory holds no `<Route>` at all, and its root component file
> **when** `metadata.container` is set
> **then** its `rootComponent` is a **fragment**.

> **Given** a micro frontend whose directory holds no `<Route>` at all, and its root component file
> **when** `metadata.container` is absent
> **then** its `rootComponent` is a **screen**, whose route is the one from `activeWhen`.

In single-spa the router is `activeWhen`: registering under a prefix already serves that route, and an internal router is only needed to serve several screens under the same prefix. No `<Route>` does not mean no screen — it means exactly one.

An always-on `activeWhen` (`/`) is **not** used as a signal: two applications can share the same `activeWhen` and both be screens.

### 3.4 · Owner of a URL

> **Given** a URL and the route table
> **when** the URL is compared against the table
> **then** the longest prefix matching on a segment boundary wins.

`/checkout` covers `/checkout` and `/checkout/cards`, and does not cover `/checkoutx`. Ordering by length matters: without it the shell, which usually registers `/`, would swallow every route.

`/` is treated as its own URL, not as a prefix over everything. In single-spa it does match every URL, but reading it as a prefix here would turn any path — an API endpoint included — into navigation towards whoever registered it.

> **Given** a URL and a route containing a `:segment`
> **when** compared
> **then** the segment matches any non-empty value in that position, and what follows the declared part still belongs to the same application.

`/users/:id/profile` owns `/users/123/profile` and `/users/123/profile/edit`, and does not own `/users//profile` or `/users/123`.

> **Given** a URL and a route containing `#`
> **when** compared
> **then** the hash must match in full, while the path before it is still matched as a prefix.

`/pathname/#/hash` owns `/pathname/#/hash` and not `/#/hash`.

---

## 4. Communication through `customProps`

> **Given** a registration carrying `customProps`, and the orchestrator that declares it
> **then** one communication is recorded per key, from the orchestrator to the registered application, on the channel named by the key, directed.

This is the channel single-spa itself recommends, and the only one in the tool that needs no pairing: the registration names **both** ends at once. Who injects is the orchestrator, who receives is the application named right there, and each key is a channel. Every other mechanism is born of two ends that have to meet over a channel name and may turn out symmetric; this one has source and target written into the declaration, so the edge is directed by construction — which is what lets `cyclic-dependency`, which counts only directed edges, read it.

The keys were already extracted into `metadata.custom_props` (§1.1); what was missing was emitting the edge. On nabstore it yields seven: the orchestrator injecting the redux actions — `addProductToCartAction`, `loginAction`, `selectEnderecoAction` — into the applications that use them.

Only the orchestrator's side is read. What the application does with the prop it receives is not traced, so there is no `consumed_at`: the declaration proves the injection, never the use. An application that is handed `onLogout` and never calls it produces the same edge as one that calls it on every screen.

When a repository holds more than one orchestrator, the edge comes from the one that **mounts** that application (§1.5). With a single orchestrator and no `mounts` match, it is attributed to that one; with several and no match, nothing is recorded rather than guessing.

---

## 5. Beyond composition

Navigation, external calls, global state and the remaining communication mechanisms — platform primitives, Web Storage, shared RxJS subjects, cross-window `postMessage`, known buses and the declared spec — do not depend on how the system is composed, and are described in [common.md](common.md).

---

## 6. Known limits

| | |
|---|---|
Everything here is either undecidable from source or a deliberate choice, not work left undone.

| | |
|---|---|
| Activity functions of unknown shape | flagged `opaque` and mined for literals — see §1.1. A function can compute its route from anything, so there is no shape list that closes this |
| `constructRoutes(variable)` | resolving it means evaluating the module — see §1.3 |
| `customProps` values that are not literals | assembled at runtime; the key is kept, the value cannot be — see §1.1 |
| Use of an injected `customProps` | only the orchestrator's side is read, so the edge proves the injection and never the use — see §4 |
| Containers assembled at runtime | `getElementById(someVariable)` names an element only the running page knows — see §2.2 |
| State writes | a deliberate exclusion, not a gap. The call site names the action, never the slice — see [common.md](common.md) |
| Coverage | the report does not say what was left unresolved (RF-25) |
