// O-Ring.exe: starts the program and shows it in its own window.
//
//  1. Picks a free local port and starts the bundled Python
//     (python\python.exe -m streamlit run app\streamlit_app.py) without a console window;
//     its output goes to a log file in the user's local application data folder.
//  2. Opens Microsoft Edge (or Chrome) in "app" mode: a plain window without tabs or address
//     bar, with a throw-away profile. A local start page waits until the server answers.
//  3. When that window is closed, the server is stopped. The server is also tied to the
//     launcher by a Windows job object, so it never outlives it.
//
// Without Edge/Chrome the default browser is used and a message box keeps the program
// running until "OK" is pressed. Nothing is installed and no administrator rights are needed.
//
// Build (from this folder): GOOS=windows GOARCH=amd64 go build -ldflags "-H=windowsgui -s -w" -o O-Ring.exe .
// Icon and manifest (asInvoker, DPI aware) are in rsrc_windows_amd64.syso, regenerated with
// github.com/akavel/rsrc: rsrc -manifest app.manifest -ico icon.ico -arch amd64 -o rsrc_windows_amd64.syso
package main

import (
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
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
	if _, err := os.Stat(python); err != nil {
		return fmt.Errorf("Python bulunamadı:\n%s\n\nO-Ring.exe, ZIP'ten çıkarılan o-ring klasörünün içinde çalıştırılmalıdır.", python)
	}

	data := dataDir()
	if err := os.MkdirAll(data, 0o755); err != nil {
		return err
	}
	port, err := freePort()
	if err != nil {
		return err
	}
	url := fmt.Sprintf("http://127.0.0.1:%d", port)

	logPath := filepath.Join(data, "son_calisma.log")
	logf, err := os.Create(logPath)
	if err != nil {
		return err
	}
	defer logf.Close()

	server := exec.Command(python, "-m", "streamlit", "run", filepath.Join(root, "app", "streamlit_app.py"),
		"--server.address", "127.0.0.1", "--server.port", fmt.Sprint(port), "--server.headless", "true",
		"--browser.gatherUsageStats", "false", "--client.toolbarMode", "minimal",
		"--server.fileWatcherType", "none", "--global.developmentMode", "false")
	server.Dir = root
	server.Stdout, server.Stderr = logf, logf
	server.Env = append(os.Environ(), "PYTHONUTF8=1", "PYTHONIOENCODING=utf-8")
	hideWindow(server)
	if err := server.Start(); err != nil {
		return fmt.Errorf("sunucu başlatılamadı: %v", err)
	}
	bindToLauncher(server)
	exited := make(chan error, 1)
	go func() { exited <- server.Wait() }()
	defer func() {
		if server.ProcessState == nil {
			_ = server.Process.Kill()
		}
	}()

	splash := filepath.Join(data, fmt.Sprintf("baslangic_%d.html", port))
	if err := os.WriteFile(splash, []byte(splashHTML(url)), 0o644); err != nil {
		return err
	}
	defer os.Remove(splash)

	browser := findBrowser()
	if browser == "" {
		return fallback(url, exited, logPath)
	}
	profile := filepath.Join(data, fmt.Sprintf("pencere_%d", port))
	win := exec.Command(browser, "--app="+fileURL(splash), "--user-data-dir="+profile,
		"--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
		"--window-size=1500,950", "--lang=tr")
	if err := win.Start(); err != nil {
		return fallback(url, exited, logPath)
	}
	opened := time.Now()
	winDone := make(chan error, 1)
	go func() { winDone <- win.Wait() }()

	select {
	case <-winDone:
		if time.Since(opened) < 3*time.Second { // browser refused (policy) or handed off
			return fallback(url, exited, logPath)
		}
	case err := <-exited:
		_ = win.Process.Kill()
		return serverFailed(err, logPath)
	}
	_ = server.Process.Kill()
	<-exited
	removeLater(profile)
	return nil
}

// fallback opens the default browser and keeps the server alive until the user confirms.
func fallback(url string, exited chan error, logPath string) error {
	if !waitHealthy(url, exited, 90*time.Second) {
		select {
		case err := <-exited:
			return serverFailed(err, logPath)
		default:
			return fmt.Errorf("Program 90 saniyede açılmadı. Ayrıntı: %s", logPath)
		}
	}
	openDefault(url)
	done := make(chan struct{})
	go func() {
		showInfo(fmt.Sprintf("Program tarayıcınızda açıldı:\n%s\n\nProgramı kapatmak için Tamam'a basın.", url))
		close(done)
	}()
	select {
	case <-done:
		return nil
	case err := <-exited:
		return serverFailed(err, logPath)
	}
}

func waitHealthy(url string, exited chan error, timeout time.Duration) bool {
	client := http.Client{Timeout: 2 * time.Second}
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if len(exited) > 0 {
			return false
		}
		if r, err := client.Get(url + "/_stcore/health"); err == nil {
			r.Body.Close()
			if r.StatusCode == 200 {
				return true
			}
		}
		time.Sleep(300 * time.Millisecond)
	}
	return false
}

func serverFailed(err error, logPath string) error {
	tail := ""
	if b, e := os.ReadFile(logPath); e == nil {
		lines := strings.Split(strings.TrimSpace(string(b)), "\n")
		if len(lines) > 12 {
			lines = lines[len(lines)-12:]
		}
		tail = strings.Join(lines, "\n")
	}
	return fmt.Errorf("Program beklenmedik şekilde kapandı (%v).\n\nKayıt dosyası: %s\n\n%s", err, logPath, tail)
}

func freePort() (int, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port, nil
}

func dataDir() string {
	if d, err := os.UserCacheDir(); err == nil { // %LocalAppData% on Windows
		return filepath.Join(d, "o-ring")
	}
	return filepath.Join(os.TempDir(), "o-ring")
}

func fileURL(p string) string {
	p = filepath.ToSlash(p)
	if !strings.HasPrefix(p, "/") {
		p = "/" + p
	}
	return "file://" + strings.ReplaceAll(p, " ", "%20")
}

func removeLater(dir string) {
	for i := 0; i < 10; i++ { // the browser may hold files for a moment after closing
		if os.RemoveAll(dir) == nil {
			return
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func splashHTML(url string) string {
	return `<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8"><title>` + appTitle + `</title>
<style>body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
font-family:"Segoe UI",Arial,sans-serif;background:#fcfcfb;color:#1f1f1d}
.c{text-align:center}.r{width:64px;height:64px;border-radius:50%;border:10px solid #2a78d6;
border-top-color:#cfe0f5;margin:0 auto 22px;animation:s 1s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}p{color:#52514e}</style></head><body><div class="c">
<div class="r"></div><h2>` + appTitle + `</h2><p>Başlatılıyor, lütfen bekleyin…</p>
<p id="m" style="font-size:13px"></p></div><script>
var u="` + url + `",t0=Date.now();
function poll(){fetch(u+"/_stcore/health",{mode:"no-cors",cache:"no-store"})
.then(function(){location.replace(u)})
.catch(function(){if(Date.now()-t0>60000)document.getElementById("m").textContent=
"Beklenenden uzun sürüyor. Pencere kendiliğinden açılmazsa kapatıp yeniden deneyin.";
setTimeout(poll,400)})}poll();</script></body></html>`
}
