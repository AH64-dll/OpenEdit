package main

import (
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestRenderCLI_BuildOK(t *testing.T) {
	binPath := filepath.Join("..", "..", "bin", "render")
	build := exec.Command("go", "build", "-o", binPath, ".")
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("go build: %v\n%s", err, out)
	}
	defer exec.Command("rm", binPath).Run()

	// Don't actually run melt here (slow, may not be installed).
	// Just verify the binary builds and --help works.
	cmd := exec.Command(binPath, "--help")
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("--help failed: %v\n%s", err, out)
	}
	if !strings.Contains(string(out), "-mlt") {
		t.Errorf("--help output missing -mlt flag; got:\n%s", out)
	}
	if !strings.Contains(string(out), "-timeout") {
		t.Errorf("--help output missing -timeout flag; got:\n%s", out)
	}
}
