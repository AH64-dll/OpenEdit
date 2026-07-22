package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"time"
)

func main() {
	mltPath := flag.String("mlt", "project.mlt", "input MLT file")
	output := flag.String("output", "final.mp4", "output MP4 file")
	dryRun := flag.Bool("dry-run", false, "render a 640x360 proxy for fast iteration")
	niceLevel := flag.Int("nice", 10, "nice level for the render subprocess (0 = disabled)")
	vcodec := flag.String("vcodec", "libx264", "video codec")
	acodec := flag.String("acodec", "aac", "audio codec")
	timeout := flag.Duration("timeout", 0, "maximum render time before killing melt (for example 10m, 1h; 0 disables)")
	flag.Parse()

	consumer := fmt.Sprintf("avformat:%s", *output)
	args := []string{*mltPath, "-consumer", consumer, "vcodec=" + *vcodec, "acodec=" + *acodec}
	if *dryRun {
		args = append(args, "s=640x360", "preset=ultrafast")
	}

	ctx := context.Background()
	var cancel context.CancelFunc
	if *timeout > 0 {
		ctx, cancel = context.WithTimeout(ctx, *timeout)
		defer cancel()
	}

	var cmd *exec.Cmd
	if *niceLevel > 0 {
		// Wrap melt in `nice -n N` so the whole subprocess tree inherits.
		niceArgs := append([]string{"-n", fmt.Sprintf("%d", *niceLevel), "melt"}, args...)
		cmd = exec.CommandContext(ctx, "nice", niceArgs...)
	} else {
		cmd = exec.CommandContext(ctx, "melt", args...)
	}

	// Disable GPU access to prevent driver crashes on hybrid GPU Wayland systems.
	cmd.Env = append(os.Environ(),
		"CUDA_VISIBLE_DEVICES=",
		"LIBGL_ALWAYS_SOFTWARE=1",
		"__GL_YIELD=USLEEP",
		"QT_QPA_PLATFORM=offscreen",
	)

	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			fmt.Fprintf(os.Stderr, "render: timed out after %s; fix: retry with --timeout 0 for no limit or a larger duration\n", (*timeout).Round(time.Second))
			os.Exit(1)
		}
		fmt.Fprintln(os.Stderr, "render:", err)
		os.Exit(1)
	}
	fmt.Printf("wrote %s\n", *output)
}
