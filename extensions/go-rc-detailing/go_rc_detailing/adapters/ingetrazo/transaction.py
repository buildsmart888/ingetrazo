"""Transaction boundary: host owns undo, rollback and scene dirty state."""
from __future__ import annotations


def run_script(viewport, code: str, *, scope=None):
    from core.ai import run_transactional
    return run_transactional(viewport, code, scope or {"__name__": "__go_rc__"})
