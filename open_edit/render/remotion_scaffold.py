"""Frozen Remotion starter copied into each project's `.open_edit/remotion/`."""

from __future__ import annotations

from pathlib import Path

STARTER_FILES: dict[str, str] = {
    "package.json": """{
  "name": "open-edit-remotion-project",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "@remotion/bundler": "4.0.278",
    "@remotion/cli": "4.0.278",
    "@remotion/renderer": "4.0.278",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "remotion": "4.0.278"
  }
}
""",
    "tsconfig.json": """{
  "compilerOptions": {
    "target": "ES2018",
    "module": "commonjs",
    "jsx": "react-jsx",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*"]
}
""",
    "src/index.ts": """import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
""",
    "src/Root.tsx": """import React from "react";
import { Composition } from "remotion";
import { TitleCard } from "./compositions/TitleCard";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TitleCard"
        component={TitleCard}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ titleText: "Open Edit" }}
      />
    </>
  );
};
""",
    "src/compositions/TitleCard.tsx": """import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

export const TitleCard: React.FC<{ titleText: string }> = ({ titleText }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        backgroundColor: "#0b0f14",
        color: "white",
        fontSize: 72,
        fontFamily: "system-ui, sans-serif",
        opacity,
      }}
    >
      {titleText}
    </AbsoluteFill>
  );
};
""",
    "public/.gitkeep": "",
    "out/.gitkeep": "",
    "LICENSE_NOTICE.txt": """This Remotion starter is subject to Remotion's license.
See https://www.remotion.dev/docs/license and docs/REMOTION_LICENSE.md
in the Open Edit repository.
""",
}


FORBIDDEN_IMPORT_PATTERNS = (
    "node:fs",
    "node:child_process",
    "node:net",
    "node:http",
    "node:https",
    "child_process",
    "fs/promises",
    'from "fs"',
    "from 'fs'",
    'from "child_process"',
    "from 'child_process'",
    'from "net"',
    "from 'net'",
    'require("fs")',
    "require('fs')",
    'require("child_process")',
    "require('child_process')",
    "process.env",
    "eval(",
    "Function(",
)

ALLOWED_IMPORT_PREFIXES = (
    "remotion",
    "@remotion/",
    "react",
    "react/",
    "react-dom",
    "./",
    "../",
)


def ensure_remotion_scaffold(project_path: Path) -> Path:
    """Create the Remotion starter under ``.open_edit/remotion`` if missing."""
    root = project_path / ".open_edit" / "remotion"
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in STARTER_FILES.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(content, encoding="utf-8")
    return root


def validate_composition_source(source: str, *, max_bytes: int = 200_000) -> list[str]:
    """Return validation errors for AI-written Remotion TSX/TS source."""
    errors: list[str] = []
    raw = source.encode("utf-8")
    if len(raw) > max_bytes:
        errors.append(f"composition source exceeds {max_bytes} bytes")
    lowered = source
    for pat in FORBIDDEN_IMPORT_PATTERNS:
        if pat in lowered:
            errors.append(f"forbidden pattern in composition source: {pat}")
    # Soft allow-list: any import line must mention an allowed prefix.
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or "require(" in stripped:
            if not any(prefix in stripped for prefix in ALLOWED_IMPORT_PREFIXES):
                # Allow type-only imports of remotion already covered; reject others
                if "from " in stripped or "require(" in stripped:
                    errors.append(f"disallowed import line: {stripped[:120]}")
    return errors


def write_composition_file(
    project_path: Path,
    relative_path: str,
    source: str,
) -> Path:
    """Write a composition file after path + source validation."""
    errors = validate_composition_source(source)
    if errors:
        raise ValueError("; ".join(errors))
    root = ensure_remotion_scaffold(project_path)
    if (
        not relative_path
        or relative_path.startswith(("/", "\\"))
        or ".." in Path(relative_path).parts
    ):
        raise ValueError(
            f"relative_path must stay under .open_edit/remotion/; got {relative_path!r}"
        )
    if not relative_path.startswith("src/"):
        raise ValueError("composition files must live under src/")
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes remotion root: {relative_path!r}") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target
