"""I link relativi della documentazione devono portare a file e sezioni che esistono.

La documentazione e' la mappa con cui un agente entra nel repository (#23): un link rotto
dopo uno spostamento di file o il cambio di un titolo e' il modo piu' silenzioso in cui
quella mappa smette di dire il vero. Si controllano solo i link Markdown relativi (file e
ancore), non gli URL esterni e non i percorsi citati fra backtick.
"""
import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [ROOT / "AGENTS.md", ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]

_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE = re.compile(r"`[^`]*`")
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")


def _prose_lines(text):
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield number, line


def _slug(heading):
    """Approssima gli id che GitHub assegna ai titoli."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = text.replace("`", "").strip().lower()
    kept = []
    for char in text:
        if char in (" ", "-"):
            kept.append("-" if char == " " else char)
        elif char == "_" or unicodedata.category(char)[0] in ("L", "N"):
            kept.append(char)
    return "".join(kept)


def _anchors(path):
    seen = {}
    anchors = set()
    for _, line in _prose_lines(path.read_text(encoding="utf-8")):
        match = _HEADING.match(line)
        if not match:
            continue
        slug = _slug(match.group(2))
        count = seen.get(slug, 0)
        anchors.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return anchors


def _relative_links(path):
    for number, line in _prose_lines(path.read_text(encoding="utf-8")):
        for target in _LINK.findall(_INLINE_CODE.sub("", line)):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            yield number, target


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_resolve(document):
    broken = []
    for number, target in _relative_links(document):
        file_part, _, anchor = target.partition("#")
        resolved = (document.parent / file_part).resolve() if file_part else document
        if not resolved.exists():
            broken.append(f"{target} (line {number}): missing path")
            continue
        if anchor and resolved.suffix == ".md" and anchor not in _anchors(resolved):
            broken.append(f"{target} (line {number}): missing anchor")
    assert not broken, "\n".join(broken)


def test_slug_matches_github_conventions():
    assert _slug("7. Deployment topology (summary)") == "7-deployment-topology-summary"
    assert _slug('Eventi "coppie padre/figlio" (manuali)') == "eventi-coppie-padrefiglio-manuali"
    assert _slug("Never trust stale state") == "never-trust-stale-state"
