"""A simple filter for obscene words in anything one user shows to another (App Store guideline 1.2)."""
import re

# Roots of Russian obscene words and a few English ones. Matched at the start of a word,
# so ordinary words that merely contain these letters in the middle are not affected.
_ROOTS = [
    r"(?:на|по|о|а|от|за|ни|до|под)?х[уy][йиеёяю]", r"п[иi]зд", r"[её]б[ауеилнт]", r"заеб", r"наеб", r"отъеб", r"уеб", r"доеб", r"въеб", r"разъеб",
    r"бляд", r"бля\b", r"бл[яе]ть", r"муд[ао]к", r"пид[оа]р", r"гандон", r"залуп", r"шлюх", r"манд[ау](?![а-яё])", r"мандавош",
    r"fuck", r"cunt", r"bitch", r"whore", r"nigg",
]
_PATTERN = re.compile(r"(?<![а-яёa-z])(?:" + "|".join(_ROOTS) + ")", re.IGNORECASE)
_SEPARATORS = re.compile(r"[\s._\-*,!?]+")


def _join_spelled_out(text: str) -> str:
    """«х у й» or «х.у.й» → «хуй»: runs of single letters are glued back into a word."""
    words, out, run = _SEPARATORS.split(text), [], ""
    for word in words:
        if len(word) == 1:
            run += word
            continue
        if run:
            out.append(run)
            run = ""
        out.append(word)
    if run:
        out.append(run)
    return " ".join(out)


def is_clean(text: str) -> bool:
    if not text:
        return True
    lowered = text.lower().replace("ё", "е").replace("0", "о").replace("@", "а")
    return not (_PATTERN.search(lowered) or _PATTERN.search(_join_spelled_out(lowered)))
