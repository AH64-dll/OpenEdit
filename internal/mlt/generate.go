package mlt

import (
	"fmt"
	"math"
	"strings"

	"mlt-pipeline/internal/edl"
	"mlt-pipeline/internal/metadata"
)

// secToTC formats seconds as MLT timecode HH:MM:SS.mmm.
func secToTC(s float64) string {
	if s < 0 {
		s = 0
	}
	totalMS := int64(math.Round(s * 1000))
	h := totalMS / 3_600_000
	m := (totalMS % 3_600_000) / 60_000
	sec := (totalMS % 60_000) / 1000
	ms := totalMS % 1000
	return fmt.Sprintf("%02d:%02d:%02d.%03d", h, m, sec, ms)
}

type profile struct {
	width  int
	height int
	fps    float64
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

	// Resolve the timeline's profile from all referenced clips. The v1 emitter
	// can only generate one global MLT profile, so mixed resolutions/FPS are a
	// hard error instead of being silently rendered with the first clip's profile.
	if len(m.Clips) == 0 {
		return "", fmt.Errorf("manifest has no clips")
	}
	prof, err := resolveProfile(e, clipByPath)
	if err != nil {
		return "", err
	}

	var b strings.Builder
	b.WriteString("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n")
	b.WriteString(fmt.Sprintf(
		"<mlt version=\"7.0.0\" title=\"auto_edit\" producer=\"main_bin\">\n"+
			"  <profile width=\"%d\" height=\"%d\" progressive=\"1\" sample_aspect_num=\"1\" sample_aspect_den=\"1\" frame_rate_num=\"%.0f\" frame_rate_den=\"1\" colorspace=\"709\"/>\n",
		prof.width, prof.height, prof.fps,
	))

	// Producers.
	for _, p := range producers {
		b.WriteString(fmt.Sprintf("  <producer id=\"%s\">\n", p.id))
		escaped := strings.ReplaceAll(p.path, "&", "&amp;")
		escaped = strings.ReplaceAll(escaped, "<", "&lt;")
		escaped = strings.ReplaceAll(escaped, ">", "&gt;")
		escaped = strings.ReplaceAll(escaped, `"`, "&quot;")
		b.WriteString(fmt.Sprintf("    <property name=\"resource\">%s</property>\n", escaped))
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

func resolveProfile(e *edl.EDL, clipByPath map[string]*metadata.Clip) (profile, error) {
	var prof profile
	for i, s := range e.Segments {
		clip := clipByPath[s.Source]
		if clip == nil {
			return profile{}, fmt.Errorf("EDL segment %d references source %q not in manifest", i, s.Source)
		}
		if clip.Width <= 0 || clip.Height <= 0 || clip.FPS <= 0 || math.IsNaN(clip.FPS) {
			return profile{}, fmt.Errorf("clip %q has invalid profile %dx%d @ %.3ffps; fix: re-run analyze on a valid video file", clip.Path, clip.Width, clip.Height, clip.FPS)
		}
		current := profile{width: clip.Width, height: clip.Height, fps: clip.FPS}
		if prof == (profile{}) {
			prof = current
			continue
		}
		if prof.width != current.width || prof.height != current.height || math.Abs(prof.fps-current.fps) > 0.001 {
			return profile{}, fmt.Errorf("mixed media profiles are not supported in v1: first referenced profile is %dx%d @ %.3ffps, segment %d source %q is %dx%d @ %.3ffps; fix: transcode footage to one resolution/FPS before analyze or split into separate projects", prof.width, prof.height, prof.fps, i, clip.Path, current.width, current.height, current.fps)
		}
	}
	if prof == (profile{}) {
		return profile{}, fmt.Errorf("EDL has no referenced segments")
	}
	return prof, nil
}
