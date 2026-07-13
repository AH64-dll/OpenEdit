package main

import (
	"flag"
	"fmt"
	"os"

	"mlt-pipeline/internal/edl"
	"mlt-pipeline/internal/metadata"
	"mlt-pipeline/internal/mlt"
)

func main() {
	edlPath := flag.String("edl", "edl.json", "path to EDL JSON")
	metadataPath := flag.String("metadata", "metadata.json", "path to manifest JSON")
	output := flag.String("output", "project.mlt", "output path for MLT")
	noClamp := flag.Bool("no-clamp", false, "disable in/out clamping against the manifest")
	flag.Parse()

	m, err := metadata.Load(*metadataPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "compile:", err)
		os.Exit(1)
	}
	e, err := edl.Load(*edlPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "compile:", err)
		os.Exit(1)
	}
	if err := edl.Validate(e, m); err != nil {
		fmt.Fprintln(os.Stderr, "compile:", err)
		os.Exit(1)
	}
	if !*noClamp {
		warnings, err := edl.Clamp(e, m)
		if err != nil {
			fmt.Fprintln(os.Stderr, "compile:", err)
			os.Exit(1)
		}
		for _, w := range warnings {
			fmt.Fprintln(os.Stderr, "compile: warning:", w)
		}
	}
	out, err := mlt.Generate(e, m)
	if err != nil {
		fmt.Fprintln(os.Stderr, "compile:", err)
		os.Exit(1)
	}
	if err := os.WriteFile(*output, []byte(out), 0644); err != nil {
		fmt.Fprintln(os.Stderr, "compile: write:", err)
		os.Exit(1)
	}
	fmt.Printf("wrote %s (%d segments)\n", *output, len(e.Segments))
}
