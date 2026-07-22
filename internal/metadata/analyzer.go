package metadata

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

const (
	probeTimeout       = 30 * time.Second
	sceneDetectTimeout = 30 * time.Minute
)

type ffprobeOutput struct {
	Streams []struct {
		CodecType  string `json:"codec_type"`
		CodecName  string `json:"codec_name"`
		Width      int    `json:"width"`
		Height     int    `json:"height"`
		RFrameRate string `json:"r_frame_rate"`
	} `json:"streams"`
	Format struct {
		Duration string `json:"duration"`
	} `json:"format"`
}

func parseFrameRate(s string) (float64, error) {
	if !strings.Contains(s, "/") {
		return 0, fmt.Errorf("invalid frame rate %q: missing '/'", s)
	}
	parts := strings.SplitN(s, "/", 2)
	num, err := strconv.ParseFloat(parts[0], 64)
	if err != nil {
		return 0, fmt.Errorf("invalid frame rate numerator %q: %w", parts[0], err)
	}
	den, err := strconv.ParseFloat(parts[1], 64)
	if err != nil {
		return 0, fmt.Errorf("invalid frame rate denominator %q: %w", parts[1], err)
	}
	if den <= 0 {
		return 0, fmt.Errorf("invalid frame rate denominator %q: must be positive", parts[1])
	}
	return num / den, nil
}

// Analyze runs ffprobe + ffmpeg scene detection on the given files and
// returns a Manifest. It does NOT write to disk — use Save for that.
//
// `scenes` toggles scene detection. `threshold` is the scene-change sensitivity
// in [0,1] (lower = more sensitive). When scenes is false, each clip gets a
// single scene entry spanning its full duration.
func Analyze(paths []string, scenes bool, threshold float64) (*Manifest, error) {
	m := &Manifest{Version: 1, Clips: make([]Clip, 0, len(paths))}
	var total float64
	for _, p := range paths {
		c, err := analyzeOne(p, scenes, threshold)
		if err != nil {
			return nil, fmt.Errorf("analyze %s: %w", p, err)
		}
		m.Clips = append(m.Clips, *c)
		total += c.DurationSec
	}
	m.TotalDurationSec = total
	return m, nil
}

func analyzeOne(path string, scenes bool, threshold float64) (*Clip, error) {
	c := &Clip{Path: path}

	probeCtx, probeCancel := context.WithTimeout(context.Background(), probeTimeout)
	defer probeCancel()
	probe := exec.CommandContext(probeCtx, "ffprobe",
		"-v", "quiet",
		"-print_format", "json",
		"-show_format",
		"-show_streams",
		path,
	)
	probeOut, err := probe.Output()
	if err != nil {
		if probeCtx.Err() == context.DeadlineExceeded {
			return nil, fmt.Errorf("ffprobe timed out after %s", probeTimeout)
		}
		return nil, fmt.Errorf("ffprobe: %w", err)
	}
	var probeData ffprobeOutput
	if err := json.Unmarshal(probeOut, &probeData); err != nil {
		return nil, fmt.Errorf("parse ffprobe: %w", err)
	}

	for _, s := range probeData.Streams {
		if s.CodecType == "video" {
			c.Width = s.Width
			c.Height = s.Height
			if strings.Contains(s.RFrameRate, "/") {
				fps, err := parseFrameRate(s.RFrameRate)
				if err != nil {
					return nil, fmt.Errorf("clip %s: invalid frame rate: %w", path, err)
				}
				c.FPS = fps
			}
		}
		if s.CodecType == "audio" {
			c.HasAudio = true
		}
	}

	dur, err := strconv.ParseFloat(probeData.Format.Duration, 64)
	if err != nil {
		return nil, fmt.Errorf("invalid duration %q: %w", probeData.Format.Duration, err)
	}
	c.DurationSec = dur

	if scenes {
		detected, err := detectScenes(path, threshold, c.DurationSec)
		if err != nil {
			return nil, err
		}
		if len(detected) == 0 {
			detected = []Scene{{StartSec: 0, EndSec: c.DurationSec}}
		}
		c.Scenes = detected
	} else {
		c.Scenes = []Scene{{StartSec: 0, EndSec: c.DurationSec}}
	}
	return c, nil
}

func detectScenes(path string, threshold float64, totalDurationSec float64) ([]Scene, error) {
	ctx, cancel := context.WithTimeout(context.Background(), sceneDetectTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, "ffmpeg",
		"-i", path,
		"-vf", fmt.Sprintf("select='gt(scene,%f)',showinfo", threshold),
		"-f", "null", "-",
	)
	out, err := cmd.CombinedOutput()
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return nil, fmt.Errorf("ffmpeg scene detect timed out after %s", sceneDetectTimeout)
		}
		return nil, fmt.Errorf("ffmpeg scene detect: %w (%s)", err, strings.TrimSpace(string(out)))
	}
	var cuts []float64
	for _, line := range strings.Split(string(out), "\n") {
		if !strings.Contains(line, "showinfo") {
			continue
		}
		idx := strings.Index(line, "pts_time:")
		if idx < 0 {
			continue
		}
		rest := line[idx+len("pts_time:"):]
		end := strings.IndexAny(rest, " \t\n")
		if end < 0 {
			end = len(rest)
		}
		t, err := strconv.ParseFloat(rest[:end], 64)
		if err == nil {
			cuts = append(cuts, t)
		}
	}

	scenes := make([]Scene, 0, len(cuts)+1)
	prev := 0.0
	for _, t := range cuts {
		scenes = append(scenes, Scene{StartSec: prev, EndSec: t})
		prev = t
	}
	scenes = append(scenes, Scene{StartSec: prev, EndSec: totalDurationSec})
	return scenes, nil
}
