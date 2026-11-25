"""Strict filesystem path confinement for CLI automation and MCP servers (Anything-Craft contract).

Mirrors the `--automation-read-root` / `--automation-write-root` boundary used by `craft_box.py`:
- Resolves all symlinks via `os.path.realpath` before checking containment.
- Rejects `..` escapes, null bytes, and symlink pivots pointing outside declared roots.
- Enforces an explicit read size cap (`MAX_READ_BYTES = 32 MiB`) to prevent OOM DoS.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MAX_READ_BYTES = 32 * 1024 * 1024  # 32 MiB


class SandboxError(PermissionError):
    """Raised when a requested path violates read/write automation roots."""


def _canonical(path: str | Path) -> Path:
    s = str(path)
    if "\x00" in s:
        raise SandboxError("Null byte not allowed in path.")
    return Path(os.path.realpath(os.path.abspath(os.path.expanduser(s))))


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass
class PathSandbox:
    read_roots: list[Path] = field(default_factory=list)
    write_roots: list[Path] = field(default_factory=list)

    @classmethod
    def from_args(
        cls,
        read_roots: list[str] | None = None,
        write_roots: list[str] | None = None,
        default_cwd_if_empty: bool = False,
    ) -> "PathSandbox":
        r_list = [_canonical(p) for p in (read_roots or [])]
        w_list = [_canonical(p) for p in (write_roots or [])]
        if default_cwd_if_empty and not r_list and not w_list:
            cwd = _canonical(Path.cwd())
            r_list = [cwd]
            w_list = [cwd]
        return cls(read_roots=r_list, write_roots=w_list)

    def check_read(self, path: str | Path) -> Path:
        if not self.read_roots:
            raise SandboxError("Read access denied: no --automation-read-root configured.")
        cand = _canonical(path)
        if not any(_is_within(cand, root) for root in self.read_roots):
            raise SandboxError(f"Read path outside allowed roots: {path}")
        return cand

    def check_write(self, path: str | Path) -> Path:
        if not self.write_roots:
            raise SandboxError("Write access denied: no --automation-write-root configured.")
        s = str(path)
        if "\x00" in s:
            raise SandboxError("Null byte not allowed in path.")
        raw = Path(os.path.abspath(os.path.expanduser(s)))
        # Verify the closest existing ancestor after symlink resolution is inside a write root
        ancestor = raw
        tail_parts: list[str] = []
        while not ancestor.exists() and ancestor != ancestor.parent:
            tail_parts.append(ancestor.name)
            ancestor = ancestor.parent
        resolved_ancestor = Path(os.path.realpath(ancestor))
        cand = resolved_ancestor.joinpath(*reversed(tail_parts))
        if not any(_is_within(cand, root) for root in self.write_roots):
            raise SandboxError(f"Write path outside allowed roots: {path}")
        # If the final target itself already exists as a symlink, check its real target too
        if raw.exists() or raw.is_symlink():
            real_target = Path(os.path.realpath(raw))
            if not any(_is_within(real_target, root) for root in self.write_roots):
                raise SandboxError(f"Write target symlink escapes allowed roots: {path}")
            return real_target
        return cand

    def read_text_bounded(self, path: str | Path, max_bytes: int = MAX_READ_BYTES) -> str:
        resolved = self.check_read(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"File not found: {resolved}")
        size = resolved.stat().st_size
        if size > max_bytes:
            raise SandboxError(f"File exceeds size limit ({size} > {max_bytes} bytes): {resolved}")
        return resolved.read_text(encoding="utf-8")
