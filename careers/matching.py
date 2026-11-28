"""Text matching shared by the loader and the posting -> program linker. No database access here."""
import re
import unicodedata


def norm(text):
    """'İSTANBUL', 'Istanbul' and 'istanbul' all give 'istanbul'; 'Boğaziçi' gives 'bogazici'."""
    text = str(text).replace("ı", "i").replace("İ", "i")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(text.casefold().split())


def strings(value):
    """A stored name list; admin input may be any JSON, and a single string counts as one name."""
    if isinstance(value, str):
        return [value]
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _plain(text):
    """norm() plus: '&' reads as 'and', hyphens as spaces, abbreviation dots dropped (B.Sc. -> bsc)."""
    text = norm(text).replace("&", " and ")
    text = re.sub(r"[-–—]", " ", text)
    text = re.sub(r"\b(b|m)\.\s?(sc|s|a|eng)\.", r"\1\2", text)
    text = re.sub(r"\bph\.\s?d\.", "phd", text)
    text = re.sub(r"\b(bsc|msc|phd|bs|ms|ba|ma|beng|meng|e\.g|i\.e|etc|vb|vs|incl)\.", lambda m: m[1].replace(".", ""), text)
    return " ".join(text.split())


# A sentence or line asks for a degree when it has one of these.
MARKER = re.compile(r"(?<!\d )\bdegree|\bdiploma|\b(bs|bsc|beng|ba|ms|msc|meng|ma|mba|phd)\b|\bbachelor|\bmasters?\b|\bmaster's|\bundergraduate"
                    r"|\buniversit|\bstudent|\bgraduat|\brelated (field|discipline|area)|\blisans|\bmezun|\bogrenci|\bbolumlerinden")
# Only these levels on offer -> the program types (bachelor's) don't apply.
VOCATIONAL = re.compile(r"\bmeslek lisesi|\bmeslek yuksek|\bmyo\b|\bon ?lisans|\bassociate degree|\bassociate's")
BACHELOR = re.compile(r"\bbachelor|\b(bs|bsc|beng)\b|\bundergraduate|\buniversit|(?<!on )(?<!yuksek )\blisans")
LINE_END = re.compile(r"[\r\n•·●▪]")  # split before _plain(), which joins lines
SENTENCE_END = re.compile(r"[.!?;]+(?:\s|$)")
LIST_SEP = r"(?:,|/|\bor\b|\band\b|\bveya\b|\bve\b|\bya da\b)"
LIST_ITEM = r"(?!(?:or|and|veya|ve|ya)\b)[\w']+"


class DegreeMatcher:
    """Which programs does a job description ask for? Built from each program's names, so it works for any data.

    A name counts only in a sentence or line with a degree marker. A one-word name before a shared ending also
    counts in a list: "Mechanical, Electrical or Materials Engineering" names Mechanical and Electrical Engineering.
    """

    def __init__(self, programs):
        """programs: (key, names) pairs; a name may belong to several keys."""
        self.patterns = []
        for key, names in programs:
            for name in {_plain(n) for n in names if n and n.strip()}:
                words = name.split()
                # A one-word name must be a whole word ("Law" is not "lawn"). Longer names may take a suffix,
                # as Turkish writes them (Mühendisliğinden).
                pattern = r"\b" + re.escape(name) + (r"\b" if len(words) == 1 else "")
                if len(words) == 2:
                    stem, head = words
                    # Atomic group, and items that are not separator words: no catastrophic backtracking.
                    pattern += rf"|\b{re.escape(stem)}(?>(?:(?:\s*{LIST_SEP})+\s*{LIST_ITEM}){{1,6}})\s+{re.escape(head)}"
                self.patterns.append((key, re.compile(pattern)))

    def match(self, description):
        found = set()
        segments = (s for line in LINE_END.split(description or "") for s in SENTENCE_END.split(_plain(line)))
        for segment in segments:
            if not MARKER.search(segment) or (VOCATIONAL.search(segment) and not BACHELOR.search(segment)):
                continue
            found.update(key for key, pattern in self.patterns if pattern.search(segment))
        return found
