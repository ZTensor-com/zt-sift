#!/usr/bin/env python3
"""Run Presidio (en_core_web_lg only) over the made-up documents and show what it finds and misses.

For every expected item the table shows the Presidio entity types that overlap it and their scores.
"MISSED" means Presidio produced no result at all for it. This is informational: Presidio has no notion
of an EIN or a password, so a match under another type (or none) is expected for some items.

    python -m tools.check_coverage                 # threshold 0.5, like the API
    python -m tools.check_coverage --threshold 0.3 # more candidates, more noise
"""
import argparse
import statistics
import sys
import time

from pii_detector.detector import detect, load_analyzer
from tools.documents import DOCUMENTS


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    analyzer = load_analyzer()
    detect(analyzer, "warm-up", args.threshold)
    found_total = expected_total = 0
    unexpected = []
    timings = []
    for name, (text, expected) in DOCUMENTS.items():
        runs = []
        for _ in range(3):
            started = time.time()
            detections = detect(analyzer, text, args.threshold)
            runs.append(time.time() - started)
        timings.append(statistics.median(runs))
        print(f"\n=== {name} ({len(text)} chars, {statistics.median(runs) * 1000:.0f} ms)")
        spans = []
        for item, kind in expected:
            start = text.index(item)
            end = start + len(item)
            spans.append((start, end))
            hits = sorted({(d["entity"], d["score"]) for d in detections if d["start"] < end and start < d["end"]},
                          key=lambda h: -h[1])
            expected_total += 1
            found_total += bool(hits)
            shown = ", ".join(f"{entity} {score:.2f}" for entity, score in hits) if hits else "MISSED"
            print(f"  {kind:24} {item[:44]!r:48} {shown}")
        for d in detections:
            if not any(d["start"] < end and start < d["end"] for start, end in spans):
                unexpected.append((name, d))
    print(f"\nPresidio produced a result for {found_total} of {expected_total} expected items "
          f"(type not checked; see the table). Median time per document {statistics.median(timings) * 1000:.0f} ms.")
    if unexpected:
        print(f"\nResults that are not one of the expected items ({len(unexpected)}):")
        for name, d in unexpected:
            print(f"  [{name}] {d['entity']:18} {d['score']:.2f}  {d['text']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
