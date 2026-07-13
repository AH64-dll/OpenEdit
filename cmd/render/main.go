package main

import (
	"flag"
	"fmt"
	"os"
	"os/exec"
)

func main() {
	mltPath := flag.String("mlt", "project.mlt", "input MLT file")
	output := flag.String("output", "final.mp4", "output MP4 file")
	dryRun := flag.Bool("dry-run", false, "render a 640x360 proxy for fast iteration")
	niceLevel := flag.Int("nice", 10, "nice level for the render subprocess (0 = disabled)")
	vcodec := flag.String("vcodec", "libx264", "video codec")
	acodec := flag.String("acodec", "aac", "audio codec")
	flag.Parse()

	consumer := fmt.Sprintf("avformat:%s", *output)
	args := []string{*mltPath, "-consumer", consumer, "vcodec=" + *vcodec, "acodec=" + *acodec}
	if *dryRun {
		args = append(args, "s=640x360", "preset=ultrafast")
	}

	var cmd *exec.Cmd
	if *niceLevel > 0 {
		// Wrap melt in `nice -n N` so the whole subprocess tree inherits.
		niceArgs := append([]string{"-n", fmt.Sprintf("%d", *niceLevel), "melt"}, args...)
		cmd = exec.Command("nice", niceArgs...)
	} else {
		cmd = exec.Command("melt", args...)
	}

	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "render:", err)
		os.Exit(1)
	}
	fmt.Printf("wrote %s\n", *output)
}
