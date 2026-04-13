# ============================================================
# FILE: ml/audio_capture.py
# PURPOSE: Capture microphone input and detect when you speak
# HOW TO RUN: python audio_capture.py
# WHAT IT DOES: Prints "SPEAKING" when you talk, "SILENT" when quiet
# ============================================================

import pyaudio
import numpy as np
import threading
import queue
import time

# ── Settings ──────────────────────────────────────────────
SAMPLE_RATE    = 16000   # 16kHz — what Whisper expects
CHUNK_MS       = 30      # 30ms per audio chunk
CHUNK_SIZE     = int(SAMPLE_RATE * CHUNK_MS / 1000)  # = 480 samples
CHANNELS       = 1       # Mono mic
FORMAT         = pyaudio.paFloat32

SILENCE_THRESH = 0.01    # Energy below this = silence
SPEECH_THRESH  = 0.015   # Energy above this = speech
SILENCE_CHUNKS = 20      # 20 chunks of silence (600ms) = end of utterance


class AudioCapture:
    """
    Listens to your microphone continuously.
    Detects when you start and stop speaking.
    Collects complete utterances and puts them in a queue.
    """

    def __init__(self):
        self.audio_queue = queue.Queue()   # Complete utterances go here
        self.is_running  = False
        self.p           = None
        self.stream      = None

    def start(self):
        """Start listening to the microphone."""
        self.is_running = True
        self.p = pyaudio.PyAudio()

        # Open mic stream
        self.stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )

        print("🎙️  Microphone open. Listening...")
        print("    Speak into your mic. Press Ctrl+C to stop.\n")

        # Run capture in background thread
        t = threading.Thread(target=self._capture_loop, daemon=True)
        t.start()

    def _capture_loop(self):
        """
        Continuously reads from mic.
        Groups chunks into utterances (speech segments).
        """
        buffer        = []   # Current utterance chunks
        silent_count  = 0    # How many consecutive silent chunks
        is_speaking   = False

        while self.is_running:
            try:
                # Read one chunk from mic
                raw = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
                chunk = np.frombuffer(raw, dtype=np.float32)

                # Measure energy (loudness)
                energy = float(np.sqrt(np.mean(chunk ** 2)))

                # ── Voice Activity Detection ──────────────────
                if energy > SPEECH_THRESH:
                    # User is speaking
                    if not is_speaking:
                        print("🔴 SPEAKING...")
                        is_speaking = True
                    buffer.append(chunk)
                    silent_count = 0

                elif is_speaking:
                    # Was speaking, now quiet
                    buffer.append(chunk)  # Include trailing silence
                    silent_count += 1

                    if silent_count >= SILENCE_CHUNKS:
                        # Silence long enough = end of utterance
                        utterance = np.concatenate(buffer)
                        duration  = len(utterance) / SAMPLE_RATE

                        print(f"⚪ SILENT (captured {duration:.1f}s of speech)")

                        if duration > 0.3:  # Ignore clicks under 300ms
                            self.audio_queue.put(utterance)

                        # Reset for next utterance
                        buffer       = []
                        silent_count = 0
                        is_speaking  = False

            except Exception as e:
                print(f"Audio error: {e}")
                time.sleep(0.01)

    def get_utterance(self, timeout=0.1):
        """
        Get the next complete utterance from the queue.
        Returns numpy array or None if nothing ready.
        """
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        """Stop capturing."""
        self.is_running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()
        print("\n🎙️  Microphone closed.")


# ── Run this file directly to test ────────────────────────
if __name__ == "__main__":
    capture = AudioCapture()
    capture.start()

    print("Test mode: Speak and watch the output.")
    print("You should see SPEAKING / SILENT toggle as you talk.\n")

    try:
        utterance_count = 0
        while True:
            # Check if a complete utterance is ready
            audio = capture.get_utterance(timeout=0.5)
            if audio is not None:
                utterance_count += 1
                duration = len(audio) / SAMPLE_RATE
                print(f"✅ Utterance #{utterance_count} ready: {duration:.2f}s, "
                      f"{len(audio)} samples")
                print("   (This audio will be sent to Whisper for transcription)\n")

    except KeyboardInterrupt:
        capture.stop()
        print(f"\nDone. Captured {utterance_count} utterances total.")
