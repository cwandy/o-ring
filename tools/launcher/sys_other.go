//go:build !windows

// Non-Windows build: only for testing the launcher logic on a developer machine.
package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

func pythonPath(root string) string {
	if p := os.Getenv("ORING_PYTHON"); p != "" {
		return p
	}
	return filepath.Join(root, "python", "bin", "python")
}

func hideWindow(*exec.Cmd)     {}
func bindToLauncher(*exec.Cmd) {}
func showError(text string)    { fmt.Fprintln(os.Stderr, "ERROR:", text) }
