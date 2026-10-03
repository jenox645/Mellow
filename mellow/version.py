"""Single source of truth for the app version.

Read by: server.py (/api/system → UI splash + sidebar), build_setup.py
(PyInstaller artifacts + passed to Inno Setup via /DAppVersion), and
build_linux_deb.py (.deb metadata). Bump it here and nowhere else.
"""
APP_VERSION = "2.3.0"
