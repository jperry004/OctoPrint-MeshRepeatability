from setuptools import setup

plugin_identifier = "mesh_repeatability"
plugin_package = "octoprint_mesh_repeatability"
plugin_name = "OctoPrint-MeshRepeatability"
plugin_version = "0.2.2"
plugin_description = "Captures and compares Marlin M420 V meshes for repeatability testing."
plugin_author = "jperry004"
plugin_author_email = "128223478+jperry004@users.noreply.github.com"
plugin_url = "https://github.com/jperry004/OctoPrint-MeshRepeatability"
plugin_license = "AGPLv3"

plugin_requires = []

additional_setup_parameters = {
    "python_requires": ">=3.7,<4",
}

try:
    import octoprint_setuptools
except ImportError:
    print(
        "Could not import OctoPrint's setuptools helpers. "
        "Make sure to run this inside OctoPrint's virtual environment."
    )
    import sys

    sys.exit(-1)


setup_parameters = octoprint_setuptools.create_plugin_setup_parameters(
    identifier=plugin_identifier,
    package=plugin_package,
    name=plugin_name,
    version=plugin_version,
    description=plugin_description,
    author=plugin_author,
    mail=plugin_author_email,
    url=plugin_url,
    license=plugin_license,
    requires=plugin_requires,
    additional_packages=[],
    ignored_packages=[],
    additional_data=[],
)

if additional_setup_parameters:
    from octoprint.util import dict_merge

    setup_parameters = dict_merge(setup_parameters, additional_setup_parameters)

setup(**setup_parameters)
