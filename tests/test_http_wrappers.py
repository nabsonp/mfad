"""
HTTP client wrapped in a project function, and Angular's.

A function that forwards a parameter as a client's URL is a client
too. The examples follow the documentation of `fetch`
(https://developer.mozilla.org/docs/Web/API/Fetch_API), of axios
(https://axios-http.com/docs/instance) and of Angular's `HttpClient`
(https://angular.dev/guide/http/making-requests).
"""

from conftest import angular_unit, mfe, root_config

from mfad.adapters.driven.antipatterns.rules.hammering_apis import HammeringApis


ROOT = root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"})


#: The most common wrapper: environment base, header and options
#: forwarded to `fetch`.
FETCH_API = """
    const API_BASE_URL = process.env.API_URL;

    export async function fetchApi(url, options = {}) {
      const headers = { ...options.headers, Authorization: token() };
      return fetch(`${API_BASE_URL}${url}`, { ...options, headers });
    }
"""


def calls_of(architecture):
    return sorted((call.microfrontend, call.method, call.path, call.client) for call in architecture.api_calls)


def test_function_that_forwards_the_url_is_a_client(system):

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { fetchApi } from "./api";
                export default function Root() {
                  fetchApi("/accounts");
                  return null;
                }
            """),
            "catalog/src/api.js": FETCH_API,
            **mfe("checkout", "@org/checkout", """
                import { fetchApi } from "./api";
                export default function Root() {
                  fetchApi("/accounts", { method: "POST", body: "{}" });
                  return null;
                }
            """),
            "checkout/src/api.js": FETCH_API,
        },
        prefix="@org/",
    )

    assert calls_of(architecture) == [
        ("catalog", "GET", "/accounts", "fetch"),
        # The verb comes from the options the caller passed and the function forwarded.
        ("checkout", "POST", "/accounts", "fetch"),
    ]

    [found] = HammeringApis().check(architecture)

    assert found.metadata["path"] == "/accounts"


def test_wrappers_are_followed_in_layers_and_through_local_values(system):
    """A service that calls the wrapper with its own parameter, and the URL built beforehand."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { fetchStatement, remove } from "./statement";
                export default function Root() {
                  fetchStatement(accountId);
                  remove("/statement/42");
                  return null;
                }
            """),
            "catalog/src/api.js": FETCH_API,
            "catalog/src/statement.js": """
                import { fetchApi } from "./api";

                function statementUrl(accountId) {
                  return `/account/${accountId}/statement`;
                }

                export async function fetchStatement(accountId) {
                  const url = statementUrl(accountId);
                  return fetchApi(url);
                }

                export const remove = (endpoint) => fetchApi(endpoint, { method: "DELETE" });
            """,
        },
        prefix="@org/",
    )

    assert calls_of(architecture) == [
        ("catalog", "DELETE", "/statement/42", "fetch"),
        ("catalog", "GET", "/account/{param}/statement", "fetch"),
    ]


def test_wrapper_members_of_a_default_export_and_of_a_namespace(system):

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import api from "./api";
                import * as client from "./api";
                export default function Root() {
                  api.get("/gigs?page=2");
                  client.post("/gigs/apply", {});
                  return null;
                }
            """),
            "catalog/src/api.js": """
                async function doFetch(endpoint, options = {}) {
                  let url;
                  url = process.env.API;
                  return fetch(`${url}${endpoint}`, { ...options });
                }
                export async function get(endpoint) {
                  return doFetch(endpoint, { headers: {} });
                }
                export async function post(endpoint, body) {
                  return doFetch(endpoint, { body, method: "POST" });
                }
                export default { get, post };
            """,
        },
        prefix="@org/",
    )

    assert calls_of(architecture) == [
        ("catalog", "GET", "/gigs", "fetch"),
        ("catalog", "POST", "/gigs/apply", "fetch"),
    ]


def test_client_instance_created_in_another_module(system):
    """`axios.create()` in a module, used by the name it exports."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { http as api } from "./http";
                export default function Root() {
                  api.get(`${process.env.API}/members/${name}`);
                  return null;
                }
            """),
            "catalog/src/http.js": """
                import axios from "axios";
                export const http = axios.create({ baseURL: "/" });
            """,
        },
        prefix="@org/",
    )

    assert calls_of(architecture) == [("catalog", "GET", "/members/{param}", "axios")]


def test_prefix_that_is_already_a_path_stays_a_call_of_its_own(system):
    """`"/api/" + endpoint` already names something; the function does not become a wrapper."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                export function get(endpoint) { return fetch("/api/" + endpoint); }
                export default function Root() {
                  get("/users");
                  return null;
                }
            """),
        },
        prefix="@org/",
    )

    assert calls_of(architecture) == [("catalog", "GET", "/api/{param}", "fetch")]


def test_angular_http_client_injected_by_type(system):
    """`HttpClient` is injected; the field's type is what identifies it."""

    architecture = system(
        angular_unit(
            "billing",
            {
                "invoices.service.ts": """
                    import { Injectable, inject } from "@angular/core";
                    import { HttpClient, HttpHeaders } from "@angular/common/http";

                    @Injectable({ providedIn: "root" })
                    export class InvoicesService {
                      private readonly client = inject(HttpClient);

                      constructor(private http: HttpClient) {}

                      list() {
                        return this.http.get<Invoice[]>("/api/invoices");
                      }

                      pay(id: string) {
                        return this.client.post(`/api/invoices/${id}/payment`, {});
                      }

                      raw() {
                        return this.http.request("PUT", "/api/invoices/batch");
                      }

                      headers() {
                        return new HttpHeaders().get("x");
                      }
                    }
                """,
            },
        )
    )

    assert calls_of(architecture) == [
        ("billing", "GET", "/api/invoices", "@angular/common/http"),
        ("billing", "POST", "/api/invoices/{param}/payment", "@angular/common/http"),
        ("billing", "PUT", "/api/invoices/batch", "@angular/common/http"),
    ]


def test_angular_services_that_wrap_the_http_client(system):
    """A generic request service and a domain service on top of it."""

    architecture = system(
        angular_unit(
            "billing",
            {
                "request.manager.ts": """
                    import { Injectable } from "@angular/core";
                    import { HttpClient } from "@angular/common/http";

                    @Injectable({ providedIn: "root" })
                    export class RequestManager {
                      private path: string;
                      constructor(private http: HttpClient) {}
                      setPath(service: string) { this.path = environment[service]; }
                      get(endpoint: string) {
                        return this.http.get<any>(`${this.path}${endpoint}`);
                      }
                      post(endpoint: string, element: any) {
                        return this.http.post<any>(`${this.path}${endpoint}`, element);
                      }
                    }
                """,
                "parameters.service.ts": """
                    import { Injectable } from "@angular/core";
                    import { RequestManager } from "./request.manager";

                    @Injectable()
                    export class ParametersService {
                      constructor(private requestManager: RequestManager) {}
                      get(endpoint: string) {
                        this.requestManager.setPath("PARAMETERS_SERVICE");
                        return this.requestManager.get(endpoint);
                      }
                    }
                """,
                "policy.component.ts": """
                    import { Component } from "@angular/core";
                    import { ParametersService } from "./parameters.service";

                    @Component({ selector: "app-policy", template: "<p></p>" })
                    export class PolicyComponent {
                      constructor(private parameters: ParametersService) {}
                      load() {
                        this.parameters.get(`parametro?query=TipoParametroId:${id}`);
                      }
                    }
                """,
            },
        )
    )

    # The base comes from the environment and ends in `/`; the caller
    # passes the path relative to it.
    assert calls_of(architecture) == [
        ("billing", "GET", "/parametro", "@angular/common/http"),
    ]


def test_call_in_a_function_nobody_calls_is_not_counted(system):
    """The same dead-code criterion as for communication and global state."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { listAccounts } from "./accounts";
                export default function Root() {
                  listAccounts();
                  return null;
                }
            """),
            "catalog/src/accounts.js": """
                export const listAccounts = () => fetch("/accounts");
                export const removeAccount = (id) => fetch(`/accounts/${id}`, { method: "DELETE" });
                function neverCalled() {
                  return fetch("/accounts/legacy");
                }
            """,
        },
        prefix="@org/",
    )

    assert calls_of(architecture) == [("catalog", "GET", "/accounts", "fetch")]
