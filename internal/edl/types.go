package edl

// EDL is the agent's output: a sequence of segments to play.
type EDL struct {
	Version           int       `json:"version"`
	TargetDurationSec float64   `json:"targetDurationSec"`
	Segments          []Segment `json:"segments"`
}

// Segment is one source-clip range to play.
type Segment struct {
	Source     string     `json:"source"`
	InSec      float64    `json:"inSec"`
	OutSec     float64    `json:"outSec"`
	Transition Transition `json:"transition,omitempty"`
}

// Transition is the type of join between this segment and the next.
type Transition string

const (
	TransitionCut  Transition = "cut"
	TransitionFade Transition = "fade"
)
