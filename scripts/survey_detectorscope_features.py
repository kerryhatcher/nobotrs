#!/usr/bin/env python3
"""Local-only feature survey; counts are not editorial validation or human review.

No excerpts are written. Sample identifiers are hashed. Only successfully completed,
fully covered reports enter denominators. Unknown/edited labels remain excluded.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def rates(rows):
    """Presence is counted once per sample, even if several hotspots share a feature."""
    totals = Counter()
    presence = {"ai": Counter(), "human": Counter()}
    for row in rows:
        label = row["label"]
        if label not in presence:
            continue
        totals[label] += 1
        presence[label].update(set(row["features"]))
    results = []
    for feature in sorted(set(presence["ai"]) | set(presence["human"])):
        ai = presence["ai"][feature] / totals["ai"] if totals["ai"] else None
        human = presence["human"][feature] / totals["human"] if totals["human"] else None
        lift = ai / human if ai is not None and human is not None and human > 0 else None
        results.append({"feature": feature, "ai_count": presence["ai"][feature],
                        "human_count": presence["human"][feature],
                        "ai_documents": totals["ai"], "human_documents": totals["human"],
                        "ai_rate": ai, "human_rate": human, "lift": lift})
    return results


def report_for_survey(report):
    """Use only DetectorScope's own completed windows, avoiding cross-model alignment."""
    backend = next((b for b in report.get('backends', []) if b['backend'] == 'detectorscope'), None)
    if not backend:
        return {'complete': False}
    outcome = backend['outcome']
    if outcome['status'] == 'abstained':
        return {'complete': True, 'checks': [{'backend': 'detectorscope', 'status': 'skipped'}]}
    evidence = outcome.get('details', {}).get('model_evidence') or {}
    windows = [w for w in evidence.get('windows', []) if w.get('status') == 'scored' and w.get('body_tokens', 0) >= 128 and w.get('raw_output') is not None]
    values = [w['raw_output'] for w in windows]
    eligible = len(values) >= 2 and max(values) > min(values)
    windows = sorted(windows, key=lambda w: (-w['raw_output'], w['index']))[:3] if eligible else []
    return {'complete': outcome['status'] == 'scored' and evidence.get('token_coverage') == 1,
            'hotspots': {'provenance': [{'backend': 'detectorscope', 'token_coverage': evidence.get('token_coverage')}],
                         'hotspots': [{'features': [{'feature_id': f['id'], 'max_activation': max((h['activation'] for h in f.get('highlights', [])), default=0)} for f in (w.get('detectorscope') or {}).get('top_features', [])]} for w in windows]}}


def survey(samples, invoke):
    rows, statuses = [], []
    for sample in samples:
        label = {"ai_drafted": "ai", "ai": "ai", "human": "human"}.get(sample.label)
        hashed = hashlib.sha256(f"{sample.corpus}:{sample.id}".encode()).hexdigest()
        if label is None or sample.confidence != "high":
            statuses.append({"id": hashed, "status": "excluded_label_or_confidence"})
            continue
        try:
            report = invoke(sample.text, sample.markdown)
            diagnostic = report.get("hotspots", {})
            if report.get("complete") and any(c.get("backend") == "detectorscope" and c.get("status") == "skipped" for c in report.get("checks", [])):
                statuses.append({"id": hashed, "status": "skipped_model_context"})
                continue
            complete = report.get("complete") and any(
                p.get("backend") == "detectorscope" and p.get("token_coverage") == 1.0
                for p in diagnostic.get("provenance", []))
            if not complete:
                statuses.append({"id": hashed, "status": "incomplete_or_no_windows"})
                continue
            features = {f["feature_id"] for h in diagnostic.get("hotspots", [])[:3]
                        for f in h.get("features", []) if f.get("max_activation", 0) > 0}
            # No eligible ranked window is missing context, not a negative feature observation.
            if not diagnostic.get("hotspots"):
                statuses.append({"id": hashed, "status": "insufficient_ranked_context"})
                continue
            rows.append({"label": label, "features": sorted(features)})
            statuses.append({"id": hashed, "status": "completed"})
        except (OSError, ValueError, subprocess.SubprocessError):
            statuses.append({"id": hashed, "status": "operational_error"})
    return rates(rows), statuses


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--corpus', action='append', required=True)
    p.add_argument('--models-dir', type=Path, required=True)
    p.add_argument('--internal-dir', type=Path)
    p.add_argument('--reports-dir', type=Path, help='reuse checkpointed <sample-id>/report.json; no inference')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--max-samples', type=int)
    p.add_argument('--timeout-ms', type=int, default=300000)
    args = p.parse_args()
    import corpora
    samples = []
    errors = []
    for corpus in args.corpus:
        try:
            samples.extend(corpora.iter_samples(corpus, args.internal_dir))
        except corpora.CorpusError as error:
            errors.append({'corpus': corpus, 'error': str(error)})
    if args.max_samples is not None:
        samples = samples[:args.max_samples]
    env = {k: v for k, v in os.environ.items() if not k.startswith('NOBOTRS_')}
    # Retain only explicit local-worker runtime configuration.
    for key in ('NOBOTRS_MODEL_PYTHON', 'NOBOTRS_DETECTORSCOPE_DEVICE', 'NOBOTRS_DETECTORSCOPE_DTYPE'):
        if key in os.environ:
            env[key] = os.environ[key]
    with tempfile.TemporaryDirectory(prefix='nobotrs-feature-survey-') as temp:
        config = Path(temp) / 'config.json'
        config.write_text('{}')
        cached_reports = {}
        if args.reports_dir:
            for sample in samples:
                path = args.reports_dir / sample.id / 'report.json'
                if path.is_file():
                    cached_reports[hashlib.sha256(sample.text.encode()).hexdigest()] = report_for_survey(json.loads(path.read_text()))
        def invoke(text, markdown):
            if args.reports_dir:
                key = hashlib.sha256(text.encode()).hexdigest()
                if key not in cached_reports:
                    raise ValueError('missing checkpointed review')
                return cached_reports[key]
            cmd = [str(args.binary.resolve()), 'review', '-', '--config', str(config),
                   '--language', 'en', '--models', 'detectorscope', '--model-coverage', 'full',
                   '--models-dir', str(args.models_dir), '--format', 'json',
                   '--timeout-ms', str(args.timeout_ms)]
            if markdown:
                cmd.append('--markdown')
            result = subprocess.run(cmd, input=text, text=True, capture_output=True,
                                    env=env, timeout=args.timeout_ms / 1000 + 30, check=False)
            if result.returncode != 0:
                raise ValueError('incomplete local review')
            return json.loads(result.stdout)
        rows, statuses = survey(samples, invoke)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ['feature', 'ai_count', 'human_count', 'ai_documents', 'human_documents',
              'ai_rate', 'human_rate', 'lift']
    with args.out.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    metadata = {'schema_version': '1.0.0', 'validated': False, 'human_reviewed': False,
                'status_counts': dict(Counter(s['status'] for s in statuses)),
                'sample_limit': args.max_samples, 'corpus_errors': errors, 'samples': statuses,
                'reports_dir': str(args.reports_dir) if args.reports_dir else None,
                'inference': 'reused_reports' if args.reports_dir else 'fresh_local',
                'note': 'Counts only; no excerpts, causal utility claim or feature mapping.'}
    args.out.with_suffix('.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return 2 if errors or any(s['status'] in ('operational_error', 'incomplete_or_no_windows') for s in statuses) else 0


if __name__ == '__main__':
    raise SystemExit(main())
