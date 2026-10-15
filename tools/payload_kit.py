"""Shared machinery for the payload builders: seeded value generation, expectations and decoys.

A builder creates a Kit, builds a JSON document with kit.gen(...) / kit.expect(...) / kit.decoy(...), and calls kit.write().
Every value is synthetic. Identifiers with a checksum are validated by *Presidio's own* recognizers (not this project's
detector), so a payload cannot pass merely because the detector agrees with itself. Each entity draws from its own seeded
stream, so changing one value never shifts any other.
"""
import base64
import inspect
import json
import os
import random

from pii_detector.recognizers import luhn_ok, vin_ok
from tools.world_pii import ENTITY_GENERATORS, digits

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "samples")
MAX_BYTES = 20_000          # what the API accepts
_SKIPPED = ("Azure", "Stanza", "Transformers", "GLiNER", "HuggingFace", "LangExtract", "MedicalNER", "Spacy")


class Kit:
    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)          # for values that have no entity of their own (hex strings, bytes, ...)
        self.generators = ENTITY_GENERATORS()
        self.manifest = []
        self._draws = {}
        self._predefined = None

    # ------------------------------------------------------------------------------------------ randomness
    def entity_rng(self, entity):
        """An independent stream per entity (and per use of it)."""
        self._draws[entity] = self._draws.get(entity, 0) + 1
        return random.Random(f"{self.seed}:{entity}:{self._draws[entity]}")

    # ------------------------------------------------------------------------------------- Presidio's recognizers
    def predefined(self):
        """Presidio's own pattern recognizers by entity."""
        if self._predefined is None:
            import presidio_analyzer.predefined_recognizers as module
            from presidio_analyzer import EntityRecognizer

            self._predefined = {}
            for name, cls in inspect.getmembers(module, inspect.isclass):
                if issubclass(cls, EntityRecognizer) and name.endswith("Recognizer") and not any(k in name for k in _SKIPPED):
                    try:
                        instance = cls(supported_language="en")
                    except Exception:
                        continue
                    self._predefined.setdefault(instance.supported_entities[0], instance)
        return self._predefined

    @staticmethod
    def score_for(recognizer, entity, value):
        return max([r.score for r in recognizer.analyze(text=value, entities=[entity], nlp_artifacts=None)] or [0.0])

    def gen(self, entity, tries=60):
        """A value the project's generator makes that Presidio's recognizer for `entity` accepts most strongly,
        preferring one that no other Presidio recognizer also accepts strongly (so the type is unambiguous)."""
        recognizers = self.predefined()
        target = recognizers.get(entity)
        stream = self.entity_rng(entity)
        best, best_key = None, None
        for _ in range(tries):
            value = self.generators[entity](stream)
            if target is None:
                return value
            strength = self.score_for(target, entity, value)
            rivals = max([self.score_for(r, e, value) for e, r in recognizers.items() if e != entity] or [0.0])
            key = (strength, -rivals)
            if best_key is None or key > best_key:
                best, best_key = value, key
            if strength >= 0.85 and rivals < 0.5:
                break
        return best

    def valid_for(self, recognizer_class, entity, make, tries=1500):
        """The strongest value the Presidio recognizer itself accepts, for types without a generator.

        A value that fails the recognizer's pattern or checksum yields no result at all; a checksum-valid one scores far
        higher than a value that only matches the pattern, so keep sampling until a strong one turns up.
        """
        recognizer = recognizer_class(supported_language="en")
        stream = self.entity_rng(entity)
        best, best_score = None, 0.0
        for _ in range(tries):
            value = make(stream)
            score = self.score_for(recognizer, entity, value)
            if score > best_score:
                best, best_score = value, score
            if best_score >= 0.85:
                break
        if best is None:
            raise RuntimeError(f"no valid {entity} found")
        return best

    # ------------------------------------------------------------------------------------------- expectations
    def expect(self, value, entity, where, note="", within=None):
        """Record that `value` must be reported as `entity`; return it.

        `within` is the full string when `value` is only a part of it (free text). Otherwise the whole leaf must equal `value`.
        """
        self.manifest.append({"entity": entity, "value": str(value), "where": where, "note": note, "within": within})
        return value

    def decoy(self, value, where):
        """Record a value that must NOT be reported at all; return it."""
        self.manifest.append({"entity": None, "value": str(value), "where": where, "note": "decoy", "within": None})
        return value

    def gap(self, value, entity, where, note="", in_key=False):
        """Record a value the detector is known NOT to report yet (a documented gap, kept apart from the required ones)."""
        self.manifest.append({"entity": entity, "value": str(value), "where": where, "note": note, "within": None, "gap": True, "in_key": in_key})
        return value

    def allow(self, value, entity, where, note="", within=None):
        """Record a value that may be reported as `entity` or not at all (neither counts as a failure); return it."""
        self.manifest.append({"entity": entity, "value": str(value), "where": where, "note": note, "within": within, "allowed": True})
        return value

    # ------------------------------------------------------------------------------------------ small helpers
    def hexstr(self, n):
        return "".join(self.rng.choice("0123456789abcdef") for _ in range(n))

    def luhn_number(self, prefix, length):
        body = prefix + digits(self.rng, length - len(prefix) - 1)
        for check in "0123456789":
            if luhn_ok(body + check):
                return body + check

    def vin(self):
        alphabet = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
        body = [self.rng.choice(alphabet) for _ in range(17)]
        for check in "0123456789X":
            body[8] = check
            candidate = "".join(body)
            if vin_ok(candidate):
                return candidate

    @staticmethod
    def b64url(data):
        return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=").decode()

    def jwt(self):
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        return ".".join([self.b64url({"alg": "HS256", "typ": "JWT"}),
                         self.b64url({"sub": digits(self.rng, 10), "iss": "https://auth.contoso.example", "iat": 1790000000 + self.rng.randint(0, 99999)}),
                         "".join(self.rng.choice(alphabet) for _ in range(43))])

    # ------------------------------------------------------------------------------------------------ output
    def write(self, doc, stem):
        """Write samples/<stem>.json and samples/<stem>.expected.json; return a one-line summary."""
        text = json.dumps(doc, indent=2, ensure_ascii=False)
        size = len(text.encode())
        if size > MAX_BYTES:
            raise SystemExit(f"payload is {size} bytes; the API accepts at most {MAX_BYTES}")
        os.makedirs(SAMPLES, exist_ok=True)
        with open(os.path.join(SAMPLES, f"{stem}.json"), "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        with open(os.path.join(SAMPLES, f"{stem}.expected.json"), "w", encoding="utf-8") as handle:
            json.dump({"seed": self.seed, "notice": "Synthetic values; checksum-valid where the identifier has a checksum, never issued to anyone.",
                       "expected": self.manifest}, handle, ensure_ascii=False, indent=1)
        entities = {m["entity"] for m in self.manifest if m["entity"] and not m.get("gap") and not m.get("allowed")}
        return (f"wrote samples/{stem}.json ({size} bytes) and {stem}.expected.json: "
                f"{len(self.manifest)} expectations, {len(entities)} distinct entity types")
