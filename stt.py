# ============================================================
# FILE: ml/stt.py  — HIGH ACCURACY VERSION
# Uses whisper small with best settings for accuracy
# NO live streaming — accuracy is the only priority
# ============================================================

from faster_whisper import WhisperModel
import numpy as np
import time

print("⏳ Loading Whisper small model (high accuracy)...")

MODEL = WhisperModel(
    "small",
    device="cpu",
    compute_type="int8",
    num_workers=4,
)

print("✅ Whisper small ready!\n")

SAMPLE_RATE = 16000

# Personal dictionary — corrects known errors
CORRECTIONS = {
    "whisper flow": "WisperFlow",
    "wisper flow":  "WisperFlow",
    "wisper":       "Wispr",
    "wisprflow":    "WisperFlow",
    "aditya kalfa": "Aditya Kalra",
    "aditya kalva": "Aditya Kalra",
    "aditiya":      "Aditya",
    "kalfa":        "Kalra",
    "kalva":        "Kalra",
}


class SpeechToText:

    def __init__(self):
        self.model = MODEL

    def transcribe(self, audio: np.ndarray) -> str:
        """
        Convert audio to text with maximum accuracy.
        Returns clean, corrected text.
        """
        if audio is None or len(audio) < 3200:
            return ""

        # Check energy — skip silent audio
        energy = float(np.sqrt(np.mean(audio ** 2)))
        if energy < 0.003:
            return ""

        start = time.perf_counter()

        segments, info = self.model.transcribe(
            audio,
            language=None,                    # Auto-detect language
            beam_size=5,                      # Higher = more accurate
            best_of=5,                        # Try 5 candidates
            temperature=0.0,                  # No randomness
            condition_on_previous_text=False, # No hallucination carry-over
            vad_filter=True,                  # Skip silent parts
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=400,
            ),
            initial_prompt=(
                "Aditya Kalra. WisperFlow. Voice to text app. "
                "Software development. Building applications."
            ),
            word_timestamps=False,
            no_speech_threshold=0.6,          # Reject low-confidence segments
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )

        # Collect all text
        text = " ".join(
            seg.text.strip()
            for seg in segments
            if seg.no_speech_prob < 0.6      # Skip low-confidence
        ).strip()

        elapsed = (time.perf_counter() - start) * 1000
        print(f"⚡ Transcribed in {elapsed:.0f}ms")

        if not text:
            return ""

        # Apply personal corrections
        text = self._apply_corrections(text)

        return text

    def _apply_corrections(self, text: str) -> str:
        """Apply personal dictionary corrections."""
        import re
        result = text
        for wrong, correct in CORRECTIONS.items():
            result = re.sub(
                rf'\b{re.escape(wrong)}\b',
                correct,
                result,
                flags=re.IGNORECASE
            )
        return result


# ── Test standalone ────────────────────────────────────────
if __name__ == "__main__":
    from audio_capture import AudioCapture

    stt     = SpeechToText()
    capture = AudioCapture()
    capture.start()

    print("=" * 50)
    print("HIGH ACCURACY VOICE TO TEXT TEST")
    print("Speak a full sentence — wait for result")
    print("Ctrl+C to stop")
    print("=" * 50 + "\n")

    try:
        while True:
            audio = capture.get_utterance(timeout=0.5)
            if audio is not None:
                print("🔄 Transcribing...")
                text = stt.transcribe(audio)
                if text:
                    print(f"\n✅ RESULT: {text}\n")
                    print("-" * 40)
                else:
                    print("(nothing detected)\n")
    except KeyboardInterrupt:
        capture.stop()
        print("\nStopped.")
