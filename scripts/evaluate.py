#!/usr/bin/env python3
"""Reproducible regression/evaluation runner. Unknown labels never become authorship truth."""
import argparse
import hashlib
import json
import math
import pathlib
import subprocess
import time
from collections import Counter, defaultdict

def ratio(numerator, denominator):
    return numerator / denominator if denominator else None

def wilson(hits, count):
    if not count:
        return None
    z = 1.96
    p = hits / count
    center = (p + z*z/(2*count))/(1+z*z/count)
    radius = z*math.sqrt(p*(1-p)/count+z*z/(4*count*count))/(1+z*z/count)
    return [max(0, center-radius), min(1, center+radius)]

def metrics(rows):
    labeled = [r for r in rows if r['label'] in ('human', 'generated')]
    covered = [r for r in labeled if r['complete'] and r['verdict'] != 'inconclusive']
    counts = Counter(('tp' if r['label']=='generated' else 'fp') if r['verdict']=='flagged' else ('fn' if r['label']=='generated' else 'tn') for r in covered)
    tp, fp, fn, tn = [counts[k] for k in ('tp','fp','fn','tn')]
    precision, recall = ratio(tp,tp+fp), ratio(tp,tp+fn)
    return {'labeled_count':len(labeled),'covered_count':len(covered),'coverage':ratio(len(covered),len(labeled)),
            'abstentions':sum(r['complete'] and r['verdict']=='inconclusive' for r in labeled),
            'operational_failures':sum(not r['complete'] for r in rows),
            'confusion_matrix':dict(zip(('tp','fp','fn','tn'),(tp,fp,fn,tn))),
            'precision':precision,'recall':recall,'f1':ratio(2*tp,2*tp+fp+fn),'false_positive_rate':ratio(fp,fp+tn),
            'false_positive_rate_wilson_95':wilson(fp,fp+tn),'auc':None,
            'auc_reason':'No calibrated or defined continuous ensemble score; discrete verdicts are not an AUC score.'}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--binary',default='target/debug/nobotrs')
    parser.add_argument('--manifest',required=True,type=pathlib.Path)
    parser.add_argument('--output',required=True,type=pathlib.Path)
    parser.add_argument('--check',type=pathlib.Path)
    parser.add_argument('--config',type=pathlib.Path)
    parser.add_argument('--split',choices=['regression','development','validation','independent-test'],default='regression')
    parser.add_argument('--sweep-quorum',type=int,nargs='+')
    parser.add_argument('--release-access-record',type=pathlib.Path)
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text())
    if manifest['schema_version']!='1.0.0':raise ValueError('unsupported corpus schema')
    source_splits=defaultdict(set)
    normalized_splits=defaultdict(set)
    ids=set()
    for sample in manifest['samples']:
        if sample['id'] in ids:raise ValueError('duplicate sample identity')
        ids.add(sample['id'])
        if not sample.get('provenance') or not sample.get('license'):raise ValueError('provenance/license required')
        source_splits[sample['source_group']].add(sample['split'])
        text=(args.manifest.parent/sample['file']).read_text()
        normalized=' '.join(text.lower().split())
        normalized_splits[hashlib.sha256(normalized.encode()).hexdigest()].add(sample['split'])
    if any(len(s)>1 for s in list(source_splits.values())+list(normalized_splits.values())):raise ValueError('source/duplicate leakage across splits')
    if args.split=='independent-test':
        if args.sweep_quorum or not args.config or not args.release_access_record:raise ValueError('independent test requires frozen config and an access record, and forbids sweeps')
        record=json.loads(args.release_access_record.read_text())
        digest=hashlib.sha256(args.config.read_bytes()).hexdigest()
        if record.get('configuration_sha256')!=digest or record.get('status')!='frozen-unopened':raise ValueError('test set already accessed or configuration not frozen; refresh required')
        record.update(status='accessed',note='Any result-informed revision requires fresh independent data.')
        args.release_access_record.write_text(json.dumps(record,indent=2)+'\n')
    rows=[]
    for sample in manifest['samples']:
        if sample['split']!=args.split:continue
        path=args.manifest.parent/sample['file']
        command=[args.binary,'detect',str(path),'--format','json']
        if args.config:command+=['--config',str(args.config)]
        start=time.perf_counter()
        process=subprocess.run(command,capture_output=True,check=False,timeout=60)
        elapsed=time.perf_counter()-start
        report=json.loads(process.stdout)
        if 'verdict' not in report:raise ValueError(f"{sample['id']}: no analysis report: {process.stderr.decode()}")
        row={'id':sample['id'],'label':sample.get('label'),'slice':sample['slice'],'verdict':report['verdict'],'complete':report['complete'],'status':process.returncode,'runtime_seconds':elapsed,'families':report['families'],'metrics':{b['backend']:b['outcome'].get('details',{}).get('metrics',{}) for b in report['backends']}}
        expected=sample.get('expected')
        if expected and (row['verdict']!=expected['verdict'] or row['status']!=expected['status']):raise ValueError(f"regression {sample['id']}: {row['verdict']}/{row['status']} != {expected}")
        rows.append(row)
    if not rows:raise ValueError('selected split has no samples; no performance claim can be produced')
    stable=[{k:r[k] for k in ('id','label','verdict','complete','status')} for r in rows]
    if args.check and json.loads(args.check.read_text())['regression_results']!=stable:raise ValueError('CI regression baseline changed')
    output={'schema_version':'1.0.0','corpus_version':manifest['corpus_version'],'split':args.split,'purpose':manifest['purpose'],'metrics':metrics(rows),'slice_metrics':{s:metrics([r for r in rows if r['slice']==s]) for s in sorted({r['slice'] for r in rows})},'regression_results':stable,'raw_feature_cache':rows,'runtime_seconds':sum(r['runtime_seconds'] for r in rows)}
    if args.sweep_quorum:
        if args.split not in ('development','validation'):raise ValueError('sweeps are development/validation selection, not regression or independent-test evidence')
        sweeps=[]
        for quorum in args.sweep_quorum:
            if not 1<=quorum<=3:raise ValueError('quorum must be 1..3')
            selected=[]
            for r in rows:
                r=dict(r)
                votes=r['families']
                r['verdict']='inconclusive' if len(votes)<quorum else 'flagged' if sum(v['vote']!='none' for v in votes)>=quorum else 'clean'
                selected.append(r)
            sweeps.append({'quorum':quorum,'metrics':metrics(selected),'use':'selection evidence only'})
        output['sweeps']=sweeps
    args.output.write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')

if __name__=='__main__':main()
