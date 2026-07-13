package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestCompileCLI_OnTestEDL(t *testing.T) {
	binPath := filepath.Join("..", "..", "bin", "compile")
	build := exec.Command("go", "build", "-o", binPath, ".")
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("go build: %v\n%s", err, out)
	}
	defer os.Remove(binPath)

	out := filepath.Join(t.TempDir(), "out.mlt")
	cmd := exec.Command(binPath,
		"--edl", "../../testdata/clip_short.edl.handwritten.json",
		"--metadata", "../../testdata/clip_short.metadata.json",
		"--output", out,
	)
	if combined, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("compile failed: %v\n%s", err, combined)
	}
	if _, err := os.Stat(out); err != nil {
		t.Fatalf("output not created: %v", err)
	}
}

func TestCompileCLI_BadEDLFails(t *testing.T) {
	binPath := filepath.Join("..", "..", "bin", "compile")
	build := exec.Command("go", "build", "-o", binPath, ".")
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("go build: %v\n%s", err, out)
	}
	defer os.Remove(binPath)

	// Write a bad EDL (inSec >= outSec).
	badPath := filepath.Join(t.TempDir(), "bad.json")
	if err := os.WriteFile(badPath, []byte(`{"version":1,"targetDurationSec":1,"segments":[{"source":"x","inSec":5,"outSec":5}]}`), 0644); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(binPath,
		"--edl", badPath,
		"--metadata", "../../testdata/clip_short.metadata.json",
		"--output", filepath.Join(t.TempDir(), "out.mlt"),
	)
	if err := cmd.Run(); err == nil {
		t.Fatal("compile should have failed on bad EDL")
	}
}
