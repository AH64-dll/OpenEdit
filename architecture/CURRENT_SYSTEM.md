# Current system

See [BLUEPRINT.md](BLUEPRINT.md) for the maintained package map and contracts.

The primary product is the Python MCP server. External MCP clients execute
editing and render tools against one pinned project. The included review UI
starts in review-only mode. Optional SDK/CLI chat is explicitly enabled.

Current behavior includes atomic operation batches, strict tool validation,
bounded asset/transcript pages, on-demand guides, durable render jobs with
settings-aware coalescing, and cancellation of local workers on shutdown.

Native graphics use HyperFrames with MLT/FFmpeg base media rendering. Legacy
Remotion operations remain replayable through the compatibility path.
