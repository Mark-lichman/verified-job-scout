"""Tiny HTTP helpers on the standard library, so the tool has no dependencies."""
import json
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; verified-job-scout/0.1; +https://github.com/Mark-lichman/verified-job-scout)"


class Response:
    def __init__(self, status, text, url):
        self.status = status
        self.text = text
        self.url = url

    def json(self):
        try:
            return json.loads(self.text)
        except ValueError:
            return None


def request(url, data=None, headers=None, timeout=25, method=None):
    """Return a Response. Never raises for HTTP errors: callers read .status.
    Network failures (DNS, timeout) return status 0."""
    h = {"User-Agent": UA, "Accept": "application/json, text/html;q=0.9, */*;q=0.5"}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return Response(r.status, r.read().decode("utf-8", "replace"), r.geturl())
    except urllib.error.HTTPError as e:
        try:
            text = e.read().decode("utf-8", "replace")
        except Exception:
            text = ""
        return Response(e.code, text, url)
    except Exception as e:  # timeouts, DNS, TLS
        return Response(0, str(e), url)


def get_json(url, **kw):
    r = request(url, **kw)
    return r.status, (r.json() if r.status == 200 else None)


def post_json(url, data, **kw):
    r = request(url, data=data, method="POST", **kw)
    return r.status, (r.json() if r.status == 200 else None)
