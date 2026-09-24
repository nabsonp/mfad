# Extraction rules — common to every technology

The rules below do not depend on how the micro frontends are composed. They start from the applications a reconstructor has already extracted and from primitives of the web platform, so every technology gets them for free, and a new reconstructor implements only discovery and composition.

Each rule as *given / when / then*. No rule executes the analysed code, reaches the network, or consults a language model.

The inputs are whatever the technology's own rules produced: the micro frontends, their screens, their routes, and the repository's source files. See [single-spa.md](single-spa.md) or [module-federation.md](module-federation.md) for how those come to be.

---

## 1. Navigation

### 1.1 · Navigation between micro frontends

> **Given** a source file of a micro frontend and the route table
> **when** an expression in it resolves to a URL owned by another micro frontend
> **then** a navigation is recorded from the origin to the route's owner.

single-spa has no standard navigation API — each project uses its framework's router, or a component of its own. Detecting the **call** would not be generic; detecting the **target** is, because every application declares its routes at registration. Whatever triggers the navigation stops mattering.

### 1.2 · Resolution confidence

> **Given** a URL expression being resolved
> **when** it is fully determined statically
> **then** `match = exact`; when only its beginning is static, `match = prefix`.

Anything matching none of the recognised forms is left unresolved, and that is a legitimate answer — the alternative would be guessing.

---

## 2. External calls

### 2.1 · Detection

> **Given** the source files under a micro frontend directory
> **when** one of them calls the platform's `fetch`, or use of an HTTP client recognised by its import specifier
> **then** an external call is recorded, with the path resolved by the same partial evaluator used for routes.

### 2.2 · Attribution to micro frontend and screen

> **Given** an external call and its file
> **when** attributing it to a micro frontend
> **then** the directory containing the call's file decides.

> **Given** an external call and the screens of that micro frontend
> **when** attributing it to a screen
> **then** internal-import reachability is followed from the screen.

Projects wrap the HTTP client in a module of their own (`services/api.js`), and that module belongs to the micro frontend containing it — the `micro frontend → endpoint` edge comes out right without following indirection. Knowing which **screen** calls requires following it, because the call lives in the service module.

---

## 3. Global state

> **Given** a source file of a micro frontend importing a known state library (`react-redux`, `zustand`, `jotai`, `recoil`, `mobx-react-lite`, `pinia`)
> **when** there is a read walking a path into the state (`useSelector((state) => state.cart)`)
> **then** an access is recorded, with library and path.

Identification is by import specifier, never by variable name.

> **Given** a state write in that same file (`dispatch(addProduct(item))`)
> **then** it is **not** extracted.

The call site reveals the action's name, not the slice it changes; finding the slice would mean following the reducer, which may not even be in the repository. Recording both in one list would mix state paths with action names.

> **Given** every state access already extracted, and a slice read by two or more micro frontends
> **then** undirected `global-state` communication edges are derived between every pair.

---

## 4. Communication

Three tiers, all producing the same artefact. Producer and consumer are paired by **channel name**, which is the contract between the two ends, not by the shape of the call.

> **Tier 1 — platform primitives.**
> **Given** the source files of a micro frontend
> **when** one of them has `dispatchEvent(new CustomEvent(channel))` with `addEventListener`, or `BroadcastChannel`, or `postMessage`
> **then** communication is recorded.

These are browser APIs: they hold in any project, with no configuration.

> **Tier 2 — known buses.**
> **Given** a source file importing `mitt`, `eventemitter3`, `tiny-emitter` or `pubsub-js`
> **when** the value coming from it is used to publish or subscribe
> **then** communication is recorded.

Not a naming heuristic: if the imported module is `mitt`, whatever comes out of it is an event bus.

> **Tier 3 — declared mechanism.**
> **Given** the communication spec
> **when** it declares the module, the export and the position of the channel argument
> **then** those calls become recognised.

For the project's own wrapper, which no catalogue knows. Without a declaration the result is not empty: the first two tiers still hold.

---
