"""
O destino de um link do React Router parte da base do roteador.

https://reactrouter.com/api/declarative-routers/BrowserRouter#basename e
https://reactrouter.com/api/data-routers/createBrowserRouter#optsbasename:
debaixo de `basename="/loja"`, `<Link to="/">` leva a `/loja`. Num micro
frontend single-spa, a base costuma ser a rota de ativação dele, e o
link para `/` fica dentro da própria unidade.
"""

from conftest import mfe, root_config


ROOT = root_config({"@org/home": "/", "@org/shop": "/shop", "@org/blog": "/blog"})

HOME = mfe("home", "@org/home", "export default () => null;")


def pairs(architecture):
    return sorted((item.source, item.target, item.resolved_url) for item in architecture.navigations)


def test_links_under_the_router_basename_stay_in_the_unit(system):

    architecture = system(
        {
            **ROOT,
            **HOME,
            **mfe("shop", "@org/shop", """
                import { BrowserRouter, Routes, Route, Link, useNavigate } from "react-router-dom";

                function Menu() {
                  const navigate = useNavigate();
                  return (
                    <nav>
                      <Link to="/">Início da loja</Link>
                      <button onClick={() => navigate("/cart")}>Carrinho</button>
                      <a href="/blog">Blog</a>
                    </nav>
                  );
                }

                export default function Root() {
                  return (
                    <BrowserRouter basename="/shop">
                      <Menu />
                      <Routes><Route path="/" element={<p />} /></Routes>
                    </BrowserRouter>
                  );
                }
            """),
            **mfe("blog", "@org/blog", "export default () => null;"),
        },
        prefix="@org/",
    )

    # O `<a href>` não passa pelo roteador: `/blog` é absoluto.
    assert pairs(architecture) == [("shop", "blog", "/blog")]


def test_data_router_basename_and_the_v5_history(system):

    architecture = system(
        {
            **ROOT,
            **HOME,
            **mfe("shop", "@org/shop", """
                import { createBrowserRouter, RouterProvider } from "react-router-dom";
                import Cart from "./Cart";
                const router = createBrowserRouter([{ path: "/cart", element: <Cart /> }], { basename: "/shop" });
                export default () => <RouterProvider router={router} />;
            """),
            "shop/src/Cart.js": """
                import { useHistory } from "react-router-dom";
                export default function Cart() {
                  const history = useHistory();
                  return <button onClick={() => history.push("/")}>Voltar</button>;
                }
            """,
            **mfe("blog", "@org/blog", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert pairs(architecture) == []


def test_without_basename_the_link_leaves_the_unit(system):
    """Sem base, `to="/"` é a raiz do site: navegação para quem a possui."""

    architecture = system(
        {
            **ROOT,
            **HOME,
            **mfe("shop", "@org/shop", """
                import { BrowserRouter, Link } from "react-router-dom";
                export default () => <BrowserRouter><Link to="/">Início</Link></BrowserRouter>;
            """),
            **mfe("blog", "@org/blog", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert pairs(architecture) == [("shop", "home", "/")]
