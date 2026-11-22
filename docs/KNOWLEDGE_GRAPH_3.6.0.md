# Knowledge-graph text extraction (3.6.0)

`nexus.graph.extract_graph(texts=...)` / `extract_mentions` still need no NER model and use the
standard library only. 3.6.0 changes how capitalised spans are cut, which title-case phrases are
rejected, finds known names written in lowercase, types more names and adds relations beyond one
sentence, including typed ones. Nothing in it knows a customer, a schema or a domain: every rule
is a word list or a text pattern, and the word lists are generic.

```python
from nexus.graph import TextGraphConfig, extract_graph

x = extract_graph(texts=[("c1", "Dr. Lena Hoffmann, CEO of Brightline Analytics, said Brightline "
                                "acquired Nordwind Labs. Nordwind Labs is headquartered in Hamburg.", "d1")])
{(r.type) for r in x.relations}   # {"co_mentioned", "works_for", "acquired", "located_in"}

# the new behaviour can be switched off
TextGraphConfig(lowercase=False, relation_window=0)
```

## What changed

### Span boundaries

| Text | 3.5.0 | 3.6.0 |
|---|---|---|
| `Cloudreach Solutions Pvt. Ltd., based in ...` | "Cloudreach Solutions Pvt" | "Cloudreach Solutions Pvt. Ltd" (abbreviated legal words join; `Inc.,` is not a sentence end) |
| `Orion Pharma Oy 5 days later` | "Orion Pharma Oy 5" | "Orion Pharma Oy" (nothing follows a legal suffix) |
| `HSBC's Global Banking team` | "HSBC's Global Banking" | "HSBC", "Global Banking" (a possessive ends a name, except before "Hospital", "College", legal suffixes, ...) |
| `Safaricom's M-Pesa` at a sentence start | missed | "Safaricom" kept (a possessive before a name is a name) |
| `SAP S/4HANA`, `Apache Log4j 2.14` | "SAP S", "Apache" (a place) | "SAP S/4HANA", "Apache Log4j" (`/` before a digit joins a token; letters-digit-letters tokens continue a name and are not record ids) |
| `iOS 17`, `eBay`, `ideaForge` | missed | found (camel-case brands); `userId`, `getUser()` are not |
| `The Ministry of Electronics and Information Technology` | "Ministry of Electronics", "Information Technology" | one name ("&lt;Ministry/Department/University&gt; of A and B" with field words such as science, health, technology; up to 8 words) |
| `Mumbai-Chennai link` | "Mumbai-Chennai" | "Mumbai", "Chennai" (hyphenated known places) |
| `CERT-In was notified.` | missed (sentence start) | found (inner capitals are never an ordinary word) |
| `Sheikh Mohammed bin Rashid`, `Ana de la Cruz` | split or untyped | one person each (particles bin, ibn, al, dos, della, "de la"; Sheikh is a title) |
| `Chief Technology Officer Alejandro Ruiz` | dropped as a role | "Alejandro Ruiz" |
| `Chennai MPLS` | "Chennai MPLS" | "Chennai" (a generic acronym after a place or person) |

### Vetoes (title-case words that are not names)

* Phrases made only of common words, adjectives and generic nouns: "Economy Class", "Large
  Conference Room", "Have a Great Weekend", "the Monthly Report". Kept when their own words type
  them ("Customer Advisory Board", "Information Security Policy") or a number follows ("Annual
  Report 2025").
* The label of a record id: "Purchase Order PO-55102", "Security Advisory SA-2024-017".
* A department after a title ("Head of Procurement"), a title with a department ("VP Engineering"),
  a kind with a roman numeral ("Type II", "Phase III").
* Nationalities and languages ("the Kenyan rollout", "in English"), contract parties ("the
  Licensor"), generic acronyms ("NPS", "SIM", "MPLS", "YoY", "KPI", "B2B").

### Lowercase mentions (`TextGraphConfig.lowercase`, default on)

Chat text often writes names in lowercase: "grafana shows 500s, rahul's on it". A lowercase token
is a mention (method `lower`, confidence 0.7) only when it is

* a known organisation or product of the lexicon that is not also an English word ("infosys",
  "datadog", "pagerduty", "redis"); one that is a word ("slack", "stripe", "react") needs a version
  or a cue word after it ("react 17", "stripe webhooks");
* a given name that is not a word or a place, next to a person cue: a speaker label ("priya:
  ..."), "hey / ping / cc / thanks / ask" before it, "said / will / can / from / 's" after it,
  or parentheses ("on-call (ana)"). Names that are also words ("will", "grace", "ana") need the
  strongest cues (speaker label, parentheses, "@").

### Typing

* A version after a name makes it a product ("Atlas Mobile 3.8.1", "Tally Prime 3.0"); "Server"
  ends product names ("SQL Server"); "applications", "add-on", "webhooks" after a name are product cues.
* A known firm with a place or another known firm ("Thales India" after "Thales", "Hindustan
  Unilever") is an organisation; a known surname after an unlisted given name is a person
  ("Bartholomew Achterberg"); given names match without accents ("José", "María").
* "Project Phoenix" makes a lone "Phoenix" in the same document a project; a weak cue before a
  list types the whole list ("join from Flutterwave, Paystack and Globant").
* Abbreviations whose letters come from inside words ("Hindustan Unilever (HUL)"), and their
  possessive ("HUL's IT lead").
* More known products (React, Angular, Django, Java, Python, Kotlin, TypeScript, Log4j, nginx, ...).

The given-name, place and surname lists are those of the guardrails layer's PII detector when
that layer is installed (about 10,000 given names and 7,000 places instead of 2,900 and 3,700,
plus 4,000 surnames). `graph_lexicon.layer_data` reads them as data: the module file holds string
constants and is executed on its own, without importing the guardrails package, so the
processing layer does not depend on a higher layer and works the same (with the smaller lists)
when installed alone.

### Relations

* `co_mentioned` now also links the names of a sentence with the next sentence when that one goes
  on about it: it is short (at most 8 tokens), opens with a label ("Contact: ..."), a pronoun or
  "The company / group / team ...", or repeats a word of a name before it
  (`TextGraphConfig.relation_window`, default 1; 0 restores 3.5.0). Such a pair counts once per
  chunk.
* The names of one key/value record of 2-10 lines ("Account: ...", "Contact: ...", "Location:
  ...") are co-mentioned.
* Typed, directed relations from the words between two neighbouring names of a sentence
  (`graph_relations.RELATION_PATTERNS`): `works_for` ("X, CEO of Y", "X works at Y", "X joined
  Y", "X from Y"), `acquired` ("Y acquired Z", "Z was acquired by Y"), `merged_with`, `part_of`
  ("X, a subsidiary of Y"), `located_in` ("X, based in P", "X (P)", "X's office in P"), `leads`,
  `reports_to`, `makes` ("Y's Z", "Y launched Z") and `uses` ("X moves to Z"). They come in
  addition to `co_mentioned`.

`EXTRACTOR_VERSION` is now `"kg2"`: stores that key extraction by it re-extract their chunks.

## Results

Precision over active entities, macro mention recall, typing accuracy (`nexus.graph_eval`) and,
for the blind development set, unordered relation pair recall.

Blind development set (64 passages, 267 entities, 100 relations; written without reading the
extractor). It was split before any change: even passages for tuning (the only errors looked
at), odd passages for validation (scores only).

| Half | Precision | Recall | Typing | Relation pairs |
|---|---|---|---|---|
| Tuning, 3.5.0 → 3.6.0 | 0.853 → 0.987 | 0.820 → 0.965 | 0.836 → 0.960 | 0.415 → 0.943 |
| Validation, 3.5.0 → 3.6.0 | 0.756 → 0.842 | 0.736 → 0.861 | 0.818 → 0.838 | 0.553 → 0.681 |
| Whole set, 3.5.0 → 3.6.0 | 0.806 → 0.916 | 0.782 → 0.916 | 0.830 → 0.905 | 0.480 → 0.820 |

Existing sets (none changed):

| Set | Precision | Recall | Typing |
|---|---|---|---|
| Hand-labelled (40 passages) | 1.00 → 1.00 | 1.00 → 1.00 | 0.983 → 0.983 |
| Held-out (20) | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 |
| Independent (15) | 1.00 → 1.00 | 1.00 → 1.00 | 0.967 → 0.967 |
| Blind (3.4.0) | 0.970 → 0.990 | 0.990 → 0.990 | 0.990 → 0.990 |
| Synthetic fixture with tables | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 |

Throughput (`extract_mentions` + resolution, same process, alternating runs, best of 15): about
12% slower than 3.5.0 on a mixed corpus of 0.44 MB (synthetic tickets, contracts and calls plus
the labelled passages 20 times; 1.55 → 1.38 MB/s) and the same ratio at 1.74 MB (1.61 → 1.42
MB/s: linear in the text length); 11% slower on the synthetic corpus of `test_throughput_smoke`.
The tokeniser (one `re.split`) and noun-phrase runs were rewritten to win back part of the cost;
their output is identical.
