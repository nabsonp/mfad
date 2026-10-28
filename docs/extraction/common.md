# Extraction rules — common to every technology

The rules below do not depend on how the micro frontends are composed. They start from the applications a reconstructor has already extracted and from primitives of the web platform, so every technology gets them for free, and a new reconstructor implements only discovery and composition.

Each rule as *given / when / then*. No rule executes the analysed code, reaches the network, or consults a language model.

The inputs are whatever the technology's own rules produced: the micro frontends, their screens, their routes, and the repository's source files. See [single-spa.md](single-spa.md) or [module-federation.md](module-federation.md) for how those come to be.


**Test code is not read.** Files named `*.spec.*` or `*.test.*`, and directories `__tests__`, `__mocks__`, `cypress` and `e2e`, are pruned from every walk. Test code is never mounted: a `setItem` in a `.spec.ts` couples nothing, and a screen declared only in a test does not exist in the system.
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

> **Given** a JSX attribute `path`, `from` or `basename`, or a `fetch(url)` call
> **when** looking for navigations
> **then** it is not one: the first declare what a router answers to, the last fetches data.

> **Given** a URL that starts with an unknown base (`${BASE}/x`, `BASE + "/x"`)
> **when** looking for navigations
> **then** it is ignored — the base may be another origin.

> **Given** a React Router target — `to` of `Link`, `NavLink` or `Navigate`, the argument of the `navigate` returned by `useNavigate()` or of `history.push`/`replace` from `useHistory()` — in a unit whose router declares one `basename` (`<BrowserRouter basename>` or `createBrowserRouter(routes, { basename })`)
> **when** resolving its URL
> **then** the URL is taken under that base: `to="/"` under `basename="/shop"` is `/shop`.

This is how React Router resolves it. Read as absolute, the link to the unit's own home became a navigation to whoever owns `/`. With two different bases in one unit the target stays as written.

> **Given** a navigation recorded as above
> **then** it also records the screens and fragments whose code reaches the file that navigates (`on`), as the ends of a channel do.

The target side needs no such record: the route already names the screen that receives.

## 2. External calls

### 2.1 · Detection

> **Given** the source files under a micro frontend directory
> **when** one of them calls the platform's `fetch`, or use of an HTTP client recognised by its import specifier
> **then** an external call is recorded, with the path resolved by the same partial evaluator used for routes.

> **Given** a call whose URL starts with an unknown base — `` `${API_URL}/users/${id}` `` or `API_URL + "/users"`
> **when** extracting the path
> **then** the path is what follows the base (`/users/{param}`, `pattern`; `/users`, `exact`).

The base almost always comes from an environment variable, so discarding the whole expression left whole systems with no external calls. A runtime segment in the middle becomes `{param}` and the rest of the path is kept, and the query string is dropped: `/account/${id}/statement?page=2` is `/account/{param}/statement`. A path with no literal segment (`/`, `/{param}`) names no service and is dropped.

> **Given** an Angular class with a field typed `HttpClient` (imported from `@angular/common/http`) — a constructor parameter property, an annotated field, or `inject(HttpClient)`
> **when** `this.<field>.get|post|put|patch|delete|head|options|jsonp(url)` or `request(method, url)` is called
> **then** an external call is recorded.

> **Given** a function of the project whose URL argument to a recognised client is one of its own parameters — at any position of its signature — with at most an unknown base and text before it, and nothing or more path (`/`, `?`) after it (`` fetch(`${BASE}${url}`, { ...options }) ``, `` `${BASE}${endpoint}/${id}` ``)
> **when** another call in the repository resolves to that function — by name, by import, as a member of a default-exported object or namespace, through `this`, or through a field whose type is the function's class
> **then** that call is an external call with the URL from the argument in that position, the verb from the options it passes (when the function forwards them) or fixed by the function, and the client underneath.

Applied in layers until nothing new is found, so a service calling the wrapper with its own parameter is a wrapper too. Text after the parameter stays, with `{param}` for what is runtime. A ternary between two URL forms (`` cond ? `${base}${url}/${id}` : `${base}${url}` ``) counts for what the two have in common, when that ends in the parameter. A URL held in a local variable or returned by a function of the project (`const url = statementUrl(id)`) is followed. When the text before the parameter is already a path (`"/api/" + endpoint`) the function is not a wrapper and its own call is recorded as before (`/api/{param}`), because what the parameter completes is unknown.

> **Given** an external call inside a named function
> **when** that function, or one around it, has no use (the rule of §4 for ends of channels)
> **then** the call is not recorded.

> **Given** an import specifier with no leading dot
> **when** resolving it to a file
> **then** the nearest `tsconfig.json` or `jsconfig.json` decides, with `extends`: `paths` first (exact pattern, then the longest prefix), then `baseUrl`; anything else is a package.

Reachability follows such an import only when the file it reaches is inside the importer's package — a `paths` entry pointing at a sibling package is a boundary, like a package import.

### 2.2 · Attribution to micro frontend and screen

> **Given** an external call and its file
> **when** attributing it to a micro frontend
> **then** the longest unit directory containing the call's file decides; a file of a shared package that is no unit counts for every unit that imports it (the recorded location stays the package's file); a file under no unit and imported by none is dropped.

> **Given** an external call and the screens of that micro frontend
> **when** attributing it to a screen
> **then** internal-import reachability is followed from the screen.

Projects wrap the HTTP client in a module of their own (`services/api.js`), and that module belongs to the micro frontend containing it — the `micro frontend → endpoint` edge comes out right without following indirection. Knowing which **screen** calls requires following it, because the call lives in the service module.

> **Given** an Angular component whose template (`template` or `templateUrl`) uses the selector of a component or directive declared in the same package
> **when** following reachability
> **then** the template use counts as an import of the file declaring that selector.

In Angular the screen does not import what it renders: the template writes `<app-table>`, and the `NgModule` binds the selector to the class. Following imports alone left out everything below the screen. Element selectors (`app-x`) and attribute selectors (`[appX]`, `button[appX]`) are matched; class selectors and `:not(...)` are not, as they do not identify a use reliably. Selectors from another package — `<mat-table>` — are outside the unit, like package imports.

---

## 3. Global state

> **Given** a source file of a micro frontend importing a known state library (`react-redux`, `zustand`, `jotai`, `recoil`, `mobx-react-lite`, `pinia`)
> **when** there is a read walking a path into the state (`useSelector((state) => state.cart)`)
> **then** an access is recorded, with library and path.

Identification is by import specifier, never by variable name.

> **Given** a state write in that same file (`dispatch(addProduct(item))`)
> **then** it is **not** extracted.

The call site reveals the action's name, not the slice it changes; finding the slice would mean following the reducer, which may not even be in the repository. Recording both in one list would mix state paths with action names.

> **Given** a source file of a micro frontend calling `localStorage` or `sessionStorage`
> **when** the call is `getItem(key)`, `setItem(key, …)` or `removeItem(key)`
> **then** an access is recorded, with the storage as library, the key as path, and `read` or `write`.

Web Storage is global state, not a message: the key is the slice, and whoever writes sends nothing to anyone — it leaves the data there for whoever comes. The writes enter here, unlike in the libraries, because `setItem("token", …)` names the slice as plainly as `getItem("token")` does. The receiver must be `localStorage` or `sessionStorage` itself: matching on the method name alone would turn every class with a `getItem` into shared state. The key must carry **literal** text — a literal, a constant that resolves, or a template whose runtime segments become `{param}`; a key held in a variable yields nothing. That costs recall and buys precision, and the trade was paid for — falling back to the variable's name paired two copies of the same theme provider that had nothing to do with each other, each with a parameter called `storageKey`.

> **Given** a function of the project whose key argument to `localStorage`/`sessionStorage` is one of its own parameters, with at most literal text before and after it (`` localStorage.getItem(`app:${key}`) ``)
> **when** another call in the repository resolves to that function — by name, by import, as a member of a default-exported object or namespace, through `this`, or through a field whose type is the function's class
> **then** that call is a storage access with the key from the argument in that position, wrapped in the same text, and `read` or `write` for each storage call the function makes.

Applied in layers until nothing new is found, as with HTTP wrappers. The access belongs to the **caller's** file and unit, not the function's: a helper in a shared package is no unit's, and the units that call it are the ones coupled by the key. Once filled in, a runtime segment of the key becomes `{param}`, as below: `` save(`cart_${id}`) `` is `cart_{param}`.

> **Given** a state access inside a named function
> **when** that function, or one around it, has no use (the rule of §4 for ends of channels)
> **then** the access is not recorded.

> **Given** a micro frontend whose own code creates a Redux store (`createStore` from `redux`, `configureStore` from `@reduxjs/toolkit`)
> **when** it reads through `react-redux`
> **then** the read is **not** recorded: it reads its own store, which no other unit shares — two units with a `lookup` slice each, in two stores, share nothing.

A runtime segment of the key becomes `{param}`: `` `${user.handle}_provider` `` is `{param}_provider`, the same slice for every user — the contract is the key's format, like the path of a URL. A key with no literal text at all (`getItem(key)`) names no slice and yields nothing. A constant (`const CART_KEY = "cart"`) resolves by name when the name has a single value in the repository.

> **Given** every state access already extracted, and a slice accessed by two or more micro frontends
> **then** undirected `global-state` communication edges are derived between every pair.

A slice is library **and** path: the `user` key of `localStorage` and the `user` slice of a Redux store are different data.

---

## 4. Communication

Four tiers, all producing the same artefact. Producer and consumer are paired by **channel name**, which is the contract between the two ends, not by the shape of the call — except in tier 0, where the declaration names both ends itself.

> **Tier 0 — declared by the technology.**
> **Given** an orchestrator that registers an application with `customProps`
> **then** one directed channel per key is recorded, from the orchestrator to that application.

This is the only channel that needs no pairing: the registration names **both** ends at once. Who injects is the orchestrator, who receives is the application named there, and each key is a channel. The edge is therefore directed, unlike the ones born of two ends meeting over a channel name, which can be symmetric.

> **Given** an end of a channel (tiers 1 to 3) inside a named function
> **when** that function, or one around it, has no use — not exported and never referenced in its file, or exported from a file other files import without bringing that name (by name, namespace, `export *`, `import()` or `require`)
> **then** the end is not recorded.

A function nobody calls communicates nothing. Files no project file imports, and class methods, count as live: their consumer may be the framework, an entry point or a host.

> **Tier 1 — platform primitives.**
> **Given** the source files of a micro frontend
> **when** one of them has `dispatchEvent(new CustomEvent(channel))` with `addEventListener`, or `BroadcastChannel`, or `postMessage`
> **then** communication is recorded.

These are browser APIs: they hold in any project, with no configuration.

Web Storage was a channel here, with `setItem` producing and `getItem` consuming; it is now global state (§3).

**Cross-window `postMessage`.** Distinguished from `BroadcastChannel` by arity: the latter takes the payload alone, because its channel is in the constructor; the former takes payload and target origin, and then the channel travels **inside** the payload. That is convention, not API — the platform defines no channel name here — so the channel is read from a `type`, `action`, `event` or `name` field of an object literal, and nothing is recorded when the payload is not a literal. On the consuming side the single `addEventListener("message", …)` handles every channel, so what separates them are the comparisons inside the handler — `event.data.type === "cart:updated"` — and only literals compared against one of those fields, inside that handler, count.

> **Tier 1b — shared RxJS subject.**
> **Given** a symbol imported from a module
> **when** it receives `.next(…)` or `.subscribe(…)`
> **then** communication is recorded on the channel `module#symbol`.

The canonical channel between Angular micro frontends, and the one case where the channel is not a string but the identity of a symbol: two units importing the same `cart$` from the same module are the two ends of one channel. The receiver has to be bound by an import — without that requirement `this.http.get(url).subscribe(…)` becomes communication and an entire Angular project turns to noise. Imports from `rxjs` itself are excluded: those are the library, not a channel.

> **Tier 2 — known buses.**
> **Given** a source file importing `mitt`, `eventemitter3`, `tiny-emitter` or `pubsub-js`
> **when** the value coming from it is used to publish or subscribe
> **then** communication is recorded.

Not a naming heuristic: if the imported module is `mitt`, whatever comes out of it is an event bus.

> **Tier 3 — declared mechanism.**
> **Given** the communication spec
> **when** it declares the module, the export and the position of the channel argument
> **then** those calls become recognised.

For the project's own wrapper, which no catalogue knows. The declaration is **additive and optional**: every mechanism above is found without it, and the spec only adds what a catalogue cannot know. Without one the result is not empty.

> **Given** a declared mechanism
> **when** it produces no communication at all
> **then** the run reports it.

A declaration whose `module` does not match the real import specifier yields zero in silence, and zero is a plausible result — the system may genuinely not use that channel. Without the warning a typo and a true absence are indistinguishable, which is exactly what happened on the reference repository, where the declared `publishEvent` and `subscribeToTopic` do not exist in the code at all.

---
