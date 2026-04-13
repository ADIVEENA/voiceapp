# ============================================================
# FILE: ml/tray_app.py — ACCURACY FIRST VERSION
#
# PRIORITY: 100% accurate text. Zero hallucinations.
#
# HOW IT WORKS:
#   1. Press Ctrl+Space
#   2. Speak your full sentence clearly
#   3. Stop speaking — 2s silence = auto stop
#   4. Whisper small transcribes full audio at once
#   5. NLP cleans grammar
#   6. Perfect text appears in your app
#
# NO live streaming. NO chunk confusion. NO backspace bugs.
# JUST clean, accurate, reliable voice to text.
# ============================================================

import pystray
from PIL import Image, ImageDraw
import threading
import keyboard
import numpy as np
import time
import sys, os, json, winreg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stt import SpeechToText
from nlp import TextCleaner
from text_inject import TextInjector
from cursor_mic import FloatingMic

# ══════════════ SETTINGS ═══════════════════════════════════
HOTKEY            = "ctrl+space"
SILENCE_STOP_SECS = 2.0      # Seconds of silence before auto-stop
SILENCE_THRESHOLD = 0.008    # Energy below this = silence
SAMPLE_RATE       = 16000
CHUNK_SIZE        = 480      # 30ms chunks
CONFIG_FILE       = os.path.join(os.path.dirname(__file__), "config.json")
# ═══════════════════════════════════════════════════════════

def load_config():
    d = {"hotkey": HOTKEY, "autostart": False,
         "silence_secs": SILENCE_STOP_SECS}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return {**d, **json.load(f)}
        except Exception:
            pass
    return d

def save_config(c):
    with open(CONFIG_FILE, "w") as f:
        json.dump(c, f, indent=2)

def make_icon(state="idle"):
    img  = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cols = {
        "idle":       ("#1a1a2e", "#7c5cfc"),
        "recording":  ("#006600", "#ffffff"),
        "processing": ("#884400", "#ffffff"),
        "done":       ("#004499", "#ffffff"),
        "error":      ("#880000", "#ffffff"),
    }
    bg, fg = cols.get(state, cols["idle"])
    draw.ellipse([4, 4, 124, 124], fill=bg, outline=fg, width=5)
    draw.rounded_rectangle([48, 18, 80, 70], radius=16, fill=fg)
    draw.arc([30, 55, 98, 90], start=0, end=180, fill=fg, width=5)
    draw.line([64, 90, 64, 106], fill=fg, width=5)
    draw.line([46, 106, 82, 106], fill=fg, width=5)
    if state == "recording":
        draw.ellipse([96, 10, 118, 32], fill="#00ff44")
    return img


class VoiceTrayApp:

    def __init__(self):
        self.config          = load_config()
        self.is_recording    = False
        self.is_running      = True
        self.icon            = None
        self.last_transcript = "(none yet)"
        self.audio_buffer    = []
        self.silent_chunks   = 0
        self.silence_secs    = float(self.config.get("silence_secs", SILENCE_STOP_SECS))
        self.silence_limit   = int(self.silence_secs * SAMPLE_RATE / CHUNK_SIZE)

        print("Loading Whisper small model...")
        self.stt      = SpeechToText()
        self.cleaner  = TextCleaner()
        self.injector = TextInjector()
        self.mic      = FloatingMic()
        self.mic.start()
        self.mic.set_state("idle")

        import pyaudio
        self.pa     = pyaudio.PyAudio()
        self.stream = self.pa.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        print("All models loaded and ready!\n")

    def run(self):
        self._register_hotkey()
        threading.Thread(target=self._audio_loop, daemon=True).start()

        self.icon = pystray.Icon(
            name="VoiceApp",
            icon=make_icon("idle"),
            title="VoiceApp — Ctrl+Space to record",
            menu=pystray.Menu(
                pystray.MenuItem(
                    "VoiceApp  ·  Ctrl+Space to record",
                    None, enabled=False
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "📋  Last Transcript",
                    self._on_transcript
                ),
                pystray.MenuItem(
                    "⚙   Settings",
                    self._on_settings
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("⏸  Pause hotkey",  self._on_pause),
                pystray.MenuItem("▶  Resume hotkey", self._on_resume),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "🚀  Start with Windows",
                    self._on_toggle_autostart,
                    checked=lambda i: self.config.get("autostart", False)
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("✕  Quit VoiceApp", self._on_quit),
            )
        )

        print("╔══════════════════════════════════════════╗")
        print("║        VOICEAPP IS READY                 ║")
        print("╠══════════════════════════════════════════╣")
        print("║                                          ║")
        print("║  1. Click where you want to type         ║")
        print("║  2. Press Ctrl+Space once                ║")
        print("║  3. Speak your full sentence             ║")
        print("║  4. Pause — auto stops in 2 seconds      ║")
        print("║  5. Accurate text appears instantly      ║")
        print("║                                          ║")
        print("║  Tray icon = bottom right of taskbar     ║")
        print("║  Right-click for menu                    ║")
        print("╚══════════════════════════════════════════╝\n")

        self.icon.run()

    # ── Hotkey ────────────────────────────────────────────
    def _register_hotkey(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        try:
            keyboard.add_hotkey(
                "ctrl+space",
                self._on_hotkey,
                suppress=False
            )
            print("✅ Hotkey ready: Ctrl+Space")
        except Exception as e:
            print(f"Hotkey error: {e}")

    def _on_hotkey(self):
        if not self.is_recording:
            self._start_recording()

    # ── Recording ─────────────────────────────────────────
    def _start_recording(self):
        self.is_recording  = True
        self.audio_buffer  = []
        self.silent_chunks = 0

        self._set_icon("recording")
        self.mic.set_state("recording")

        if self.icon:
            self.icon.title = "VoiceApp — 🟢 Listening... speak now"

        print("🟢 Listening — speak your full sentence...")
        print(f"   Auto-stops after {self.silence_secs:.0f}s silence\n")

    # ── Audio Loop ────────────────────────────────────────
    def _audio_loop(self):
        """
        Continuously reads mic.
        Collects audio while recording.
        Detects silence to auto-stop.
        """
        while self.is_running:
            if self.is_recording:
                try:
                    raw    = self.stream.read(
                        CHUNK_SIZE,
                        exception_on_overflow=False
                    )
                    chunk  = np.frombuffer(raw, dtype=np.float32)
                    energy = float(np.sqrt(np.mean(chunk ** 2)))

                    # Collect audio
                    self.audio_buffer.append(chunk)

                    # Update mic waveform animation
                    self.mic.update_waveform(chunk)

                    # Silence detection
                    if energy < SILENCE_THRESHOLD:
                        self.silent_chunks += 1
                        secs_silent = (
                            self.silent_chunks * CHUNK_SIZE / SAMPLE_RATE
                        )
                        remaining = max(0, self.silence_secs - secs_silent)

                        if self.icon and remaining > 0:
                            self.icon.title = (
                                f"VoiceApp — ⬜ "
                                f"Stopping in {remaining:.0f}s..."
                            )

                        # Auto stop when silence limit reached
                        if self.silent_chunks >= self.silence_limit:
                            self._stop_and_transcribe()

                    else:
                        # Speech — reset silence counter
                        self.silent_chunks = 0
                        if self.icon:
                            self.icon.title = "VoiceApp — 🟢 Listening..."

                except Exception:
                    pass
            else:
                time.sleep(0.01)

    # ── Transcribe Pipeline ───────────────────────────────
    def _stop_and_transcribe(self):
        """Silence detected — stop and transcribe full audio."""
        self.is_recording  = False
        audio_data         = list(self.audio_buffer)
        self.audio_buffer  = []

        self._set_icon("processing")
        self.mic.set_state("processing")

        if self.icon:
            self.icon.title = "VoiceApp — ⚙️ Transcribing..."

        threading.Thread(
            target=self._run_pipeline,
            args=(audio_data,),
            daemon=True
        ).start()

    def _run_pipeline(self, audio_data):
        """
        Full accuracy pipeline:
        audio → Whisper small → NLP clean → inject
        """
        try:
            if not audio_data:
                print("(no audio captured)")
                self._reset_idle()
                return

            # Combine all chunks into one array
            audio    = np.concatenate(audio_data)
            duration = len(audio) / SAMPLE_RATE

            if duration < 0.5:
                print(f"(too short: {duration:.1f}s — ignored)")
                self._reset_idle()
                return

            print(f"⚙️  Transcribing {duration:.1f}s...")

            # ── STEP 1: Whisper small — maximum accuracy ──
            raw_text = self.stt.transcribe(audio)

            if not raw_text or not raw_text.strip():
                print("(no speech detected)")
                self._set_icon("error")
                self.mic.set_state("idle")
                if self.icon:
                    self.icon.title = "VoiceApp — ❌ Nothing detected"
                time.sleep(1.5)
                self._reset_idle()
                return

            print(f"📝 Whisper: {raw_text}")

            # ── STEP 2: NLP — clean grammar ───────────────
            clean_text = self.cleaner.clean(raw_text)
            print(f"✨ Clean:   {clean_text}")

            # ── STEP 3: Inject into active window ─────────
            self.injector.inject(clean_text)
            self.last_transcript = clean_text

            print(f"💉 Injected successfully!\n")

            # Show done
            self._set_icon("done")
            self.mic.set_state("done")
            if self.icon:
                self.icon.title = "VoiceApp — ✅ Done!"

            time.sleep(1.2)

        except Exception as e:
            print(f"Pipeline error: {e}")
            self._set_icon("error")
            time.sleep(1.0)

        self._reset_idle()

    def _reset_idle(self):
        self._set_icon("idle")
        self.mic.set_state("idle")
        if self.icon:
            self.icon.title = "VoiceApp — Ctrl+Space to record"
        print("Ready — press Ctrl+Space to record again.\n")

    def _set_icon(self, state):
        if self.icon:
            try:
                self.icon.icon = make_icon(state)
            except Exception:
                pass

    # ── Menu Actions ──────────────────────────────────────
    def _on_pause(self, icon, item):
        keyboard.unhook_all()
        self.mic.set_state("hidden")
        if self.icon:
            self.icon.title = "VoiceApp — ⏸ Paused"
        print("⏸ Hotkey paused")

    def _on_resume(self, icon, item):
        self._register_hotkey()
        self.mic.set_state("idle")
        if self.icon:
            self.icon.title = "VoiceApp — Ctrl+Space to record"
        print("▶ Hotkey resumed")

    def _on_transcript(self, icon, item):
        threading.Thread(
            target=self._show_transcript_popup,
            daemon=True
        ).start()

    def _show_transcript_popup(self):
        import tkinter as tk
        r = tk.Tk()
        r.title("Last Transcript")
        r.geometry("540x200")
        r.configure(bg="#1e1e1e")
        r.attributes("-topmost", True)

        tk.Label(
            r, text="Last Transcript",
            font=("Segoe UI", 12, "bold"),
            bg="#1e1e1e", fg="white"
        ).pack(pady=10)

        tk.Label(
            r, text=self.last_transcript,
            font=("Segoe UI", 11),
            bg="#1e1e1e", fg="#cccccc",
            wraplength=500
        ).pack(padx=20)

        tk.Button(
            r, text="📋  Copy & Close",
            command=lambda: [
                r.clipboard_clear(),
                r.clipboard_append(self.last_transcript),
                r.destroy()
            ],
            bg="#0078d4", fg="white",
            font=("Segoe UI", 10),
            relief="flat", padx=15, pady=6
        ).pack(pady=12)

        r.mainloop()

    def _on_settings(self, icon, item):
        threading.Thread(
            target=self._show_settings_window,
            daemon=True
        ).start()

    def _show_settings_window(self):
        import tkinter as tk
        from tkinter import ttk, messagebox

        r = tk.Tk()
        r.title("VoiceApp Settings")
        r.geometry("420, 340")
        r.resizable(False, False)
        r.configure(bg="#1e1e1e")
        r.attributes("-topmost", True)

        tk.Label(
            r, text="VoiceApp Settings",
            font=("Segoe UI", 14, "bold"),
            bg="#1e1e1e", fg="white"
        ).pack(pady=15)

        def make_row(label, default):
            f = tk.Frame(r, bg="#1e1e1e")
            f.pack(fill="x", padx=25, pady=8)
            tk.Label(
                f, text=label,
                bg="#1e1e1e", fg="#aaaaaa",
                font=("Segoe UI", 10),
                width=24, anchor="w"
            ).pack(side="left")
            v = tk.StringVar(value=default)
            tk.Entry(
                f, textvariable=v,
                bg="#2d2d2d", fg="white",
                font=("Segoe UI", 10), width=14,
                insertbackground="white"
            ).pack(side="right")
            return v

        hk_var  = make_row(
            "Hotkey:",
            self.config.get("hotkey", HOTKEY)
        )
        sil_var = make_row(
            "Silence stop (seconds):",
            str(self.config.get("silence_secs", SILENCE_STOP_SECS))
        )

        # Autostart toggle
        f3 = tk.Frame(r, bg="#1e1e1e")
        f3.pack(fill="x", padx=25, pady=8)
        tk.Label(
            f3, text="Start with Windows:",
            bg="#1e1e1e", fg="#aaaaaa",
            font=("Segoe UI", 10),
            width=24, anchor="w"
        ).pack(side="left")
        av = tk.BooleanVar(value=self.config.get("autostart", False))
        tk.Checkbutton(
            f3, variable=av,
            bg="#1e1e1e",
            activebackground="#1e1e1e",
            selectcolor="#0078d4",
            fg="white"
        ).pack(side="right")

        # Info label
        tk.Label(
            r,
            text="Tip: Speak clearly in a quiet room for best accuracy",
            font=("Segoe UI", 9),
            bg="#1e1e1e", fg="#555577"
        ).pack(pady=4)

        def save():
            try:
                sil = float(sil_var.get())
            except ValueError:
                sil = SILENCE_STOP_SECS

            self.config["hotkey"]       = hk_var.get()
            self.config["silence_secs"] = sil
            self.config["autostart"]    = av.get()

            # Update silence limit live
            self.silence_secs  = sil
            self.silence_limit = int(sil * SAMPLE_RATE / CHUNK_SIZE)

            save_config(self.config)

            if av.get():
                self._enable_autostart()
            else:
                self._disable_autostart()

            messagebox.showinfo(
                "Saved",
                "Settings saved!\n"
                "Restart VoiceApp if you changed the hotkey."
            )
            r.destroy()

        tk.Button(
            r, text="Save Settings",
            command=save,
            bg="#0078d4", fg="white",
            font=("Segoe UI", 11, "bold"),
            relief="flat", padx=20, pady=8
        ).pack(pady=16)

        r.mainloop()

    def _on_toggle_autostart(self, icon, item):
        self.config["autostart"] = not self.config.get("autostart", False)
        save_config(self.config)
        if self.config["autostart"]:
            self._enable_autostart()
        else:
            self._disable_autostart()

    def _enable_autostart(self):
        try:
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            cmd = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(k, "VoiceApp", 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(k)
            print("✅ Starts with Windows enabled")
        except Exception as e:
            print(f"Autostart error: {e}")

    def _disable_autostart(self):
        try:
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(k, "VoiceApp")
            winreg.CloseKey(k)
            print("Autostart disabled")
        except Exception:
            pass

    def _on_quit(self, icon, item):
        self.is_running = False
        keyboard.unhook_all()
        self.mic.stop()
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.pa.terminate()
        icon.stop()
        print("Goodbye!")


if __name__ == "__main__":
    print("\n" + "=" * 45)
    print("  VoiceApp — Starting (Accuracy First)")
    print("=" * 45 + "\n")
    VoiceTrayApp().run()
