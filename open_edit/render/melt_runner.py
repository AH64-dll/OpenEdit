"""Melt subprocess execution: command building, timeout, and cache mediation."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from open_edit.render.cache import RenderCache
from open_edit.render.profiles import RenderProfile, profile_to_mlt_args


class MeltTimeoutError(Exception):
    """Raised when melt exceeds its wall-clock budget."""


class MeltRunner:
    """Build and run melt commands, mediating the render cache.

    Cache lookup happens before emit (fresh hits short-circuit the render);
    ``cache_put`` stores the final MP4 after overlay burning.
    """

    def __init__(
        self,
        melt_bin: str,
        cache: Optional[RenderCache] = None,
        nice_level: int = 10,
        encoder_backend: Optional[str] = None,
    ):
        self.melt_bin = melt_bin
        self.cache = cache
        self.nice_level = nice_level
        self.encoder_backend = encoder_backend

    def cached(self, key: str) -> Optional[Path]:
        """Look up a cached render for ``key`` (None if absent)."""
        if self.cache is None:
            return None
        return self.cache.get(key)

    def is_fresh(self, path: Path) -> bool:
        """True if the cached file is younger than the cache freshness window."""
        if self.cache is None:
            return False
        return self.cache.is_fresh(path)

    def cache_put(self, key: str, source_path: str | Path) -> Path:
        """Copy ``source_path`` into the cache under ``key``. Returns the cached path."""
        if self.cache is None:
            return Path(source_path)
        return self.cache.put(key, source_path)

    def build_command(
        self,
        xml_path: Path,
        output_mp4: Path,
        profile: RenderProfile,
        mode: str = "proxy",
    ) -> list[str]:
        """Build the melt command line."""
        args = [self.melt_bin, str(xml_path), "-consumer", f"avformat:{output_mp4}"]
        args += profile_to_mlt_args(profile, backend=self.encoder_backend, mode=mode)
        if self.nice_level > 0 and os.name == "posix":
            return ["nice", "-n", str(self.nice_level)] + args
        return args

    def run(
        self,
        xml_path: Path,
        output_mp4: Path,
        profile: RenderProfile,
        mode: str,
        timeout_s: float,
    ) -> subprocess.CompletedProcess:
        """Run melt against ``xml_path``; raise MeltTimeoutError on timeout."""
        cmd = self.build_command(xml_path, output_mp4, profile, mode=mode)
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise MeltTimeoutError(f"melt timed out after {timeout_s:g}s") from exc
