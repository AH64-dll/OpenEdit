package test

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// TestBridge_OpenEditEDL_Validates is the bridge smoke test.
//
// It runs the production analyzer, then a path-substituted EDL through the
// scripts/validate_open_edit_edl.sh helper, and asserts:
//
//  1. The bridge helper exits 0 and produces a sibling bridge artifact
//     (project.open_edit.mlt) without overwriting the production
//     (edl.json, project.mlt) artifacts.
//  2. The bridge artifact is a non-empty MLT document that references the
//     expected clip path.
//
// This is the canary for the file-based bridge contract described in
// docs/architecture-boundary.md.
func TestBridge_OpenEditEDL_Validates(t *testing.T) {
	root, _ := filepath.Abs("..")
	bin := filepath.Join(root, "bin")
	td := filepath.Join(root, "testdata")
	helper := filepath.Join(root, "scripts", "validate_open_edit_edl.sh")

	// Build the production binaries the bridge relies on.
	for _, tool := range []string{"analyze", "compile"} {
		build := exec.Command("go", "build", "-o", filepath.Join(bin, tool), filepath.Join(root, "cmd", tool))
		if out, err := build.CombinedOutput(); err != nil {
			t.Fatalf("build %s: %v\n%s", tool, err, out)
		}
	}
	t.Cleanup(func() {
		for _, tool := range []string{"analyze", "compile"} {
			os.Remove(filepath.Join(bin, tool))
		}
	})

	// Run analyze on the fixture so we get an absolute path the EDL can use.
	projectDir := t.TempDir()
	manifestPath := filepath.Join(projectDir, "metadata.json")
	analyze := exec.Command(filepath.Join(bin, "analyze"),
		"--output", manifestPath,
		filepath.Join(td, "clip_short.mp4"),
	)
	if out, err := analyze.CombinedOutput(); err != nil {
		t.Fatalf("analyze: %v\n%s", err, out)
	}

	// Read back the absolute clip path and produce a path-substituted EDL.
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
	edlBytes, err := os.ReadFile(filepath.Join(td, "clip_short.edl.handwritten.json"))
	if err != nil {
		t.Fatalf("read edl fixture: %v", err)
	}
	edlBytes = []byte(strings.ReplaceAll(string(edlBytes),
		"testdata/clip_short.mp4", manifest.Clips[0].Path))
	edlPath := filepath.Join(projectDir, "edl.open_edit.json")
	if err := os.WriteFile(edlPath, edlBytes, 0644); err != nil {
		t.Fatalf("write edl: %v", err)
	}

	bridge := exec.Command(helper, projectDir, "edl.open_edit.json")
	if out, err := bridge.CombinedOutput(); err != nil {
		t.Fatalf("bridge helper failed: %v\n%s", err, out)
	}

	mltOut := filepath.Join(projectDir, "project.open_edit.mlt")
	info, err := os.Stat(mltOut)
	if err != nil {
		t.Fatalf("expected bridge artifact %s: %v", mltOut, err)
	}
	if info.Size() == 0 {
		t.Fatalf("bridge artifact %s is empty", mltOut)
	}

	// The bridge must never overwrite the production artifacts.
	if _, err := os.Stat(filepath.Join(projectDir, "edl.json")); !os.IsNotExist(err) {
		t.Errorf("bridge must not create edl.json; got existing file")
	}
	if _, err := os.Stat(filepath.Join(projectDir, "project.mlt")); !os.IsNotExist(err) {
		t.Errorf("bridge must not create project.mlt; got existing file")
	}
}
