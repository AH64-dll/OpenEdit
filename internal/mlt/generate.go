package mlt

import (
	"fmt"
	"strings"

	"mlt-pipeline/internal/edl"
	"mlt-pipeline/internal/metadata"
)

// secToTC formats seconds as MLT timecode HH:MM:SS.mmm.
func secToTC(s float64) string {
	if s < 0 {
		s = 0
	}
	h := int(s) / 3600
	m := (int(s) % 3600) / 60
	sec := int(s) % 60
	ms := int((s - float64(int(s))) * 1000)
	return fmt.Sprintf("%02d:%02d:%02d.%03d", h, m, sec, ms)
}

// Generate returns a minimal MLT XML document for the given EDL.
// The output is a single-tractor timeline (no nested tracks).
// Each segment becomes a <producer> + <entry>. A "fade" transition adds a
// <transition> element between entries.
func Generate(e *edl.EDL, m *metadata.Manifest) (string, error) {
	// Build producer spec list (one per segment).
	type producer struct {
		id   string
		path string
	}
	producers := make([]producer, 0, len(e.Segments))
	for i, s := range e.Segments {
		producers = append(producers, producer{
			id:   fmt.Sprintf("producer%d", i),
			path: s.Source,
		})
	}

	// Verify each source exists in the manifest.
	clipByPath := make(map[string]*metadata.Clip, len(m.Clips))
	for i := range m.Clips {
		clipByPath[m.Clips[i].Path] = &m.Clips[i]
	}
	for i, p := range producers {
		if _, ok := clipByPath[p.path]; !ok {
			return "", fmt.Errorf("EDL segment %d references source %q not in manifest", i, p.path)
		}
	}

	// Resolve the timeline's profile (width, height, fps) from the first clip.
	// For v1 we use the first clip's profile for the whole timeline; mixed
	// resolutions would need per-segment producers with different profiles.
	if len(m.Clips) == 0 {
		return "", fmt.Errorf("manifest has no clips")
	}
	profile := m.Clips[0]

	var b strings.Builder
	b.WriteString("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n")
	b.WriteString(fmt.Sprintf(
		"<mlt version=\"7.0.0\" title=\"auto_edit\" producer=\"main_bin\">\n"+
			"  <profile width=\"%d\" height=\"%d\" progressive=\"1\" sample_aspect_num=\"1\" sample_aspect_den=\"1\" frame_rate_num=\"%.0f\" frame_rate_den=\"1\" colorspace=\"709\"/>\n",
		profile.Width, profile.Height, profile.FPS,
	))

	// Producers.
	for _, p := range producers {
		b.WriteString(fmt.Sprintf("  <producer id=\"%s\">\n", p.id))
		b.WriteString(fmt.Sprintf("    <property name=\"resource\">%s</property>\n", p.path))
		b.WriteString("  </producer>\n")
	}

	// Playlist with transitions between fade segments.
	b.WriteString("  <playlist id=\"video_track\">\n")
	for i, s := range e.Segments {
		prodID := producers[i].id
		b.WriteString(fmt.Sprintf("    <entry producer=\"%s\" in=\"%s\" out=\"%s\"/>\n",
			prodID, secToTC(s.InSec), secToTC(s.OutSec)))
		// Insert a fade transition between this entry and the next.
		if s.Transition == edl.TransitionFade && i < len(e.Segments)-1 {
			// Fade duration: 1 frame at the timeline's FPS.
			fadeFrames := 1
			b.WriteString(fmt.Sprintf("    <transition name=\"fade\" duration=\"%d\"/>\n", fadeFrames))
		}
	}
	b.WriteString("  </playlist>\n")

	// Tractor.
	b.WriteString("  <tractor id=\"main_tractor\">\n")
	b.WriteString("    <track producer=\"video_track\"/>\n")
	b.WriteString("  </tractor>\n")
	b.WriteString("</mlt>\n")
	return b.String(), nil
}
