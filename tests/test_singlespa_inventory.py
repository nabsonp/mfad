"""Inventário single-spa: quem é micro frontend, com quais rotas e telas."""

from conftest import by_id, mfe, root_config


ROOT_CONFIG = root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"})


def test_registered_applications_get_their_routes(system):

    architecture = system(
        {
            **ROOT_CONFIG,
            **mfe("catalog", "@org/catalog", "export default () => null;"),
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert by_id(architecture, "@org/catalog").routes == ["/catalog"]
    assert by_id(architecture, "@org/checkout").routes == ["/checkout"]


def test_root_component_named_with_dotted_suffix_is_the_screen(system):
    """`./root.component` é `root.component.js` — a extensão é acrescentada."""

    architecture = system(
        {
            **ROOT_CONFIG,
            **mfe("catalog", "@org/catalog", "export default () => null;"),
        },
        prefix="@org/",
    )

    screens = by_id(architecture, "@org/catalog").screens

    assert [screen.file for screen in screens] == ["catalog/src/root.component.js"]


def test_test_files_are_not_read(system):

    architecture = system(
        {
            **ROOT_CONFIG,
            **mfe("catalog", "@org/catalog", "export default () => null;"),
            "catalog/src/root.component.spec.js": """
                localStorage.setItem("token", "x");
            """,
            "catalog/src/__tests__/helpers.js": """
                localStorage.setItem("token", "x");
            """,
        },
        prefix="@org/",
    )

    assert architecture.state_accesses == []


def test_units_nested_in_a_monorepo_folder_own_their_code(system):
    """`apps/catalog/...` é de `@org/catalog`, não de uma unidade chamada `apps`."""

    catalog_root = """
        import { navigateToUrl } from "single-spa";

        export default function Root() {
          localStorage.setItem("token", "x");
          return <button onClick={() => navigateToUrl("/checkout")}>Comprar</button>;
        }
    """

    architecture = system(
        {
            **root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"}, "apps/root-config"),
            **mfe("apps/catalog", "@org/catalog", catalog_root),
            **mfe("apps/checkout", "@org/checkout", 'localStorage.getItem("token");'),
            "tools/script.js": 'fetch("/api/orders");',
        },
        prefix="@org/",
    )

    assert [(item.source, item.target) for item in architecture.navigations] == [
        ("@org/catalog", "@org/checkout")
    ]
    assert sorted(item.microfrontend for item in architecture.state_accesses) == [
        "@org/catalog",
        "@org/checkout",
    ]
    # Código fora de qualquer unidade não vira consumidor fantasma.
    assert architecture.api_calls == []
