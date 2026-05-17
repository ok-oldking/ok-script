import requests
from packaging.version import Version


class GetPyPiLatestVersion:
    def __call__(self, module_name):
        response = requests.get(f"https://pypi.org/pypi/{module_name}/json", timeout=30)
        response.raise_for_status()
        return response.json()["info"]["version"]

    def version_add_one(self, version, add_patch=False):
        parsed = Version(version)
        major = parsed.major
        minor = parsed.minor
        micro = parsed.micro + 1 if add_patch else parsed.micro
        if not add_patch:
            minor += 1
            micro = 0
        return f"{major}.{minor}.{micro}"
