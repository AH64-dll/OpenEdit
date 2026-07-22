package metadata

import (
	"encoding/json"
	"strings"
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

func TestAnalyze_RejectsNaN(t *testing.T) {
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

	var probeData ffprobeOutput
	if err := json.Unmarshal([]byte(output), &probeData); err != nil {
		t.Fatal(err)
	}

	for _, s := range probeData.Streams {
		if s.CodecType == "video" {
			_, err := parseFrameRate(s.RFrameRate)
			if err == nil {
				t.Fatal("expected error for NaN frame rate, got nil")
			}
			if !strings.Contains(err.Error(), "invalid frame rate") {
				t.Errorf("error message = %q, want containing 'invalid frame rate'", err.Error())
			}
		}
	}
}
