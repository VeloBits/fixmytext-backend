# Backend Tool Endpoint Reference

> Complete reference for all text transformation endpoints exposed by the FixMyText backend.

## Summary

| Category | Count |
|----------|-------|
| LOCAL endpoints (pure text service) | 106 |
| AI endpoints (Groq-powered service) | 65 |
| **Total** | **171** |

All endpoints are `POST /api/v1/text/{slug}`. Tool definitions live in `app/core/tool_registry.py` (LOCAL) and `app/core/tools/ai.py` (AI). Custom request schemas are defined in `app/schemas/text.py`.

**Table columns:**

- **slug** — the URL path segment; full URL is `POST /api/v1/text/{slug}`
- **type** — `LOCAL` (runs in `text_service`, no external API) or `AI` (dispatched via `ai_service` to Groq)
- **schema** — request body schema; `TextRequest` means `{"text": "..."}` only
- **description** — brief description of the transformation

---

## Case Transformations (LOCAL)

| slug | type | schema | description |
|------|------|--------|-------------|
| `uppercase` | LOCAL | TextRequest | Convert all letters to UPPERCASE |
| `lowercase` | LOCAL | TextRequest | Convert all letters to lowercase |
| `inversecase` | LOCAL | TextRequest | Toggle the case of each letter |
| `sentencecase` | LOCAL | TextRequest | Capitalize the first letter of each sentence |
| `titlecase` | LOCAL | TextRequest | Title Case every word |
| `ap-title-case` | LOCAL | TextRequest | AP-style title case (lowercase articles & prepositions) |
| `upper-camel-case` | LOCAL | TextRequest | UpperCamelCase (PascalCase) |
| `lower-camel-case` | LOCAL | TextRequest | lowerCamelCase |
| `snake-case` | LOCAL | TextRequest | snake_case |
| `kebab-case` | LOCAL | TextRequest | kebab-case |
| `dot-case` | LOCAL | TextRequest | dot.case |
| `constant-case` | LOCAL | TextRequest | CONSTANT_CASE |
| `train-case` | LOCAL | TextRequest | Train-Case |
| `path-case` | LOCAL | TextRequest | path/case |
| `flat-case` | LOCAL | TextRequest | flatcase |
| `cobol-case` | LOCAL | TextRequest | COBOL-CASE |
| `capitalize-words` | LOCAL | TextRequest | Capitalize the first letter of every word |
| `alternating-case` | LOCAL | TextRequest | aLtErNaTiNg CaSe |
| `inverse-word-case` | LOCAL | TextRequest | Invert the case of each word (not each character) |
| `swap-word-case` | LOCAL | TextRequest | Swap case alternating by word |
| `wide-text` | LOCAL | TextRequest | W i d e  spaced text |
| `small-caps` | LOCAL | TextRequest | Convert to small caps Unicode characters |
| `upside-down` | LOCAL | TextRequest | Flip text upside down using Unicode |
| `strikethrough` | LOCAL | TextRequest | Apply strikethrough Unicode combining characters |

---

## Text Cleanup (LOCAL)

| slug | type | schema | description |
|------|------|--------|-------------|
| `remove-extra-spaces` | LOCAL | TextRequest | Collapse multiple spaces into one |
| `remove-all-spaces` | LOCAL | TextRequest | Remove every space character |
| `remove-line-breaks` | LOCAL | TextRequest | Join all lines into one paragraph |
| `strip-html` | LOCAL | TextRequest | Remove all HTML tags |
| `remove-accents` | LOCAL | TextRequest | Strip diacritical marks (à → a) |
| `toggle-smart-quotes` | LOCAL | TextRequest | Convert between curly and straight quotes |
| `strip-invisible` | LOCAL | TextRequest | Remove zero-width and other invisible characters |
| `strip-emoji` | LOCAL | TextRequest | Remove emoji characters |
| `normalize-whitespace` | LOCAL | TextRequest | Normalize all whitespace to standard spaces |
| `strip-non-ascii` | LOCAL | TextRequest | Remove non-ASCII characters |
| `fix-line-endings` | LOCAL | TextRequest | Normalize CRLF / CR to LF |
| `strip-markdown` | LOCAL | TextRequest | Remove Markdown formatting syntax |
| `trim-lines` | LOCAL | TextRequest | Trim leading and trailing whitespace from each line |
| `strip-empty-lines` | LOCAL | TextRequest | Remove blank lines |
| `strip-urls` | LOCAL | TextRequest | Remove all URLs from text |
| `strip-emails` | LOCAL | TextRequest | Remove all email addresses |
| `normalize-punctuation` | LOCAL | TextRequest | Normalize punctuation marks |
| `strip-numbers` | LOCAL | TextRequest | Remove all digit characters |

---

## Encoding / Decoding (LOCAL)

| slug | type | schema | description |
|------|------|--------|-------------|
| `base64-encode` | LOCAL | TextRequest | Encode text to Base64 |
| `base64-decode` | LOCAL | TextRequest | Decode Base64 to text |
| `url-encode` | LOCAL | TextRequest | URL-percent-encode the text |
| `url-decode` | LOCAL | TextRequest | Decode URL-percent-encoding |
| `hex-encode` | LOCAL | TextRequest | Encode text as hexadecimal |
| `hex-decode` | LOCAL | TextRequest | Decode hexadecimal to text |
| `morse-encode` | LOCAL | TextRequest | Encode text to Morse code |
| `morse-decode` | LOCAL | TextRequest | Decode Morse code to text |
| `binary-encode` | LOCAL | TextRequest | Encode text as binary (space-separated bytes) |
| `binary-decode` | LOCAL | TextRequest | Decode binary to text |
| `octal-encode` | LOCAL | TextRequest | Encode text as octal |
| `octal-decode` | LOCAL | TextRequest | Decode octal to text |
| `decimal-encode` | LOCAL | TextRequest | Encode text as decimal code points |
| `decimal-decode` | LOCAL | TextRequest | Decode decimal code points to text |
| `unicode-escape` | LOCAL | TextRequest | Escape text to Unicode escape sequences |
| `unicode-unescape` | LOCAL | TextRequest | Unescape Unicode escape sequences |
| `brainfuck-encode` | LOCAL | TextRequest | Encode text as Brainfuck |
| `brainfuck-decode` | LOCAL | TextRequest | Decode Brainfuck to text |
| `base32-encode` | LOCAL | TextRequest | Encode text to Base32 |
| `base32-decode` | LOCAL | TextRequest | Decode Base32 to text |
| `ascii85-encode` | LOCAL | TextRequest | Encode text as Ascii85 |
| `ascii85-decode` | LOCAL | TextRequest | Decode Ascii85 to text |

---

## Escape / Unescape (LOCAL)

| slug | type | schema | description |
|------|------|--------|-------------|
| `json-escape` | LOCAL | TextRequest | Escape text for use in a JSON string value |
| `json-unescape` | LOCAL | TextRequest | Unescape a JSON-escaped string |
| `html-escape` | LOCAL | TextRequest | Escape HTML special characters (`<`, `>`, `&`, `"`) |
| `html-unescape` | LOCAL | TextRequest | Unescape HTML entities back to characters |

---

## Ciphers (LOCAL)

| slug | type | schema | description |
|------|------|--------|-------------|
| `rot13` | LOCAL | TextRequest | ROT-13 rotation cipher |
| `atbash` | LOCAL | TextRequest | Atbash substitution cipher |
| `caesar-cipher` | LOCAL | CaesarRequest | Caesar cipher with configurable shift |
| `caesar-brute-force` | LOCAL | TextRequest | Try all 25 Caesar shifts and return results |
| `vigenere-encrypt` | LOCAL | KeyedCipherRequest | Vigenere encryption with key |
| `vigenere-decrypt` | LOCAL | KeyedCipherRequest | Vigenere decryption with key |
| `rail-fence-encrypt` | LOCAL | RailFenceRequest | Rail fence cipher encryption |
| `rail-fence-decrypt` | LOCAL | RailFenceRequest | Rail fence cipher decryption |
| `playfair-encrypt` | LOCAL | KeyedCipherRequest | Playfair cipher encryption with key |
| `substitution-cipher` | LOCAL | SubstitutionRequest | Substitution cipher with 26-char mapping alphabet |
| `columnar-transposition` | LOCAL | KeyedCipherRequest | Columnar transposition cipher with key |
| `nato-phonetic` | LOCAL | TextRequest | Convert letters to NATO phonetic alphabet words |
| `bacon-cipher` | LOCAL | TextRequest | Bacon's binary-letter cipher |

---

## Lines & Sorting (LOCAL)

| slug | type | schema | description |
|------|------|--------|-------------|
| `reverse` | LOCAL | TextRequest | Reverse the entire text character by character |
| `reverse-lines` | LOCAL | TextRequest | Reverse the order of lines |
| `sort-lines-asc` | LOCAL | TextRequest | Sort lines alphabetically A → Z |
| `sort-lines-desc` | LOCAL | TextRequest | Sort lines alphabetically Z → A |
| `remove-duplicate-lines` | LOCAL | TextRequest | Remove duplicate lines, preserve order |
| `number-lines` | LOCAL | TextRequest | Prefix each line with its line number |
| `shuffle-lines` | LOCAL | TextRequest | Randomly reorder lines |
| `sort-by-length` | LOCAL | TextRequest | Sort lines by character length (shortest first) |
| `sort-numeric` | LOCAL | TextRequest | Sort lines numerically |
| `line-frequency` | LOCAL | TextRequest | Count and rank line occurrences by frequency |
| `split-to-lines` | LOCAL | SplitJoinRequest | Split text into one-item-per-line using delimiter |
| `join-lines` | LOCAL | SplitJoinRequest | Join lines into a single line using delimiter |
| `pad-lines` | LOCAL | PadRequest | Pad each line to equal width with alignment |
| `wrap-lines` | LOCAL | WrapRequest | Prepend/append a prefix and suffix to each line |
| `filter-lines` | LOCAL | FilterRequest | Keep only lines matching a pattern or regex |
| `remove-lines` | LOCAL | FilterRequest | Remove lines matching a pattern or regex |
| `truncate-lines` | LOCAL | TruncateRequest | Truncate each line to a maximum character length |
| `extract-nth-lines` | LOCAL | NthLineRequest | Extract every Nth line starting from an offset |

---

## Developer Tools (LOCAL)

| slug | type | schema | description |
|------|------|--------|-------------|
| `format-json` | LOCAL | TextRequest | Prettify JSON with indentation |
| `json-to-yaml` | LOCAL | TextRequest | Convert JSON to YAML |
| `json-escape` | LOCAL | TextRequest | Escape a string value for use in JSON |
| `json-unescape` | LOCAL | TextRequest | Unescape a JSON-escaped string |
| `html-escape` | LOCAL | TextRequest | Escape HTML special characters |
| `html-unescape` | LOCAL | TextRequest | Unescape HTML entities |
| `csv-to-json` | LOCAL | TextRequest | Convert CSV to a JSON array of objects |
| `json-to-csv` | LOCAL | TextRequest | Convert a JSON array of objects to CSV |
| `xml-to-json` | LOCAL | TextRequest | Convert XML to JSON |
| `csv-to-table` | LOCAL | TextRequest | Render CSV as an ASCII table |
| `sql-insert-gen` | LOCAL | TextRequest | Generate SQL INSERT statements from CSV |

---

## AI Writing (AI)

All AI endpoints require a `GROQ_API_KEY`. They fall back to local heuristics when the key is absent or Groq is unreachable.

| slug | type | schema | description |
|------|------|--------|-------------|
| `summarize` | AI | TextRequest | Summarize text into key points |
| `fix-grammar` | AI | TextRequest | Fix grammar and spelling errors |
| `paraphrase` | AI | TextRequest | Rewrite text using different wording |
| `proofread` | AI | TextRequest | Detailed proofreading with corrections |
| `eli5` | AI | TextRequest | Explain text in simple, easy-to-understand language |
| `lengthen-text` | AI | TextRequest | Expand text with more detail |
| `rewrite-email` | AI | TextRequest | Rewrite email for clarity and professionalism |
| `change-tone` | AI | ToneRequest | Rewrite text in the specified tone |
| `change-format` | AI | FormatRequest | Reformat text into the specified structure |
| `academic-style` | AI | TextRequest | Rewrite in academic / scholarly style |
| `creative-style` | AI | TextRequest | Rewrite in creative / expressive style |
| `technical-style` | AI | TextRequest | Rewrite in precise technical style |
| `active-voice` | AI | TextRequest | Convert passive voice to active voice |
| `redundancy-remover` | AI | TextRequest | Remove redundant words and phrases |
| `sentence-splitter` | AI | TextRequest | Split long sentences into shorter ones |
| `conciseness` | AI | TextRequest | Make text more concise |
| `resume-bullets` | AI | TextRequest | Transform experience into resume bullet points |
| `meeting-notes` | AI | TextRequest | Summarize text as structured meeting notes |
| `cover-letter` | AI | TextRequest | Draft a cover letter from provided details |
| `outline-to-draft` | AI | TextRequest | Expand an outline into a full draft |
| `continue-writing` | AI | TextRequest | Continue writing from the given text |
| `rewrite-unique` | AI | TextRequest | Rewrite text to be original and unique |
| `tone-analyzer` | AI | TextRequest | Identify the tone and voice of the text |
| `refactor-prompt` | AI | TextRequest | Improve and restructure an instruction prompt |

---

## AI Content (AI)

| slug | type | schema | description |
|------|------|--------|-------------|
| `generate-hashtags` | AI | TextRequest | Generate relevant hashtags for the content |
| `generate-seo-titles` | AI | TextRequest | Generate SEO-optimized title options |
| `generate-meta-descriptions` | AI | TextRequest | Generate meta description options |
| `generate-blog-outline` | AI | TextRequest | Create a structured blog post outline |
| `shorten-for-tweet` | AI | TextRequest | Condense text to tweet-length |
| `extract-keywords` | AI | TextRequest | Extract key terms and phrases |
| `generate-title` | AI | TextRequest | Generate a compelling title for the content |
| `analyze-sentiment` | AI | TextRequest | Analyze sentiment (positive / negative / neutral) |
| `linkedin-post` | AI | TextRequest | Rewrite as a LinkedIn post |
| `twitter-thread` | AI | TextRequest | Format content as a Twitter thread |
| `instagram-caption` | AI | TextRequest | Write an Instagram caption |
| `youtube-description` | AI | TextRequest | Write a YouTube video description |
| `social-bio` | AI | TextRequest | Write a social media bio |
| `product-description` | AI | TextRequest | Write a product description |
| `cta-generator` | AI | TextRequest | Generate call-to-action variations |
| `ad-copy` | AI | TextRequest | Write advertising copy |
| `landing-headline` | AI | TextRequest | Generate landing page headline options |
| `email-subject` | AI | TextRequest | Generate email subject line options |
| `content-ideas` | AI | TextRequest | Brainstorm content ideas |
| `hook-generator` | AI | TextRequest | Generate attention-grabbing opening hooks |
| `angle-generator` | AI | TextRequest | Generate unique content angles |
| `faq-schema` | AI | TextRequest | Generate FAQ schema markup |

---

## AI Language (AI)

| slug | type | schema | description |
|------|------|--------|-------------|
| `translate` | AI | TranslateRequest | Translate text into the specified target language |
| `transliterate` | AI | TranslateRequest | Transliterate text into the target language script |
| `emojify` | AI | TextRequest | Replace words with relevant emoji |
| `detect-language` | AI | TextRequest | Detect the language of the input text |
| `pos-tagger` | AI | TextRequest | Tag each word with its part of speech |
| `sentence-type` | AI | TextRequest | Classify sentences by type (declarative, question, etc.) |
| `grammar-explain` | AI | TextRequest | Explain the grammar rules in the text |
| `synonym-finder` | AI | TextRequest | Find synonyms for key words |
| `antonym-finder` | AI | TextRequest | Find antonyms for key words |
| `define-words` | AI | TextRequest | Define words found in the text |
| `word-power` | AI | TextRequest | Suggest stronger, more impactful word choices |
| `vocab-complexity` | AI | TextRequest | Score and explain vocabulary complexity |
| `jargon-simplifier` | AI | TextRequest | Replace jargon with plain-language equivalents |
| `formality-detector` | AI | TextRequest | Measure the formality level of the text |
| `cliche-detector` | AI | TextRequest | Identify and flag clichés |

---

## AI Generators (AI)

| slug | type | schema | description |
|------|------|--------|-------------|
| `regex-generator` | AI | TextRequest | Generate a regex pattern from a plain-English description |
| `writing-prompt` | AI | TextRequest | Generate creative writing prompts |
| `team-name-generator` | AI | TextRequest | Generate team or project name ideas |
| `mock-api-response` | AI | TextRequest | Generate a mock JSON API response |
