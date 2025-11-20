#!/usr/bin/env python3
"""Evaluate the NLU intents model (Accuracy, F1 macro) using a CSV with text,intent

Usage:
  python scripts/eval_nlu.py --input tests/intents_eval.csv
"""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
import json

try:
    from sklearn.metrics import f1_score, accuracy_score
except Exception:
    f1_score = None
    accuracy_score = None

from backend.nlu.intents import IntentsRuntime, INTENTS_PATH


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input file not found: {in_path}")
        return

    # Ensure model exists
    runtime = IntentsRuntime()
    if runtime.model is None:
        print('Warning: intents.joblib model not available. IntentsRuntime will use rule-based fallback. Aborting.')
        return

    y_true = []
    y_pred = []
    rows = []
    with in_path.open('r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            text = r.get('text') or r.get('sentence') or r.get('query') or ''
            intent = r.get('intent') or r.get('label') or ''
            if not text or not intent:
                continue
            label, prob = runtime.predict(text)
            y_true.append(intent)
            y_pred.append(label)
            rows.append({'text': text, 'expected': intent, 'predicted': label, 'prob': prob})

    if not rows:
        print('No evaluation rows found.')
        return

    # Compute metrics
    if f1_score is None or accuracy_score is None:
        print('sklearn not available; printing per-sample summary only.')
        correct = sum(1 for a,b in zip(y_true, y_pred) if a==b)
        print(f'Accuracy: {correct}/{len(y_true)} = {correct/len(y_true):.3f}')
        return

    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average='macro')
    print('NLU evaluation:')
    print(f'  samples: {len(y_true)}')
    print(f'  accuracy: {acc:.4f}')
    print(f'  f1_macro: {f1:.4f}')

    # Optional: show top confusion cases
    errors = [r for r in rows if r['expected'] != r['predicted']]
    errors = sorted(errors, key=lambda x: x['prob'], reverse=True)[:20]
    if errors:
        print('\nSample errors (up to 20):')
        for e in errors[:20]:
            print(f"- text={e['text']!r} expected={e['expected']} predicted={e['predicted']} prob={e['prob']}")


if __name__ == '__main__':
    main()
