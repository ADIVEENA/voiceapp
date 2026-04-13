# ============================================================
# FILE: ml/nlp.py
# PURPOSE: Clean up raw transcription — remove fillers,
#          fix punctuation, apply dictionary, expand snippets
# HOW TO RUN: python nlp.py  (runs built-in tests)
# ============================================================

import re
import json
import os
import spacy

# Load spaCy English model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Downloading spaCy model...")
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")


# ── Filler words to always remove ─────────────────────────
FILLER_WORDS = {
    "um", "uh", "umm", "uhh", "hmm", "hm",
    "like", "you know", "you know what i mean",
    "basically", "literally", "actually",
    "kind of", "sort of", "i mean",
}

# ── Spoken punctuation → symbol ───────────────────────────
SPOKEN_MARKS = {
    r"\bcomma\b":           ",",
    r"\bperiod\b":          ".",
    r"\bfull stop\b":       ".",
    r"\bquestion mark\b":   "?",
    r"\bexclamation mark\b":"!",
    r"\bexclamation point\b":"!",
    r"\bnew line\b":        "\n",
    r"\bnew paragraph\b":   "\n\n",
    r"\bcolon\b":           ":",
    r"\bsemicolon\b":       ";",
    r"\bdash\b":            " — ",
    r"\bopen bracket\b":    "(",
    r"\bclose bracket\b":   ")",
    r"\bopen quotes\b":     '"',
    r"\bclose quotes\b":    '"',
    r"\bhyphen\b":          "-",
}

# ── Tech vocab — always capitalize correctly ───────────────
TECH_VOCAB = {
    "github": "GitHub",
    "chatgpt": "ChatGPT",
    "openai": "OpenAI",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "python": "Python",
    "supabase": "Supabase",
    "vercel": "Vercel",
    "cloudflare": "Cloudflare",
    "whatsapp": "WhatsApp",
    "linkedin": "LinkedIn",
    "youtube": "YouTube",
    "instagram": "Instagram",
    "iphone": "iPhone",
    "macos": "macOS",
    "windows": "Windows",
    "android": "Android",
    "api": "API",
    "sdk": "SDK",
    "ui": "UI",
    "ux": "UX",
    "saas": "SaaS",
    "ai": "AI",
    "ml": "ML",
    "aws": "AWS",
    "gpt": "GPT",
    "url": "URL",
    "html": "HTML",
    "css": "CSS",
    "sql": "SQL",
    "vscode": "VS Code",
    "vs code": "VS Code",
}

# ── Backtrack triggers ─────────────────────────────────────
BACKTRACK_TRIGGERS = [
    "actually", "i mean", "no wait",
    "scratch that", "correction", "rather",
    "instead", "no no",
]


class TextCleaner:
    """
    Cleans raw Whisper transcription into polished text.
    Works in milliseconds — no API calls.
    """

    def __init__(self, dictionary_path="dictionary.json", snippets_path="snippets.json"):
        self.dictionary = self._load_json(dictionary_path)
        self.snippets   = self._load_json(snippets_path)

    def _load_json(self, path):
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return {}

    def clean(self, raw_text: str) -> str:
        """
        Full cleaning pipeline.
        Input:  "um so basically I want to uh send a email to john period"
        Output: "I want to send an email to John."
        """
        if not raw_text or not raw_text.strip():
            return ""

        text = raw_text.strip()

        # 1. Handle backtrack corrections first
        text = self._handle_backtrack(text)

        # 2. Apply personal dictionary
        text = self._apply_dictionary(text)

        # 3. Remove filler words
        text = self._remove_fillers(text)

        # 4. Convert spoken punctuation
        text = self._apply_spoken_marks(text)

        # 5. Fix tech vocabulary capitalization
        text = self._apply_tech_vocab(text)

        # 6. Detect and format lists
        text = self._format_lists(text)

        # 7. Apply snippets (voice shortcuts)
        text = self._apply_snippets(text)

        # 8. Final cleanup
        text = self._final_cleanup(text)

        return text

    def _handle_backtrack(self, text: str) -> str:
        """
        "Meet at 2 actually 3pm" → "Meet at 3pm"
        """
        lower = text.lower()
        for trigger in BACKTRACK_TRIGGERS:
            if trigger in lower:
                idx = lower.find(trigger)
                before = text[:idx].strip().rstrip(".,!?")
                after  = text[idx + len(trigger):].strip()

                if after:
                    # Use spaCy to find the last entity/number in 'before'
                    doc = nlp(before)
                    replaced = False
                    for ent in reversed(list(doc.ents)):
                        if ent.label_ in ("TIME", "DATE", "CARDINAL", "PERSON", "GPE"):
                            text = before[:ent.start_char] + after
                            replaced = True
                            break
                    if not replaced:
                        # Fallback: replace last word
                        words = before.split()
                        if words:
                            words[-1] = after
                            text = " ".join(words)
                break
        return text

    def _remove_fillers(self, text: str) -> str:
        """Remove filler words and sounds."""
        for filler in sorted(FILLER_WORDS, key=len, reverse=True):
            # Remove as standalone word (not part of another word)
            pattern = r'\b' + re.escape(filler) + r'\b'
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # Clean up extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _apply_spoken_marks(self, text: str) -> str:
        """Replace spoken punctuation words with symbols."""
        for pattern, symbol in SPOKEN_MARKS.items():
            text = re.sub(pattern, symbol, text, flags=re.IGNORECASE)
        return text

    def _apply_tech_vocab(self, text: str) -> str:
        """Fix capitalization of tech terms."""
        for wrong, correct in TECH_VOCAB.items():
            text = re.sub(
                r'\b' + re.escape(wrong) + r'\b',
                correct,
                text,
                flags=re.IGNORECASE
            )
        return text

    def _apply_dictionary(self, text: str) -> str:
        """Apply user's personal dictionary."""
        for wrong, correct in self.dictionary.items():
            text = re.sub(
                r'\b' + re.escape(wrong) + r'\b',
                correct,
                text,
                flags=re.IGNORECASE
            )
        return text

    def _apply_snippets(self, text: str) -> str:
        """Expand voice shortcuts into full text."""
        lower = text.lower().strip()
        for trigger, expansion in self.snippets.items():
            if trigger.lower() in lower:
                text = re.sub(
                    re.escape(trigger),
                    expansion,
                    text,
                    flags=re.IGNORECASE
                )
        return text

    def _format_lists(self, text: str) -> str:
        """
        "1. Apples 2. Bananas 3. Oranges" → formatted list
        """
        pattern = r'(\d+)\.\s+(\w)'
        matches = list(re.finditer(pattern, text))
        if len(matches) >= 2:
            text = re.sub(pattern, r'\n\1. \2', text).strip()
        return text

    def _final_cleanup(self, text: str) -> str:
        """Final polish: capitalize, fix 'i', clean spaces."""
        # Fix spaces before punctuation
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)

        # Clean multiple spaces
        text = re.sub(r'\s+', ' ', text).strip()

        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]

        # Fix standalone "i" → "I"
        text = re.sub(r'\bi\b', 'I', text)
        text = re.sub(r"\bi'm\b", "I'm", text, flags=re.IGNORECASE)
        text = re.sub(r"\bi've\b", "I've", text, flags=re.IGNORECASE)
        text = re.sub(r"\bi'll\b", "I'll", text, flags=re.IGNORECASE)
        text = re.sub(r"\bi'd\b", "I'd", text, flags=re.IGNORECASE)

        # Add period if no ending punctuation
        if text and text[-1] not in ".!?,\n:;":
            text += "."

        return text

    def add_to_dictionary(self, wrong: str, correct: str):
        """Learn a new word correction."""
        self.dictionary[wrong.lower()] = correct
        with open("dictionary.json", "w") as f:
            json.dump(self.dictionary, f, indent=2)
        print(f"📚 Learned: '{wrong}' → '{correct}'")

    def add_snippet(self, trigger: str, expansion: str):
        """Add a voice shortcut."""
        self.snippets[trigger.lower()] = expansion
        with open("snippets.json", "w") as f:
            json.dump(self.snippets, f, indent=2)
        print(f"⚡ Snippet added: '{trigger}' → '{expansion[:30]}...'")


# ── Test the cleaner ───────────────────────────────────────
if __name__ == "__main__":
    cleaner = TextCleaner()

    test_cases = [
        "um so basically i want to uh send an email to john period",
        "let's meet at 2pm actually 3pm on friday",
        "going to the store for 1. apples 2. bananas 3. oranges",
        "i'm working on a python project using github and supabase",
        "can you like you know help me with this comma please",
        "i use vs code and chatgpt every day for my saas project",
    ]

    print("=" * 55)
    print("NLP CLEANER TEST")
    print("=" * 55)

    for raw in test_cases:
        cleaned = cleaner.clean(raw)
        print(f"\nRAW:     {raw}")
        print(f"CLEANED: {cleaned}")
        print("-" * 55)
