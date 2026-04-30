"""multicz — multi-component versioning for monorepos."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("multicz")
except PackageNotFoundError:  # editable install before metadata is built
    __version__ = "0.0.0"

__all__ = ["__version__"]
