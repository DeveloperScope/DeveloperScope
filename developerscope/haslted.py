from radon.metrics import h_visit  # Halstead
import git


def _is_python(path: str) -> bool:
    return path.endswith(".py")

def _halstead_effort_for_blob(blob: git.Blob) -> float:
    """Compute Halstead *effort* for a *single* blob – non‑blocking."""
    if not _is_python(blob.path):
        return 0.0
    code = blob.data_stream.read().decode("utf-8", errors="replace")
    if not code.strip():
        return 0.0
    try:
        h = h_visit(code).total if hasattr(h_visit(code), "total") else h_visit(code)
        return float(getattr(h, "effort", 0.0))
    except Exception:
        return 0.0


def halstead_effort(commit: git.Commit, *, changed_only: bool = True) -> float:
    """Return cumulative Halstead **effort** for the *Python* files in *commit*.

    If *changed_only* is True we look at the diff – cheaper and more relevant –
    otherwise we walk the whole tree.
    """
    total = 0.0
    if changed_only:
        parent = commit.parents[0]
        for diff in parent.diff(commit):
            blob = diff.b_blob or diff.a_blob
            if blob:
                total += _halstead_effort_for_blob(blob)
    else:
        for blob in commit.tree.traverse():
            if blob.type == "blob":
                total += _halstead_effort_for_blob(blob)
    return round(total, 2)