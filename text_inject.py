# ============================================================
# FILE: ml/text_inject.py  (FINAL VERSION)
# HOW TO RUN: python text_inject.py
# ============================================================

import ctypes
import time
import win32clipboard
import win32con
import win32gui

PUL = ctypes.POINTER(ctypes.c_ulong)


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.c_ushort),
        ("wScan",       ctypes.c_ushort),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg",    ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class Input_I(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii",   Input_I),
    ]


INPUT_KEYBOARD    = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP   = 0x0002
VK_CONTROL        = 0x11
VK_V              = 0x56


class TextInjector:

    def inject(self, text, method="clipboard"):
        if not text:
            return True
        try:
            if method == "clipboard":
                return self._inject_clipboard(text)
            else:
                return self._inject_keys(text)
        except Exception as e:
            print(f"Injection error: {e}")
            return False

    def inject_into_window(self, hwnd, text):
        """Inject text directly into a specific window by handle."""
        try:
            # Focus the target window first
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.3)  # Wait for window to become active
            return self._inject_clipboard(text)
        except Exception as e:
            print(f"Window injection error: {e}")
            return False

    def _inject_clipboard(self, text):
        original = self._get_clipboard()
        try:
            self._set_clipboard(text)
            time.sleep(0.1)
            self._press_ctrl_v()
            time.sleep(0.15)
            if original:
                self._set_clipboard(original)
            return True
        except Exception as e:
            print(f"Clipboard error: {e}")
            return False

    def _inject_keys(self, text):
        user32 = ctypes.windll.user32
        for char in text:
            extra = ctypes.c_ulong(0)
            ii_down = Input_I()
            ii_down.ki = KeyBdInput(
                wVk=0, wScan=ord(char),
                dwFlags=KEYEVENTF_UNICODE, time=0,
                dwExtraInfo=ctypes.pointer(extra),
            )
            inp_down = Input(type=INPUT_KEYBOARD, ii=ii_down)
            ii_up = Input_I()
            ii_up.ki = KeyBdInput(
                wVk=0, wScan=ord(char),
                dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0,
                dwExtraInfo=ctypes.pointer(extra),
            )
            inp_up = Input(type=INPUT_KEYBOARD, ii=ii_up)
            user32.SendInput(1, ctypes.pointer(inp_down), ctypes.sizeof(Input))
            user32.SendInput(1, ctypes.pointer(inp_up),   ctypes.sizeof(Input))
            time.sleep(0.002)
        return True

    def _press_ctrl_v(self):
        user32 = ctypes.windll.user32
        extra  = ctypes.c_ulong(0)

        def key_event(vk, flags):
            ii = Input_I()
            ii.ki = KeyBdInput(
                wVk=vk, wScan=0, dwFlags=flags,
                time=0, dwExtraInfo=ctypes.pointer(extra),
            )
            return Input(type=INPUT_KEYBOARD, ii=ii)

        for event in [
            key_event(VK_CONTROL, 0),
            key_event(VK_V, 0),
            key_event(VK_V, KEYEVENTF_KEYUP),
            key_event(VK_CONTROL, KEYEVENTF_KEYUP),
        ]:
            user32.SendInput(1, ctypes.pointer(event), ctypes.sizeof(Input))
            time.sleep(0.01)

    def _get_clipboard(self):
        try:
            win32clipboard.OpenClipboard()
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return data
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
            return ""

    def _set_clipboard(self, text):
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        win32clipboard.CloseClipboard()


def find_notepad():
    """Find the Notepad window handle."""
    result = []

    def callback(hwnd, extra):
        title = win32gui.GetWindowText(hwnd)
        if "Notepad" in title and win32gui.IsWindowVisible(hwnd):
            result.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return result[0] if result else None


if __name__ == "__main__":
    injector = TextInjector()

    print("")
    print("Text Injection Test")
    print("=" * 45)
    print("")

    # Step 1: Find Notepad automatically
    print("Step 1: Looking for Notepad window...")
    notepad_hwnd = find_notepad()

    if notepad_hwnd:
        print(f"  Found Notepad! (window ID: {notepad_hwnd})")
        print("")
        print("Step 2: Injecting text into Notepad in 3 seconds...")
        print("")

        for i in range(3, 0, -1):
            print(f"  {i}...")
            time.sleep(1)

        print("  INJECTING!")
        test_text = "Hello from VoiceApp! Text injection is working perfectly!"
        success = injector.inject_into_window(
            notepad_hwnd,
            test_text
        )

        if success:
            print("")
            print("  Done! Text was sent to Notepad directly.")
            print("  Check your Notepad window now.")
        else:
            print("  Something went wrong.")

    else:
        print("")
        print("  Notepad NOT found!")
        print("")
        print("  Please:")
        print("  1. Open Notepad (Windows key -> type Notepad -> Enter)")
        print("  2. Run this script again")
        print("")
        print("  The script finds Notepad automatically -")
        print("  you do NOT need to click anything!")
