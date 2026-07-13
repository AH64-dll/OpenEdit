package metadata

import (
	"path/filepath"
	"testing"
)

func TestLoad_ValidManifest(t *testing.T) {
	m, err := Load(filepath.Join("..", "..", "testdata", "clip_short.metadata.json"))
	if err != nil {
		t.Fatalf("Load failed: %v", err)
	}
	if m.Version != 1 {
		t.Errorf("Version = %d, want 1", m.Version)
	}
	if len(m.Clips) != 1 {
		t.Fatalf("len(Clips) = %d, want 1", len(m.Clips))
	}
	c := m.Clips[0]
	if c.Path == "" {
		t.Error("Clip.Path is empty")
	}
	if c.DurationSec < 9.0 || c.DurationSec > 11.0 {
		t.Errorf("DurationSec = %f, want ~10", c.DurationSec)
	}
	if c.Width != 1920 || c.Height != 1080 {
		t.Errorf("resolution = %dx%d, want 1920x1080", c.Width, c.Height)
	}
	if len(c.Scenes) < 2 {
		t.Errorf("len(Scenes) = %d, want >= 2 (two scene cuts)", len(c.Scenes))
	}
}
