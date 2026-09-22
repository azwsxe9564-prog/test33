#!/usr/bin/env python3
import json,re,sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup

PAPERS=[
("110-1","110030","105","040"),("110-2","110111","105","040"),
("111-1","111030","105","040"),("111-2","111110","105","040"),
("112-1","112030","103","030"),("112-2","112110","103","030"),
("113-1","113030","103","030"),("113-2","113100","103","030"),
("114-1","114030","103","030"),("114-2","114100","103","030"),
("115-1","115030","103","030"),("115-2","115100","103","030")]
SUBJECTS=[("社會工作","110"),("社會工作直接服務","210"),("社會政策與社會立法","310"),("人類行為與社會環境","410"),("社會工作研究方法","510")]
S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0 official-answer-verifier"

def parse(html,subject):
    soup=BeautifulSoup(html,"html.parser"); text=soup.get_text(" ",strip=True)
    if subject not in text: raise ValueError("subject not found")
    # Official HTML answer pages contain 10 tables, each with question headers and answer row.
    out={}
    for table in soup.find_all("table"):
        rows=table.find_all("tr")
        if len(rows)<2: continue
        heads=[c.get_text(" ",strip=True) for c in rows[0].find_all(["th","td"])]
        vals=[c.get_text(" ",strip=True) for c in rows[1].find_all(["th","td"])]
        if not any("第1題" in h for h in heads): continue
        for h,v in zip(heads,vals):
            m=re.search(r"第(\d+)題",h)
            if m and v in "ABCD": out[int(m.group(1))]=v
    if len(out)<40:
        pairs=re.findall(r"第(\d+)題\s*([ABCD])",text)
        for n,a in pairs: out[int(n)]=a
    if len(out)<40: raise ValueError(f"only {len(out)} answers parsed")
    return "".join(out[i] for i in range(1,41))

def main():
    bank=json.loads(Path("bank.json").read_text(encoding="utf-8"))
    by={(f'{q["year"]}-{q.get("session","")}',q["subject"],q["number"]):q for q in bank["questions"]}
    report={"checked_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),"source":"考選部「測驗式試題標準答案」","papers":[],"mismatches":[],"parse_errors":[]}
    for paper,code,c,sbase in PAPERS:
        p={"paper":paper,"code":code,"subjects":[]}
        for subject,scode in SUBJECTS:
            idx=int(scode)//100
            s=f"{sbase}{idx}"
            url=f"https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?c={c}&code={code}&q=1&s={s}&t=S"
            try:
                r=S.get(url,timeout=60); r.raise_for_status()
                official=parse(r.text,subject)
            except Exception as e:
                err={"paper":paper,"subject":subject,"url":url,"error":str(e)}
                p["subjects"].append({"subject":subject,"status":"parse_error",**err}); report["parse_errors"].append(err); continue
            ss={"subject":subject,"status":"checked","url":url,"official":official,"mismatches":[]}
            for i,letter in enumerate(official,1):
                q=by.get((paper,subject,i))
                if not q:
                    item={"paper":paper,"subject":subject,"number":i,"reason":"missing question"}
                else:
                    accepted={"ABCD"[x] for x in q.get("accepted_answers",[q["answer"]])}
                    if letter in accepted: continue
                    item={"paper":paper,"subject":subject,"number":i,"bank_answer":"ABCD"[q["answer"]],"accepted_answers":sorted(accepted),"official_answer":letter,"id":q.get("id")}
                ss["mismatches"].append(item); report["mismatches"].append(item)
            p["subjects"].append(ss)
        report["papers"].append(p)
    report["totals"]={"papers":len(PAPERS),"subjects":len(PAPERS)*len(SUBJECTS),"questions":len(bank["questions"]),"mismatches":len(report["mismatches"]),"parse_errors":len(report["parse_errors"])}
    Path("official_answer_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report["totals"],ensure_ascii=False))
    for x in report["mismatches"][:200]: print("MISMATCH",json.dumps(x,ensure_ascii=False))
    if report["parse_errors"] or report["mismatches"]: sys.exit(1)

if __name__=="__main__": main()
