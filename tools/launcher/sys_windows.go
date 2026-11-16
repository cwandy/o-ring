//go:build windows

package main

import (
	"os/exec"
	"path/filepath"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

const createNoWindow = 0x08000000

var job windows.Handle // kept open for the launcher's lifetime; closing it kills the server

func pythonPath(root string) string { return filepath.Join(root, "python", "pythonw.exe") }

func hideWindow(c *exec.Cmd) {
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
}

// bindToLauncher puts the server in a job object that is killed when the launcher exits,
// even if the launcher itself is terminated.
func bindToLauncher(c *exec.Cmd) {
	h, err := windows.CreateJobObject(nil, nil)
	if err != nil {
		return
	}
	info := windows.JOBOBJECT_EXTENDED_LIMIT_INFORMATION{}
	info.BasicLimitInformation.LimitFlags = windows.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
	if _, err := windows.SetInformationJobObject(h, windows.JobObjectExtendedLimitInformation,
		uintptr(unsafe.Pointer(&info)), uint32(unsafe.Sizeof(info))); err != nil {
		windows.CloseHandle(h)
		return
	}
	p, err := windows.OpenProcess(windows.PROCESS_SET_QUOTA|windows.PROCESS_TERMINATE, false, uint32(c.Process.Pid))
	if err != nil {
		windows.CloseHandle(h)
		return
	}
	defer windows.CloseHandle(p)
	if windows.AssignProcessToJobObject(h, p) == nil {
		job = h
	}
}

func messageBox(text string, flags uint32) {
	t, _ := windows.UTF16PtrFromString(text)
	c, _ := windows.UTF16PtrFromString(appTitle)
	windows.MessageBox(0, t, c, flags|windows.MB_SETFOREGROUND)
}

func showError(text string) { messageBox(text, windows.MB_OK|windows.MB_ICONERROR) }
