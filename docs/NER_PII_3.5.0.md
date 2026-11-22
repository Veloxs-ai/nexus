# Person and location PII (3.5.0)

Regular expressions find e-mail addresses, phone numbers and card numbers, but not names or
places. Nexus 3.5.0 adds named-entity PII detection for **person** and **location** to
`nexus.guardrails`, with two backends behind one call.

| Backend | Install | What it uses |
|---|---|---|
| `lexicon` | built in (standard library only) | about 10,000 given names, 4,000 surnames and 7,000 places across cultures (the knowledge-graph lexicons plus PII extensions), honorifics (Mr, Ms, Dr, Prof, Shri, Smt, ...), role labels ("Customer", "Patient"), context cues ("my name is", "reported by", "Dear", "ask"), person verbs ("said", "visited"), place heads ("Airport", "Nagar", "Beach"), lowercase chat, key/value fields, signature blocks, organisation, brand and nationality vetoes |
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
| tuning set (247 sentences) | lexicon | 1.00 / 1.00 | 1.00 / 1.00 | 0.08 |
| tuning set | spaCy `en_core_web_sm` 3.8 | 0.88 / 0.71 | 0.88 / 0.65 | 2.2 |
| held-out (48 sentences) | lexicon | 0.88 / 1.00 | 1.00 / 1.00 | 0.08 |
| held-out | spaCy `en_core_web_sm` 3.8 | 0.68 / 0.68 | 0.77 / 0.48 | 2.1 |

`auto` equals the spaCy row where spaCy is installed and the lexicon row where it is not.
The tuning set was used to develop the lexicon rules, so its lexicon scores are optimistic;
the held-out set (rarer names, small towns, lowercase chat, brand names such as "Lincoln
Navigator" or "Georgia Pacific") is the realistic figure. Known gaps of the lexicon detector:
brand names built from a given name ("Raymond suits", "Lincoln Navigator"), single unknown
surnames without a cue, names that are also ordinary words at the start of a sentence ("Rose
from accounts"), and rare spellings that are in no lexicon and have no cue.

### How the lexicon detector decides

- **Lexicons** (`ner_words`): the knowledge-graph given names and places plus PII extensions
  (`ner_names_south_asia`, `ner_names_world`, `ner_places`: Indian and world given names,
  Indian towns, metro neighbourhoods, landmarks, airports, world cities) and surnames
  (`ner_surnames`). Names that are also English words ("Grace", "Jade") count only inside a
  multi-word name or right after a cue ("Ask Mark"); places that are also words ("Reading")
  need a place cue. Built lazily, once per process.
- **Capitalised names**: given name + surname, unknown word + known surname ("Jagdeep Singh
  Bains"), surname first ("Park Min-jun"), a lone given name mid-sentence or before a person
  verb ("Riya said"), a lone surname before a verb or after "ask"/"tell" ("Sharma will call").
- **Places**: lexicon places, compass regions ("South India"), names ending in a place head
  ("Kempegowda International Airport", "Lajpat Nagar", "Marina Beach"), a place before
  "Office"/"Branch" ("Dublin Office"), unknown words with a place ending ("-nagar", "-abad",
  "-puram"). Streets are not locations ("Baker Street", "MG Road").
- **Lowercase chat** ("hey priya can u ask ramesh to call back from pune"): a lowercase given
  name that is not also an English or chat word, next to a cue ("hey", "ask", "tell", "@",
  "said", "will"); a lowercase place after "from"/"in"/"to"/"at" or before "office". Without a
  cue, nothing in lowercase is masked ("may", "will", "grace", "mark", "bill" never fire).
- **Fields**: `name: Ravi`, `customer_name=ravi kumar`, `"first_name": "Sakura"`, `city:
  Kyoto`, `origin: Enugu`; placeholder values ("Unassigned", "N/A") and `username` are skipped.
- **Signatures**: the name line after "Regards," / "Thanks," / "Cheers," and a place starting
  one of the next two lines.
- **Vetoes**: organisation tails ("Reddy's Laboratories", "Mumbai Indians", "Tata Motors"),
  person-named brands ("Calvin Klein", "Marks & Spencer"), "&" inside a person, short all-caps
  words ("EMI"), nationalities and languages ("in Spanish"), festivals ("Ganesh Chaturthi"),
  group words ("Hi Everyone").

Every rule scans the text once with bounded patterns, so time grows linearly with the text.

## Standard library only

`ner.py`, `ner_lexicon.py`, `ner_rules.py`, `ner_words.py` and the `ner_*` data modules
import only the standard library and Nexus modules at top level; spaCy is imported inside the
loader. Without the processing layer (the guardrails layer installed on its own) the graph
pass is skipped and the rules run on the PII lexicon extensions alone.
