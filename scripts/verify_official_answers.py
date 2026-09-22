#!/usr/bin/env python3
import json,re,sys
from pathlib import Path
import requests,fitz

PAPERS=[
('110-1','110030','105','040'),('110-2','110111','105','040'),
('111-1','111030','105','040'),('111-2','111110','105','040'),
('112-1','112030','103','030'),('112-2','112110','103','030'),
('113-1','113030','103','030'),('113-2','113100','103','030'),
('114-1','114030','103','030'),('114-2','114100','103','030'),
('115-1','115030','103','030'),('115-2','115100','103','030')]
SUBJECTS=[('社會工作',1),('社會工作直接服務',2),('社會政策與社會立法',4),('人類行為與社會環境',5),('社會工作研究方法',6)]
S115=[('社會工作',1),('社會工作直接服務',2),('社會政策與社會立法',3),('人類行為與社會環境',4),('社會工作研究方法',5)]

def parse_pdf(data):
    doc=fitz.open(stream=data,filetype='pdf')
    page=doc[0]
    words=page.get_text('words')
    qs=[]; ans=[]
    for w in words:
        x0,y0,x1,y1,t,*_=w
        m=re.fullmatch(r'第(\d+)題',t)
        if m and int(m.group(1))<=40: qs.append((int(m.group(1)),x0,y0,x1,y1))
        if re.fullmatch(r'[ABCD#]',t): ans.append((t,x0,y0,x1,y1))
    out={}
    for n,x0,y0,x1,y1 in qs:
        xc=(x0+x1)/2
        cand=[]
        for a,ax0,ay0,ax1,ay1 in ans:
            ax=(ax0+ax1)/2; dy=ay0-y1; dx=abs(ax-xc)
            if dy>=0 and dy<100 and dx<35: cand.append((dy+dx*.2,a))
        if cand: out[n]=min(cand)[1]
    if len(out)!=40:
        out={}
        for n,x0,y0,x1,y1 in qs:
            xc=(x0+x1)/2; cand=[]
            for a,ax0,ay0,ax1,ay1 in ans:
                dy=ay0-y1; dx=abs((ax0+ax1)/2-xc)
                if 0<=dy<120: cand.append((dy+dx*.05,a))
            if cand: out[n]=min(cand)[1]
    if len(out)!=40: raise ValueError(f'parsed {len(out)}/40 questions; q={sorted(out)}')
    return ''.join(out[i] for i in range(1,41))

def main():
    bank=json.loads(Path('bank.json').read_text(encoding='utf-8'))
    by={(f'{q["year"]}-{q.get("session","")}',q['subject'],q['number']):q for q in bank['questions']}
    report={'papers':[],'mismatches':[],'unresolved':[]}
    S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0'
    for paper,code,c,sbase in PAPERS:
        subs=S115 if paper.startswith('115-') else SUBJECTS
        p={'paper':paper,'subjects':[]}
        for subject,idx in subs:
            url=f'https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?c={c}&code={code}&q=1&s={sbase}{idx}&t=S'
            try:
                r=S.get(url,timeout=60); r.raise_for_status(); official=parse_pdf(r.content)
            except Exception as e:
                p['subjects'].append({'subject':subject,'status':'parse_error','url':url,'error':str(e)}); continue
            ss={'subject':subject,'status':'checked','url':url,'official':official,'mismatches':[]}
            for i,ch in enumerate(official,1):
                q=by.get((paper,subject,i))
                if not q: continue
                if ch=='#':
                    report['unresolved'].append({'paper':paper,'subject':subject,'number':i,'reason':'official correction marker #; correction rule required'})
                    continue
                accepted={'ABCD'[x] for x in q.get('accepted_answers',[q['answer']])}
                if ch not in accepted:
                    item={'paper':paper,'subject':subject,'number':i,'bank_answer':'ABCD'[q['answer']],'accepted_answers':sorted(accepted),'official_answer':ch,'id':q.get('id'),'source_url':url}
                    ss['mismatches'].append(item); report['mismatches'].append(item)
            p['subjects'].append(ss)
        report['papers'].append(p)
    report['totals']={'papers':12,'subjects':60,'questions':2400,'mismatches':len(report['mismatches']),'unresolved':len(report['unresolved']),'parse_errors':sum(1 for p in report['papers'] for s in p['subjects'] if s.get('status')=='parse_error')}
    if '--fix' in sys.argv and not report['totals']['parse_errors'] and not report['unresolved']:
        from datetime import datetime,timezone
        now=datetime.now(timezone.utc).isoformat()
        for item in report['mismatches']:
            q=by[(item['paper'],item['subject'],item['number'])]
            old_ans='ABCD'[q['answer']]; new_ans=item['official_answer']
            q['answer']='ABCD'.index(new_ans)
            q['accepted_answers']=[q['answer']]
            q['corrected']=True
            q['answer_source']='考選部官方標準答案（逐題驗證）'
            q['answer_verified_at']=now
            log=q.get('answer_correction_log',[])
            if not isinstance(log,list): log=[]
            log.append({'verified_at':now,'source':item['source_url'],'previous_answer':old_ans,'corrected_answer':new_ans})
            q['answer_correction_log']=log
        Path('bank.json').write_text(json.dumps(bank,ensure_ascii=False,indent=2),encoding='utf-8')
        print('APPLIED_CORRECTIONS',len(report['mismatches']))
        return
    Path('official_answer_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['totals'],ensure_ascii=False))
    for x in report['mismatches'][:200]: print('MISMATCH',json.dumps(x,ensure_ascii=False))
    for x in report['unresolved'][:100]: print('UNRESOLVED',json.dumps(x,ensure_ascii=False))
    if report['totals']['parse_errors'] or report['unresolved'] or report['mismatches']: sys.exit(1)
if __name__=='__main__': main()
