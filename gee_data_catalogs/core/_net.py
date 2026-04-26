"""Network helpers shared across the plugin."""

from urllib.parse import urlparse
from urllib.request import Request


def require_https(url) -> None:
    """Raise ValueError unless the URL uses the https scheme.

    Bandit B310 flags ``urllib.request.urlopen`` calls because they accept any
    scheme, including ``file://``. Every urlopen call site in this plugin only
    fetches resources from known https endpoints (GitHub releases, GitHub raw,
    plugin repository metadata). Calling this guard before urlopen makes that
    invariant explicit, both at runtime and to security scanners.

    Args:
        url: Either a string URL or a :class:`urllib.request.Request`.

    Raises:
        ValueError: If the resolved scheme is not exactly ``https``.
    """
    if isinstance(url, Request):
        target = url.full_url
    else:
        target = url
    scheme = urlparse(target).scheme.lower()
    if scheme != "https":
        raise ValueError(f"Refusing to fetch non-https URL: {target!r}")
