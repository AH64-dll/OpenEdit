# Release OpenEdit

Release artifacts are produced from the repository; runtimes are installed from
pinned, checksum-verified upstream archives. No local workspace path is required
to build the public download packages.

1. Set the intended version in `pyproject.toml`. Update release notes. Published
   versions are immutable; bump the version before updating a published release.
2. Open a change on a `feat/*` or `fix/*` branch. Wait for CI, Diffusion acceptance
   and **Release packages** to pass before merging. The latter installs actual
   Linux/Windows download ZIPs in paths with spaces and checks MCP, dependency
   consistency, cuts, transition pixels, animated overlay pixels, audio timing,
   full decoding and reopening. Windows proof comes from its native runner.
3. Merge to `main`. Its successful package workflow creates a **draft release**
   for the package version and uploads both ZIPs and SHA-256 files. Publication
   remains a deliberate maintainer action in GitHub Releases.
4. Review the native platform verification artifacts and release notes, then
   publish the draft. The draft targets the tested commit. Tag builds enforce
   that the tag is exactly `v` plus the package version.

For a manual build:

```bash
python -m pip install build==1.5.0
python -m build
python scripts/package_release.py --platform linux-x64
python scripts/package_release.py --platform windows-x64
```

Outputs are `dist/release/OpenEdit-VERSION-{linux,windows}-x64.zip` and matching
`.zip.sha256` files. Creating the Windows ZIP on Linux proves archive construction,
not native Windows behavior. The workflow or a real Windows machine must install
and validate it before a Windows readiness claim.

Runtime URLs/hashes are in `scripts/runtime-downloads.json`; core Python pins are
in `requirements/release-constraints.txt`. Node workers retain their separate npm
lockfiles. To upgrade a runtime, obtain its SHA-256 from the official publisher,
update the manifest, rerun both platform installers and review the retained
license/source notices. Keep optional HTML, Remotion and Whisper out of the
normal installation.

The wheel and sdist include package-owned static UI, worker source, locks, patches,
font/licenses and MCP playbooks. Download archives include the wheel, both
installers, runtime bootstrap, smoke verifier, constraints and installation docs.
The original explainer's source/audio/preview are in `examples/openedit-explainer`.
Release evidence and known limitations belong in `docs/RELEASE_VERIFICATION.md`.
