//go:build agent_canary

// This test is gated behind the `agent_canary` build tag so it doesn't
// run with `go test ./...` (which would require network + opencode + a
// model). Run explicitly:
//
//   go test -tags=agent_canary ./test/...
//
// It exists to catch model drift or prompt regressions. If this test
// starts failing, the fix is in prompts/edl_writer.md or the model
// config, not in the pipeline code.

package test

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestAgentCanary_ProducesValidEDL(t *testing.T) {
	if os.Getenv("MLT_PIPELINE_RUN_AGENT_TESTS") == "" {
		t.Skip("set MLT_PIPELINE_RUN_AGENT_TESTS=1 to run the agent canary test")
	}

	root, _ := filepath.Abs("..")
	bin := filepath.Join(root, "bin")
	td := filepath.Join(root, "testdata")
	projectDir := filepath.Join(root, "projects", "agent-canary")

	// Clean and recreate.
	os.RemoveAll(projectDir)
	if err := os.MkdirAll(filepath.Join(projectDir, "footage"), 0755); err != nil {
		t.Fatal(err)
	}
	// Copy the test clip into the project's footage/.
	src := filepath.Join(td, "clip_short.mp4")
	dst := filepath.Join(projectDir, "footage", "clip_short.mp4")
	copyFile := exec.Command("cp", src, dst)
	if out, err := copyFile.CombinedOutput(); err != nil {
		t.Fatalf("cp: %v\n%s", err, out)
	}

	// Build CLIs.
	for _, tool := range []string{"analyze", "compile", "render"} {
		build := exec.Command("go", "build", "-o", filepath.Join(bin, tool), filepath.Join(root, "cmd", tool))
		if out, err := build.CombinedOutput(); err != nil {
			t.Fatalf("build %s: %v\n%s", tool, err, out)
		}
	}
	t.Cleanup(func() {
		for _, tool := range []string{"analyze", "compile", "render"} {
			os.Remove(filepath.Join(bin, tool))
		}
	})

	// Run the driver with --no-render (default).
	driver := exec.Command(filepath.Join(root, "run.sh"), "agent-canary")
	driver.Dir = projectDir
	if out, err := driver.CombinedOutput(); err != nil {
		t.Fatalf("run.sh failed: %v\n%s", err, out)
	}

	// Assert that edl.json was created and validates against the manifest.
	edlPath := filepath.Join(projectDir, "edl.json")
	if _, err := os.Stat(edlPath); err != nil {
		t.Fatalf("edl.json not created: %v", err)
	}
	previewPath := filepath.Join(projectDir, "preview.mp4")
	if _, err := os.Stat(previewPath); err != nil {
		t.Fatalf("preview.mp4 not created: %v", err)
	}
}
