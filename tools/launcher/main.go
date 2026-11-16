// O-Ring.exe: starts the desktop program with the bundled Python, without a console window.
//
// Runs python\pythonw.exe desktop\main.py from the folder of the exe (the unzipped package).
// Program output goes to %LOCALAPPDATA%\o-ring\son_calisma.log; if the program ends with an
// error, the end of that log is shown in a message box. The Python process is tied to the
// launcher by a Windows job object. Nothing is installed and no administrator rights are needed.
//
// Build (from this folder): GOOS=windows GOARCH=amd64 go build -ldflags "-H=windowsgui -s -w" -o O-Ring.exe .
// Icon and manifest (asInvoker, DPI aware) are in rsrc_windows_amd64.syso, regenerated with
// github.com/akavel/rsrc: rsrc -manifest app.manifest -ico icon.ico -arch amd64 -o rsrc_windows_amd64.syso
package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const appTitle = "O-Ring Yuva Tasarım Programı"

func main() {
	if err := run(); err != nil {
		showError(err.Error())
		os.Exit(1)
	}
}

func run() error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	root := filepath.Dir(exe)
	if d := os.Getenv("ORING_ROOT"); d != "" { // for testing
		root = d
	}
	python := pythonPath(root)
	script := filepath.Join(root, "desktop", "main.py")
	for _, p := range []string{python, script} {
		if _, err := os.Stat(p); err != nil {
			return fmt.Errorf("Dosya bulunamadı:\n%s\n\nO-Ring.exe, ZIP'ten çıkarılan o-ring klasörünün içinde çalıştırılmalıdır.", p)
		}
	}
	data := dataDir()
	if err := os.MkdirAll(data, 0o755); err != nil {
		return err
	}
	logPath := filepath.Join(data, "son_calisma.log")
	logf, err := os.Create(logPath)
	if err != nil {
		return err
	}
	defer logf.Close()

	cmd := exec.Command(python, script)
	cmd.Dir = root
	cmd.Stdout, cmd.Stderr = logf, logf
	cmd.Env = append(os.Environ(), "PYTHONUTF8=1", "PYTHONIOENCODING=utf-8")
	hideWindow(cmd)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("program başlatılamadı: %v", err)
	}
	bindToLauncher(cmd)
	if err := cmd.Wait(); err != nil {
		return failed(err, logPath)
	}
	return nil
}

func failed(err error, logPath string) error {
	tail := ""
	if b, e := os.ReadFile(logPath); e == nil {
		lines := strings.Split(strings.TrimSpace(string(b)), "\n")
		if len(lines) > 15 {
			lines = lines[len(lines)-15:]
		}
		tail = strings.Join(lines, "\n")
	}
	return fmt.Errorf("Program bir hatayla kapandı (%v).\n\nKayıt dosyası: %s\n\n%s", err, logPath, tail)
}

func dataDir() string {
	if d, err := os.UserCacheDir(); err == nil { // %LocalAppData% on Windows
		return filepath.Join(d, "o-ring")
	}
	return filepath.Join(os.TempDir(), "o-ring")
}
