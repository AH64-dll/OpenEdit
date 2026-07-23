# Go Pipeline Production Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 2 critical, 2 high, and 2 medium bugs in the deterministic Go video pipeline (analyze → compile → render).

**Architecture:** Three Go CLI binaries (`cmd/analyze`, `cmd/compile`, `cmd/render`) with shared packages (`internal/metadata`, `internal/edl`, `internal/mlt`). Zero external dependencies. All bugs are in ~1,500 LOC across 21 files.

**Tech Stack:** Go 1.22, no external deps, ffprobe/ffmpeg/melt subprocesses.

**Global Constraints:**
- Zero new external Go dependencies
- All file paths must be XML-escaped in `mlt/generate.go`
- `cmd/render/main.go` must handle SIGINT/SIGTERM by cleaning up subprocesses
- `strconv.ParseFloat` errors must not be silently discarded
- Go tests must be addable to `.github/workflows/ci.yml`

---

### Task 1: Prevent orphaned melt subprocesses

**Files:**
- Modify: `cmd/render/main.go:45-60`
- Test: `test/e2e_test.go` (already has correct pattern — verify it still works)

**Interfaces:**
- Consumes: `exec.CommandContext` pattern from `test/e2e_test.go:96-97`
- Produces: `render` binary that kills `melt` on SIGINT/SIGTERM

- [ ] **Step 1: Write failing test for orphan behavior**

```go
// Add to test/e2e_test.go or a new test file
func TestRenderSignalCleanup(t *testing.T) {
    // Build render binary
    // Start render with timeout context
    // Send SIGINT
    // Verify melt process is dead (pgrep melt returns empty)
}
```

- [ ] **Step 2: Verify test fails**

Run: `go test ./test/ -run TestRenderSignalCleanup -v -count=1`
Expected: Test fails because melt stays running after SIGINT

- [ ] **Step 3: Add signal handler + process group to cmd/render/main.go**

```go
// Add import "os/signal"

// Before cmd.Start():
cmd.SysProcAttr = &syscall.SysProcAttr{
    Setpgid: true,
}

// After cmd.Start():
// Set up signal handling
sigCh := make(chan os.Signal, 1)
signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
go func() {
    <-sigCh
    syscall.Kill(-cmd.Process.Pid, syscall.SIGTERM) // Kill process group
    os.Exit(1)
}()
```

- [ ] **Step 4: Run test to verify fix**

Run: `go test ./test/ -run TestRenderSignalCleanup -v -count=1`
Expected: PASS (melt cleaned up on SIGINT)

- [ ] **Step 5: Verify existing e2e test still passes**

Run: `go test ./test/ -run TestFullPipeline -v -count=1`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add cmd/render/main.go test/
git commit -m "fix(render): add signal handler + Setpgid to prevent orphaned melt subprocess"
```

---

### Task 2: Fix XML injection in MLT generation

**Files:**
- Modify: `internal/mlt/generate.go:78-85`

- [ ] **Step 1: Write failing test**

```go
// Add to internal/mlt/generate_test.go
func TestGenerateXMLEscapesPaths(t *testing.T) {
    edl := goodEDL()
    // Set a source path with XML-special characters
    edl.Segments[0].Source = "/path/foo & bar <baz>.mp4"
    m := goodManifest()
    
    xml, err := Generate(edl, m)
    if err != nil {
        t.Fatal(err)
    }
    
    if strings.Contains(xml, "&") && !strings.Contains(xml, "&amp;") {
        t.Error("Unescaped & in XML output")
    }
    if strings.Contains(xml, "<") && !strings.Contains(xml, "&lt;") {
        t.Error("Unescaped < in XML output")
    }
}
```

- [ ] **Step 2: Verify test fails**

Run: `go test ./internal/mlt/ -run TestGenerateXMLEscapesPaths -v`
Expected: FAIL (XML contains raw `&` and `<`)

- [ ] **Step 3: Add XML escaping to resource property**

```go
// In internal/mlt/generate.go, around line 82, change:
// <property name="resource">%s</property>
// to:
escaped := strings.ReplaceAll(s.Source, "&", "&amp;")
escaped = strings.ReplaceAll(escaped, "<", "&lt;")
escaped = strings.ReplaceAll(escaped, ">", "&gt;")
escaped = strings.ReplaceAll(escaped, `"`, "&quot;")
fmt.Fprintf(&buf, `<property name="resource">%s</property>`+"\n", escaped)
```

- [ ] **Step 4: Verify test passes**

Run: `go test ./internal/mlt/ -run TestGenerateXMLEscapesPaths -v`
Expected: PASS

- [ ] **Step 5: Update golden test file**

```bash
go test ./internal/mlt/ -run TestGenerateGolden -update 2>/dev/null || true
# Or manually regenerate the expected.mlt file
```

- [ ] **Step 6: Run full mlt test suite**

Run: `go test ./internal/mlt/ -v -count=1`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add internal/mlt/generate.go internal/mlt/generate_test.go
git commit -m "fix(mlt): escape XML-special characters in file paths"
```

---

### Task 3: Fix swallowed parse errors → NaN FPS

**Files:**
- Modify: `internal/metadata/analyzer.go:78-84, 92-94`
- Modify: `internal/mlt/generate.go:112-117`
- Add test: `internal/metadata/analyzer_test.go`

- [ ] **Step 1: Write failing test for NaN FPS detection**

```go
// Add to internal/metadata/analyzer_test.go
func TestAnalyzeRejectsNaN(t *testing.T) {
    // Feed a fake ffprobe output with r_frame_rate = "-nan/1"
    output := `{
        "format": {"duration": "10.0"},
        "streams": [{
            "codec_type": "video",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "-nan/1",
            "duration": "10.0"
        }]
    }`
    
    var probeData struct{ /* mirror ffprobeOutput */ }
    // ... parse and call analyzeClip
    // Should return error "invalid frame rate"
}
```

- [ ] **Step 2: Add error handling for ParseFloat failures**

```go
// In internal/metadata/analyzer.go, around line 80:
num, err := strconv.ParseFloat(parts[0], 64)
if err != nil {
    return Clip{}, fmt.Errorf("invalid frame rate numerator %q: %w", parts[0], err)
}
den, err := strconv.ParseFloat(parts[1], 64)
if err != nil {
    return Clip{}, fmt.Errorf("invalid frame rate denominator %q: %w", parts[1], err)
}

// Around line 92:
dur, err := strconv.ParseFloat(probeData.Format.Duration, 64)
if err != nil {
    return Clip{}, fmt.Errorf("invalid duration %q: %w", probeData.Format.Duration, err)
}
c.DurationSec = dur
```

- [ ] **Step 3: Add NaN guard in mlt/generate.go**

```go
// Around line 116, change:
// if clip.FPS <= 0 {
// To:
if clip.FPS <= 0 || math.IsNaN(clip.FPS) {
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/metadata/ ./internal/mlt/ -v -count=1`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add internal/metadata/analyzer.go internal/mlt/generate.go internal/metadata/analyzer_test.go
git commit -m "fix(metadata): handle NaN FPS from ffprobe r_frame_rate"
```

---

### Task 4: Add Go pipeline to CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add Go test job to CI**

```yaml
# After the python-unit job, add:
  go-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - name: Unit tests
        run: go test ./internal/... -v -count=1
      - name: Build CLIs
        run: go build ./cmd/...
```

- [ ] **Step 2: Verify CI syntax is valid**

```bash
# Install yq or use python to parse the YAML
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('Valid YAML')"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add Go pipeline unit tests and build to CI"
```

---

### Task 5: Remove redundant ffprobe subprocess in scene detection

**Files:**
- Modify: `internal/metadata/analyzer.go:146-171`

- [ ] **Step 1: Pass existing duration into detectScenes**

```go
// Change detectScenes signature to accept durationSec
func detectScenes(clipPath string, durationSec float64) ([]Scene, error) {
    // Remove the redundant ffprobe call and use durationSec directly
    // Skip scene detection if duration < 1.0 (still fine)
}
```

- [ ] **Step 2: Update caller**

```go
// In Analyze():
scenes, err := detectScenes(clipPath, durationSec)
```

- [ ] **Step 3: Run tests**

Run: `go test ./internal/metadata/ -v -count=1`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add internal/metadata/analyzer.go
git commit -m "perf(analyzer): eliminate redundant ffprobe call in scene detection"
```

---

### Task 6: Fix misleading fix hint for inSec > outSec

**Files:**
- Modify: `internal/edl/validate.go:42`

- [ ] **Step 1: Improve the fix hint**

```go
// Change:
fix: set inSec=%v outSec=%v
// To:
fix: set inSec=%v outSec=%.1f (setting outSec to inSec+0.1s)
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/edl/ -v -count=1`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add internal/edl/validate.go
git commit -m "fix(edl): improve fix hint for inSec > outSec to suggest inSec+0.1"
```
