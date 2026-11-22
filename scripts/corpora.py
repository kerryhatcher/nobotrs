#!/usr/bin/env python3
"""Local corpus registry, checksum verification and sample readers (Plan 5, Task 1).

Local corpora live under ``$NOBOTRS_INTERNAL_DIR`` (default
``/mnt/storage/projects/nobotrs/docs/internal``) and are verified against
``test-artifacts/SHA256SUMS`` before any sample is yielded. A mismatch stops the
run and names the file. Only the owner-post corpus is committed; the other
corpora are read in place and never copied into the repository.

Standard library only. ``pyarrow`` is imported lazily for the Beemo Parquet shard.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import mmap
import os
import re
import shutil
import sys
import tarfile
import zipfile
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "evaluation" / "corpora" / "registry.json"
DEFAULT_INTERNAL_DIR = Path("/mnt/storage/projects/nobotrs/docs/internal")
OWNER_CORPUS = "owner-posts-v1"
OWNER_CUTOFF = "2025-03-10"
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:['’][a-z0-9]+)*")


class CorpusError(RuntimeError):
    """A local corpus cannot be read or does not match its checksums."""


class ChecksumMismatch(CorpusError):
    """A file's SHA-256 differs from SHA256SUMS (or the file is missing)."""


@dataclass(frozen=True)
class Sample:
    corpus: str
    id: str
    group: str
    label: str
    genre: str
    date: str | None
    text: str
    markdown: bool
    confidence: str = "high"


# ---------------------------------------------------------------- paths and registry

def internal_dir(override: str | Path | None = None) -> Path:
    if override is not None:
        return Path(override)
    env = os.environ.get("NOBOTRS_INTERNAL_DIR")
    return Path(env) if env else DEFAULT_INTERNAL_DIR


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    corpora = {entry["id"]: entry for entry in data["corpora"]}
    if len(corpora) != len(data["corpora"]):
        raise CorpusError("registry contains duplicate corpus ids")
    return corpora


def non_owner_corpora(registry: dict[str, dict]) -> list[str]:
    return [cid for cid, entry in registry.items() if not entry.get("owner")]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums(path: Path) -> dict[str, str]:
    """Map SHA256SUMS paths (relative to test-artifacts/) to their digests."""
    entries: dict[str, str] = {}
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        digest, sep, rel = line.partition("  ")
        if not sep and " *" in line:
            digest, _, rel = line.partition(" *")
        if len(digest) != 64 or not rel:
            raise CorpusError(f"{path}:{line_no}: malformed checksum line")
        entries[rel] = digest
    return entries


def _corpus_subtree(entry: dict) -> str:
    root = entry["root"]
    if not root.startswith("test-artifacts/"):
        raise CorpusError(f"{entry['id']}: registry root must start with test-artifacts/")
    return root[len("test-artifacts/"):] + "/"


def verify_corpus(entry: dict, internal: Path) -> list[str]:
    """Check every SHA256SUMS line under this corpus. Returns the file names checked."""
    base = internal / "test-artifacts"
    sums_path = internal / entry["checksums"]
    if not sums_path.is_file():
        raise CorpusError(f"{entry['id']}: missing checksum file {sums_path}")
    prefix = _corpus_subtree(entry)
    expected = {rel: digest for rel, digest in parse_checksums(sums_path).items()
                if rel.startswith(prefix)}
    if not expected:
        raise CorpusError(f"{entry['id']}: SHA256SUMS lists no files under {prefix}")
    for rel in sorted(expected):
        target = base / rel
        if not target.is_file():
            raise ChecksumMismatch(f"{entry['id']}: missing file {rel}")
        actual = sha256_file(target)
        if actual != expected[rel]:
            raise ChecksumMismatch(
                f"{entry['id']}: checksum mismatch for {rel} "
                f"(expected {expected[rel][:12]}…, got {actual[:12]}…)")
    return sorted(expected)


def verify_owner_committed(entry: dict, manifest: dict) -> None:
    committed = ROOT / entry["committed"]
    for post in manifest["posts"]:
        target = committed / post["file"]
        if not target.is_file():
            raise ChecksumMismatch(f"{OWNER_CORPUS}: committed copy missing {post['file']}")
        if sha256_file(target) != post["sha256"]:
            raise ChecksumMismatch(f"{OWNER_CORPUS}: committed copy differs from manifest {post['file']}")


# ---------------------------------------------------------------- label and manifest rules

def owner_label(filename: str) -> str:
    """Provenance label for an owner post, from its filename (roadmap decision 1)."""
    name = Path(filename).name
    match = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+?)(?:\.md)?$", name)
    if not match:
        raise CorpusError(f"owner post filename lacks a date prefix: {filename}")
    date, slug = match.group(1), match.group(2)
    if "crossover" in slug:
        return "ai_drafted"
    return "ai_drafted" if date >= OWNER_CUTOFF else "human"


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def primary(samples: Iterable[Sample]) -> list[Sample]:
    """Primary owner-corpus analysis excludes medium-confidence provenance (decision 2)."""
    return [s for s in samples if s.confidence != "medium"]


def load_owner_manifest(path: Path | None = None) -> dict:
    path = path or ROOT / "evaluation" / "corpora" / OWNER_CORPUS / "manifest.json"
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    for post in manifest["posts"]:
        if owner_label(post["file"]) != post["label"]:
            raise CorpusError(
                f"{post['file']}: manifest label {post['label']!r} violates the label rule")
        if post["confidence"] == "medium" and not post.get("provenance_note"):
            raise CorpusError(f"{post['file']}: medium confidence requires provenance_note")
    return manifest


# ---------------------------------------------------------------- readers

def _read_owner(entry: dict, internal: Path | None) -> Iterator[Sample]:
    manifest = load_owner_manifest()
    verify_owner_committed(entry, manifest)
    if internal is not None and (internal / entry["checksums"]).is_file():
        verify_corpus(entry, internal)
    counts = Counter(p["label"] for p in manifest["posts"])
    if counts != {"ai_drafted": 28, "human": 15}:
        raise CorpusError(f"owner manifest totals {dict(counts)}, expected 28 ai_drafted / 15 human")
    committed = ROOT / entry["committed"]
    for post in manifest["posts"]:
        stem = Path(post["file"]).stem
        text = (committed / post["file"]).read_text(encoding="utf-8")
        yield Sample(
            corpus=OWNER_CORPUS, id=stem, group=stem, label=post["label"],
            genre=post["genre"], date=post["date"], text=text, markdown=True,
            confidence=post["confidence"])


def beemo_samples(rows: Iterable[dict], corpus: str = "beemo") -> Iterator[Sample]:
    """Split Beemo rows into three labelled samples per prompt. Variants share a group."""
    columns = (("human_output", "human"), ("model_output", "ai"),
               ("human_edits", "ai_edited_by_human"))
    for index, row in enumerate(rows):
        prompt_id = str(row["prompt_id"])
        for column, label in columns:
            text = row.get(column)
            if not text or not str(text).strip():
                continue
            yield Sample(corpus=corpus, id=f"{index}:{column}", group=prompt_id, label=label,
                         genre="unspecified", date=None, text=str(text), markdown=False)


def _parquet_rows(path: Path) -> list[dict]:
    try:
        import pyarrow.parquet as pq  # lazy: optional dependency for this one reader
    except ImportError as exc:
        raise CorpusError(
            "pyarrow is required to read the Beemo Parquet shard "
            "(install it locally; the harness does not fetch it)") from exc
    table = pq.read_table(path, columns=["prompt_id", "model_output", "human_output", "human_edits"])
    return table.to_pylist()


def _read_beemo(entry: dict, internal: Path) -> Iterator[Sample]:
    path = internal / "test-artifacts" / "beemo" / "data" / "train-00000-of-00001.parquet"
    yield from beemo_samples(_parquet_rows(path))


TOKEN_NGRAM = 5


def _ngrams(tokens: list[str], size: int) -> list[tuple[str, ...]]:
    return [tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)]


def link_polished(originals: dict[str, str], polished: dict[str, str],
                  min_jaccard: float = 0.05) -> dict[str, str | None]:
    """Link each polished variant to its single best original by 5-gram Jaccard.

    APT-Eval has no explicit key, so grouping uses text. A variant is left unlinked
    (None) when no original reaches ``min_jaccard`` or when the best two tie.
    """
    original_grams = {oid: set(_ngrams(TOKEN_RE.findall(text.lower()), TOKEN_NGRAM))
                      for oid, text in originals.items()}
    index: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for oid, grams in original_grams.items():
        for gram in grams:
            index[gram].append(oid)
    links: dict[str, str | None] = {}
    for pid, text in polished.items():
        grams = set(_ngrams(TOKEN_RE.findall(text.lower()), TOKEN_NGRAM))
        overlap: Counter[str] = Counter()
        for gram in grams:
            for oid in index.get(gram, ()):
                overlap[oid] += 1
        scored = []
        for oid, shared in overlap.items():
            union = len(grams) + len(original_grams[oid]) - shared
            scored.append((shared / union if union else 0.0, oid))
        scored.sort(reverse=True)
        if not scored or scored[0][0] < min_jaccard:
            links[pid] = None
        elif len(scored) > 1 and scored[0][0] == scored[1][0]:
            links[pid] = None
        else:
            links[pid] = scored[0][1]
    return links


def apt_samples(original_rows: list[dict], polished_rows: list[dict],
                corpus: str = "apt-eval") -> Iterator[Sample]:
    originals = {str(r["id"]): r["generation"] for r in original_rows}
    polished = {str(r["id"]): r["generation"] for r in polished_rows}
    links = link_polished(originals, polished)
    domains = {str(r["id"]): r.get("domain") or "unspecified" for r in original_rows}
    for row in original_rows:
        oid = str(row["id"])
        yield Sample(corpus=corpus, id=f"orig-{oid}", group=oid, label="human",
                     genre=domains[oid], date=None, text=row["generation"], markdown=False)
    for row in polished_rows:
        pid = str(row["id"])
        origin = links.get(pid)
        group = origin if origin is not None else f"unlinked-{pid}"
        yield Sample(corpus=corpus, id=f"polished-{pid}", group=group, label="ai_polished",
                     genre=domains.get(origin, "unspecified") if origin else "unspecified",
                     date=None, text=row["generation"], markdown=False,
                     confidence="high" if origin is not None else "medium")


def _read_apt(entry: dict, internal: Path) -> Iterator[Sample]:
    base = internal / "test-artifacts" / "apt-eval"
    csv.field_size_limit(10**9)
    with (base / "original.csv").open(encoding="utf-8", newline="") as handle:
        originals = list(csv.DictReader(handle))
    with (base / "merged_apt_eval_dataset.csv").open(encoding="utf-8", newline="") as handle:
        polished = list(csv.DictReader(handle))
    yield from apt_samples(originals, polished)


def wi_locness_samples(lines_by_file: dict[str, Iterable[str]],
                       corpus: str = "wi-locness") -> Iterator[Sample]:
    """W&I learner essays (A/B/C) and LOCNESS native essays (N), one JSON object per line."""
    for name, lines in sorted(lines_by_file.items()):
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            record = json.loads(line)
            band = record.get("cefr", "?")
            genre = "native" if band == "N" else "learner"
            stem = Path(name).stem  # e.g. "A.dev": keeps splits of one band apart
            yield Sample(corpus=corpus, id=f"{stem}-{index}", group=f"{stem}-{index}",
                         label="human", genre=genre, date=None,
                         text=record["text"], markdown=False)


def _read_wi(entry: dict, internal: Path) -> Iterator[Sample]:
    archive = internal / "test-artifacts" / "wi-locness" / "wi+locness_v2.1.bea19.tar.gz"
    wanted = re.compile(r"^wi\+locness/json/[ABCN]\.(dev|train)\.json$")
    lines_by_file: dict[str, list[str]] = {}
    with tarfile.open(archive, "r:gz") as archive_handle:
        for member in archive_handle:
            if member.isfile() and wanted.match(member.name):
                handle = archive_handle.extractfile(member)
                lines_by_file[member.name] = io.TextIOWrapper(
                    handle, encoding="utf-8").read().splitlines()
    yield from wi_locness_samples(lines_by_file)


def gao_samples(reports, corpus: str = "govinfo-gao-2008") -> Iterator[Sample]:
    """``reports`` is a mapping or an iterable of (name, text); streamed, not loaded at once."""
    pairs = reports.items() if isinstance(reports, Mapping) else reports
    for name, text in pairs:
        stem = Path(name).stem
        yield Sample(corpus=corpus, id=stem, group=stem, label="human", genre="civic",
                     date=None, text=text, markdown=False)


def _read_gao(entry: dict, internal: Path) -> Iterator[Sample]:
    folder = internal / "test-artifacts" / "govinfo-gao-2008" / "reports"
    paths = sorted(folder.glob("*.txt"))
    yield from gao_samples((p.name, p.read_text(encoding="utf-8", errors="replace")) for p in paths)


def apply_delta(doc: str, ops: list[dict]) -> str:
    """Apply one Quill-style delta (retain / insert / delete) to a document string."""
    out: list[str] = []
    cursor = 0
    for op in ops:
        if "retain" in op:
            n = int(op["retain"])
            out.append(doc[cursor:cursor + n])
            cursor += n
        elif "insert" in op:
            out.append(str(op["insert"]))
        elif "delete" in op:
            cursor += int(op["delete"])
    out.append(doc[cursor:])
    return "".join(out)


def reconstruct_session(events: Iterable[dict]) -> tuple[str, Counter]:
    """Final document text and event counts for one CoAuthor writing session."""
    doc = ""
    counts: Counter = Counter()
    for event in events:
        counts[event.get("eventName", "unknown")] += 1
        if not doc and event.get("currentDoc"):
            doc = event["currentDoc"]
        delta = event.get("textDelta")
        if isinstance(delta, dict) and isinstance(delta.get("ops"), list):
            doc = apply_delta(doc, delta["ops"])
    return doc, counts


def coauthor_samples(sessions: Iterable[tuple[str, Iterable[dict]]],
                     corpus: str = "coauthor") -> Iterator[Sample]:
    """One sample per session: the reconstructed final text. Label is mixed provenance.

    ``group`` is the session. Writer-level grouping needs the metadata workbook, which this
    reader does not parse yet; writer-disjoint analysis is therefore not supported.
    """
    for session_id, events in sessions:
        text, _ = reconstruct_session(events)
        if not text.strip():
            continue
        yield Sample(corpus=corpus, id=session_id, group=session_id, label="mixed_provenance",
                     genre="unspecified", date=None, text=text, markdown=False)


def _read_coauthor(entry: dict, internal: Path) -> Iterator[Sample]:
    archive = internal / "test-artifacts" / "coauthor" / "chi2022-coauthor-v1.0.zip"

    def sessions() -> Iterator[tuple[str, Iterator[dict]]]:
        with zipfile.ZipFile(archive) as zf:
            for name in sorted(zf.namelist()):
                if not name.endswith(".jsonl"):
                    continue
                session_id = Path(name).stem
                with zf.open(name) as handle:
                    # Stream each session; events are not held for the whole archive.
                    events = (json.loads(line) for line in io.TextIOWrapper(
                        handle, encoding="utf-8") if line.strip())
                    yield session_id, events

    yield from coauthor_samples(sessions())


READERS: dict[str, Callable[[dict, Path], Iterator[Sample]]] = {
    "beemo": _read_beemo,
    "apt-eval": _read_apt,
    "coauthor": _read_coauthor,
    "govinfo-gao-2008": _read_gao,
    "wi-locness": _read_wi,
}


def iter_samples(corpus_id: str, internal_dir_path: str | Path | None = None,
                 registry: dict[str, dict] | None = None) -> Iterator[Sample]:
    """Verify checksums first, then yield samples for ``corpus_id``."""
    registry = registry if registry is not None else load_registry()
    if corpus_id not in registry:
        raise CorpusError(f"unknown corpus {corpus_id!r}")
    entry = registry[corpus_id]
    internal = internal_dir(internal_dir_path)
    if corpus_id == OWNER_CORPUS:
        yield from _read_owner(entry, internal if internal.is_dir() else None)
        return
    if not internal.is_dir():
        raise CorpusError(f"internal corpus directory not found: {internal}")
    verify_corpus(entry, internal)
    reader = READERS.get(corpus_id)
    if reader is None:
        raise CorpusError(f"no reader registered for {corpus_id}")
    yield from reader(entry, internal)


# ---------------------------------------------------------------- guard primitives
#
# Memory and CPU are bounded: digests are 8-byte SHA-256 prefixes, the corpus index is
# 256 on-disk buckets merged into one sorted file that is searched through mmap with
# bisect, and each corpus is read once per run. Nothing holds the whole archive's
# shingles in RAM.

BUCKETS = 256
RECORD = 8
CACHE_VERSION = "v2-bucketed"


def _digest_of(tokens: list[str], start: int, shingle: int) -> bytes:
    return hashlib.sha256(" ".join(tokens[start:start + shingle]).encode("utf-8")).digest()[:RECORD]


def token_list(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def shingle_digests_from_tokens(tokens: list[str], shingle: int = 12) -> set[bytes]:
    return {_digest_of(tokens, i, shingle) for i in range(len(tokens) - shingle + 1)}


def shingle_digests(text: str, shingle: int = 12) -> set[bytes]:
    return shingle_digests_from_tokens(token_list(text), shingle)


class _SortedDigests:
    """Read-only, sorted array of 8-byte records, searched by bisect over mmap."""

    def __init__(self, path: Path):
        self._file = path.open("rb")
        size = os.fstat(self._file.fileno()).st_size
        self._size = size // RECORD
        self._map = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ) if size else None

    def __len__(self) -> int:
        return self._size

    def __getitem__(self, index: int) -> bytes:
        return self._map[index * RECORD:(index + 1) * RECORD]

    def contains(self, digest: bytes) -> bool:
        position = bisect.bisect_left(self, digest)
        return position < self._size and self[position] == digest

    def close(self) -> None:
        if self._map is not None:
            self._map.close()
        self._file.close()


def _index_key(entry: dict, internal: Path, corpus_id: str, shingle: int) -> str:
    sums = (internal / entry["checksums"]).read_bytes()
    return hashlib.sha256(sums + f"|{corpus_id}|{shingle}|{CACHE_VERSION}".encode()).hexdigest()


def _build_index(corpus_id: str, shingle: int, internal: Path, registry: dict[str, dict],
                 cache: Path) -> None:
    """Stream the corpus into bucket files, then merge each bucket into the sorted cache."""
    work = cache.with_name(cache.name + ".buckets")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    handles = [(work / f"{b:03d}.bin").open("wb") for b in range(BUCKETS)]
    try:
        for sample in iter_samples(corpus_id, internal, registry):
            for digest in shingle_digests(sample.text, shingle):
                handles[digest[0]].write(digest)
    finally:
        for handle in handles:
            handle.close()
    partial = cache.with_name(cache.name + ".partial")
    with partial.open("wb") as out:
        for b in range(BUCKETS):
            data = (work / f"{b:03d}.bin").read_bytes()
            records = {data[i:i + RECORD] for i in range(0, len(data), RECORD)}
            out.write(b"".join(sorted(records)))
    shutil.rmtree(work, ignore_errors=True)
    os.replace(partial, cache)


def open_index(corpus_id: str, shingle: int = 12, internal: Path | None = None,
               registry: dict[str, dict] | None = None) -> _SortedDigests:
    """Open the cached digest index for a local corpus, building it if stale."""
    internal = internal_dir(internal)
    registry = registry if registry is not None else load_registry()
    entry = registry[corpus_id]
    cache_dir = internal / "derived" / "shingles"
    cache = cache_dir / f"{corpus_id}-{shingle}.sorted"
    stamp = cache.with_name(cache.name + ".key")
    key = _index_key(entry, internal, corpus_id, shingle)
    fresh = cache.is_file() and stamp.is_file() and stamp.read_text().strip() == key
    if not fresh:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _build_index(corpus_id, shingle, internal, registry, cache)
        stamp.write_text(key + "\n", encoding="utf-8")
    return _SortedDigests(cache)


def _hashed_id(corpus: str, sample_id: str) -> str:
    return hashlib.sha256(f"{corpus}:{sample_id}".encode("utf-8")).hexdigest()[:12]


def leaked(paths: list[Path], corpora: list[str], shingle: int = 12, *,
           internal: Path | None = None, registry: dict[str, dict] | None = None,
           ) -> list[tuple[Path, str, str]]:
    """Return ``(file, corpus, hashed sample id)`` for each corpus sample that shares a
    ``shingle``-word lowercase run with a file. Owner posts are never guarded sources.
    Each corpus is opened once and scanned once, however many files are checked."""
    registry = registry if registry is not None else load_registry()
    internal = internal_dir(internal)
    hits: list[tuple[Path, str, str]] = []
    for corpus in corpora:
        if corpus == OWNER_CORPUS or registry.get(corpus, {}).get("owner"):
            raise CorpusError("owner posts are not guarded; pass only local non-owner corpora")
        index = open_index(corpus, shingle, internal, registry)
        try:
            wanted: dict[bytes, list[Path]] = {}
            for path in paths:
                tokens = token_list(Path(path).read_bytes().decode("utf-8", errors="replace"))
                for digest in shingle_digests_from_tokens(tokens, shingle):
                    if index.contains(digest):
                        wanted.setdefault(digest, []).append(Path(path))
        finally:
            index.close()
        if not wanted:
            continue
        wanted_set = set(wanted)
        found: set[tuple[Path, str, str]] = set()
        for sample in iter_samples(corpus, internal, registry):
            matched = shingle_digests(sample.text, shingle) & wanted_set
            for digest in matched:
                for path in wanted[digest]:
                    found.add((path, corpus, _hashed_id(corpus, sample.id)))
        hits.extend(sorted(found, key=lambda h: (str(h[0]), h[2])))
    return hits


# ---------------------------------------------------------------- CLI

def _cmd_verify(args: argparse.Namespace) -> int:
    registry = load_registry(Path(args.registry))
    internal = internal_dir(args.internal_dir)
    targets = list(registry) if args.all else args.corpus
    if not targets:
        print("verify: name a corpus or pass --all", file=sys.stderr)
        return 2
    failures = 0
    for cid in targets:
        try:
            if cid == OWNER_CORPUS:
                list(_read_owner(registry[cid], internal if internal.is_dir() else None))
                print(f"OK {cid}: owner manifest and committed copies match")
            else:
                names = verify_corpus(registry[cid], internal)
                print(f"OK {cid}: {len(names)} files")
        except CorpusError as exc:
            failures += 1
            print(f"FAIL {exc}", file=sys.stderr)
    return 1 if failures else 0


def _cmd_list(args: argparse.Namespace) -> int:
    for cid, entry in load_registry(Path(args.registry)).items():
        print(f"{cid}\t{entry['root']}\t{entry['licence'][:60]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default=str(REGISTRY_PATH))
    parser.add_argument("--internal-dir", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="check SHA-256 sums of local corpora")
    verify.add_argument("corpus", nargs="*")
    verify.add_argument("--all", action="store_true")
    verify.set_defaults(func=_cmd_verify)
    listing = sub.add_parser("list", help="show registry entries")
    listing.set_defaults(func=_cmd_list)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
