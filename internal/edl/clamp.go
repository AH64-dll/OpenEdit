package edl

import (
	"fmt"

	"mlt-pipeline/internal/metadata"
)

// Clamp bounds each segment's inSec and outSec against its source clip's
// duration. It returns a list of human-readable warnings (one per adjusted
// value) and a hard error only when a segment's source is not in the manifest.
//
// Clamp does NOT validate other rules (transition, inSec<outSec) — call
// Validate first, then Clamp.
func Clamp(e *EDL, m *metadata.Manifest) (warnings []string, err error) {
	clipByPath := make(map[string]*metadata.Clip, len(m.Clips))
	for i := range m.Clips {
		clipByPath[m.Clips[i].Path] = &m.Clips[i]
	}

	for i := range e.Segments {
		s := &e.Segments[i]
		clip, ok := clipByPath[s.Source]
		if !ok {
			return warnings, fmt.Errorf("segment %d source %q unknown; cannot clamp", i, s.Source)
		}
		if s.InSec < 0 {
			warnings = append(warnings, fmt.Sprintf("segment %d: inSec %v clamped to 0", i, s.InSec))
			s.InSec = 0
		}
		if s.OutSec > clip.DurationSec {
			warnings = append(warnings, fmt.Sprintf("segment %d: outSec %v clamped to %v (clip duration)", i, s.OutSec, clip.DurationSec))
			s.OutSec = clip.DurationSec
		}
	}
	return warnings, nil
}
