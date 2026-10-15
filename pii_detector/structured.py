"""Value-aware JSON analysis with offsets into the original serialized document.

The JSON decoder validates the document; the scanner only records its scalar
source ranges. Each value is analyzed independently, so keys and adjacent fields
cannot become part of a detection. NLP runs as one batch, not one model call per
value. No JSON reserialization is used for output offsets.
"""
import json
import re
from dataclasses import dataclass

from . import policy


@dataclass
class Scalar:
    key: str
    value: str
    spans: list
    parents: tuple = ()
    is_number: bool = False


def _string(text, start, end):
    """Decode a JSON string and map each decoded codepoint to a source interval."""
    spans, chars = [], []
    i = start + 1
    while i < end - 1:
        a = i
        if text[i] != '\\':
            chars.append(text[i]); i += 1
        elif text[i + 1] != 'u':
            chars.append(json.loads('"' + text[i:i + 2] + '"')); i += 2
        else:
            cp = int(text[i + 2:i + 6], 16); i += 6
            if 0xD800 <= cp <= 0xDBFF and text[i:i + 2] == '\\u':
                low = int(text[i + 2:i + 6], 16)
                if 0xDC00 <= low <= 0xDFFF:
                    cp = 0x10000 + ((cp - 0xD800) << 10) + low - 0xDC00
                    i += 6
            chars.append(chr(cp))
        spans.append((a, i))
    return ''.join(chars), spans


TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}\[\]:,]')


def json_scalars(text):
    """Return scalar leaves for valid object/array JSON, or None for plain text."""
    if text.lstrip()[:1] not in ('{', '['):
        return None
    try:
        parsed = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(parsed, (dict, list)):
        return None
    tokens = list(TOKEN.finditer(text))
    leaves = []
    pos = 0

    def visit(key='', parents=()):
        nonlocal pos
        token = tokens[pos]; raw = token.group(); pos += 1
        if raw == '{':
            while tokens[pos].group() != '}':
                field = json.loads(tokens[pos].group()); pos += 2  # key and colon
                visit(field, parents + ((key,) if key else ()))
                if tokens[pos].group() == ',':
                    pos += 1
            pos += 1
        elif raw == '[':
            while tokens[pos].group() != ']':
                visit(key, parents)
                if tokens[pos].group() == ',':
                    pos += 1
            pos += 1
        elif raw.startswith('"'):
            value, spans = _string(text, token.start(), token.end())
            leaves.append(Scalar(key, value, spans, parents))
        elif raw not in {'true', 'false', 'null'}:
            leaves.append(Scalar(key, raw, [(i, i + 1) for i in range(token.start(), token.end())], parents, True))

    try:
        visit()
    except (IndexError, RecursionError):
        # Very deeply nested valid JSON should retain the plain-text fallback.
        return None
    return leaves


def normalize_key(key):
    return re.sub(r'[^a-z0-9]', '', key.lower())


def label(key):
    key = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', key)
    return re.sub(r'[_-]+', ' ', key)


# These aliases intentionally identify whole values from their schema context.
# Other typed fields retain the existing recognizers' value validation.
NAME_FIELDS = {'firstname', 'lastname', 'middlename', 'givenname', 'familyname', 'surname', 'fullname', 'personname', 'name'}
ORG_FIELDS = {'companyname', 'organizationname', 'organisationname', 'employer', 'partners'}
EMPTY_VALUES = {'', 'null', 'unknown', 'n/a', 'none', 'unavailable', 'nil'}


def valid_age(leaf):
    from decimal import Decimal, InvalidOperation
    if not leaf.is_number:
        return leaf.value.isdigit() and 0 <= int(leaf.value) < 120
    try:
        value = Decimal(leaf.value)
        return value.is_finite() and value == value.to_integral_value() and 0 <= value < 120
    except InvalidOperation:
        return False


def analyze_json(analyzer, text, leaves, threshold, entities):
    from .recognizers import StructuredFieldRecognizer
    custom = 'StructuredFieldRecognizer' in getattr(analyzer, 'custom_recognizer_names', ())
    wanted = set(entities) if entities else None
    fields, inputs = [], []
    for leaf in leaves:
        if not leaf.value or leaf.value.lower() in EMPTY_VALUES:
            continue
        key = normalize_key(leaf.key)
        prefix = label(leaf.key) + ': ' if leaf.key else ''
        prefix = ''.join('\ufffd' if 0xD800 <= ord(c) <= 0xDFFF else c for c in prefix)
        # Unknown keys still offer context, but cannot be matched as data.
        fields.append((leaf, key, len(prefix)))
        inputs.append(prefix + ''.join('\ufffd' if 0xD800 <= ord(c) <= 0xDFFF else c for c in leaf.value))
    # Scan patterns once over a boundary-marked corpus. Results are assigned to
    # a single value before context enhancement; keys/neighboring values cannot
    # boost confidence or enter the returned span. NLP remains batched per value.
    from bisect import bisect_right
    from presidio_analyzer import RecognizerResult
    corpus_parts, starts, cursor = [], [], 0
    for piece in inputs:
        starts.append(cursor)
        corpus_parts.append(piece + '\n\x00\n')
        cursor += len(piece) + 3
    corpus = ''.join(corpus_parts)
    wanted_entities = entities or analyzer.get_supported_entities(language='en')
    recognizers = analyzer.registry.get_recognizers(language='en', entities=wanted_entities)
    grouped = [[] for _ in fields]
    nlp_recognizers = []
    for recognizer in recognizers:
        if recognizer.name == 'SpacyRecognizer':
            nlp_recognizers.append(recognizer)
            continue
        if not recognizer.is_loaded:
            recognizer.load()
            recognizer.is_loaded = True
        for result in recognizer.analyze(text=corpus, entities=wanted_entities, nlp_artifacts=None):
            index = bisect_right(starts, result.start) - 1
            if index < 0:
                continue
            offset = starts[index]
            value_offset = fields[index][2]
            if result.start < offset + value_offset or result.end > offset + len(inputs[index]):
                continue
            result.start -= offset
            result.end -= offset
            result.recognition_metadata = dict(result.recognition_metadata or {})
            result.recognition_metadata.setdefault(RecognizerResult.RECOGNIZER_NAME_KEY, recognizer.name)
            result.recognition_metadata.setdefault(RecognizerResult.RECOGNIZER_IDENTIFIER_KEY, recognizer.id)
            grouped[index].append(result)
    from presidio_analyzer.nlp_engine import NlpArtifacts
    artifacts_by_index = [None] * len(fields)
    need_nlp = []
    for index, (leaf, key, _) in enumerate(fields):
        canonical = StructuredFieldRecognizer.FIELDS.get(key)
        if key in NAME_FIELDS - {'name'}:
            canonical = 'PERSON'
        elif key in ORG_FIELDS:
            canonical = 'ORGANIZATION'
        # A known key is insufficient when the value contains free-form prose,
        # or the caller explicitly requests a different NLP classification.
        nlp_entities = {'PERSON', 'ORGANIZATION', 'LOCATION', 'NRP', 'DATE_TIME'}
        requested_nlp = wanted & nlp_entities if wanted is not None else set()
        whole_typed = any(r.start == fields[index][2] and r.end == len(inputs[index]) for r in grouped[index])
        trusted = custom and (canonical in {'PERSON', 'ORGANIZATION'} or whole_typed) and not (requested_nlp - ({canonical} if canonical else set()))
        if canonical == 'PHONE_NUMBER' and not (7 <= len(re.sub(r'\D', '', leaf.value)) <= 15 and re.fullmatch(r'\+?[\d ().-]+', leaf.value)):
            trusted = False
        if trusted:
            doc = analyzer.nlp_engine.nlp['en'].make_doc(inputs[index])
            artifacts_by_index[index] = NlpArtifacts([], doc, [t.idx for t in doc], [t.lower_ for t in doc], analyzer.nlp_engine, 'en')
        else:
            need_nlp.append(index)
    batch = analyzer.nlp_engine.process_batch([inputs[i] for i in need_nlp], language='en', batch_size=64)
    for index, (_, artifacts) in zip(need_nlp, batch):
        artifacts_by_index[index] = artifacts
    found = []
    for index, (leaf, key, offset) in enumerate(fields):
        piece, artifacts = inputs[index], artifacts_by_index[index]
        results = grouped[index]
        for recognizer in nlp_recognizers:
            for result in recognizer.analyze(text=piece, entities=wanted_entities, nlp_artifacts=artifacts):
                result.recognition_metadata = dict(result.recognition_metadata or {})
                result.recognition_metadata.setdefault(RecognizerResult.RECOGNIZER_NAME_KEY, recognizer.name)
                result.recognition_metadata.setdefault(RecognizerResult.RECOGNIZER_IDENTIFIER_KEY, recognizer.id)
                results.append(result)
        results = analyzer.context_aware_enhancer.enhance_using_context(
            text=piece, raw_results=results, nlp_artifacts=artifacts, recognizers=recognizers)
        for r in results:
            explanation = r.analysis_explanation
            context_word = (explanation.supportive_context_word if explanation else "") or ""
            has_context = bool(context_word)
            if not policy.accepts(r.entity_type, r.score, has_context, threshold):
                continue
            if key == 'age' and r.entity_type == 'AGE' and (r.start != offset or r.end != len(piece) or not valid_age(leaf)):
                continue
            a, b = r.start - offset, r.end - offset
            if not 0 <= a < b <= len(leaf.spans):
                continue
            if r.entity_type == 'DATE_TIME' and leaf.value.isdigit() and key not in {'year', 'birthyear', 'yearofbirth'}:
                continue
            # Schema field-name lists contain vocabulary, not customer values.
            if key in {'required', 'fields', 'fieldnames', 'keys'} and r.entity_type in {'PERSON', 'ORGANIZATION', 'LOCATION', 'NRP'}:
                continue
            # Currency codes are schema values, not locations or affiliations.
            if key in {'currency', 'currencycode'} and r.entity_type in {'LOCATION', 'ORGANIZATION', 'NRP'}:
                continue
            sa, sb = leaf.spans[a][0], leaf.spans[b - 1][1]
            found.append(dict(text=text[sa:sb], entity=r.entity_type, start=sa, end=sb, score=round(float(r.score), 3),
                              recognizer=(r.recognition_metadata or {}).get('recognizer_name', ''), context=has_context, context_word=context_word))
        if custom:
            entity = StructuredFieldRecognizer.FIELDS.get(key)
            if key in NAME_FIELDS and (key != 'name' or any(normalize_key(p) in {'person', 'people', 'customer', 'customers', 'user', 'users', 'patient', 'patients', 'contact', 'contacts', 'profile'} for p in leaf.parents)) and any(c.isalpha() for c in leaf.value):
                entity = 'PERSON'
            elif key in ORG_FIELDS and any(c.isalpha() for c in leaf.value):
                entity = 'ORGANIZATION'
            if entity and (wanted is None or entity in wanted) and threshold <= .9:
                if not StructuredFieldRecognizer.valid_alias(key, leaf.value):
                    continue
                if entity == 'AGE' and not valid_age(leaf):
                    continue
                if entity == 'PHONE_NUMBER' and not (7 <= len(re.sub(r'\D', '', leaf.value)) <= 15 and re.fullmatch(r'\+?[\d ().-]+', leaf.value)):
                    continue
                sa, sb = leaf.spans[0][0], leaf.spans[-1][1]
                found.append(dict(text=text[sa:sb], entity=entity, start=sa, end=sb, score=.9, recognizer='StructuredFieldRecognizer', context=False))
    return found
