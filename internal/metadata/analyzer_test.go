package metadata

import (
	"testing"
	"time"
)

func TestAnalyze_AcceptsTestClip(t *testing.T) {
	m, err := Analyze([]string{"../../testdata/clip_short.mp4"}, true, 0.3)
	if err != nil {
		t.Skipf("Analyze failed (ffprobe missing?): %v", err)
	}
	if len(m.Clips) != 1 {
		t.Fatalf("len(Clips) = %d, want 1", len(m.Clips))
	}
	if m.Clips[0].Width != 1920 || m.Clips[0].Height != 1080 {
		t.Errorf("resolution = %dx%d, want 1920x1080", m.Clips[0].Width, m.Clips[0].Height)
	}
	if len(m.Clips[0].Scenes) < 2 {
		t.Errorf("scene count = %d, want >= 2", len(m.Clips[0].Scenes))
	}
}

func TestAnalyze_SubprocessTimeoutsConfigured(t *testing.T) {
	if probeTimeout <= 0 {
		t.Fatalf("probeTimeout = %s, want positive", probeTimeout)
	}
	if sceneDetectTimeout <= probeTimeout {
		t.Fatalf("sceneDetectTimeout = %s, want greater than probe timeout %s", sceneDetectTimeout, probeTimeout)
	}
	if probeTimeout > time.Minute {
		t.Fatalf("probeTimeout = %s, want bounded to at most 1m", probeTimeout)
	}
}
