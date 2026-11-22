# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Named-entity PII: person and location spans in free text.

Two backends behind one call, :func:`find_entities`:

* ``"lexicon"`` (standard library only, always available): given-name, surname and place
  lexicons with honorific and context cues (``ner_lexicon``);
* ``"spacy"``: a spaCy NER model (``pip install "veloxs-nexus[ner]"`` and
  ``python -m spacy download en_core_web_sm``). spaCy is imported lazily; the model is
  loaded once per process (thread-safe) from the ``model`` argument, else the
  ``NEXUS_NER_MODEL`` environment variable, else ``en_core_web_sm``. Labels map
  ``PERSON`` -> ``person`` and ``GPE``/``LOC``/``FAC`` -> ``location``.

``backend="auto"`` (the default) uses spaCy when it is installed and the model loads, and
the lexicon detector otherwise. A missing spaCy or model never raises: it is logged once and
the lexicon detector answers instead.

Spans are :class:`~nexus.guardrails.pii.PiiSpan` objects on the original text, sorted and
non-overlapping (where two overlap, the earlier and then longer one is kept), so they can be
passed straight to :func:`~nexus.guardrails.pii.mask_spans`.
"""

from __future__ import annotations

import logging
import os
import threading
from bisect import bisect_left
from collections.abc import Callable, Iterable
from itertools import accumulate
from typing import Any

from .ner_lexicon import lexicon_entities
from .pii import NER_ENTITIES, PiiSpan

ENTITIES = NER_ENTITIES
BACKENDS = ("auto", "lexicon", "spacy")
DEFAULT_MODEL = "en_core_web_sm"
MODEL_ENV = "NEXUS_NER_MODEL"
SPACY_LABELS = {"PERSON": "person", "GPE": "location", "LOC": "location", "FAC": "location"}
_DISABLE = ("parser", "lemmatizer", "tagger", "attribute_ruler", "morphologizer")

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_models: dict[str, Any] = {}  # model name -> loaded pipeline, or None when it failed to load


def model_name(model: str | None = None) -> str:
    """The spaCy model to use: ``model``, else ``$NEXUS_NER_MODEL``, else ``en_core_web_sm``."""
    return model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL


def _load_spacy(name: str) -> Any:
    """The spaCy pipeline ``name`` (loaded once per process), or ``None`` if unavailable."""
    if name in _models:
        return _models[name]
    with _lock:
        if name not in _models:
            nlp = None
            try:
                import spacy  # optional: pip install "veloxs-nexus[ner]"

                nlp = spacy.load(name, disable=list(_DISABLE))
            except Exception as exc:  # ImportError, OSError (model missing), version errors
                _log.warning(
                    "spaCy NER model %r unavailable (%s); using the lexicon detector. "
                    'Install with: pip install "veloxs-nexus[ner]" && python -m spacy download %s',
                    name, exc, name,
                )
            _models[name] = nlp
    return _models[name]


def spacy_available(model: str | None = None) -> bool:
    """True when spaCy is installed and the model loads (loads it on first call)."""
    return _load_spacy(model_name(model)) is not None


def backend_in_use(backend: str = "auto", model: str | None = None) -> str:
    """``"spacy"`` or ``"lexicon"``: what :func:`find_entities` would run for ``backend``."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown NER backend {backend!r}; expected one of {BACKENDS}")
    if backend == "lexicon":
        return "lexicon"
    return "spacy" if spacy_available(model) else "lexicon"


def _windows(text: str, size: int) -> Iterable[tuple[int, str]]:
    """``text`` in pieces of at most ``size`` characters, cut at a line break or space."""
    start, n = 0, len(text)
    while start < n:
        end = min(n, start + size)
        if end < n:
            cut = max(text.rfind("\n", start, end), text.rfind(" ", start, end))
            if cut > start + size // 2:
                end = cut + 1
        yield start, text[start:end]
        start = end


def _spacy_spans(nlp: Any) -> Callable[[str], list[tuple[int, int, str]]]:
    def run(piece: str) -> list[tuple[int, int, str]]:
        return [
            (e.start_char, e.end_char, SPACY_LABELS[e.label_])
            for e in nlp(piece).ents
            if e.label_ in SPACY_LABELS
        ]

    return run


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    """A span without surrounding whitespace or a trailing possessive/punctuation."""
    while start < end and not text[start].isalnum():
        start += 1
    while end > start and not text[end - 1].isalnum():
        if text[end - 1] == "." and end - start >= 2 and text[end - 3 : end - 2] in (" ", ""):
            break  # the dot of a trailing initial ("John F.")
        end -= 1
    if text[start:end].endswith(("'s", "’s")):
        end -= 2
    return start, end


def non_overlapping(spans: Iterable[PiiSpan]) -> list[PiiSpan]:
    """Spans in text order with overlaps dropped (earlier start, then longer span, wins)."""
    kept: list[PiiSpan] = []
    for span in sorted(spans, key=lambda s: (s.start, -(s.end - s.start), s.entity)):
        if span.end > span.start and (not kept or span.start >= kept[-1].end):
            kept.append(span)
    return kept


def find_entities(
    text: str,
    wanted: Iterable[str] = ENTITIES,
    *,
    backend: str = "auto",
    model: str | None = None,
    max_chars: int = 100_000,
) -> list[PiiSpan]:
    """Person/location spans in ``text`` (entity names ``"person"``, ``"location"``).

    ``wanted`` is a subset of :data:`ENTITIES` (case-insensitive; other names are ignored).
    ``backend``: ``"auto"`` | ``"lexicon"`` | ``"spacy"`` (module doc); ``"spacy"`` without
    spaCy falls back to the lexicon detector like ``"auto"``. ``model`` names the spaCy model.
    ``max_chars`` bounds the piece of text handed to the detector at once: longer text is
    scanned in pieces cut at a line break or space, so every part of it is covered.
    """
    want = {w.lower() for w in wanted} & set(ENTITIES)
    if not text or not want:
        return []
    use = backend_in_use(backend, model)
    detect = _spacy_spans(_load_spacy(model_name(model))) if use == "spacy" else lexicon_entities
    found: list[PiiSpan] = []
    for offset, piece in _windows(text, max(1000, int(max_chars))):
        for start, end, entity in detect(piece):
            if entity in want:
                start, end = _trim(piece, start, end)
                found.append(PiiSpan(offset + start, offset + end, entity))
    return non_overlapping(found)


def add_entities(
    text: str,
    spans: Iterable[PiiSpan],
    wanted: Iterable[str] = ENTITIES,
    *,
    backend: str = "auto",
    model: str | None = None,
) -> list[PiiSpan]:
    """``spans`` (pattern detector spans, kept as they are) plus the person/location spans
    that do not overlap any of them, in text order."""
    kept = sorted(spans, key=lambda s: (s.start, s.end))
    ends = list(accumulate((s.end for s in kept), max))  # running max: robust to overlaps
    starts = [s.start for s in kept]
    extra = []
    for n in find_entities(text, wanted, backend=backend, model=model):
        i = bisect_left(starts, n.end)  # spans starting before n ends: kept[:i]
        if i == 0 or ends[i - 1] <= n.start:
            extra.append(n)
    return sorted(kept + extra, key=lambda s: (s.start, s.end))


def reset_models() -> None:
    """Forget loaded spaCy models (tests; a later call loads them again)."""
    with _lock:
        _models.clear()
