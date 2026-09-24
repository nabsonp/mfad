# Extraction rules — single-spa

What the single-spa reconstructor reads from source, and under which conditions. Each rule as *given / when / then*.

Written from the implementation in `src/damfe/adapters/driven/reconstruction/singlespa/`. It exists so you can check what the tool does without rereading the code, and so you can write a reconstructor for another technology from a known baseline.

No rule executes the analysed code, reaches the network, or consults a language model.

---

## 1. Discovery

### 1.1 · Micro frontend inventory

> **Given** a repository
> **when** there are calls to `registerApplication`, either in object form `({ name, app, activeWhen })` or positional form `(name, loadingFn, activeWhen)`
> **then** each call is a micro frontend, with `name` as its identity and `activeWhen` as its routes.

`registerApplication` is single-spa's own source of truth about which applications exist — including those with no package of their own. Starting from `package.json` misses those.

### 1.2 · Entrypoint

> **Given** a registered micro frontend
> **when** `app` loads a package specifier (`() => System.import("@org/mfe-x")`)
> **then** the entrypoint is looked up, in this order, in the directory whose `package.json` declares that name, by the convention `src/{org}-{project}.{js,jsx,ts,tsx}`, and then through the manifest's `module`, `main` or `source` fields.

> **Given** a registered micro frontend
> **when** `app` loads a relative path (`() => import("./monolith")`)
> **then** the file is resolved against the file that declares the registration.

This is how a monolith under migration enters the graph: it is a registered application like any other, and it would vanish if we only looked at the import map.

> **Given** a registered micro frontend
> **when** no entrypoint resolves
> **then** it stays in the graph, flagged `metadata.entrypoint_resolved = false`.

Applications registered with inline lifecycles in the shell do exist. Disappearing is worse than showing up incomplete.

### 1.3 · Role in the system

> **Given** the entrypoint
> **when** it exports `bootstrap`, `mount`, `unmount` or `update`
> **then** the names found go into `metadata.lifecycles`.

Those are single-spa's contract, and they are what confirms the thing is a micro frontend rather than any other package.

---

## 2. Composition

### 2.1 · Exposed fragments

> **Given** the entrypoint
> **when** it has a named `export` that is not a lifecycle
> **then** each exported name is a fragment of that micro frontend.

### 2.2 · Mount container

> **Given** the entrypoint
> **when** there is a `domElementGetter` resolving to `getElementById("x")` or `querySelector("#x")`
> **then** `metadata.container` receives the element's identifier.

Declaring a container means the shell reserved a slot in its layout: that micro frontend is fitted into a page alongside other things. One that declares nothing gets a `div` single-spa appends to the body.

### 2.3 · Fragment consumption

> **Given** the fragment catalogue of every micro frontend
> **when** one micro frontend imports, from another, a name present in that catalogue
> **then** a `FragmentImport` is recorded between the two.

The catalogue is what buys precision here: without it there is no way to tell a fragment from any other export of the same package, nor to recognise a JSX instantiation without falling back on naming conventions.

---

## 3. Screens and routes

### 3.1 · Declared screens

> **Given** a micro frontend
> **when** any file under its directory has `<Route path=… element=… />`
> **then** each occurrence is a screen, taking the component from `element` and the route from `path`.

Every file is searched, not only the reachable ones: the question reconstruction answers is which screens the micro frontend **defines**.

### 3.2 · Screen wired or unwired

> **Given** a declared screen
> **when** the file declaring it is reachable through imports from `rootComponent`
> **then** `reachable = true`; otherwise `false`.

A screen declared in a file nobody imports exists in the code and does not exist at runtime. Both facts matter, for different reasons.

### 3.3 · Micro frontend without its own router

> **Given** a micro frontend with no `<Route>` at all
> **when** it declares a mount container
> **then** its `rootComponent` is a **fragment**.

> **Given** a micro frontend with no `<Route>` at all
> **when** it declares no container
> **then** its `rootComponent` is a **screen**, whose route is the one from `activeWhen`.

In single-spa the router is `activeWhen`: registering under a prefix already serves that route, and an internal router is only needed to serve several screens under the same prefix. No `<Route>` does not mean no screen — it means exactly one.

An always-on `activeWhen` (`/`) is **not** used as a signal: two applications can share the same `activeWhen` and both be screens.

### 3.4 · Owner of a URL

> **Given** a URL
> **when** compared against the micro frontends' routes
> **then** the longest prefix matching on a segment boundary wins.

`/checkout` covers `/checkout` and `/checkout/cards`, and does not cover `/checkoutx`. Ordering by length matters: without it the shell, which usually registers `/`, would swallow every route.

---

## 4. Navigation

### 4.1 · Navigation between micro frontends

> **Given** an expression that produces a URL
> **when** that URL belongs to another micro frontend
> **then** a navigation is recorded from the origin to the route's owner.

single-spa has no standard navigation API — each project uses its framework's router, or a component of its own. Detecting the **call** would not be generic; detecting the **target** is, because every application declares its routes at registration. Whatever triggers the navigation stops mattering.

### 4.2 · Resolution confidence

> **Given** a URL expression
> **when** it is fully determined statically
> **then** `match = exact`; when only its beginning is static, `match = prefix`.

Anything matching none of the recognised forms is left unresolved, and that is a legitimate answer — the alternative would be guessing.

---

## 5. External calls

### 5.1 · Detection

> **Given** the code of a micro frontend
> **when** there is a platform `fetch`, or use of an HTTP client recognised by its import specifier
> **then** an external call is recorded, with the path resolved by the same partial evaluator used for routes.

### 5.2 · Attribution to micro frontend and screen

> **Given** an external call
> **when** attributing it to a micro frontend
> **then** the directory containing the call's file decides.

> **Given** an external call
> **when** attributing it to a screen
> **then** internal-import reachability is followed from the screen.

Projects wrap the HTTP client in a module of their own (`services/api.js`), and that module belongs to the micro frontend containing it — the `micro frontend → endpoint` edge comes out right without following indirection. Knowing which **screen** calls requires following it, because the call lives in the service module.

---

## 6. Global state

> **Given** an import of a known state library (`react-redux`, `zustand`, `jotai`, `recoil`, `mobx-react-lite`, `pinia`)
> **when** there is a read walking a path into the state (`useSelector((state) => state.cart)`)
> **then** an access is recorded, with library and path.

Identification is by import specifier, never by variable name.

> **Given** a state write (`dispatch(addProduct(item))`)
> **then** it is **not** extracted.

The call site reveals the action's name, not the slice it changes; finding the slice would mean following the reducer, which may not even be in the repository. Recording both in one list would mix state paths with action names.

> **Given** a slice read by two or more micro frontends
> **then** undirected `global-state` communication edges are derived between every pair.

---

## 7. Communication

Three tiers, all producing the same artefact. Producer and consumer are paired by **channel name**, which is the contract between the two ends, not by the shape of the call.

> **Tier 1 — platform primitives.**
> **Given** any code
> **when** there is `dispatchEvent(new CustomEvent(channel))` with `addEventListener`, or `BroadcastChannel`, or `postMessage`
> **then** communication is recorded.

These are browser APIs: they hold in any project, with no configuration.

> **Tier 2 — known buses.**
> **Given** an import of `mitt`, `eventemitter3`, `tiny-emitter` or `pubsub-js`
> **when** the value coming from it is used to publish or subscribe
> **then** communication is recorded.

Not a naming heuristic: if the imported module is `mitt`, whatever comes out of it is an event bus.

> **Tier 3 — declared mechanism.**
> **Given** a `.damfe/communication.yml`
> **when** it declares the module, the export and the position of the channel argument
> **then** those calls become recognised.

For the project's own wrapper, which no catalogue knows. Without a declaration the result is not empty: the first two tiers still hold.

---

## 8. Known limits

| | |
|---|---|
| `single-spa-layout` | routes and slots defined in layout HTML are not read |
| `customProps` | not extracted |
| Runtime composition | a container created dynamically is not recognised |
| State writes | out of scope, see §6 |
| Component containment | fragment → screen is not resolved (US-26) |
| Coverage | the report does not say what was left unresolved (US-25) |
