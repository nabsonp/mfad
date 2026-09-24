# Extraction rules — Module Federation

What the Module Federation reconstructor reads from source, and under which conditions. Each rule as *given / when / then*.

Written from the implementation in `src/damfe/adapters/driven/reconstruction/modulefederation/`, and checked against a real system: [diego-coronado/microfrontend-healthcare-system](https://github.com/diego-coronado/diego-coronado-microfrontend-healthcare-system), seven Vite units.

No rule executes the analysed code, reaches the network, or consults a language model.

---

## 1. Inputs

| input | what it is | example |
|---|---|---|
| **repository** | the directory handed to `damfe reconstruct`, minus generated trees | `healthcare-system/` |
| **federation config** | a source file whose name starts with `webpack.config`, `vite.config`, `rspack.config`, `module-federation.config`, `federation.config` or `next.config` | `pharmacy/vite.config.ts` |
| **federation declaration** | the object given to the federation builder, read into `name`, `exposes`, `remotes` and `shared` | `{ name: "hs-pharmacy", exposes: { "./Pharmacy": "./src/pages/Pharmacy.tsx" } }` |
| **unit directory** | the directory whose `package.json` contains the config | `pharmacy/` |
| **fragment catalogue** | every unit's `exposes` keys, gathered before consumption is looked for | `{ "hs-pharmacy": ["Pharmacy"] }` |

---

## 2. Discovery

### 2.1 · Unit inventory

Module Federation has no orchestrator: no file registers the system's units. Each unit declares itself in its own build config, and the system is what emerges when those declarations are read together. Discovery therefore sweeps configs rather than starting from one file.

> **Given** the repository
> **when** a federation config contains a call to `ModuleFederationPlugin`, `withModuleFederation`, `NxModuleFederationPlugin`, `federation` or `moduleFederationPlugin`, carrying an object with a `name`
> **then** that object declares a micro frontend, identified by `name`.

The search is for the configuration object, not for the plugin. The same declaration ships under four wrappers — webpack's plugin, `@originjs/vite-plugin-federation`, Rspack's, and Nx's `withModuleFederation` — and they all receive the same shape. Matching plugin names would miss the wrappers, which is how an entire Nx project reads as having no federation at all.

Both `new ModuleFederationPlugin({…})` and `withModuleFederation({…})` are recognised: the first is a `new_expression` in the tree and the second a `call_expression`. Looking for only one returns nothing across a whole webpack project.

### 2.2 · The package behind a unit

> **Given** a unit and its directory
> **when** the `package.json` there declares a `name` different from the federation `name`
> **then** it is recorded in `metadata.package`.

A unit's federation name is its identity on the network and need not match the published package. `hs-pharmacy` living in a package called `pharmacy` is normal, and both names are worth keeping: one is how remotes address it, the other how the repository names it.

### 2.3 · Host without a host

Host and remote are not exclusive roles here: a unit can consume remotes and be consumed at the same time. What can be stated from the declarations is who consumes without being consumed.

> **Given** every unit's `remotes`
> **when** a unit declares remotes and appears in nobody else's
> **then** it takes `role = "shell"`, with `mounts` listing the remotes it consumes.

This is the closest thing Module Federation defines to an orchestrator. When every unit consumes another, no unit is marked — which is the honest answer, not a failure: in a fully bidirectional system there is no host.

---

## 3. Composition

### 3.1 · Exposed fragments

> **Given** a federation declaration
> **when** it carries `exposes`
> **then** each key is a fragment of that unit, and its value resolves to the internal file, trying the path as given, then with each known extension, then as a directory with an `index`.

`exposes` is an explicit declaration, which is why it is trusted directly: the unit states what it publishes, and nothing has to be inferred from naming or from which exports happen to exist.

> **Given** an exposed module
> **when** its body only re-exports names declared elsewhere — `export { Card } from "./ui/card"` — rather than defining what it publishes
> **then** the count of re-exported names goes into `metadata.reexports`.

A module shaped like that is a catalogue of parts rather than a part, which is the shape of a component library. It is recorded as a signal and changes no rule: a library can expose one component per entry and show no barrel, and a remote can expose a barrel of pages. The shape catches the common case and never proves what the unit is — and telling a shared library from a micro frontend everyone depends on is a judgement about the thing, not about the graph, since both look identical in it.

### 3.2 · Static consumption

> **Given** the fragment catalogue and a source file
> **when** it imports from `remote/Exposed`, where `remote` names a unit and `Exposed` is one of its exposed paths without the leading `./`
> **then** a `FragmentImport` is recorded between the two.

Both ends are declared here: the publisher says `exposes`, the consumer says `remotes`, and the import only matches when the two declarations meet.

The longest prefix wins, because a unit's name can contain a slash: `@org/app1/Button` is unit `@org/app1` publishing `./Button`.

### 3.3 · Dynamic consumption

> **Given** a source file
> **when** it calls `import("remote/Exposed")`, typically inside `lazy(() => …)`
> **then** the same applies, and the local name comes from the variable declaration enclosing the call.

This is how a host loads a remote page, and it is not an optional style. Fetching code at the moment of use is the point of the technology, and the framework requires a lazy boundary for it. Reading only static imports finds the shared libraries and misses exactly the pages — the consumption that defines the system. On the healthcare system it was the difference between 7 and 12 imports, with every remote page among the missing five.

### 3.4 · Where a fragment appears

> **Given** a fragment import and the screens of the consuming unit
> **when** a screen's component is the fragment's local name
> **then** that screen, and only that one, is recorded on the render site.

> **Given** a fragment import whose local name matches no screen
> **when** a screen reaches the render site's file through relative imports
> **then** that screen is recorded on the render site.

Exact match first, because falling back to reachability in a routing file would return every screen declared there — routers usually declare all of them in one place.

---

## 4. Screens and routes

### 4.1 · Declared screens

> **Given** the source files under a unit's directory
> **when** one has `<Route path=… element=… />`
> **then** each occurrence is a screen of that unit.

> **Given** a route's `element`
> **when** it wraps the component — `element={<Suspense fallback={…}><Pharmacy /></Suspense>}`
> **then** the screen's component is the innermost capitalised one, not the wrapper.

`Suspense` is the lazy boundary remote loading requires, and it appears on every route of a federated host. Keeping the outer name would give the same component as the screen of every route in the system.

> **Given** a screen and the file declaring its route
> **when** the component resolves through that file's imports
> **then** the screen's file is the **component's** file, not the router's.

Pointing at the router makes every screen reach everything the router imports, and fragment-to-screen attribution turns to noise: each screen inherits the dependencies of all the others.

### 4.2 · Routes of a unit

> **Given** a unit's screens
> **then** its routes are the routes of those screens.

Module Federation resolves remote code loading and says nothing about URLs, so there is no route to read from the declaration. A unit with no router has no routes, and that is correct: it answers no URL.

---

## 5. Beyond composition

Navigation, external calls, global state and communication do not depend on how the system is composed, and are described in [common.md](common.md).

---

## 6. Known limits

| | |
|---|---|
| Declarations built at runtime | `federation(myConfig)` with the object assembled elsewhere is not read; resolving it means evaluating the module |
| `remotes` URLs | the remote's address is usually an environment variable, so only the alias is read, never where it points |
| Shared dependencies | `shared` is recorded as names, with versions and options ignored |
| Runtime API | `import("remote/x")` built from a variable, and the low-level `__webpack_init_sharing__` / `loadRemote` path, are not recognised |
| Route ownership | with no `activeWhen`, ownership comes from screens; a unit with no router contributes nothing to it |
