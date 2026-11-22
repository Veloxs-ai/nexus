# Person and location PII (3.5.0)

Regular expressions find e-mail addresses, phone numbers and card numbers, but not names or
places. Nexus 3.5.0 adds named-entity PII detection for **person** and **location** to
`nexus.guardrails`, with two backends behind one call.

| Backend | Install | What it uses |
|---|---|---|
| `lexicon` | built in (standard library only) | given-name, surname and place lexicons shared with the knowledge-graph entity typing, honorifics (Mr, Ms, Dr, Prof, Shri, Smt, ...), role labels ("Customer", "Patient"), context cues ("my name is", "reported by", "Dear"), person verbs ("said", "visited"), organisation and product vetoes |
| `spacy` | `pip install "veloxs-nexus[ner]"` then `python -m spacy download en_core_web_sm` | a spaCy NER model: `PERSON` becomes `person`; `GPE`, `LOC`, `FAC` become `location` |

`backend="auto"` (the default) uses spaCy when it is installed and the model loads, and the
lexicon detector otherwise. A missing spaCy or model never raises: it is logged once and the
lexicon detector answers.

## Use

```python
from nexus.guardrails.ner import find_entities
from nexus.guardrails.pii import detect_pii_spans, mask_pii, mask_spans
from nexus.guardrails.config import PiiConfig

text = "Dear Ms. Fernandes, Priya Nair from our Pune office will call."

find_entities(text, {"person", "location"})                       # auto backend
find_entities(text, {"person"}, backend="lexicon")                 # never loads a model
find_entities(text, {"person"}, backend="spacy", model="en_core_web_md")

# Together with the pattern detectors (spans never overlap; patterns win):
spans = detect_pii_spans(text, entities=["email", "address", "person", "location"])
masked = mask_spans(text, spans)        # "[PERSON]", "[LOCATION]", "[EMAIL]", ...

# Or through the masking config:
mask_pii(text, PiiConfig(detectors=["email", "phone", "person", "location"]))
```

`find_entities(text, wanted, *, backend="auto", model=None, max_chars=100_000)` returns
`PiiSpan(start, end, entity)` objects on the original text, sorted and non-overlapping
(where two overlap, the earlier and then longer one is kept). Entity names in `wanted` are
case-insensitive. Text longer than `max_chars` is scanned in pieces cut at a line break or
space, so all of it is covered.

`detect_pii_spans(..., ner_backend="auto", ner_model=None)` passes the backend and model
through.

### spaCy model

The model is loaded once per process (thread-safe) and cached per name: the `model`
argument, else the `NEXUS_NER_MODEL` environment variable, else `en_core_web_sm` (about
13 MB). `en_core_web_md` / `_lg` are larger. Helpers: `spacy_available(model=None)`,
`backend_in_use(backend="auto", model=None)`, `reset_models()`.

## Accuracy

Measured on labelled sentences in `orchestration-guardrails/tests/ner_samples*.py`: e-mails,
tickets, chat, records and notes with Indian and Western names and places, plus negatives
(products, companies, headings, brand names that contain person or place words). Overlap
match: a predicted span counts when it overlaps a gold span of the same type.

| Set | Backend | Person P / R | Location P / R | ms per sentence |
|---|---|---|---|---|
| tuning set (220 sentences) | lexicon | 1.00 / 1.00 | 1.00 / 1.00 | 0.09 |
| tuning set | spaCy `en_core_web_sm` 3.8 | 0.89 / 0.75 | 0.90 / 0.68 | 3.7 |
| held-out (48 sentences) | lexicon | 0.82 / 0.85 | 0.95 / 0.95 | 0.09 |
| held-out | spaCy `en_core_web_sm` 3.8 | 0.68 / 0.70 | 0.77 / 0.48 | 3.6 |

`auto` equals the spaCy row where spaCy is installed and the lexicon row where it is not.
The tuning set was used to develop the lexicon rules, so its lexicon scores are optimistic;
the held-out set (rarer names, small towns, lowercase chat, brand names such as "Lincoln
Navigator" or "Georgia Pacific") is the realistic figure. Known gaps of the lexicon detector:
names written in lowercase ("hey priya"), single unknown surnames without a cue, and
brand names built from a given name ("Raymond suits").

## Standard library only

`ner.py`, `ner_lexicon.py` and `ner_data.py` import only the standard library and Nexus
modules at top level; spaCy is imported inside the loader. Without the processing layer
(the guardrails layer installed on its own) the lexicon detector keeps its honorific, cue
and surname rules.
