package metadata

import (
	"encoding/json"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
)

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

	probe := exec.Command("ffprobe",
		"-v", "quiet",
		"-print_format", "json",
		"-show_format",
		"-show_streams",
		path,
	)
	probeOut, err := probe.Output()
	if err != nil {
		return nil, fmt.Errorf("ffprobe: %w", err)
	}
	var probeData struct {
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
	if err := json.Unmarshal(probeOut, &probeData); err != nil {
		return nil, fmt.Errorf("parse ffprobe: %w", err)
	}

	for _, s := range probeData.Streams {
		if s.CodecType == "video" {
			c.Width = s.Width
			c.Height = s.Height
			if strings.Contains(s.RFrameRate, "/") {
				parts := strings.SplitN(s.RFrameRate, "/", 2)
				num, _ := strconv.ParseFloat(parts[0], 64)
				den, _ := strconv.ParseFloat(parts[1], 64)
				if den > 0 {
					c.FPS = num / den
				}
			}
		}
		if s.CodecType == "audio" {
			c.HasAudio = true
		}
	}

	if dur, err := strconv.ParseFloat(probeData.Format.Duration, 64); err == nil {
		c.DurationSec = dur
	}

	if scenes {
		detected, err := detectScenes(path, threshold)
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

func detectScenes(path string, threshold float64) ([]Scene, error) {
	cmd := exec.Command("ffmpeg",
		"-i", path,
		"-vf", fmt.Sprintf("select='gt(scene,%f)',showinfo", threshold),
		"-f", "null", "-",
	)
	out, err := cmd.CombinedOutput()
	if err != nil {
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

	durCmd := exec.Command("ffprobe",
		"-v", "quiet",
		"-print_format", "json",
		"-show_format", path,
	)
	durOut, err := durCmd.Output()
	if err != nil {
		return nil, fmt.Errorf("ffprobe for duration: %w", err)
	}
	var durData struct {
		Format struct {
			Duration string `json:"duration"`
		} `json:"format"`
	}
	if err := json.Unmarshal(durOut, &durData); err != nil {
		return nil, fmt.Errorf("parse duration: %w", err)
	}
	totalDur, err := strconv.ParseFloat(durData.Format.Duration, 64)
	if err != nil {
		return nil, fmt.Errorf("parse duration float: %w", err)
	}

	scenes := make([]Scene, 0, len(cuts)+1)
	prev := 0.0
	for _, t := range cuts {
		scenes = append(scenes, Scene{StartSec: prev, EndSec: t})
		prev = t
	}
	scenes = append(scenes, Scene{StartSec: prev, EndSec: totalDur})
	return scenes, nil
}
