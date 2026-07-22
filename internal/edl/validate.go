package edl

import (
	"encoding/json"
	"fmt"
	"os"

	"mlt-pipeline/internal/metadata"
)

// Validate checks an EDL against a Manifest. It mutates the EDL in place
// (defaults Transition to "cut" when empty) and returns the first error found.
// All errors include a `fix:` line in their message that the agent uses to
// recover without re-prompting.
func Validate(e *EDL, m *metadata.Manifest) error {
	if e.Version != 1 {
		return fmt.Errorf("EDL version %d not supported (only version 1); fix: set version to 1", e.Version)
	}
	if len(e.Segments) == 0 {
		return fmt.Errorf("EDL has no segments; fix: add at least one segment to the segments array")
	}

	// Build a path → clip index for fast lookup.
	clipByPath := make(map[string]*metadata.Clip, len(m.Clips))
	for i := range m.Clips {
		clipByPath[m.Clips[i].Path] = &m.Clips[i]
	}

	for i := range e.Segments {
		s := &e.Segments[i]

		// Default transition.
		if s.Transition == "" {
			s.Transition = TransitionCut
		}
		if s.Transition != TransitionCut && s.Transition != TransitionFade {
			return fmt.Errorf("segment %d transition %q invalid; v1 only supports cut/fade; fix: set transition to \"cut\" or \"fade\"", i, s.Transition)
		}

		// inSec < outSec.
		if s.InSec >= s.OutSec {
			return fmt.Errorf("segment %d: inSec must be less than outSec (got inSec=%v, outSec=%v); fix: set outSec=%.1f (outSec = inSec+0.1)", i, s.InSec, s.OutSec, s.InSec+0.1)
		}

		// inSec >= 0.
		if s.InSec < 0 {
			return fmt.Errorf("segment %d inSec=%v must be >= 0; fix: set inSec=0", i, s.InSec)
		}

		// Source must be in the manifest.
		clip, ok := clipByPath[s.Source]
		if !ok {
			return fmt.Errorf("segment %d: unknown source %q; fix: use a path that appears in metadata.json", i, s.Source)
		}

		// outSec <= clip duration.
		if s.OutSec > clip.DurationSec {
			return fmt.Errorf("segment %d outSec=%v beyond clip %q duration=%v; fix: set outSec=%v", i, s.OutSec, clip.Path, clip.DurationSec, clip.DurationSec)
		}
	}

	// targetDurationSec defaults to the sum if missing.
	if e.TargetDurationSec == 0 {
		var sum float64
		for _, s := range e.Segments {
			sum += s.OutSec - s.InSec
		}
		e.TargetDurationSec = sum
	}

	return nil
}

// Load reads an edl.json file and returns the parsed EDL.
func Load(path string) (*EDL, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}
	var e EDL
	if err := json.Unmarshal(data, &e); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	return &e, nil
}
