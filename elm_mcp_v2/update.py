"""In-place self-update for the download / point-at-a-file install.

The extracted ZIP is NOT a git checkout, so we can't `git pull`. Instead we
download the latest GitHub release tarball and copy it over the folder the host
points at (the one containing `run_server.py`). Stdlib only — no extra deps,
works on a locked-down box that can still reach GitHub.

For a pip/uvx ("managed") install we don't touch site-packages — we tell the
user to update via uvx/pip instead.
"""
from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import elm_mcp_v2

REPO = "brettscharm/elm-mcp-v2"


def install_root() -> Path:
    """Folder that holds the elm_mcp_v2 package (and run_server.py for a
    download install)."""
    return Path(elm_mcp_v2.__file__).resolve().parent.parent


def is_download_install() -> bool:
    """True if this is a point-at-a-file install we can update in place."""
    return (install_root() / "run_server.py").exists()


def _ver_tuple(v: str) -> tuple:
    try:
        return tuple(int(p) for p in v.lstrip("v").split(".")[:3] if p.isdigit()) or (0, 0, 0)
    except Exception:  # noqa: BLE001
        return (0, 0, 0)


def _get(url: str, accept: str | None = None) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": f"elm-mcp-v2/{elm_mcp_v2.__version__}",
        **({"Accept": accept} if accept else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def latest_tag() -> str | None:
    """Latest published release tag, or None on failure."""
    try:
        import json
        data = json.loads(_get(
            f"https://api.github.com/repos/{REPO}/releases/latest",
            accept="application/vnd.github+json").decode("utf-8"))
        return (data.get("tag_name") or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def _download_and_replace(tag: str, root: Path) -> int:
    """Download the tag tarball and copy its tree over `root`. Returns the
    number of files written."""
    url = f"https://github.com/{REPO}/archive/refs/tags/{tag}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        tgz = tmp_p / "src.tgz"
        tgz.write_bytes(_get(url))
        with tarfile.open(tgz) as tf:
            tf.extractall(tmp_p)  # noqa: S202 — trusted GitHub archive
        # GitHub tarballs contain a single top-level dir (repo-<tag>/)
        srcdir = next(p for p in tmp_p.iterdir() if p.is_dir())
        written = 0
        for src in srcdir.rglob("*"):
            if src.is_dir():
                continue
            rel = src.relative_to(srcdir)
            # never overwrite local secrets / venvs
            if rel.parts and rel.parts[0] in (".venv", ".env"):
                continue
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            written += 1
        return written


def self_update() -> dict:
    """Update in place if a newer release exists. Returns a result dict:
    {ok, updated, current, latest, message}."""
    current = elm_mcp_v2.__version__
    res = {"ok": False, "updated": False, "current": current,
           "latest": None, "message": ""}

    root = install_root()
    if not is_download_install():
        res["message"] = (
            f"This is a managed (pip/uvx) install in `{root}`, not a download. "
            f"Update it with `uvx --refresh --from git+https://github.com/{REPO} "
            f"elm-mcp-v2`, or `pip install -U git+https://github.com/{REPO}`.")
        return res
    if not os.access(root, os.W_OK):
        res["message"] = (
            f"The install folder `{root}` isn't writable, so I can't update in "
            f"place. Re-download the ZIP from github.com/{REPO} and replace the "
            f"folder by hand.")
        return res

    tag = latest_tag()
    res["latest"] = tag
    if not tag:
        res["message"] = ("Couldn't reach GitHub to check for updates "
                          f"(you're on v{current}). Try again, or re-download the ZIP.")
        return res
    if _ver_tuple(tag) <= _ver_tuple(current):
        res["ok"] = True
        res["message"] = f"Already on the latest version (v{current})."
        return res

    try:
        n = _download_and_replace(tag, root)
    except Exception as e:  # noqa: BLE001
        res["message"] = (f"Update download/extract failed ({type(e).__name__}: {e}). "
                          f"You can re-download the ZIP from github.com/{REPO} manually.")
        return res

    res.update(ok=True, updated=True)
    res["message"] = (f"Updated **v{current} → {tag}** in `{root}` ({n} files). "
                      f"Fully quit and reopen your host to load it.")
    return res
