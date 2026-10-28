"""
Fixes for what was missing (agent-judge, part 2, October 2026).

The agent pointed out what the reconstruction failed to extract in
sampled MFEs; each omission was checked in the code. One test per
fixed defect, with a minimal repository written from the technology's
documentation. The list is in `estudo/avaliacao/correcoes-reconstrucao.md`.
"""

from conftest import mfe, root_config


ROOT = root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"})


def accesses(architecture):
    return sorted(
        (item.microfrontend, item.library, item.path, item.access)
        for item in architecture.state_accesses
    )


# ----------------------------------------------------------------------
# 14. Storage key with a runtime part
# ----------------------------------------------------------------------


def test_storage_key_with_a_runtime_part_becomes_a_pattern(system):
    """
    `` `${user.handle}_${PROVIDER}` `` is the same key for every user:
    the variable part becomes `{param}`, and the rest is still the contract.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                const PROVIDER = "payment_provider";
                export default function Root({ user }) {
                  localStorage.getItem(`${user?.handle}_${PROVIDER}`);
                  localStorage.removeItem(`${user?.handle}_${PROVIDER}`);
                  return null;
                }
            """),
        },
        prefix="@org/",
    )

    assert accesses(architecture) == [
        ("catalog", "localStorage", "{param}_payment_provider", "read"),
        ("catalog", "localStorage", "{param}_payment_provider", "write"),
    ]


# ----------------------------------------------------------------------
# 21. `localStorage.clear()`
# ----------------------------------------------------------------------


def test_storage_clear_writes_every_key(system):
    """
    `clear()` empties the storage
    (https://developer.mozilla.org/docs/Web/API/Storage/clear): it is a
    write to every key, recorded as `*`.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                export default function Root() {
                  return <button onClick={() => window.localStorage.clear()} />;
                }
            """),
        },
        prefix="@org/",
    )

    assert accesses(architecture) == [("catalog", "localStorage", "*", "write")]


# ----------------------------------------------------------------------
# 24. `useSelector` under another name
# ----------------------------------------------------------------------


def test_typed_selector_hook_is_a_selector(system):
    """
    Redux Toolkit says to declare `useAppSelector` once and use it in
    place of `useSelector`
    (https://redux.js.org/usage/usage-with-typescript#define-typed-hooks),
    in both forms: assignment and `useSelector.withTypes()`.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { useAppSelector } from "./hooks";
                import { useTypedSelector } from "./typed";
                export default function Root() {
                  const user = useAppSelector((state) => state.user);
                  const cart = useTypedSelector((state) => state.cart.items);
                  return null;
                }
            """),
            "catalog/src/hooks.ts": """
                import { TypedUseSelectorHook, useSelector } from "react-redux";
                export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;
            """,
            "catalog/src/typed.ts": """
                import { useSelector } from "react-redux";
                export const useTypedSelector = useSelector.withTypes<RootState>();
            """,
        },
        prefix="@org/",
    )

    assert accesses(architecture) == [
        ("catalog", "redux", "cart.items", "read"),
        ("catalog", "redux", "user", "read"),
    ]


def calls(architecture):
    return sorted((call.microfrontend, call.method, call.path) for call in architecture.api_calls)


# ----------------------------------------------------------------------
# 16. URL built with `new URL(...)`
# ----------------------------------------------------------------------


def test_url_built_with_the_url_constructor(system):
    """
    `new URL(path, base)` (https://developer.mozilla.org/docs/Web/API/URL/URL):
    an absolute path keeps only the base's origin, and `toString()` and
    `href` return the whole URL.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                export default function Root() {
                  const url = new URL("/fhir/Composition", window.location.origin);
                  url.searchParams.append("type", "summary");
                  fetch(url.toString());
                  fetch(new URL("/fhir/Bundle", origin).href);
                  return null;
                }
            """),
        },
        prefix="@org/",
    )

    assert calls(architecture) == [
        ("catalog", "GET", "/fhir/Bundle"),
        ("catalog", "GET", "/fhir/Composition"),
    ]


# ----------------------------------------------------------------------
# 17 and 27. The function that wraps the client builds more than `${base}${url}`
# ----------------------------------------------------------------------


def test_wrapper_whose_url_continues_after_the_endpoint(system):
    """
    `${base}${endpoint}/${id}`: the parameter is the URL, and what follows
    is still its path. With a ternary between the form with and without
    id, what both have in common applies. With the base also received
    (`${base}${endpoint}`), the URL is the last parameter, as before.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { get, remove, update } from "./request";
                export default function Root() {
                  remove("/products", 3);
                  update("/carts", { Id: 1 });
                  get(process.env.API_URL, "/users");
                  return null;
                }
            """),
            "catalog/src/request.js": """
                import axios from "axios";
                const BASE = process.env.API_URL;
                export function remove(endpoint, id) {
                  return axios.delete(`${BASE}${endpoint}/${id}`);
                }
                export function get(base, endpoint) {
                  return axios.get(`${base}${endpoint}`);
                }
                export function update(endpoint, element) {
                  const path = element.Id ? `${BASE}${endpoint}/${element.Id}` : `${BASE}${endpoint}`;
                  return axios.put(path, element);
                }
            """,
        },
        prefix="@org/",
    )

    assert calls(architecture) == [
        ("catalog", "DELETE", "/products/{param}"),
        ("catalog", "GET", "/users"),
        ("catalog", "PUT", "/carts"),
    ]


# ----------------------------------------------------------------------
# 18. Destination in a template string
# ----------------------------------------------------------------------


def test_template_destination_reaches_a_dynamic_route(system):
    """
    `/movie/${id}` goes to the route `/movie/:id`
    (https://single-spa.js.org/docs/api#activewhen); the prefix `/movie/`,
    without the segment, does not reach it. Only substitutions, with no
    text, is not a destination.
    """

    architecture = system(
        {
            **root_config({"@org/catalog": "/catalog", "@org/movie": "/movie/:id"}),
            **mfe("catalog", "@org/catalog", """
                import { navigateToUrl } from "single-spa";
                export default function Root({ id, kind }) {
                  navigateToUrl(`/movie/${id}`);
                  navigateToUrl(`/${kind}/${id}`);
                  return null;
                }
            """),
            **mfe("movie", "@org/movie", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert [(item.target, item.resolved_url) for item in architecture.navigations] == [("movie", "/movie/{param}")]


# ----------------------------------------------------------------------
# 15. Owner of the destination through the internal routes
# ----------------------------------------------------------------------


def test_destination_owned_through_the_screens_of_another_unit(system):
    """
    With no matching `activeWhen`, the URL belongs to the application that
    has a screen on it (React Router's `<Route path>`,
    https://reactrouter.com/en/main/route/route), if only one does.
    """

    architecture = system(
        {
            **root_config({"@org/catalog": "/catalog", "@org/property": "/assets"}),
            **mfe("catalog", "@org/catalog", """
                import { Link } from "react-router-dom";
                export default function Root({ asset }) {
                  return <Link to={`/property/${asset.id}`}>x</Link>;
                }
            """),
            **mfe("property", "@org/property", """
                import { BrowserRouter, Route, Switch } from "react-router-dom";
                import { PropertyView } from "./property-view";
                export default function Root() {
                  return (
                    <BrowserRouter>
                      <Switch>
                        <Route path="/property/:assetId/edit"><PropertyView /></Route>
                      </Switch>
                    </BrowserRouter>
                  );
                }
            """),
            "property/src/property-view.js": "export const PropertyView = () => <main>p</main>;",
        },
        prefix="@org/",
    )

    assert [(item.source, item.target, item.resolved_url) for item in architecture.navigations] == [
        ("catalog", "property", "/property/{param}"),
    ]


# ----------------------------------------------------------------------
# 26. Units registered with the same name
# ----------------------------------------------------------------------


def test_orchestrators_with_the_same_package_name_stay_apart(system):
    """
    Two orchestrators, each in its own directory, both `@org/root-config`
    (the name `create-single-spa` generates): each one gets its
    directory's name, and what each one does still belongs to it.
    """

    shop = root_config({"@org/catalog": "/catalog"}, directory="shop-root")
    admin = root_config({"@org/checkout": "/checkout"}, directory="admin-root")

    admin["admin-root/src/org-root-config.js"] += (
        'window.dispatchEvent(new CustomEvent("session:logout"));\n'
    )

    architecture = system(
        {
            **shop,
            **admin,
            **mfe("catalog", "@org/catalog", """
                export default function Root() {
                  window.addEventListener("session:logout", () => {});
                  return null;
                }
            """),
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    ids = sorted(item.id for item in architecture.microfrontends)

    assert "admin-root" in ids and "shop-root" in ids

    assert [(item.source, item.target) for item in architecture.communications] == [("admin-root", "catalog")]


# ----------------------------------------------------------------------
# 12. Shared package code
# ----------------------------------------------------------------------


def test_shared_package_code_counts_for_each_unit_that_imports_it(system):
    """
    The monorepo's common package (https://docs.npmjs.com/cli/using-npm/workspaces)
    does not run on its own: the call and the access that live in it happen
    in each micro frontend that imports it, and the function that forwards
    the URL is a client for whoever calls it.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { usePerson, request } from "@org/common";
                export default function Root() {
                  usePerson();
                  request("/products");
                  return null;
                }
            """),
            **mfe("checkout", "@org/checkout", """
                import { usePerson } from "@org/common/src/person";
                export default function Root() {
                  usePerson();
                  return null;
                }
            """),
            "common/package.json": {"name": "@org/common", "main": "dist/index.js", "types": "src/index.d.ts"},
            "common/src/index.ts": 'export * from "./person";\nexport * from "./request";\n',
            "common/src/person.ts": """
                import axios from "axios";
                export function usePerson() {
                  localStorage.getItem("person_id");
                  return axios.get("/api/person");
                }
            """,
            "common/src/request.ts": """
                import axios from "axios";
                export function request(url) {
                  return axios.get(url);
                }
            """,
        },
        prefix="@org/",
    )

    assert calls(architecture) == [
        ("catalog", "GET", "/api/person"),
        ("catalog", "GET", "/products"),
        ("checkout", "GET", "/api/person"),
    ]

    assert accesses(architecture) == [
        ("catalog", "localStorage", "person_id", "read"),
        ("checkout", "localStorage", "person_id", "read"),
    ]
