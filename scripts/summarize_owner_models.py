#!/usr/bin/env python3
"""Summarize owner baseline coverage without promoting classifier scores to editing advice."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def summarize(directory: Path) -> dict:
    run = json.loads((directory / 'run.json').read_text())
    models = run['settings']['models']
    counts = {model: Counter({status: 0 for status in ('scored_full', 'skipped', 'incomplete', 'failed', 'missing', 'missing_backend', 'missing_full_evidence', 'missing_output')}) for model in models}
    windows = {model: Counter() for model in models}
    labels = Counter()
    reasons = Counter()
    missing_files = []
    issues = []
    incomplete_documents = []
    for doc in run['documents']:
        labels[f"{doc['label']}:{doc['confidence']}"] += 1
        stem = Path(doc['file']).stem
        report_path = directory / stem / 'report.json'
        review_path = directory / stem / 'review.json'
        if not report_path.is_file() or not review_path.is_file():
            missing_files.append(doc['file'])
            for model in models:
                recorded = doc.get('backends', {}).get(model)
                counts[model]['missing' if recorded == 'missing' else 'missing_output'] += 1
            continue
        report = json.loads(report_path.read_text())
        review = json.loads(review_path.read_text())
        if not report.get('complete') or not review.get('complete'):
            incomplete_documents.append(doc['file'])
        if review.get('hotspots', {}).get('reason'):
            reasons[review['hotspots']['reason']] += 1
        for model in models:
            backend = next((b for b in report['backends'] if b['backend'] == model), None)
            status = 'missing_backend'
            if backend:
                outcome = backend['outcome']
                state = outcome['status']
                score = outcome['details'] if state == 'scored' else outcome['details'].get('score') if state == 'incomplete' else None
                evidence = (score or {}).get('model_evidence') or {}
                status = 'scored_full' if state == 'scored' and evidence.get('token_coverage') == 1 else 'skipped' if state == 'abstained' else state
                if state == 'scored' and status != 'scored_full':
                    status = 'missing_full_evidence'
                for w in evidence.get('windows', []):
                    windows[model]['total'] += 1
                    windows[model][w['status']] += 1
                    windows[model]['insufficient_context' if w['insufficient_context'] else 'eligible_context'] += 1
                if status not in ('scored_full', 'skipped'):
                    issues.append({'file': doc['file'], 'backend': model, 'status': status})
            if backend is None:
                issues.append({'file': doc['file'], 'backend': model, 'status': status})
            recorded = doc.get('backends', {}).get(model)
            if recorded in ('missing', 'missing_backend'):
                status = recorded
                issues = [i for i in issues if not (i['file'] == doc['file'] and i['backend'] == model)]
                issues.append({'file': doc['file'], 'backend': model, 'status': recorded})
            counts[model][status] += 1
    processed = sum(doc.get('attempted', True) for doc in run['documents'])
    unprocessed = run['planned_documents'] - processed
    return {'schema_version': 'owner-model-coverage-summary-v1', 'validated_editorial_utility': False,
            'run_sha256': hashlib.sha256((directory / 'run.json').read_bytes()).hexdigest(),
            'binary_sha256': run['binary_sha256'], 'git_revision_at_run_start': run['git_revision'],
            'manifest_sha256': run['corpus_manifest_sha256'], 'finished': run['finished'],
            'planned_documents': run['planned_documents'], 'processed_documents': processed,
            'unprocessed_documents': unprocessed, 'fully_resolved_documents': run.get('fully_resolved_documents'), 'catalogued_documents': len(run['documents']), 'label_confidence_counts': dict(labels),
            'backend_status_counts': {k: dict(v) for k, v in counts.items()},
            'window_counts': {k: dict(v) for k, v in windows.items()},
            'empty_ranking_reasons': dict(reasons), 'missing_output_files': missing_files,
            'incomplete_or_failed': issues, 'incomplete_documents': incomplete_documents,
            'elapsed_ms': run['elapsed_ms'],
            'note': 'One registry reused, no remote services. Authorship scores and feature presence do not establish editorial utility. The medium-confidence human post is retained for sensitivity analysis only.'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('directory', type=Path)
    p.add_argument('--out', type=Path)
    args = p.parse_args()
    result = summarize(args.directory)
    text = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.out:
        args.out.write_text(text)
    else:
        print(text, end='')
    return 0 if result['finished'] and not result['missing_output_files'] and not result['incomplete_or_failed'] and not result['incomplete_documents'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
