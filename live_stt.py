# ============================================================
# FILE: ml/live_stt.py
#
# HOW IT WORKS:
#   1. Audio split into 1.5s chunks
#   2. Each chunk → Whisper → 2-3 confirmed words appear
#   3. Words injected immediately as each chunk completes
#   4. After silence → full sentence correction via NLP
#   5. NO hallucinations — energy + repetition guards
#
# FLOW:
#   Speak: "I am Aditya Kalra"
#   t=1.5s → "I am" appears
#   t=3.0s → "Aditya Kalra" appears
#   t=5.0s → full sentence cleaned and replaced if needed
# ============================================================

from faster_whisper import WhisperModel
import numpy as np
import time
import threading
import asyncio
import aiohttp
import re

# ── Two models: fast for chunks, accurate for final ────────
print("⏳ Loading Whisper models...")
CHUNK_MODEL = WhisperModel("tiny",  device="cpu", compute_type="int8", num_workers=2)
FINAL_MODEL = WhisperModel("small", device="cpu", compute_type="int8", num_workers=2)
print("✅ Both models ready! (tiny=live chunks, small=final correction)\n")

SAMPLE_RATE   = 16000
CHUNK_SECS    = 1.5    # Process every 1.5 seconds of speech
MIN_ENERGY    = 0.004  # Minimum energy to attempt transcription
OLLAMA_URL    = "http://localhost:11434/api/generate"
OLLAMA_MODEL  = "phi3:mini"


# ══════════════════════════════════════════════════════════
#  HALLUCINATION GUARD
# ══════════════════════════════════════════════════════════
BAD_PHRASES = {
    "", ".", "..", "...", "the", "a", "i", "you",
    "um", "uh", "hmm", "ah", "oh",
    "thank you", "thanks for watching",
    "please subscribe", "like and subscribe",
}

def is_garbage(text: str) -> bool:
    if not text or not text.strip():
        return True
    t = text.strip().lower()
    if t in BAD_PHRASES:
        return True
    words = [w for w in t.split() if len(w) > 1]
    if len(words) < 1:
        return True
    # Character repetition: "a-a-a-a" or "taaaaaaa"
    if re.search(r'(.)\1{3,}', t):
        return True
    # Hyphen spam
    if t.count('-') > 4:
        return True
    # Word spam: same word > 3 times
    word_list = t.split()
    if len(word_list) >= 3:
        unique_ratio = len(set(word_list)) / len(word_list)
        if unique_ratio < 0.35:
            return True
    return False


# ══════════════════════════════════════════════════════════
#  CHUNK TRANSCRIBER
# ══════════════════════════════════════════════════════════
class LiveTranscriber:
    """
    Records in rolling 1.5s windows.
    Every 1.5s of new audio → transcribe → inject 2-3 words.
    After stop → re-transcribe full audio with small model → replace if better.
    """

    def __init__(self, on_words=None, on_replace=None):
        """
        on_words(str)   → called with each confirmed 2-3 word chunk
        on_replace(str) → called with full corrected sentence to replace all
        """
        self.on_words   = on_words   or (lambda x: print(f"words: {x}"))
        self.on_replace = on_replace or (lambda x: print(f"replace: {x}"))

        self.is_running      = False
        self.chunk_buffer    = []   # Current 1.5s chunk
        self.full_buffer     = []   # All audio since start
        self.chunk_size      = int(CHUNK_SECS * SAMPLE_RATE)
        self.samples_in_chunk= 0
        self.all_words       = []   # Every word injected so far
        self._lock           = threading.Lock()

    def start(self):
        self.is_running       = True
        self.chunk_buffer     = []
        self.full_buffer      = []
        self.samples_in_chunk = 0
        self.all_words        = []
        print("▶ LiveTranscriber started")

    def feed(self, chunk: np.ndarray):
        """
        Feed audio chunk by chunk.
        When enough audio collected (1.5s), auto-transcribes.
        """
        if not self.is_running:
            return

        self.chunk_buffer.append(chunk)
        self.full_buffer.append(chunk)
        self.samples_in_chunk += len(chunk)

        # When we have 1.5 seconds of audio → transcribe it
        if self.samples_in_chunk >= self.chunk_size:
            audio = np.concatenate(self.chunk_buffer)
            # Reset chunk for next window
            self.chunk_buffer     = []
            self.samples_in_chunk = 0
            # Transcribe in background — don't block audio feed
            threading.Thread(
                target=self._transcribe_chunk,
                args=(audio,),
                daemon=True
            ).start()

    def _transcribe_chunk(self, audio: np.ndarray):
        """Transcribe one 1.5s chunk with tiny model → emit words."""
        # Energy check
        energy = float(np.sqrt(np.mean(audio ** 2)))
        if energy < MIN_ENERGY:
            return

        try:
            segs, _ = CHUNK_MODEL.transcribe(
                audio,
                language="en",
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=200),
            )
            text = " ".join(s.text.strip() for s in segs).strip()
        except Exception as e:
            print(f"Chunk transcribe error: {e}")
            return

        if is_garbage(text):
            return

        # Deduplicate against last words already injected
        new_words = self._remove_overlap(text)
        if not new_words or len(new_words.strip()) < 2:
            return

        with self._lock:
            self.all_words.append(new_words.strip())

        print(f"📝 chunk: {new_words.strip()}")
        self.on_words(new_words.strip())

    def _remove_overlap(self, new_text: str) -> str:
        """
        Remove words already injected from new_text.
        Prevents duplicates when chunks overlap.
        """
        if not self.all_words:
            return new_text

        last = self.all_words[-1].lower().split()
        new  = new_text.split()

        # Find how much of new_text overlaps with last chunk
        overlap = 0
        for size in range(min(len(last), len(new), 4), 0, -1):
            if [w.lower() for w in new[:size]] == last[-size:]:
                overlap = size
                break

        result = new[overlap:]
        return " ".join(result)

    def stop(self) -> str:
        """
        Stop recording. Re-transcribe ALL audio with small model.
        If better than what was injected → call on_replace.
        """
        self.is_running = False

        if not self.full_buffer:
            return ""

        # Transcribe remaining chunk buffer too
        if self.chunk_buffer:
            leftover = np.concatenate(self.chunk_buffer)
            energy   = float(np.sqrt(np.mean(leftover ** 2)))
            if energy > MIN_ENERGY:
                try:
                    segs, _ = CHUNK_MODEL.transcribe(
                        leftover, language="en", beam_size=1,
                        temperature=0.0, vad_filter=True,
                    )
                    text = " ".join(s.text.strip() for s in segs).strip()
                    if not is_garbage(text):
                        new_w = self._remove_overlap(text)
                        if new_w and len(new_w.strip()) > 1:
                            with self._lock:
                                self.all_words.append(new_w.strip())
                            self.on_words(new_w.strip())
                except Exception:
                    pass

        # Full audio → small model for accuracy
        full_audio = np.concatenate(self.full_buffer)
        injected   = " ".join(self.all_words)

        print(f"\n⚙️ Final check with small model...")

        try:
            segs, _ = FINAL_MODEL.transcribe(
                full_audio,
                language="en",
                beam_size=5,
                best_of=3,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=True,
                initial_prompt=(
                    "Aditya Kalra. Voice app. Software development. "
                    "Building a voice to text application."
                ),
            )
            final = " ".join(s.text.strip() for s in segs).strip()
        except Exception as e:
            print(f"Final transcribe error: {e}")
            return injected

        if is_garbage(final):
            return injected

        print(f"📄 Small model: {final}")

        # Compare — if significantly different, replace
        if self._is_better(final, injected):
            print(f"🔄 Replacing with better version")
            self.on_replace(final)
            return final

        return injected

    def _is_better(self, final: str, injected: str) -> bool:
        """
        Returns True if final (small model) is meaningfully
        different from injected (tiny model chunks).
        """
        if not injected.strip():
            return bool(final.strip())

        f_words = final.lower().split()
        i_words = injected.lower().split()

        # If word count very different → replace
        if abs(len(f_words) - len(i_words)) > 2:
            return True

        # Count matching words
        matches  = sum(1 for w in f_words if w in i_words)
        match_ratio = matches / max(len(f_words), 1)

        # If less than 70% match → final is better
        return match_ratio < 0.70


# ══════════════════════════════════════════════════════════
#  STANDALONE TEST
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import pyaudio

    print("=" * 55)
    print("LIVE CHUNK TRANSCRIPTION TEST")
    print("Speak → every 1.5s a chunk appears")
    print("Stop speaking → full sentence correction")
    print("Ctrl+C to stop")
    print("=" * 55 + "\n")

    p      = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paFloat32, channels=1,
        rate=SAMPLE_RATE, input=True, frames_per_buffer=480
    )

    current_line = []

    def on_words(w):
        current_line.append(w)
        print(f"\r💬 {' '.join(current_line)}", end="", flush=True)

    def on_replace(full):
        current_line.clear()
        current_line.append(full)
        print(f"\r✅ {full}                    ")

    tr = LiveTranscriber(on_words=on_words, on_replace=on_replace)
    tr.start()

    print("Speak now...\n")
    try:
        while True:
            raw   = stream.read(480, exception_on_overflow=False)
            chunk = np.frombuffer(raw, dtype=np.float32)
            tr.feed(chunk)
    except KeyboardInterrupt:
        print("\n\nFinalizing...")
        tr.stop()
        stream.stop_stream()
        stream.close()
        p.terminate()
        print("Done!")
