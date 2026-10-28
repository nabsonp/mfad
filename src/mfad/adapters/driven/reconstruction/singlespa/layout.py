"""
Routes declared through `single-spa-layout`.

There are two ways to say which application answers for which URL. The
usual one is the `activeWhen` of `registerApplication`. The other is
single-spa-layout, which moves that decision into a template:

    <template id="single-spa-layout">
      <single-spa-router>
        <route path="/produtos">
          <application name="@org/mfe-produtos"></application>
        </route>
      </single-spa-router>
    </template>

Under a layout the applications do NOT need any `activeWhen` — the
layout engine turns the `path` into an activity function. Reading only
the registration, in that case, returns the application's name and no
route, and the result looks valid: a whole system with no route owners,
no navigation and no screens, with nothing indicating that information
was missing.

Here the template is read and the application/route pairs are
recovered. Nested routes concatenate, as in single-spa-layout.

The layout is read in the two forms the documentation describes: inside
`<template id="single-spa-layout">`, in the page's HTML, and as its own
file whose root is `<single-spa-router>` — the `microfrontend-layout.html`
that `create-single-spa` generates and the code passes to
`constructRoutes(microfrontendLayout)`. Reading only the first left
every system created by the official generator without routes.

`<route default>` answers when no other route matches. It owns no
prefix, so the application enters the layout without a route. The same
holds for an application outside any `<route>` — navigation bar,
footer: it stays mounted all the time, and owns no URL. Giving it the
route `/` turned every `"/"` in the code into navigation to it.

The JavaScript form — `constructRoutes({ routes: [...] })` — is read
when the argument is an object literal, which is how it is written. An
argument built in a variable or coming from another module is not
resolved: that would require evaluating the code.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


class _LayoutReader(HTMLParser):
    """Walks the layout accumulating the path of the nested routes."""

    #: The elements that open a layout: the template in the page, or
    #: the root of the layout file.
    ROOTS = ("template", "single-spa-router")

    def __init__(self):
        super().__init__(convert_charrefs=True)

        #: the tag that opened the layout, while inside it
        self.opened_by: str | None = None
        self.depth: list[str | None] = []
        self.found: dict[str, list[str]] = {}

    def handle_starttag(self, tag, attrs):

        values = dict(attrs)

        if self.opened_by is None:

            if tag == "template" and values.get("id") == "single-spa-layout":
                self.opened_by = tag

            elif tag == "single-spa-router":
                self.opened_by = tag

            return

        if tag == "route":
            # `None` marks the default route: below it there is no prefix.
            self.depth.append(
                None if "default" in values else (values.get("path", "") or "")
            )
            return

        if tag == "application":

            name = values.get("name")

            if not name:
                return

            routes = self.found.setdefault(name, [])

            route = self._route()

            if route is not None:
                routes.append(route)

    def handle_endtag(self, tag):

        if tag == self.opened_by:
            self.opened_by = None

        elif tag == "route" and self.depth and self.opened_by:
            self.depth.pop()

    def _route(self) -> str | None:
        """Concatenates the `path` of the routes enclosing the application."""

        if None in self.depth or not self.depth:
            return None

        parts = [part.strip("/") for part in self.depth if part.strip("/")]

        return "/" + "/".join(parts) if parts else "/"


def layouts(tree) -> dict[Path, dict[str, list[str]]]:
    """
    File → (application → routes), from the repository's layouts.

    Per file, and not merged, because the layout also says WHO mounts:
    the package containing it is the orchestrator of those
    applications. A repository may have more than one system, each with
    its own.

    Returns empty when there is no layout, which is the common case.
    """

    found: dict[Path, dict[str, list[str]]] = {}

    for file_path in tree.markup_files():

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if "single-spa-layout" not in content and "single-spa-router" not in content:
            continue

        reader = _LayoutReader()

        try:
            reader.feed(content)
        except Exception:
            continue

        if reader.found:
            found[file_path] = {
                name: sorted(set(routes)) for name, routes in reader.found.items()
            }

    return found


def routes_from_construct(root, source, reader) -> dict[str, list[str]]:
    """
    Application → routes, read from `constructRoutes({ routes: [...] })`.

    The JavaScript form of the same layout, equivalent to the template:

        constructRoutes({
          routes: [
            { type: "route", path: "/produtos", routes: [
              { type: "application", name: "@org/mfe-produtos" }
            ]}
          ]
        })

    Only object literals are read. `constructRoutes(minhaConfig)` is
    left out — resolving that would require evaluating the module, and
    what looks like a route there may be built at runtime.
    """

    found: dict[str, list[str]] = {}

    for call in reader.find_all(root, "call_expression"):

        function = call.child_by_field_name("function")
        arguments = call.child_by_field_name("arguments")

        if not function or not arguments:
            continue

        name = reader.text(function, source).split(".")[-1].strip()

        if name != "constructRoutes":
            continue

        for child in arguments.named_children:

            if child.type == "object":
                _walk_object(child, source, reader, [], found)

    return {name: sorted(set(routes)) for name, routes in found.items()}


def _walk_object(node, source, reader, depth, found) -> None:
    """A configuration node: a route stacks a path, an application registers."""

    fields = {}

    for pair in node.named_children:

        if pair.type != "pair":
            continue

        key_node = pair.child_by_field_name("key")
        value_node = pair.child_by_field_name("value")

        if key_node and value_node:
            fields[reader.strip_quotes(reader.text(key_node, source))] = (
                value_node
            )

    kind = (
        reader.strip_quotes(reader.text(fields["type"], source))
        if "type" in fields
        else ""
    )

    if kind == "application" or ("name" in fields and "path" not in fields):

        name = reader.strip_quotes(reader.text(fields["name"], source))

        if name:
            parts = [part.strip("/") for part in depth if part.strip("/")]

            found.setdefault(name, []).append(
                "/" + "/".join(parts) if parts else "/"
            )

        return

    nested = depth

    if "path" in fields:
        nested = depth + [
            reader.strip_quotes(reader.text(fields["path"], source))
        ]

    for key in ("routes", "children"):

        if key not in fields:
            continue

        for child in fields[key].named_children:

            if child.type == "object":
                _walk_object(child, source, reader, nested, found)
