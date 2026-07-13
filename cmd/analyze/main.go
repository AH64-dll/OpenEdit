package main

import (
	"flag"
	"fmt"
	"os"

	"mlt-pipeline/internal/metadata"
)

func main() {
	scenes := flag.Bool("scenes", true, "run scene detection")
	threshold := flag.Float64("scene-threshold", 0.3, "scene-change sensitivity in [0,1] (lower = more sensitive)")
	output := flag.String("output", "metadata.json", "output path for the manifest JSON")
	flag.Parse()

	paths := flag.Args()
	if len(paths) == 0 {
		fmt.Fprintln(os.Stderr, "usage: analyze [--scenes] [--scene-threshold N] --output FILE <clip1> [clip2 ...]")
		os.Exit(2)
	}

	m, err := metadata.Analyze(paths, *scenes, *threshold)
	if err != nil {
		fmt.Fprintln(os.Stderr, "analyze:", err)
		os.Exit(1)
	}
	if err := metadata.Save(*output, m); err != nil {
		fmt.Fprintln(os.Stderr, "save:", err)
		os.Exit(1)
	}
	fmt.Printf("wrote %s (%d clips, %.2fs total)\n", *output, len(m.Clips), m.TotalDurationSec)
}
