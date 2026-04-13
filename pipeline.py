# ============================================================
# FILE: ml/pipeline.py
# PURPOSE: MAIN APP - Hold Ctrl+Space to record, release to stop
# HOW TO RUN: python pipeline.py
# ============================================================

import keyboard
import time
import threading
import numpy as np
import win32gui
import pyaudio

from audio_capture import AudioCapture
from stt import SpeechToText
from nlp import TextCleaner
from text_inject import TextInjector

# ── Settings ───────────────────────────────────────────────
HOLD_KEY    = "ctrl+space"   # Hold to record, release to transcribe
SAMPLE_RATE = 16000
CHUNK_SIZE  = 480            # 30ms per chunk


class VoiceApp:

    def __init__(self):
        print("")
        print("Loading models... please wait 30 seconds...")
        print("")

        # Load all modules
        self.stt      = SpeechToText()    # Whisper
        self.cleaner  = TextCleaner()     # NLP grammar cleaner
        self.injector = TextInjector()    # Windows text injection

        # Recording state
        self.is_recording = False
        self.audio_buffer = []
        self.is_running   = True
        self.target_hwnd  = None

        # Open microphone
        self.pa     = pyaudio.PyAudio()
        self.stream = self.pa.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )

        print("")
        print("=" * 50)
        print("  VOICEAPP IS READY")
        print("=" * 50)
        print("  HOW TO USE:")
        print("  1. Click into any app (Notepad, Gmail etc)")
        print("  2. HOLD Ctrl+Space")
        print("  3. Speak your text")
        print("  4. RELEASE Ctrl+Space")
        print("  5. Your text appears automatically!")
        print("")
        print("  Press Ctrl+C to quit")
        print("=" * 50)
        print("")

    def start(self):
        """Register hotkey and start main loop."""

        keyboard.on_press_key("space",   self._key_pressed)
        keyboard.on_release_key("space", self._key_released)

        print("Waiting... Hold Ctrl+Space to start recording.")
        print("")

        try:
            while self.is_running:
                if self.is_recording:
                    # Read mic audio while key is held
                    try:
                        raw   = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
                        chunk = np.frombuffer(raw, dtype=np.float32)
                        self.audio_buffer.append(chunk)
                    except Exception:
                        pass
                else:
                    time.sleep(0.01)

        except KeyboardInterrupt:
            self.stop()

    def _key_pressed(self, event):
        """Space pressed while Ctrl held — start recording."""
        if not keyboard.is_pressed("ctrl"):
            return
        if self.is_recording:
            return

        # Remember which window was active
        hwnd  = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)

        self.target_hwnd  = hwnd
        self.is_recording = True
        self.audio_buffer = []

        print(f"RECORDING → [{title}]  (release Ctrl+Space when done)")

    def _key_released(self, event):
        """Space released — stop recording and process."""
        if not self.is_recording:
            return

        self.is_recording = False

        if not self.audio_buffer:
            print("(nothing recorded)\n")
            return

        audio    = np.concatenate(self.audio_buffer)
        duration = len(audio) / SAMPLE_RATE

        if duration < 0.5:
            print(f"(too short: {duration:.1f}s — hold longer)\n")
            return

        print(f"STOPPED ({duration:.1f}s)")

        # Process in background — does not block
        thread = threading.Thread(
            target=self._process,
            args=(audio, self.target_hwnd),
            daemon=True
        )
        thread.start()

    def _process(self, audio, target_hwnd):
        """audio → whisper → clean → inject into window."""

        # Step 1: Whisper transcription
        print("Transcribing...")
        raw_text = self.stt.transcribe(audio)

        if not raw_text or not raw_text.strip():
            print("(no speech detected — speak louder)\n")
            return

        print(f"Raw:     {raw_text}")

        # Step 2: NLP cleaning
        clean_text = self.cleaner.clean(raw_text)
        print(f"Cleaned: {clean_text}")

        # Step 3: Focus original window and inject
        try:
            win32gui.SetForegroundWindow(target_hwnd)
            time.sleep(0.25)
        except Exception:
            pass

        success = self.injector.inject(clean_text)

        if success:
            print("Injected successfully!")
        else:
            print("Injection failed — trying again...")
            self.injector.inject(clean_text, method="keys")

        print("")
        print("Ready — hold Ctrl+Space to record again.")
        print("")

    def stop(self):
        """Shutdown cleanly."""
        self.is_running = False
        keyboard.unhook_all()
        self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()
        print("\nVoiceApp stopped.")


if __name__ == "__main__":
    app = VoiceApp()
    app.start()
