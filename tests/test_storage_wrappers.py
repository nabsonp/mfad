"""
`localStorage` e `sessionStorage` embrulhados numa função do projeto.

A chave só aparece em quem chama a embrulhadora, e o acesso é de
quem chama: o arquivo de utilitários não grava nada sozinho. A API é
a da Web Storage
(https://developer.mozilla.org/docs/Web/API/Web_Storage_API).
"""

from conftest import angular_unit, mfe, root_config


ROOT = root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"})


def accesses(architecture):
    return sorted(
        (item.microfrontend, item.library, item.path, item.access, item.at.file)
        for item in architecture.state_accesses
    )


def test_function_that_forwards_the_key_is_storage(system):

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { setLocalStorageItem } from "./utils/windowUtils";
                export default function Root() {
                  return <button onClick={() => setLocalStorageItem("accountId", "1")} />;
                }
            """),
            "catalog/src/utils/windowUtils.ts": """
                export const setLocalStorageItem = (key: string, value: string): void => {
                  try {
                    window.localStorage.setItem(key, value);
                  } catch (error) {
                    console.error(error);
                  }
                };
            """,
            **mfe("checkout", "@org/checkout", """
                localStorage.getItem("accountId");
                export default () => null;
            """),
        },
        prefix="@org/",
    )

    assert accesses(architecture) == [
        ("@org/catalog", "localStorage", "accountId", "write", "catalog/src/root.component.js"),
        ("@org/checkout", "localStorage", "accountId", "read", "checkout/src/root.component.js"),
    ]


def test_shared_helper_is_attributed_to_each_caller(system):
    """O utilitário fora das unidades: quem acessa é quem chama."""

    storage = "../../shared/src/storage"

    architecture = system(
        {
            **ROOT,
            "shared/src/storage.js": """
                export function read(key) {
                  return JSON.parse(sessionStorage.getItem(key));
                }
                export function write(key, value) {
                  sessionStorage.setItem(key, JSON.stringify(value));
                }
                export default { read, write };
            """,
            **mfe("catalog", "@org/catalog", f"""
                import storage from "{storage}";
                export default function Root() {{
                  storage.write("token", "abc");
                  return null;
                }}
            """),
            **mfe("checkout", "@org/checkout", f"""
                import * as session from "{storage}";
                export default function Root() {{
                  session.read("token");
                  return null;
                }}
            """),
        },
        prefix="@org/",
    )

    assert accesses(architecture) == [
        ("@org/catalog", "sessionStorage", "token", "write", "catalog/src/root.component.js"),
        ("@org/checkout", "sessionStorage", "token", "read", "checkout/src/root.component.js"),
    ]


def test_layers_and_a_literal_prefix_in_the_key(system):

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { readPreference } from "./preferences";
                export default function Root() {
                  readPreference("theme");
                  return null;
                }
            """),
            "catalog/src/storage.js": """
                export function getItem(key) {
                  return localStorage.getItem(`app:${key}`);
                }
            """,
            "catalog/src/preferences.js": """
                import { getItem } from "./storage";
                export const readPreference = (name) => getItem("pref." + name);
            """,
        },
        prefix="@org/",
    )

    assert accesses(architecture) == [
        ("@org/catalog", "localStorage", "app:pref.theme", "read", "catalog/src/root.component.js"),
    ]


def test_angular_storage_service_injected_by_type(system):
    """Um método que lê e grava a mesma chave conta as duas coisas."""

    architecture = system(
        angular_unit(
            "billing",
            {
                "local-storage.service.ts": """
                    import { Injectable } from "@angular/core";

                    @Injectable({ providedIn: "root" })
                    export class LocalStorageService {
                      getItem<T>(key: string): T | null {
                        const item = localStorage.getItem(key);
                        return item ? (JSON.parse(item) as T) : null;
                      }
                      addItemToList<T>(key: string, value: T): void {
                        const current: T[] = JSON.parse(localStorage.getItem(key) ?? "[]");
                        localStorage.setItem(key, JSON.stringify([value, ...current]));
                      }
                    }
                """,
                "banner.component.ts": """
                    import { Component } from "@angular/core";
                    import { LocalStorageService } from "./local-storage.service";

                    @Component({ selector: "app-banner", template: "<p></p>" })
                    export class BannerComponent {
                      constructor(private storage: LocalStorageService) {}
                      close(id: string) {
                        this.storage.addItemToList("closedBanners", id);
                      }
                    }
                """,
            },
        )
    )

    assert accesses(architecture) == [
        ("billing", "localStorage", "closedBanners", "read", "billing/src/app/banner.component.ts"),
        ("billing", "localStorage", "closedBanners", "write", "billing/src/app/banner.component.ts"),
    ]


def test_methods_named_like_storage_are_not_storage(system):
    """`cache.getItem(key)` de uma classe qualquer, e chave de runtime."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { save } from "./cart";
                class Cache {
                  getItem(key) { return this.items.get(key); }
                }
                const cache = new Cache();
                export default function Root() {
                  cache.getItem("cart");
                  save(`cart_${userId}`);
                  return null;
                }
            """),
            "catalog/src/cart.js": """
                export function save(key) {
                  localStorage.setItem(key, "[]");
                }
            """,
        },
        prefix="@org/",
    )

    assert accesses(architecture) == []


def test_storage_access_in_a_function_nobody_calls_is_not_counted(system):
    """O mesmo critério de código morto da comunicação."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { getToken } from "./auth";
                export default () => <p>{getToken()}</p>;
            """),
            "catalog/src/auth.js": """
                export const getToken = () => localStorage.getItem("token");
                export const clearToken = () => localStorage.removeItem("token");
                function neverCalled() {
                  localStorage.setItem("token", "x");
                }
            """,
        },
        prefix="@org/",
    )

    assert accesses(architecture) == [
        ("@org/catalog", "localStorage", "token", "read", "catalog/src/auth.js"),
    ]
