"""
Platforms with their own integration stay out of the analysis.

They use single-spa or Module Federation underneath, and an extractor
would recognize them and reconstruct them wrongly.
"""

import pytest

from conftest import mfe, package, reconstruct, root_config, write

from mfad.application.errors import UnsupportedPlatform
from mfad.composition import Container


@pytest.mark.parametrize(
    "dependency",
    ["@openmrs/esm-framework", "@edx/frontend-platform", "@openedx/frontend-platform"],
)
def test_repository_made_only_of_the_platform_is_refused(tmp_path, dependency):

    write(
        tmp_path,
        {
            # The vendored framework calls `registerApplication` underneath
            # and does not depend on itself: it is left out by package name.
            "libs/routes/package.json": {"name": "@openmrs/esm-routes"},
            "libs/routes/src/pages.js": 'import { registerApplication } from "single-spa";',
            "apps/home/package.json": package("@org/home", **{dependency: "^5"}),
            "apps/home/src/index.js": "export const x = 1;",
        },
    )

    with pytest.raises(UnsupportedPlatform):
        Container().reconstructor(None, tmp_path)


def test_platform_packages_are_left_out_and_the_rest_is_reconstructed(tmp_path):
    """An OpenMRS module next to regular units does not bring the system down."""

    write(
        tmp_path,
        {
            **root_config({"@org/catalog": "/catalog"}),
            **mfe("catalog", "@org/catalog", 'localStorage.getItem("token");'),
            "lab/package.json": package("@org/lab", **{"@openmrs/esm-framework": "^5"}),
            "lab/src/index.js": 'localStorage.getItem("token");',
        },
    )

    architecture = reconstruct(tmp_path, prefix="@org/")

    assert [item.microfrontend for item in architecture.state_accesses] == ["catalog"]
    assert Container().excluded_packages(tmp_path) == {"lab": "OpenMRS 3 (esm-framework)"}
