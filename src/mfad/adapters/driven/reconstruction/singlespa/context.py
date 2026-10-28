"""
Shared state of a reconstruction.

The repository is scanned ONCE. During that scan the two things the
rest of the process needs are collected together: the repository's
constants and the `registerApplication` calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
import re

from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.singlespa import layout
from mfad.adapters.driven.reconstruction.ast import (
    ModuleResolver,
    AstReader,
    RouteConstantTable,
    SourceTree,
    SymbolIndex,
)
from mfad.adapters.driven.reconstruction.singlespa import sizing
from mfad.adapters.driven.reconstruction.templates import AngularTemplates
from mfad.domain import CodeSize


@dataclass
class Registration:
    """
    A `registerApplication` found in the orchestrator.

    It is single-spa's source of truth about which applications exist
    — including the ones that have no package of their own.
    """

    name: str
    active_when: list[str]
    specifier: str | None
    declared_in: Path

    #: How `activeWhen` was written: `literal` when it is strings or a
    #: list of strings, `function` when it is an activity function,
    #: `absent` when there is none.
    #:
    #: The API accepts `(location) => boolean`, and a function cannot
    #: be resolved statically. What is extracted from it are the string
    #: literals that appear inside, which gets the common cases right
    #: and silently gets the rest wrong — a function with no literal
    #: returns no route, a function that tests a literal negatively
    #: returns a route the application does not own. Consumers need to
    #: know the difference.
    active_when_form: str = "absent"

    #: `customProps` as key -> value, with an empty value when it is
    #: not a literal.
    custom_props: dict[str, str] = field(default_factory=dict)

    #: Entry file, when it is already known.
    #:
    #: Filled in by the bottom-up discovery, which starts from the file
    #: that exports the lifecycles instead of starting from the
    #: registration. On that path there is no specifier to resolve: the
    #: file IS the starting point.
    entrypoint: Path | None = None


@dataclass
class ScanContext:

    repository: Path
    tree: SourceTree
    reader: AstReader
    routes: RouteConstantTable
    registrations: list[Registration] = field(default_factory=list)
    packages: dict[str, Path] = field(default_factory=dict)

    #: application -> routes declared in a layout template
    layout_routes: dict[str, list[str]] = field(default_factory=dict)

    #: layout file -> (application -> routes). Whoever declares the
    #: layout is the orchestrator of the applications it names.
    layouts: dict[Path, dict[str, list[str]]] = field(default_factory=dict)

    #: path -> (physical lines, lines of code)
    measurements: dict[Path, tuple[int, int]] = field(default_factory=dict)

    _templates: AngularTemplates | None = field(default=None, repr=False)

    _symbols: SymbolIndex | None = field(default=None, repr=False)

    #: HTTP calls already extracted, per set of units: navigation needs
    #: them too (`api_calls.requests_of`)
    _api: dict = field(default_factory=dict, repr=False)

    #: Angular routes file → prefixes under which a `loadChildren`
    #: mounts it (`routers.angular`)
    _angular_mounts: dict | None = field(default=None, repr=False)

    @classmethod
    def build(cls, repository: Path) -> "ScanContext":

        tree = SourceTree(repository)

        context = cls(
            repository=repository,
            tree=tree,
            reader=AstReader(),
            routes=RouteConstantTable(),
        )

        context.packages = context._index_packages()

        context._scan()

        context.layouts.update(layout.layouts(tree))

        for declared in context.layouts.values():
            for name, routes in declared.items():
                context.layout_routes.setdefault(name, []).extend(routes)

        context.layout_routes = {
            name: sorted(set(routes))
            for name, routes in context.layout_routes.items()
        }

        context.routes.resolve_pending()

        return context

    def relative(self, path: Path) -> str:
        return self.tree.relative(path)

    def layout_routes_of(self, name: str) -> list[str] | None:
        """
        The routes the layout gives an application, or `None` if it does not name it.

        The layout names the application by the import map specifier,
        and the unit is named by its `package.json`. When the two
        match, the link is direct. When they do not, the single-spa
        convention is for the specifier to be `@org/<pacote>`: the name
        without the scope is compared. Any similarity beyond that —
        prefixes, suffixes — would be guessing, and is left out.
        """

        if name in self.layout_routes:
            return self.layout_routes[name]

        wanted = unscoped(name)

        matches = [
            routes
            for declared, routes in self.layout_routes.items()
            if unscoped(declared) == wanted
        ]

        # Two specifiers from different scopes with the same name:
        # ambiguous, and neither is chosen.
        return matches[0] if len(matches) == 1 else None

    def templates(self) -> AngularTemplates:
        """
        The template-based link between components, indexed once.

        Lazy: only whoever asks about reachability needs it, and the
        index reads every file that declares a component.
        """

        if self._templates is None:
            self._templates = AngularTemplates(
                self.reader, list(self.tree.source_files())
            )

        return self._templates

    def symbols(self) -> SymbolIndex:
        """Functions, exports and what each call refers to — read on demand."""

        if self._symbols is None:
            self._symbols = SymbolIndex(self.reader, self.package_entry)

        return self._symbols

    #: Where a package declares the code that is imported from it, in order.
    #: https://nodejs.org/api/packages.html#package-entry-points
    ENTRY_FIELDS = ("source", "module", "main", "types", "typings")

    ENTRY_FALLBACKS = ("src/index", "lib/index", "index")

    def package_entry(self, specifier: str) -> Path | None:
        """
        The file that `import ... from "@org/common"` loads, when the
        package is in the corpus itself: a monorepo workspace or a
        sibling repository. An outside package (`react`) has no file.
        """

        if not specifier or specifier.startswith((".", "/")):
            return None

        segments = specifier.split("/")
        size = 2 if specifier.startswith("@") else 1

        directory = self.packages.get("/".join(segments[:size]))

        if directory is None:
            return None

        subpath = "/".join(segments[size:])

        if subpath:
            return ModuleResolver.resolve("./" + subpath, directory / "package.json") or ModuleResolver.resolve(
                "./src/" + subpath, directory / "package.json"
            )

        try:
            manifest = json.loads((directory / "package.json").read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

        entries = [manifest.get(name) for name in self.ENTRY_FIELDS]

        for entry in [item for item in entries if isinstance(item, str)] + list(self.ENTRY_FALLBACKS):

            # `main` usually points to the build (`dist/index.js`), which
            # is not in the repository; the `.d.ts` points to the source next to it.
            entry = entry.removesuffix(".d.ts")

            found = ModuleResolver.resolve("./" + entry.lstrip("./"), directory / "package.json")

            if found is not None:
                return found

        return None

    def size_of(self, directory: Path) -> "CodeSize":
        """Sums the measurements of the files under a directory."""

        return sizing.total(
            [
                measurement
                for path, measurement in self.measurements.items()
                if directory in path.parents
            ]
        )

    def package_dir(self, file_path: Path) -> Path:

        directory = file_path.parent

        # The second test stops at the filesystem root: a path resolved
        # through a symbolic link may not have the repository as an ancestor.
        while directory != self.repository and directory != directory.parent:

            if (directory / "package.json").is_file():
                return directory

            directory = directory.parent

        return self.repository

    def _index_packages(self) -> dict[str, Path]:

        index: dict[str, Path] = {}

        for manifest_file in self.tree.manifests():

            try:
                manifest = json.loads(
                    manifest_file.read_text(encoding="utf-8")
                )
            except Exception:
                continue

            name = manifest.get("name")

            if name:
                index.setdefault(name, manifest_file.parent)

        return index

    def _scan(self) -> None:

        for file_path in self.tree.source_files():

            try:
                root, source = self.reader.parse(file_path)
            except Exception:
                continue

            self.routes.index_file(root, source)

            self.measurements[file_path] = sizing.measure(root, source)

            # The JavaScript form of the layout lives in the code, not in
            # the template, so this is where it is collected.
            declared = layout.routes_from_construct(root, source, AstReader)

            if declared:
                self.layouts[file_path] = declared

            self.registrations.extend(
                self._registrations(root, source, file_path)
            )

    def _registrations(
        self,
        root: Node,
        source: bytes,
        file_path: Path,
    ) -> list[Registration]:

        found: list[Registration] = []

        for node in AstReader.find_all(root, "call_expression"):

            function = node.child_by_field_name("function")

            if not function:
                continue

            if AstReader.text(function, source) != "registerApplication":
                continue

            registration = self._registration(node, source, file_path)

            if registration:
                found.append(registration)

        return found

    def _registration(
        self,
        node: Node,
        source: bytes,
        file_path: Path,
    ) -> Registration | None:
        """
        Reads a `registerApplication` in the two accepted forms:

            registerApplication({ name, app, activeWhen })
            registerApplication(name, loadingFn, activeWhen)
        """

        arguments = node.child_by_field_name("arguments")

        if not arguments:
            return None

        parts = [
            child
            for child in arguments.named_children
            if child.type != "comment"
        ]

        if not parts:
            return None

        if parts[0].type == "object":
            name, active_when, loader, form, custom_props = (
                self._object_form(parts[0], source)
            )
        else:
            name, active_when, loader, form, custom_props = (
                self._positional_form(parts, source)
            )

        if not name:
            return None

        return Registration(
            name=name,
            active_when=active_when,
            specifier=(
                self._loader_specifier(loader, source) if loader else None
            ),
            declared_in=file_path,
            active_when_form=form,
            custom_props=custom_props,
        )

    def _object_form(
        self,
        node: Node,
        source: bytes,
    ) -> tuple[str | None, list[str], Node | None, str, dict[str, str]]:

        name: str | None = None
        active_when: list[str] = []
        loader: Node | None = None
        form = "absent"
        custom_props: dict[str, str] = {}

        for pair in node.named_children:

            if pair.type != "pair":
                continue

            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")

            if not key_node or not value_node:
                continue

            key = AstReader.strip_quotes(AstReader.text(key_node, source))

            if key == "name":
                name = self._literal_name(value_node, source)

            elif key == "activeWhen":
                active_when, form = self._active_when(value_node, source)

            elif key == "app":
                loader = value_node

            elif key == "customProps":
                custom_props = self._property_names(value_node, source)

        return name, active_when, loader, form, custom_props

    def _positional_form(
        self,
        parts: list[Node],
        source: bytes,
    ) -> tuple[str | None, list[str], Node | None, str, dict[str, str]]:

        name = self._literal_name(parts[0], source)

        loader = parts[1] if len(parts) > 1 else None

        active_when, form = (
            self._active_when(parts[2], source)
            if len(parts) > 2
            else ([], "absent")
        )

        custom_props = (
            self._property_names(parts[3], source) if len(parts) > 3 else {}
        )

        return name, active_when, loader, form, custom_props

    @staticmethod
    def _literal_name(node: Node, source: bytes) -> str | None:
        """
        The application name, only when written as text.

        `registerApplication(appName, ...)` inside a loop registers
        whatever comes at runtime. Taking the identifier's text as the
        name created an application called `appName`. Without a literal
        name the registration is discarded, and the lifecycle-based
        discovery finds the unit through its own package.
        """

        if node.type == "string":
            return AstReader.strip_quotes(AstReader.text(node, source)) or None

        if node.type == "template_string" and not any(
            child.type == "template_substitution" for child in node.named_children
        ):
            return AstReader.strip_quotes(AstReader.text(node, source)) or None

        return None

    #: Activity function forms that resolve statically.
    #:
    #: The API accepts `(location) => boolean`, and an arbitrary
    #: function cannot be resolved. But the ones that appear in real
    #: code are few and have a fixed shape, and recognizing them is the
    #: difference between extracting the right route and sweeping
    #: literals hoping to get it right.
    ACTIVITY_SHAPES = (
        # (l) => l.pathname.startsWith("/users")
        r"""\.startsWith\(\s*["'`](?P<r>[^"'`]+)["'`]""",
        # (l) => l.pathname === "/users"
        r"""pathname\s*={2,3}\s*["'`](?P<r>[^"'`]+)["'`]""",
        # (l) => l.pathname.includes("/users")
        r"""\.includes\(\s*["'`](?P<r>[^"'`]+)["'`]""",
        # pathToActiveWhen("/users")
        r"""pathToActiveWhen\(\s*["'`](?P<r>[^"'`]+)["'`]""",
    )

    def _active_when(
        self,
        node: Node,
        source: bytes,
    ) -> tuple[list[str], str]:
        """
        The routes of `activeWhen`, and how they were obtained.

        `literal` when they are strings or a list of strings, and then
        there is nothing to interpret. `function` when it is an activity
        function of a recognized shape — `startsWith`, `pathname`
        comparison, `includes`, `pathToActiveWhen` —, which resolves
        with the same confidence as a literal. `opaque` when it is a
        function of unknown shape: then what remains are whatever string
        literals are inside, which may not be routes at all.
        """

        FUNCTIONS = {
            "arrow_function",
            "function_expression",
            "function_declaration",
            "identifier",
            "call_expression",
        }

        if node.type == "array":

            routes: list[str] = []
            forms: set[str] = set()

            for child in node.named_children:

                found, form = self._active_when(child, source)

                routes.extend(found)
                forms.add(form)

            for level in ("opaque", "function", "literal"):
                if level in forms:
                    return routes, level

            return routes, "absent"

        if node.type not in FUNCTIONS:
            return self._string_literals(node, source), "literal"

        text = AstReader.text(node, source)

        recognised = []

        for shape in self.ACTIVITY_SHAPES:
            recognised.extend(
                found.group("r") for found in re.finditer(shape, text)
            )

        if recognised:
            return sorted(set(recognised)), "function"

        return self._string_literals(node, source), "opaque"

    #: Nodes whose text is the value itself.
    LITERALS = {"string", "number", "true", "false", "null"}

    @classmethod
    def _property_names(cls, node: Node, source: bytes) -> dict[str, str]:
        """
        The keys of an object literal, and the values that are static.

        A literal value is hand-written configuration and says
        something about the system. A value that is a function or a
        variable is data built at runtime, and then only the key
        survives — recorded with an empty value, because knowing the
        key exists is already information.
        """

        found: dict[str, str] = {}

        for pair in node.named_children:

            # `customProps: { store }` — the shorthand form is also a
            # key, and it is usually precisely the shared object's.
            if pair.type == "shorthand_property_identifier":
                found[AstReader.text(pair, source)] = ""
                continue

            if pair.type != "pair":
                continue

            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")

            if not key_node:
                continue

            key = AstReader.strip_quotes(AstReader.text(key_node, source))

            value = ""

            if value_node and value_node.type in cls.LITERALS:
                value = AstReader.strip_quotes(
                    AstReader.text(value_node, source)
                )

            found[key] = value

        return dict(sorted(found.items()))

    @staticmethod
    def _string_literals(node: Node, source: bytes) -> list[str]:

        return [
            AstReader.strip_quotes(AstReader.text(literal, source))
            for literal in AstReader.find_all(node, "string")
        ]

    @staticmethod
    def _loader_specifier(node: Node, source: bytes) -> str | None:
        """
        Extracts the module loaded by `app`:

            () => System.import("@org/mfe-users")
            () => import("./monolito")
            "@org/mfe-users"
        """

        if node.type in {"string", "template_string"}:
            return AstReader.strip_quotes(AstReader.text(node, source))

        for call in AstReader.find_all(node, "call_expression"):

            function = call.child_by_field_name("function")

            if not function:
                continue

            text = AstReader.text(function, source)

            if text != "import" and not text.endswith(".import"):
                continue

            arguments = call.child_by_field_name("arguments")

            if not arguments:
                continue

            for child in arguments.named_children:

                if child.type in {"string", "template_string"}:
                    return AstReader.strip_quotes(
                        AstReader.text(child, source)
                    )

        return None


def unscoped(name: str) -> str:
    """`@org/Meu_App` → `meu-app`: the package name without the scope."""

    return name.rpartition("/")[2].lower().replace("_", "-")
