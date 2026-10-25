"""
Correções do que faltou (agent-judge, parte 2, outubro de 2026).

O agente apontou o que a reconstrução deixou de extrair em MFEs
sorteados; cada omissão foi conferida no código. Um teste por defeito
corrigido, com um repositório mínimo escrito a partir da documentação
da tecnologia. A lista está em `estudo/avaliacao/correcoes-reconstrucao.md`.
"""

from conftest import mfe, root_config


ROOT = root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"})


def accesses(architecture):
    return sorted(
        (item.microfrontend, item.library, item.path, item.access)
        for item in architecture.state_accesses
    )


# ----------------------------------------------------------------------
# 14. Chave de storage com trecho de runtime
# ----------------------------------------------------------------------


def test_storage_key_with_a_runtime_part_becomes_a_pattern(system):
    """
    `` `${user.handle}_${PROVIDER}` `` é a mesma chave para todo usuário:
    o trecho variável vira `{param}`, e o resto continua sendo o contrato.
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
    `clear()` esvazia o armazenamento
    (https://developer.mozilla.org/docs/Web/API/Storage/clear): é escrita
    em todas as chaves, registrada como `*`.
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
# 24. `useSelector` com outro nome
# ----------------------------------------------------------------------


def test_typed_selector_hook_is_a_selector(system):
    """
    O Redux Toolkit manda declarar `useAppSelector` uma vez e usá-lo no
    lugar de `useSelector`
    (https://redux.js.org/usage/usage-with-typescript#define-typed-hooks),
    nas duas formas: atribuição e `useSelector.withTypes()`.
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
# 16. URL montada com `new URL(...)`
# ----------------------------------------------------------------------


def test_url_built_with_the_url_constructor(system):
    """
    `new URL(caminho, base)` (https://developer.mozilla.org/docs/Web/API/URL/URL):
    caminho absoluto fica só com a origem da base, e `toString()` e `href`
    devolvem a URL inteira.
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
# 17 e 27. A função que embrulha o cliente monta mais que `${base}${url}`
# ----------------------------------------------------------------------


def test_wrapper_whose_url_continues_after_the_endpoint(system):
    """
    `${base}${endpoint}/${id}`: o parâmetro é a URL, e o que segue continua
    o caminho dela. Com ternário entre a forma com e sem id, vale o que as
    duas têm em comum. Com a base também recebida (`${base}${endpoint}`),
    a URL é o último parâmetro, como antes.
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
# 18. Destino em template string
# ----------------------------------------------------------------------


def test_template_destination_reaches_a_dynamic_route(system):
    """
    `/movie/${id}` vai para a rota `/movie/:id`
    (https://single-spa.js.org/docs/api#activewhen); o prefixo `/movie/`,
    sem o segmento, não a alcança. Só substituições, sem texto, não é destino.
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
# 15. Dono do destino pelas rotas internas
# ----------------------------------------------------------------------


def test_destination_owned_through_the_screens_of_another_unit(system):
    """
    Sem `activeWhen` que case, a URL é da aplicação que tem tela nela
    (`<Route path>` do React Router, https://reactrouter.com/en/main/route/route),
    se só uma tem.
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
# 26. Unidades registradas com o mesmo nome
# ----------------------------------------------------------------------


def test_orchestrators_with_the_same_package_name_stay_apart(system):
    """
    Dois orquestradores, cada um no seu diretório, ambos `@org/root-config`
    (o nome que o `create-single-spa` gera): cada um fica com o nome do
    diretório, e o que cada um faz continua sendo dele.
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
# 12. Código de pacote compartilhado
# ----------------------------------------------------------------------


def test_shared_package_code_counts_for_each_unit_that_imports_it(system):
    """
    O pacote comum do monorepo (https://docs.npmjs.com/cli/using-npm/workspaces)
    não roda sozinho: a chamada e o acesso que moram nele acontecem em cada
    micro frontend que o importa, e a função que repassa a URL é cliente
    para quem a chama.
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
