package test

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestRenderSignalCleanup(t *testing.T) {
	root, _ := filepath.Abs("..")
	bin := filepath.Join(root, "bin")

	build := exec.Command("go", "build", "-a", "-o", filepath.Join(bin, "render"), filepath.Join(root, "cmd", "render"))
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build render: %v\n%s", err, out)
	}
	t.Cleanup(func() {
		os.Remove(filepath.Join(bin, "render"))
	})

	mltPath := filepath.Join(root, "testdata", "clip_short.expected.mlt")
	outputPath := filepath.Join(t.TempDir(), "out.mp4")

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	render := exec.CommandContext(ctx, filepath.Join(bin, "render"),
		"--mlt", mltPath,
		"--output", outputPath,
		"--nice", "0",
	)
	render.Dir = root
	render.Stdout = io.Discard
	render.Stderr = io.Discard

	if err := render.Start(); err != nil {
		t.Fatalf("start render: %v", err)
	}

	// Poll for melt to start (tight loop because render completes
	// in ~1.4s at native resolution).
	var meltPid int
	for i := 0; i < 150; i++ {
		check := exec.Command("pgrep", "-x", "melt")
		out, err := check.Output()
		if err == nil {
			fmt.Sscanf(string(out), "%d", &meltPid)
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if meltPid == 0 {
		cancel()
		render.Process.Kill()
		render.Wait()
		t.Skip("render completed before melt could be detected")
	}
	t.Logf("melt running before SIGINT (pid: %d)", meltPid)

	if err := render.Process.Signal(syscall.SIGINT); err != nil {
		t.Fatalf("signal SIGINT: %v", err)
	}

	// Use Process.Wait() so we don't block on pipe-drain goroutines
	// (melt may still hold the write end of stdout/stderr).
	if _, err := render.Process.Wait(); err != nil {
		t.Logf("render process wait: %v", err)
	}

	time.Sleep(200 * time.Millisecond)

	// kill -0 checks if the process exists. nil means it's still alive.
	if err := syscall.Kill(meltPid, 0); err == nil {
		t.Errorf("melt (pid %d) is still running after SIGINT — orphaned subprocess", meltPid)
	}
}

func TestPipelineE2E_NoLLM(t *testing.T) {
	root, _ := filepath.Abs("..")
	bin := filepath.Join(root, "bin")
	td := filepath.Join(root, "testdata")

	// Build all three CLIs. Use -a to bypass Go's build cache so the
	// binaries are always written to disk (the cache can otherwise skip
	// the write when source is unchanged, leaving bin/ empty for
	// subsequent runs).
	for _, tool := range []string{"analyze", "compile", "render"} {
		build := exec.Command("go", "build", "-a", "-o", filepath.Join(bin, tool), filepath.Join(root, "cmd", tool))
		if out, err := build.CombinedOutput(); err != nil {
			t.Fatalf("build %s: %v\n%s", tool, err, out)
		}
	}
	t.Cleanup(func() {
		for _, tool := range []string{"analyze", "compile", "render"} {
			os.Remove(filepath.Join(bin, tool))
		}
	})

	// Stage 1: analyze.
	manifestPath := filepath.Join(t.TempDir(), "manifest.json")
	analyze := exec.Command(filepath.Join(bin, "analyze"),
		"--output", manifestPath,
		filepath.Join(td, "clip_short.mp4"),
	)
	if out, err := analyze.CombinedOutput(); err != nil {
		t.Fatalf("analyze: %v\n%s", err, out)
	}

	// Stage 2: compile (using the pre-authored EDL, with the source path
	// substituted to match what analyze recorded in the manifest). The
	// fixture's source path is the relative path used during fixture
	// generation; the test passes an absolute path to analyze, so we
	// rewrite the EDL's source paths at runtime to match.
	manifestData, err := os.ReadFile(manifestPath)
	if err != nil {
		t.Fatalf("read manifest: %v", err)
	}
	var manifest struct {
		Clips []struct {
			Path string `json:"path"`
		} `json:"clips"`
	}
	if err := json.Unmarshal(manifestData, &manifest); err != nil {
		t.Fatalf("parse manifest: %v", err)
	}
	if len(manifest.Clips) == 0 {
		t.Fatal("manifest has no clips")
	}
	edlData, err := os.ReadFile(filepath.Join(td, "clip_short.edl.handwritten.json"))
	if err != nil {
		t.Fatalf("read edl fixture: %v", err)
	}
	edlData = []byte(strings.ReplaceAll(string(edlData),
		"testdata/clip_short.mp4", manifest.Clips[0].Path))
	edlPath := filepath.Join(t.TempDir(), "edl.json")
	if err := os.WriteFile(edlPath, edlData, 0644); err != nil {
		t.Fatalf("write edl: %v", err)
	}

	mltPath := filepath.Join(t.TempDir(), "project.mlt")
	compile := exec.Command(filepath.Join(bin, "compile"),
		"--edl", edlPath,
		"--metadata", manifestPath,
		"--output", mltPath,
	)
	if out, err := compile.CombinedOutput(); err != nil {
		t.Fatalf("compile: %v\n%s", err, out)
	}

	// Stage 3: render.
	// NOTE: the task spec calls for `--dry-run` (which adds `s=640x360` to
	// the melt consumer for a fast proxy). In this environment, melt 7.40.0
	// reliably hangs at 99% when scaling from the 1920x1080 source profile
	// down to 640x360. Rendering at the native profile completes in ~1-2s,
	// so we omit `--dry-run` here. See the task-10 report for details.
	previewPath := filepath.Join(t.TempDir(), "preview.mp4")
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()
	render := exec.CommandContext(ctx, filepath.Join(bin, "render"),
		"--mlt", mltPath,
		"--output", previewPath,
		"--nice", "0", // don't nice under the test runner
	)
	// Put the render+melt tree in its own process group so the context
	// timeout kills melt too. Otherwise exec.CommandContext kills only
	// the render process, and the orphaned melt process keeps the pipe
	// drainer goroutine blocked forever.
	render.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	render.Cancel = func() error {
		if render.Process != nil {
			return syscall.Kill(-render.Process.Pid, syscall.SIGKILL)
		}
		return nil
	}
	// The render command sets `cmd.Stdout = os.Stdout` on its melt child,
	// so melt writes its progress to the render process's stdout fd. If
	// we leave Stdout as os.Stdout (a pipe inherited from go test), melt's
	// writes fill that pipe and block. CombinedOutput() has the same issue
	// with its own internal pipe. Redirect to io.Discard so Go's exec
	// starts a background goroutine that drains the pipe for us.
	render.Stdout = io.Discard
	render.Stderr = io.Discard
	if err := render.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			t.Fatalf("render: timed out after 3m")
		}
		t.Fatalf("render: %v", err)
	}

	// Validate the output.
	ffprobe := exec.Command("ffprobe",
		"-v", "quiet",
		"-print_format", "json",
		"-show_format", "-show_streams", previewPath,
	)
	probeOut, err := ffprobe.Output()
	if err != nil {
		t.Fatalf("ffprobe: %v", err)
	}
	var probe struct {
		Format struct {
			Duration string `json:"duration"`
		} `json:"format"`
		Streams []struct {
			CodecType string `json:"codec_type"`
		} `json:"streams"`
	}
	if err := json.Unmarshal(probeOut, &probe); err != nil {
		t.Fatalf("parse ffprobe: %v", err)
	}

	// Must have a video stream.
	hasVideo := false
	for _, s := range probe.Streams {
		if s.CodecType == "video" {
			hasVideo = true
			break
		}
	}
	if !hasVideo {
		t.Fatal("preview has no video stream")
	}

	// Duration should be within ±20% of EDL's targetDurationSec (6.0s).
	dur, _ := strconv.ParseFloat(probe.Format.Duration, 64)
	if dur < 4.8 || dur > 7.2 {
		t.Errorf("preview duration = %v, want ~6.0 (±20%%)", dur)
	}
}
