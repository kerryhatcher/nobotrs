#!/usr/bin/env python3
"""Dump independently loaded pinned Python tokenizer IDs and UTF-8 byte offsets.

Only the public Bibb fixture is intended for a committed reference. No network access.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--text', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--models-dir', type=Path,
                        default=Path(os.environ.get('NOBOTRS_MODELS_DIR', Path.home() / '.cache/nobotrs-local-ai/models-v1')))
    args = parser.parse_args()
    from transformers import AutoTokenizer
    manifest = json.loads(args.manifest.read_text())
    tokenizer = AutoTokenizer.from_pretrained(args.models_dir / 'detectorscope/extractor', local_files_only=True)
    text = ' '.join(args.text.read_text().split())
    encoded = tokenizer(text, add_special_tokens=True, truncation=False, padding=False,
                        return_offsets_mapping=True)
    byte = [0]
    for ch in text:
        byte.append(byte[-1] + len(ch.encode('utf-8')))
    result = {'tokenizer_revision': manifest['tokenizer']['revision'],
              'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
              'ids': encoded['input_ids'],
              'offsets': [[byte[a], byte[b]] for a, b in encoded['offset_mapping']]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
