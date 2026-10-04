# Extraction rules — Angular Router

What the Angular route reader takes from source, and under which conditions. Each rule as *given / when / then*.

Written from the `Route` interface as documented at [angular.dev/api/router/Route](https://angular.dev/api/router/Route) and [angular.dev/guide/routing/define-routes](https://angular.dev/guide/routing/define-routes) — **not** from any analysed repository. The systems selected for the empirical study are the evaluation set, so no rule here was derived by reading one of them.

No rule executes the analysed code, reaches the network, or consults a language model.

---

## 1. Why this is a separate document

Routing and integration are different axes. single-spa and Module Federation say how units become a system; React Router, Angular Router and Vue Router say how **one unit** declares its screens. Any combination exists — single-spa with Angular, Module Federation with React — so the route reader belongs to neither reconstructor and is used by both.

Until this reader existed, screens came only from JSX `<Route>`. An Angular unit answered a URL and declared no screen at all, which is not a limitation of the integration technology but a missing axis.

---

## 2. Recognising a route table

> **Given** a source file
> **when** it holds an array whose elements are object literals carrying `path` together with one of `component`, `loadComponent`, `children`, `loadChildren` or `redirectTo`
> **then** that array is a route table.

`path` alone is not enough — any configuration object has a field by that name. What makes it a route is `path` **plus a destination**, and the destinations are exactly those five in the documented interface.

Recognition is of the table, not of its registration. `provideRouter(routes)`, `RouterModule.forRoot(routes)` and `forChild(routes)` all receive the same array, and the array is frequently declared in its own file (`app.routes.ts`) and registered elsewhere. Matching the registration call would miss it.

A nested array is skipped at the top level: it is already walked as the `children` of its parent.

---

## 3. Screens

> **Given** a route entry
> **when** it carries `component: X`
> **then** `X` is a screen, and its file is resolved through the file's imports.

> **Given** a route entry
> **when** it carries `loadComponent: () => import('./x').then(m => m.X)`
> **then** `X` is a screen, and its file is the specifier resolved relative to the declaring file.

The lazy form is the more direct of the two: the path to the file travels inside the specifier, so it needs no import table. The component's name comes from the capitalised symbol in the `.then(…)`, falling back to the last segment of the specifier.

> **Given** a route entry carrying only `redirectTo`
> **then** no screen is recorded.

A redirect answers a URL by sending the browser elsewhere. It renders nothing, so there is no screen.

---

## 4. Route composition

> **Given** a nested route entry
> **then** its route is the parent's route joined with its own `path` segment.

In Angular `path` is **relative**: `path: 'info'` inside `path: 'product/:id'` answers `/product/:id/info`. Reading the segment on its own would report a route the application does not have — the single most consequential difference from the React Router rules, where nested paths are commonly written absolute.

> **Given** a route entry with `path: ''`
> **then** its route is the parent's, or `/` at the top level.

The empty path is the documented way of declaring the default child, and it answers the parent's own URL.

---

## 5. Known limits

| | |
|---|---|
| `loadChildren` | the child routes live in another module and are not followed; the entry yields no screen. Resolving it means loading that module's own route table and composing the prefix across files |
| `matcher` | a custom `UrlMatcher` cannot be resolved statically, the same way an opaque single-spa activity function cannot. The interface forbids `path` alongside it, so the entry has no segment to read either |
| Route tables built at runtime | `provideRouter(buildRoutes())` and spreads of arrays assembled elsewhere are not read |
| `outlet` | named outlets are ignored: two entries on the same path for different outlets read as two screens |
| Template-level routing | `<router-outlet>` placement is not read; it says where a screen renders, not which screens exist |
