package edl

import (
	"strings"
	"testing"

	"mlt-pipeline/internal/metadata"
)

func goodManifest() *metadata.Manifest {
	return &metadata.Manifest{
		Version: 1,
		Clips: []metadata.Clip{
			{Path: "/tmp/a.mp4", DurationSec: 10.0, Width: 1920, Height: 1080, FPS: 30, HasAudio: false},
			{Path: "/tmp/b.mp4", DurationSec: 20.0, Width: 1920, Height: 1080, FPS: 30, HasAudio: false},
		},
		TotalDurationSec: 30.0,
	}
}

func goodEDL() *EDL {
	return &EDL{
		Version:           1,
		TargetDurationSec: 10.0,
		Segments: []Segment{
			{Source: "/tmp/a.mp4", InSec: 0, OutSec: 5, Transition: TransitionCut},
			{Source: "/tmp/b.mp4", InSec: 5, OutSec: 10, Transition: TransitionCut},
		},
	}
}

func TestValidate_Good(t *testing.T) {
	if err := Validate(goodEDL(), goodManifest()); err != nil {
		t.Fatalf("Validate failed on good EDL: %v", err)
	}
}

func TestValidate_WrongVersion(t *testing.T) {
	e := goodEDL()
	e.Version = 2
	err := Validate(e, goodManifest())
	if err == nil || !strings.Contains(err.Error(), "version") {
		t.Fatalf("expected version error, got %v", err)
	}
}

func TestValidate_InGteOut(t *testing.T) {
	e := goodEDL()
	e.Segments[0].InSec = 5
	e.Segments[0].OutSec = 5
	err := Validate(e, goodManifest())
	if err == nil || !strings.Contains(err.Error(), "inSec must be less than outSec") {
		t.Fatalf("expected inSec/outSec error, got %v", err)
	}
}

func TestValidate_NegativeIn(t *testing.T) {
	e := goodEDL()
	e.Segments[0].InSec = -1
	err := Validate(e, goodManifest())
	if err == nil || !strings.Contains(err.Error(), "inSec") {
		t.Fatalf("expected negative inSec error, got %v", err)
	}
}

func TestValidate_OutBeyondClip(t *testing.T) {
	e := goodEDL()
	e.Segments[0].OutSec = 100 // clip is 10s
	err := Validate(e, goodManifest())
	if err == nil || !strings.Contains(err.Error(), "outSec") {
		t.Fatalf("expected out-of-range error, got %v", err)
	}
}

func TestValidate_UnknownSource(t *testing.T) {
	e := goodEDL()
	e.Segments[0].Source = "/tmp/missing.mp4"
	err := Validate(e, goodManifest())
	if err == nil || !strings.Contains(err.Error(), "unknown source") {
		t.Fatalf("expected unknown-source error, got %v", err)
	}
}

func TestValidate_EmptySegments(t *testing.T) {
	e := goodEDL()
	e.Segments = nil
	err := Validate(e, goodManifest())
	if err == nil || !strings.Contains(err.Error(), "segments") {
		t.Fatalf("expected empty-segments error, got %v", err)
	}
}

func TestValidate_DissolveRejected(t *testing.T) {
	e := goodEDL()
	e.Segments[0].Transition = "dissolve"
	err := Validate(e, goodManifest())
	if err == nil || !strings.Contains(err.Error(), "v1 only supports cut/fade") {
		t.Fatalf("expected dissolve-rejection error, got %v", err)
	}
}

func TestValidate_FadeAccepted(t *testing.T) {
	e := goodEDL()
	e.Segments[0].Transition = TransitionFade
	if err := Validate(e, goodManifest()); err != nil {
		t.Fatalf("fade should be accepted, got %v", err)
	}
}

func TestValidate_DefaultTransitionIsCut(t *testing.T) {
	e := goodEDL()
	e.Segments[0].Transition = ""
	if err := Validate(e, goodManifest()); err != nil {
		t.Fatalf("empty transition (defaults to cut) should pass, got %v", err)
	}
	if e.Segments[0].Transition != TransitionCut {
		t.Errorf("default transition not applied: got %q", e.Segments[0].Transition)
	}
}
