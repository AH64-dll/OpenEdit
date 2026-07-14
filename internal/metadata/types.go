package metadata

// Manifest is the output of the `analyze` CLI.
type Manifest struct {
	Version          int     `json:"version"`
	Clips            []Clip  `json:"clips"`
	TotalDurationSec float64 `json:"totalDurationSec"`
}

// Clip is one source media file.
type Clip struct {
	Path        string  `json:"path"`
	DurationSec float64 `json:"durationSec"`
	Width       int     `json:"width"`
	Height      int     `json:"height"`
	FPS         float64 `json:"fps"`
	HasAudio    bool    `json:"hasAudio"`
	Scenes      []Scene `json:"scenes"`
}

// Scene is a detected scene boundary within a Clip.
type Scene struct {
	StartSec float64 `json:"startSec"`
	EndSec   float64 `json:"endSec"`
}
