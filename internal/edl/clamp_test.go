package edl

import (
	"strings"
	"testing"
)

func TestClamp_NegativeInFlooredToZero(t *testing.T) {
	m := goodManifest()
	e := goodEDL()
	e.Segments[0].InSec = -2.5
	warnings, err := Clamp(e, m)
	if err != nil {
		t.Fatalf("Clamp returned error: %v", err)
	}
	if e.Segments[0].InSec != 0 {
		t.Errorf("InSec = %v, want 0", e.Segments[0].InSec)
	}
	if len(warnings) != 1 || !strings.Contains(warnings[0], "inSec") {
		t.Errorf("expected one inSec warning, got %v", warnings)
	}
}

func TestClamp_OutBeyondCeiledToDuration(t *testing.T) {
	m := goodManifest()
	e := goodEDL()
	e.Segments[0].OutSec = 15.0 // clip is 10s
	warnings, err := Clamp(e, m)
	if err != nil {
		t.Fatalf("Clamp returned error: %v", err)
	}
	if e.Segments[0].OutSec != 10.0 {
		t.Errorf("OutSec = %v, want 10.0", e.Segments[0].OutSec)
	}
	if len(warnings) != 1 || !strings.Contains(warnings[0], "outSec") {
		t.Errorf("expected one outSec warning, got %v", warnings)
	}
}

func TestClamp_InRangeNoWarning(t *testing.T) {
	m := goodManifest()
	e := goodEDL()
	warnings, err := Clamp(e, m)
	if err != nil {
		t.Fatalf("Clamp returned error: %v", err)
	}
	if len(warnings) != 0 {
		t.Errorf("expected no warnings, got %v", warnings)
	}
}

func TestClamp_UnknownSourceIsError(t *testing.T) {
	m := goodManifest()
	e := goodEDL()
	e.Segments[0].Source = "/tmp/missing.mp4"
	_, err := Clamp(e, m)
	if err == nil {
		t.Fatal("expected error for unknown source, got nil")
	}
}
