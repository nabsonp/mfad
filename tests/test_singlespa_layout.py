"""
single-spa-layout e as outras fontes de rota.

Os layouts seguem https://single-spa.js.org/docs/layout-definition e o
que o `create-single-spa` gera para um root-config com layout.
"""

from conftest import by_id, mfe, package


LAYOUT_ROOT = {
    "root-config/package.json": package("@org/root-config", **{"single-spa": "^6", "single-spa-layout": "^2"}),
    # O que o gerador oficial escreve: o layout num arquivo próprio,
    # importado e passado a `constructRoutes`, e o registro sem nome
    # literal nenhum.
    "root-config/src/org-root-config.js": """
        import { registerApplication, start } from "single-spa";
        import { constructApplications, constructRoutes, constructLayoutEngine } from "single-spa-layout";
        import microfrontendLayout from "./microfrontend-layout.html";

        const routes = constructRoutes(microfrontendLayout);
        const applications = constructApplications({
          routes,
          loadApp({ name }) { return System.import(name); },
        });
        const layoutEngine = constructLayoutEngine({ routes, applications });

        applications.forEach(registerApplication);
        layoutEngine.activate();
        start();
    """,
    "root-config/src/microfrontend-layout.html": """
        <single-spa-router>
          <nav>
            <application name="@org/navbar"></application>
          </nav>
          <route path="catalog">
            <application name="@org/catalog"></application>
          </route>
          <route path="account">
            <route path="orders">
              <application name="@org/orders"></application>
            </route>
          </route>
          <route default>
            <application name="@org/not-found"></application>
          </route>
        </single-spa-router>
    """,
}


def test_layout_file_from_the_generator_gives_routes(system):

    architecture = system(
        {
            **LAYOUT_ROOT,
            **mfe("catalog", "@org/catalog", "export default () => null;"),
            **mfe("orders", "@org/orders", "export default () => null;"),
            **mfe("navbar", "@org/navbar", "export default () => null;"),
            **mfe("not-found", "@org/not-found", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert by_id(architecture, "@org/catalog").routes == ["/catalog"]
    # Rotas aninhadas concatenam.
    assert by_id(architecture, "@org/orders").routes == ["/account/orders"]
    # Fora de qualquer rota: sempre montada, dona de URL nenhuma.
    assert by_id(architecture, "@org/navbar").routes == []
    # A rota padrão não é dona de prefixo nenhum.
    assert by_id(architecture, "@org/not-found").routes == []


def test_the_package_declaring_the_layout_is_the_shell(system):

    architecture = system(
        {
            **LAYOUT_ROOT,
            **mfe("catalog", "@org/catalog", "export default () => null;"),
        },
        prefix="@org/",
    )

    shell = by_id(architecture, "@org/root-config")

    assert shell.role == "shell"
    assert "@org/catalog" in shell.mounts


def test_layout_inside_the_page_template(system):

    architecture = system(
        {
            "root-config/package.json": package("@org/root-config"),
            "root-config/src/index.ejs": """
                <html><head>
                <template id="single-spa-layout">
                  <single-spa-router>
                    <route path="catalog">
                      <application name="@org/catalog"></application>
                    </route>
                  </single-spa-router>
                </template>
                </head><body></body></html>
            """,
            "root-config/src/org-root-config.js": """
                import { constructRoutes } from "single-spa-layout";
                const routes = constructRoutes(document.querySelector("#single-spa-layout"));
            """,
            **mfe("catalog", "@org/catalog", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert by_id(architecture, "@org/catalog").routes == ["/catalog"]


def test_layout_name_matches_the_package_without_its_scope(system):
    """O layout diz `@org/catalog`; o `package.json`, `catalog`."""

    unscoped = mfe("catalog", "@org/catalog", "export default () => null;")
    unscoped["catalog/package.json"] = {"name": "catalog", "dependencies": {"single-spa": "^6"}}

    architecture = system({**LAYOUT_ROOT, **unscoped})

    assert by_id(architecture, "catalog").routes == ["/catalog"]
    assert "catalog" in by_id(architecture, "@org/root-config").mounts


ANGULAR_ENTRY = """
    import { enableProdMode, NgZone } from "@angular/core";
    import { platformBrowserDynamic } from "@angular/platform-browser-dynamic";
    import { Router, NavigationStart } from "@angular/router";
    import { singleSpaAngular } from "single-spa-angular";
    import { AppModule } from "./app/app.module";

    const lifecycles = singleSpaAngular({
      bootstrapFunction: () => platformBrowserDynamic().bootstrapModule(AppModule),
      template: "<app-root />",
      Router,
      NavigationStart,
      NgZone,
    });

    export const bootstrap = lifecycles.bootstrap;
    export const mount = lifecycles.mount;
    export const unmount = lifecycles.unmount;
"""


def test_angular_base_href_is_the_route_when_nothing_else_declares_one(system):
    """single-spa-angular: `APP_BASE_HREF` é o prefixo da montagem."""

    architecture = system(
        {
            "billing/package.json": package("billing", **{"single-spa-angular": "^9"}),
            "billing/src/main.single-spa.ts": ANGULAR_ENTRY,
            "billing/src/app/app-routing.module.ts": """
                import { NgModule } from "@angular/core";
                import { RouterModule, Routes } from "@angular/router";
                import { APP_BASE_HREF } from "@angular/common";
                import { InvoicesComponent } from "./invoices.component";

                const routes: Routes = [{ path: "invoices", component: InvoicesComponent }];

                @NgModule({
                  imports: [RouterModule.forRoot(routes)],
                  exports: [RouterModule],
                  providers: [{ provide: APP_BASE_HREF, useValue: "/billing/" }],
                })
                export class AppRoutingModule {}
            """,
            "billing/src/app/invoices.component.ts": """
                import { Component } from "@angular/core";
                @Component({ selector: "app-invoices", template: "<p></p>" })
                export class InvoicesComponent {}
            """,
        }
    )

    billing = by_id(architecture, "billing")

    assert billing.routes == ["/billing"]
    assert billing.metadata["routes_from"] == "APP_BASE_HREF"
