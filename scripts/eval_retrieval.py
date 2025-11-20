#!/usr/bin/env python3
"""Evaluate retrieval module (Precision@K, MRR, nDCG@K) using a CSV of ground-truth.

CSV format: query,relevant_ids
relevant_ids: semicolon-separated list of ProposalLog.id values (integers)

Example:
desarrollo de API en 3 meses,"12;34;78"

Usage:
  python scripts/eval_retrieval.py --input tests/retrieval_eval.csv --k 5 --out reports/retrieval_eval.csv
"""
from __future__ import annotations
import argparse
import csv
import json
from typing import List
from pathlib import Path

try:
    from sklearn.metrics import ndcg_score
except Exception:
    ndcg_score = None

from backend.retrieval.similarity import get_retriever


def precision_at_k(retrieved: List[int], relevant: List[int], k: int) -> float:
    if k <= 0:
        return 0.0
    topk = retrieved[:k]
    if not topk:
        return 0.0
    hits = sum(1 for x in topk if x in relevant)
    return hits / float(k)


def reciprocal_rank(retrieved: List[int], relevant: List[int]) -> float:
    for idx, doc in enumerate(retrieved, start=1):
        if doc in relevant:
            return 1.0 / idx
    return 0.0


def parse_relevant(cell: str) -> List[int]:
    if not cell:
        return []
    parts = [p.strip() for p in cell.split(';') if p.strip()]
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except Exception:
            continue
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--out", type=str, help="CSV output per-query metrics")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input file not found: {in_path}")
        return

    retr = get_retriever()
    # Ensure index refreshed
    try:
        retr.refresh()
    except Exception as e:
        print(f"Warning: retriever.refresh() failed: {e}")

    rows = []
    with in_path.open('r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            q = r.get('query') or r.get('text') or ''
            rel = parse_relevant(r.get('relevant_ids', ''))
            if not q:
                continue
            rows.append({'query': q, 'relevant': rel})

    if not rows:
        print('No queries found in input file.')
        return

    results = []
    precisions = []
    rr_list = []
    ndcgs = []
    for r in rows:
        q = r['query']
        relevant = r['relevant']
        hits = retr.retrieve(q, top_k=args.k)
        retrieved_ids = [int(h.get('id')) for h in hits if h.get('id') is not None]
        p_at_k = precision_at_k(retrieved_ids, relevant, args.k)
        rr = reciprocal_rank(retrieved_ids, relevant)
        precisions.append(p_at_k)
        rr_list.append(rr)
        # ndcg: sklearn expects array-like of shape (n_samples, n_scores)
        if ndcg_score is not None:
            # Build relevance vector: for retrieved docs set 1 if in relevant, else 0
            scores = [1 if did in relevant else 0 for did in retrieved_ids]
            # if len(scores) < k, pad with zeros
            if len(scores) < args.k:
                scores = scores + [0] * (args.k - len(scores))
            try:
                nd = ndcg_score([ [1 if i in relevant else 0 for i in retrieved_ids] ], [scores], k=args.k)
            except Exception:
                try:
                    # fallback: compute ndcg with simpler approach
                    nd = ndcg_score([[1 if i in relevant else 0 for i in retrieved_ids]], [scores])
                except Exception:
                    nd = 0.0
            ndcgs.append(float(nd))
        else:
            ndcgs.append(0.0)

        results.append({
            'query': q,
            'relevant_ids': ';'.join(str(x) for x in relevant),
            'retrieved_ids': ';'.join(str(x) for x in retrieved_ids),
            'precision_at_k': p_at_k,
            'reciprocal_rank': rr,
            'ndcg_at_k': ndcgs[-1] if ndcgs else 0.0
        })

    # Summary
    import statistics
    summary = {
        'queries': len(results),
        'mean_precision_at_k': statistics.mean(precisions) if precisions else 0.0,
        'mean_mrr': statistics.mean(rr_list) if rr_list else 0.0,
        'mean_ndcg_at_k': statistics.mean(ndcgs) if ndcgs else 0.0
    }

    print('Retrieval evaluation summary:')
    print(json.dumps(summary, indent=2))

    if args.out:
        outp = Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with outp.open('w', encoding='utf-8', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
            writer.writeheader()
            for r in results:
                writer.writerow(r)
        print(f'Wrote per-query results to {outp}')


if __name__ == '__main__':
    main()
