# Legacy Remotion migration

Remotion is migration-only. New motion graphics must use the native
`hyperframes_native` guide and `add_hyperframes_overlay` operation.

When migrating an existing Remotion composition:

1. Inspect timing, props, assets, alpha intent, and visual behavior.
2. Author equivalent HTML/CSS/JavaScript under project-managed HyperFrames composition files.
3. Preserve timeline position and duration.
4. Run HyperFrames lint and render.
5. Compare representative frames and A/V timing against legacy output.
6. Keep legacy graph operation until parity passes.

Do not create new `AddRemotionCompositionOp` entries. Do not delete old
Remotion source or graph operations before migration evidence exists.

Remotion render paths remain host-only during compatibility migration. Never
run Remotion or HyperFrames from `run_script`.

See `skills/hyperframes_native.md` for native contract.
