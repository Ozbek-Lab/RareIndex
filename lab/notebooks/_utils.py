import jwt
import os
import urllib.parse

import requests

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")


def _normalize_api_url(raw_url: str | None) -> str:
    url = (raw_url or "http://127.0.0.1:8000").strip()
    parts = urllib.parse.urlsplit(url)
    if parts.hostname == "localhost":
        netloc = "127.0.0.1"
        if parts.port:
            netloc += f":{parts.port}"
        if parts.username:
            auth = parts.username
            if parts.password:
                auth += f":{parts.password}"
            netloc = f"{auth}@{netloc}"
        parts = parts._replace(netloc=netloc)
        url = urllib.parse.urlunsplit(parts)
    return url


DJANGO_API_URL = _normalize_api_url(os.environ.get("DJANGO_API_URL"))


def _jwt_shape_ok(t: str | None) -> bool:
    return bool(t and str(t) != "None" and len(str(t).split(".")) == 3 and len(str(t)) >= 20)


def _qp_get(qp, key: str, default=None):
    if hasattr(qp, "get"):
        v = qp.get(key)
    else:
        try:
            v = qp[key]
        except (KeyError, TypeError):
            v = None
    if isinstance(v, list):
        v = v[0] if v else None
    if v is None or v == "":
        return default
    return v


def resolve_plot_token(mo) -> str | None:
    """Token from URL query, else optional env MARIMO_PLOT_JWT (local dev)."""
    qp = mo.query_params()
    t = _qp_get(qp, "token")
    if _jwt_shape_ok(t):
        return str(t)
    env_t = os.environ.get("MARIMO_PLOT_JWT") or os.environ.get("DJANGO_PLOT_JWT")
    if _jwt_shape_ok(env_t):
        return str(env_t)
    return None


def auth_prompt_mo(mo):
    """
    Markdown-only (no inline scripts). Marimo edit mode often does not run <script> in mo.Html(),
    which left the old AuthBridge stuck on 'Checking session…'.
    """
    import marimo as mo_module

    qp = mo.query_params()
    file_part = _qp_get(qp, "file") or _qp_get(qp, "notebook")

    auth_url = f"{DJANGO_API_URL.rstrip('/')}/authoring/marimo/"
    if file_part:
        auth_url += "?" + urllib.parse.urlencode({"file": str(file_part)})

    run_with_token_url = f"{DJANGO_API_URL.rstrip('/')}/authoring/marimo-run/"
    if file_part:
        run_with_token_url += "?" + urllib.parse.urlencode({"file": str(file_part)})

    mode = ""
    try:
        m = mo_module.app_meta().mode
        if m:
            mode = f"\n\n*Marimo mode: `{m}`*\n"
    except Exception:
        pass

    run_hint = (
        f"**Run server (e.g. port 8080):** [Open this app with `token` via Django]({run_with_token_url}) "
        f"— `marimo run` does not know your session; the URL must include `token=` or you must set "
        f"`MARIMO_PLOT_JWT` for the Marimo process.\n\n"
        if file_part
        else ""
    )

    return mo_module.md(
        f"### Plot data — Django JWT required\n\n"
        f"This notebook calls Django’s `/api/plot-data/` API. "
        f"You need a JWT in the page URL (`token=…`) or in the environment.\n\n"
        f"{run_hint}"
        f"**Edit in Marimo (e.g. port 8082):** [Open with editor token via Django]({auth_url}) — "
        f"log in if asked, then you’ll return here with `token` set.{mode}\n\n"
        f"**Local dev:** export a JWT and re-run cells:\n"
        f"```bash\n"
        f"export MARIMO_PLOT_JWT=\"…\"   # from /api/plot-token/ or issue_editor_plot_token()\n"
        f"```\n"
    )


def verify_token(token: str) -> int:
    if not SECRET_KEY:
        raise RuntimeError(
            "DJANGO_SECRET_KEY must be set in the environment for the Marimo process "
            "(must match Django SECRET_KEY used to sign plot JWTs)."
        )
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    return payload["user_id"]

def fetch_plot_data(token: str, model: str, config: dict) -> list:
    import json

    if not _jwt_shape_ok(token):
        raise ValueError(f"Invalid token provided to fetch_plot_data: {token}")

    qs = urllib.parse.urlencode({"model": model, "config": json.dumps(config)})
    r = requests.get(f"{DJANGO_API_URL}/api/plot-data/?{qs}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()["data"]
