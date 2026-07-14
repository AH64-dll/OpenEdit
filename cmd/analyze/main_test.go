package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestAnalyzeCLI_OnTestClip(t *testing.T) {
	binPath := filepath.Join("..", "..", "bin", "analyze")
	build := exec.Command("go", "build", "-o", binPath, ".")
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("go build: %v\n%s", err, out)
	}
	defer os.Remove(binPath)

	out := filepath.Join(t.TempDir(), "out.json")
	cmd := exec.Command(binPath, "--output", out,
		"../../testdata/clip_short.mp4")
	if combined, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("analyze failed: %v\n%s", err, combined)
	}
	if _, err := os.Stat(out); err != nil {
		t.Fatalf("output not created: %v", err)
	}
}
