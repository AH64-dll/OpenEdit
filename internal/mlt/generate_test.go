package mlt

import (
	"encoding/xml"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"mlt-pipeline/internal/edl"
	"mlt-pipeline/internal/metadata"
)

func loadTestdata(t *testing.T) (*edl.EDL, *metadata.Manifest) {
	t.Helper()
	td := filepath.Join("..", "..", "testdata")
	e, err := edl.Load(filepath.Join(td, "clip_short.edl.handwritten.json"))
	if err != nil {
		t.Fatalf("load EDL: %v", err)
	}
	m, err := metadata.Load(filepath.Join(td, "clip_short.metadata.json"))
	if err != nil {
		t.Fatalf("load manifest: %v", err)
	}
	return e, m
}

func TestGenerate_ValidXML(t *testing.T) {
	e, m := loadTestdata(t)
	out, err := Generate(e, m)
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}
	// Smoke check: must be valid XML.
	var v interface{}
	if err := xml.Unmarshal([]byte(out), &v); err != nil {
		t.Fatalf("output is not valid XML: %v\n---\n%s\n---", err, out)
	}
	// Must contain MLT root.
	if !strings.HasPrefix(out, `<?xml`) {
		t.Error("output missing XML declaration")
	}
	if !strings.Contains(out, "<mlt") {
		t.Error("output missing <mlt> root")
	}
}

func TestGenerate_HasProducerPerSegment(t *testing.T) {
	e, m := loadTestdata(t)
	out, err := Generate(e, m)
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}
	// 3 segments → 3 producer entries.
	count := strings.Count(out, "<producer ")
	if count != 3 {
		t.Errorf("producer count = %d, want 3", count)
	}
	// 3 playlist entries.
	count = strings.Count(out, "<entry ")
	if count != 3 {
		t.Errorf("entry count = %d, want 3", count)
	}
}

func TestGenerate_FadeAddsTransition(t *testing.T) {
	e, m := loadTestdata(t)
	out, err := Generate(e, m)
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}
	if !strings.Contains(out, "<transition") {
		t.Error("expected <transition> element for fade segment, got none")
	}
	// A cut transition should NOT add a <transition> element.
	// The 3-segment EDL has 1 fade (segment 1) and 2 cuts → 1 <transition>.
	count := strings.Count(out, "<transition")
	if count != 1 {
		t.Errorf("transition count = %d, want 1", count)
	}
}

func TestGenerate_GoldenMatch(t *testing.T) {
	e, m := loadTestdata(t)
	out, err := Generate(e, m)
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}
	golden, err := os.ReadFile(filepath.Join("..", "..", "testdata", "clip_short.expected.mlt"))
	if err != nil {
		t.Skipf("golden file missing (regenerate by running with -update): %v", err)
	}
	if string(golden) != out {
		t.Errorf("output does not match golden file\n--- got ---\n%s\n--- want ---\n%s\n", out, string(golden))
	}
}
