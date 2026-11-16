//go:build !windows

// Non-Windows build: only for testing the launcher logic on a developer machine.
// ORING_BROWSER selects the "browser" program (it receives the same arguments as Edge).
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
func findBrowser() string      { return os.Getenv("ORING_BROWSER") }
func openDefault(url string)   { fmt.Println("open", url) }
func showError(text string)    { fmt.Fprintln(os.Stderr, "ERROR:", text) }
func showInfo(text string)     { fmt.Println("INFO:", text) }
