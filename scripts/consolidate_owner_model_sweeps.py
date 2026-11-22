#!/usr/bin/env python3
"""Join immutable single-model attempts without claiming a concurrent model run."""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path

MODELS=('desklib','conpara','detectorscope')

def read(path):
    return json.loads(path.read_text())

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def state(backend):
    if backend is None:
        return 'missing'
    outcome=backend['outcome']; status=outcome['status']
    if status=='abstained':
        return 'skipped'
    if status=='scored':
        return 'scored_full' if outcome['details'].get('model_evidence',{}).get('token_coverage')==1 else 'missing_full_evidence'
    return status

def latest(directory,prefix):
    paths=list(directory.glob(prefix+'-attempt-*.json'))
    return max(paths,key=lambda p:int(p.stem.rsplit('-',1)[1])) if paths else None

def consolidate(original,recovery,manifest_path,out):
    manifest=read(manifest_path); initial=read(original/'run.json'); out.mkdir(parents=True,exist_ok=True)
    initial_entries={d['file']:d for d in initial['documents']}
    counts={m:Counter({s:0 for s in ('scored_full','skipped','failed','incomplete','missing','missing_full_evidence')}) for m in MODELS}
    origins={m:Counter() for m in MODELS};documents=[]; unresolved=[]
    for post in sorted(manifest['posts'],key=lambda p:p['file']):
        if post['file'] in initial_entries and (initial_entries[post['file']]['input_sha256'] != post['sha256'] or initial_entries[post['file']]['label'] != post['label']):
            raise ValueError('initial checkpoint source identity mismatch')
        stem=Path(post['file']).stem; old_path=original/stem/'report.json'; old=read(old_path) if old_path.is_file() else None
        selected=[];sources={};template=copy.deepcopy(old) if old else None;review_path=original/stem/'review.json';review=read(review_path) if review_path.is_file() else None
        for model in MODELS:
            directory=recovery/model/stem; candidate=directory/'backend.json'; old_backend=next((b for b in (old or {}).get('backends',[]) if b['backend']==model),None)
            entry_path=directory/'entry.json'
            if candidate.is_file() and (not entry_path.is_file() or read(entry_path)['input_sha256'] != post['sha256']):
                raise ValueError('recovery backend has no matching input identity checkpoint')
            backend=read(candidate) if candidate.is_file() else old_backend
            status=state(backend); origin='original_reused' if backend is not None and backend==old_backend and status in ('scored_full','skipped') else 'recovery_attempt' if candidate.is_file() else 'original_failure' if old_backend else 'unprocessed'
            source=old_path if origin in ('original_reused','original_failure') else latest(directory,'backend') or candidate
            sources[model]={'path':str(source),'sha256':digest(source) if source.is_file() else None,'origin':origin,'status':status}
            counts[model][status]+=1;origins[model][origin]+=1
            if backend is None:
                backend={'backend':model,'family':'Model','outcome':{'status':'failed','details':{'ModelLoadFailed':'no completed attempt available'}}};unresolved.append({'file':post['file'],'backend':model})
            selected.append(backend)
            report_candidate=latest(directory,'report')
            if template is None and report_candidate:
                template=read(report_candidate)
            review_candidate=latest(directory,'review')
            if review is None and review_candidate:
                review=read(review_candidate)
        if template is None:
            unresolved.append({'file':post['file'],'backend':'core_template'})
            documents.append({'file':post['file'],'input_sha256':post['sha256'],'label':post['label'],'confidence':post['confidence'],'attempted':False,'backends':{m:sources[m]['status'] for m in MODELS},'sources':sources})
            continue
        core=[b for b in template['backends'] if b['backend'] not in MODELS]
        complete=all(b['outcome']['status'] not in ('failed','incomplete') for b in core+selected)
        template['backends']=core+selected;template['settings']['models']=list(MODELS);template['settings']['model_coverage']='full';template['complete']=complete
        template['warnings']=[w for w in template.get('warnings',[]) if w['family']!='Model']
        template['incomplete_reasons']=[f"{b['backend']}: {b['outcome']['status']}" for b in core+selected if b['outcome']['status'] in ('failed','incomplete')]
        template['_recovery']={'schema_version':'owner-model-consolidated-v1','single_concurrent_run':False,'model_sources':sources,'note':'Scores join separate immutable attempts; original failure and runtime/thread provenance remain in original and recovery records.'}
        target=out/stem;target.mkdir(exist_ok=True)
        (target/'report.json').write_text(json.dumps(template,indent=2,allow_nan=False)+'\n')
        if review:
            review['complete']=complete;review['incomplete_reasons']=template['incomplete_reasons'];review['checks']=[c for c in review['checks'] if c['backend'] not in MODELS]+[{'backend':m,'status':'completed' if sources[m]['status']=='scored_full' else 'skipped' if sources[m]['status']=='skipped' else 'incomplete','reason':'See immutable per-model attempt record.'} for m in MODELS]
            review['hotspots']={'label':'Where local classifiers react most. Not a Google signal and not evidence of authorship.','ranking_policy':'within-doc-z-v1','validated':False,'reason':'Consolidated per-model sweeps; joint ranks not computed. Per-model ranks remain in immutable review-attempt files.','hotspots':[],'provenance':[]}
            review['_recovery']=template['_recovery'];(target/'review.json').write_text(json.dumps(review,indent=2,allow_nan=False)+'\n')
        documents.append({'file':post['file'],'input_sha256':post['sha256'],'label':post['label'],'confidence':post['confidence'],'attempted':True,'backends':{m:sources[m]['status'] for m in MODELS},'complete':complete,'sources':sources})
    sweep_runs={m:read(recovery/m/'run.json') if (recovery/m/'run.json').is_file() else None for m in MODELS}
    run={'schema_version':'owner-model-consolidated-v1','finished':not unresolved and all(r and r['finished'] for r in sweep_runs.values()),'planned_documents':len(manifest['posts']),'catalogued_documents':len(documents),'completed_documents':sum(d.get('attempted',False) for d in documents),'fully_resolved_documents':sum(d.get('complete',False) for d in documents),'documents':documents,'backend_status_counts':{m:dict(v) for m,v in counts.items()},'origin_counts':{m:dict(v) for m,v in origins.items()},'unresolved':unresolved,'settings':initial['settings'],'binary_sha256':None,'binary_sha256_by_sweep':{m:r['binary_sha256'] if r else None for m,r in sweep_runs.items()},'git_revision':'multiple immutable attempts; see per-model run metadata','corpus_manifest_sha256':digest(manifest_path),'elapsed_ms':initial.get('elapsed_ms',0)+sum(r.get('elapsed_ms',0) for r in sweep_runs.values() if r),'original_run':{'path':str(original/'run.json'),'sha256':digest(original/'run.json'),'status_counts':initial['backend_status_counts']},'single_concurrent_run':False,'external':'none','validated_editorial_utility':False}
    (out/'run.json').write_text(json.dumps(run,indent=2,allow_nan=False)+'\n')
    return run


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--original',type=Path,required=True);parser.add_argument('--recovery',type=Path,required=True);parser.add_argument('--manifest',type=Path,default=Path('evaluation/corpora/owner-posts-v1/manifest.json'));parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();run=consolidate(args.original,args.recovery,args.manifest,args.out)
    print(json.dumps({'finished':run['finished'],'counts':run['backend_status_counts'],'origins':run['origin_counts'],'unresolved':len(run['unresolved'])},indent=2))
    return 0 if run['finished'] else 2

if __name__=='__main__':
    raise SystemExit(main())
