# ============================================================
# FILE: ml/cursor_mic.py  (FIXED - small icon, text-focus only)
# Small mic near cursor, only when typing, green when listening
# ============================================================

import tkinter as tk
import threading
import time
import ctypes
import ctypes.wintypes
import win32gui
import win32api
import win32con
import win32process
import numpy as np

# ── Get cursor/caret position ──────────────────────────────
def get_cursor_pos():
    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def get_caret_pos():
    """
    Get the TEXT CURSOR (caret) position — not mouse.
    This is the blinking line where you type.
    Returns (x, y) in screen coordinates or None.
    """
    try:
        # Method 1: Use Windows GUITHREADINFO
        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize",        ctypes.c_ulong),
                ("flags",         ctypes.c_ulong),
                ("hwndActive",    ctypes.wintypes.HWND),
                ("hwndFocus",     ctypes.wintypes.HWND),
                ("hwndCapture",   ctypes.wintypes.HWND),
                ("hwndMenuOwner", ctypes.wintypes.HWND),
                ("hwndMoveSize",  ctypes.wintypes.HWND),
                ("hwndCaret",     ctypes.wintypes.HWND),
                ("rcCaret",       ctypes.wintypes.RECT),
            ]

        info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        ctypes.windll.user32.GetGUIThreadInfo(0, ctypes.byref(info))

        # rcCaret is the caret rectangle in CLIENT coords
        rect = info.rcCaret
        hwnd = info.hwndCaret or info.hwndFocus

        if hwnd and (rect.left != 0 or rect.top != 0):
            # Convert client coords to screen coords
            pt = ctypes.wintypes.POINT(rect.left, rect.top)
            ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
            return pt.x, pt.y

    except Exception:
        pass

    return None   # No caret found


def is_text_field_focused():
    """
    Returns True if a text input field currently has keyboard focus.
    Checks the class name of the focused window.
    """
    try:
        hwnd = win32gui.GetForegroundWindow()
        # Get the focused child control
        tid  = win32api.GetCurrentThreadId()
        focused = ctypes.windll.user32.GetFocus()
        if not focused:
            focused = hwnd

        cls = win32gui.GetClassName(focused)

        text_classes = [
            "edit",
            "richedit",
            "richedit20",
            "richedit50",
            "scintilla",
            "chrome_renderwidgethosthwnd",
            "mozillawindowclass",
            "internetexplorer_server",
            "consolewindowclass",
            "thunderbird_",
        ]

        cls_lower = cls.lower()
        for tc in text_classes:
            if tc in cls_lower:
                return True

        # For Chrome/Edge — always assume text field possible
        title = win32gui.GetWindowText(hwnd).lower()
        if any(x in title for x in ["chrome", "edge", "firefox", "notepad", "word"]):
            return True

        return False

    except Exception:
        return False


# ══════════════════════════════════════════════════════════
#  FLOATING MIC WINDOW — small, near text cursor
# ══════════════════════════════════════════════════════════
class FloatingMic:

    SIZE     = 32    # Icon size in pixels (small!)
    OFFSET_X = 8     # Right of caret
    OFFSET_Y = -40   # Above caret

    def __init__(self):
        self.root       = None
        self.canvas     = None
        self.is_visible = False
        self.state      = "hidden"   # hidden, idle, recording, processing, done
        self.waveform   = [0.0] * 12
        self.is_running = True
        self._angle     = 0.0        # For spinner animation

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost",        True)
        self.root.attributes("-alpha",          0.95)
        self.root.attributes("-transparentcolor", "#010101")

        S = self.SIZE
        self.root.geometry(f"{S}x{S}+200+200")
        self.root.configure(bg="#010101")

        self.canvas = tk.Canvas(
            self.root, width=S, height=S,
            bg="#010101", highlightthickness=0
        )
        self.canvas.pack()
        self.root.withdraw()

        self.root.after(40,  self._position_loop)
        self.root.after(60,  self._draw_loop)
        self.root.mainloop()

    # ── Position near TEXT CARET ───────────────────────────
    def _position_loop(self):
        if not self.is_running:
            return
        try:
            if self.state in ("recording", "processing", "done"):
                # While active — stay near last known caret
                pos = get_caret_pos()
                if pos:
                    self._show_at(pos[0] + self.OFFSET_X, pos[1] + self.OFFSET_Y)
                elif not self.is_visible:
                    # Fallback to mouse position
                    mx, my = get_cursor_pos()
                    self._show_at(mx + self.OFFSET_X, my + self.OFFSET_Y)

            elif self.state == "idle":
                # Only show if a text field has focus AND caret is visible
                if is_text_field_focused():
                    pos = get_caret_pos()
                    if pos:
                        self._show_at(pos[0] + self.OFFSET_X, pos[1] + self.OFFSET_Y)
                    else:
                        self._hide()
                else:
                    self._hide()

            else:  # hidden
                self._hide()

        except Exception:
            pass

        self.root.after(40, self._position_loop)

    def _show_at(self, x, y):
        # Keep icon on screen
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = max(0, min(x, sw - self.SIZE))
        y  = max(0, min(y, sh - self.SIZE))
        self.root.geometry(f"{self.SIZE}x{self.SIZE}+{x}+{y}")
        if not self.is_visible:
            self.root.deiconify()
            self.is_visible = True

    def _hide(self):
        if self.is_visible:
            self.root.withdraw()
            self.is_visible = False

    # ── Draw ───────────────────────────────────────────────
    def _draw_loop(self):
        if not self.is_running:
            return
        try:
            self._draw()
            self._angle += 0.3
        except Exception:
            pass
        self.root.after(60, self._draw_loop)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        S = self.SIZE
        s = S - 2   # inner size
        state = self.state

        if state == "hidden":
            return

        # ── Background circle ──
        if state == "recording":
            bg = "#00cc44"    # GREEN when listening ✅
            fg = "#ffffff"
        elif state == "processing":
            bg = "#ff8c00"
            fg = "#ffffff"
        elif state == "done":
            bg = "#0066ff"
            fg = "#ffffff"
        else:
            bg = "#333355"    # Dark idle
            fg = "#aaaacc"

        c.create_oval(1, 1, S-1, S-1, fill=bg, outline="#ffffff", width=1)

        if state == "recording":
            # ── Waveform bars (green bg, white bars) ──
            bars    = 5
            bar_w   = 3
            gap     = 1
            total_w = bars * bar_w + (bars - 1) * gap
            start_x = (S - total_w) // 2
            mid_y   = S // 2

            for i in range(bars):
                amp = self.waveform[i % len(self.waveform)]
                h   = max(3, int(3 + amp * (S * 0.6)))
                x0  = start_x + i * (bar_w + gap)
                c.create_rectangle(
                    x0,        mid_y - h // 2,
                    x0 + bar_w, mid_y + h // 2,
                    fill="white", outline=""
                )

        elif state == "processing":
            # Spinning dots
            import math
            cx, cy = S // 2, S // 2
            r = S // 2 - 6
            for i in range(5):
                a     = self._angle + i * (2 * math.pi / 5)
                px    = cx + r * math.cos(a)
                py    = cy + r * math.sin(a)
                alpha = 1.0 - (i / 5)
                sz    = max(1, int(alpha * 3))
                gray  = int(150 + alpha * 105)
                col   = f"#{gray:02x}{gray:02x}ff"
                c.create_oval(px-sz, py-sz, px+sz, py+sz, fill=col, outline="")

        elif state == "done":
            # Checkmark
            m = S // 4
            c.create_line(m, S//2, S//2-2, S-m-2, fill="white", width=2, capstyle="round")
            c.create_line(S//2-2, S-m-2, S-m, m, fill="white", width=2, capstyle="round")

        else:
            # Idle mic icon — tiny
            mx  = S // 2
            c.create_rectangle(mx-4, 4, mx+4, 16, fill=fg, outline="")
            c.create_oval(mx-4, 2, mx+4, 10, fill=fg, outline="")
            c.create_oval(mx-4, 12, mx+4, 20, fill=fg, outline="")
            c.create_arc(mx-7, 12, mx+7, 22, start=0, extent=-180,
                         style="arc", outline=fg, width=1)
            c.create_line(mx, 22, mx, 26, fill=fg, width=1)
            c.create_line(mx-4, 26, mx+4, 26, fill=fg, width=1)

    # ── Public API ─────────────────────────────────────────
    def set_state(self, state):
        """
        state: "hidden"     - completely invisible
               "idle"       - shows only over text fields at caret
               "recording"  - green with waveform
               "processing" - orange spinner
               "done"       - blue checkmark
        """
        self.state = state
        if state == "hidden" or state == "idle":
            # Reset waveform
            self.waveform = [0.0] * 12

    def update_waveform(self, chunk):
        """Feed audio to animate waveform bars."""
        if chunk is None or len(chunk) == 0:
            return
        cs = max(1, len(chunk) // 12)
        for i in range(12):
            s = i * cs
            e = s + cs
            if e <= len(chunk):
                amp = float(np.sqrt(np.mean(chunk[s:e] ** 2)))
                self.waveform[i] = min(1.0, self.waveform[i] * 0.5 + amp * 10)

    def stop(self):
        self.is_running = False
        if self.root:
            try:
                self.root.quit()
            except Exception:
                pass
