import re


_TYPE_TAG_RE = re.compile(r"\[\[type:([a-zA-Z0-9_\-]+)\]\]")


def clean_for_tts(text: str) -> str:
    """Sanitize AI text for TTS to avoid awkward pronunciation.

    - Remove provider/flow tags like [[type:...]]
    - Convert literal "\n" to real newlines, then newlines to sentence breaks
    - Strip basic Markdown: **bold**, *italics*, __, _, `code`, [label](url)
    - Collapse spaces and fix spacing around punctuation
    - Ensure ending punctuation for better prosody
    """
    if not text:
        return text

    s = str(text)

    # 1) Remove [[type:...]] tag if any
    s = _TYPE_TAG_RE.sub("", s)

    # 2) Convert escaped newlines to real newlines, then reduce to sentence breaks
    s = s.replace("\\n", "\n")
    # Normalize CRLF
    s = s.replace("\r\n", "\n")

    # 3) Strip Markdown links [label](url) -> label
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)

    # 4) Remove emphasis markers and backticks
    s = s.replace("**", "").replace("__", "")
    s = s.replace("`", "")
    # Single * or _ often used for italics; remove when around word boundaries
    s = re.sub(r"(?<!\w)[*_](?!\w)|(?<=\w)[*_](?!\w)|(?<!\w)[*_](?=\w)", "", s)

    # 5) Remove leading markdown headings (#)
    s = re.sub(r"^\s*#+\s*", "", s, flags=re.MULTILINE)

    # 6) Replace newlines with sentence breaks
    # If a line ends without terminal punctuation, add a period to improve TTS cadence
    lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
    processed = []
    for ln in lines:
        if not re.search(r"[.!?…]$", ln):
            processed.append(ln + ".")
        else:
            processed.append(ln)
    s = " ".join(processed)

    # 7) Fix spacing around punctuation
    s = re.sub(r"\s+([,.!?…])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)

    # 8) Collapse extra spaces
    s = re.sub(r"\s{2,}", " ", s).strip()

    return s
