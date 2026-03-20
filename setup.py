from setuptools import setup

plugin_identifier = "mesh_repeatability"
plugin_package = "octoprint_mesh_repeatability"
plugin_name = "OctoPrint-MeshRepeatability"
plugin_version = "0.2.0"
plugin_description = "Captures and compares Marlin M420 V meshes for repeatability testing. Features auto-capture on print done/failed/cancelled, rotating 50-record buffer, delta stats, and CSV export."
plugin_author = "MVP Author"
plugin_author_email = "you@example.com"
plugin_url = "https://github.com/yourusername/OctoPrint-MeshRepeatability"
plugin_license = "AGPLv3"

setup(
    name=plugin_name,
    version=plugin_version,
    description=plugin_description,
    author=plugin_author,
    author_email=plugin_author_email,
    url=plugin_url,
    license=plugin_license,
    packages=[plugin_package],
    include_package_data=True,
    zip_safe=False,
    entry_points={
        "octoprint.plugin": [
            "mesh_repeatability = octoprint_mesh_repeatability:__plugin_load__"
        ]
    }
)
