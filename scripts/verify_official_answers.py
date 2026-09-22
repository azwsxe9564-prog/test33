#!/usr/bin/env python3
import json, re, sys, tempfile
from pathlib import Path

import requests
import fitz  # PyMuPDF

PAPERS = [
    ("110-1", "110030"),
    ("110-2", "110111"),
    ("111-1", "111030"),
    ("111-2", "111110"),
    ("112-1", "112030"),
    ("112-2", "112110"),
    ("113-1", "113030"),
    ("113-2", "113100"),
    ("114-1", "114030"),
    ("114-2", "114100"),
    ("115-1", "115030"),
    ("115-2", "115100"),
]

SUBJECTS = [
    "社會工作",
    "社會工作直接服務",
    "社會政策與社會立法",
    "人類行為與社會環境",
    "社會工作研究方法",
]

BASE = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?code={}&t=A"
BANK = Path("bank.json")

def norm(s):
    return re.sub(r"\\s+", " ", s.replace("\\u3000", " "))

def extract_subject(text, subject):
    # Start at the subject heading and stop before the next subject heading.
    m = re.search(r"(?:科目名稱|科目名稱：|科目名稱:)\\s*" + re.escape(subject), text)
    if not m:
        return None
    tail = text[m.start():]
    nexts = []
    for other in SUBJECTS:
        if other == subject:
            continue
        x = re.search(r"(?:科目名稱|科目名稱：|科目名稱:)\\s*" + re.escape(other), tail[10:])
        if x:
            nexts.append(x.start() + 10)
    if nexts:
        tail = tail[:min(nexts)]
    return tail[:10000]

def parse_official(text, subject):
    block = extract_subject(text, subject)
    if block is None:
        raise ValueError(f"subject not found: {subject}")
    # Correction sheets render four 10-question answer chunks.
    chunks = re.findall(r"(?<![A-Z#])[ABCD#]{10}(?![A-Z#])", block)
    if len(chunks) < 4:
        # Some PDF extraction joins punctuation into the answer row; try a looser scan.
        chunks = re.findall(r"[ABCD#]{10}", block)
    if len(chunks) < 4:
        raise ValueError(f"answer chunks not found: {subject}; found={chunks[:10]}")
    answers = "".join(chunks[:4])
    note_match = re.search(r"備註[:：]?(.{0,500})", block)
    note = note_match.group(1).strip() if note_match else ""
    return answers, note

def accepted_from_note(note, number, answer_char):
    # A question marked # is handled from the correction note.
    if "#" not in note and answer_char != "#":
        return {answer_char}
    n = str(number)
    # Notes can say "第7題一律給分", "第22題答Ｃ或Ｄ或CD者均給分", etc.
    if ("一律給分" in note or "均給分" in note and ("或" not in note or "未作答者" in note)):
        # If the note specifically names this question, all options are accepted.
        if re.search(rf"第?0*{n}題[^。；;]*一律給分", note) or re.search(rf"第?0*{n}題[^。；;]*均給分", note):
            if "未作答者不給分" in note:
                return {c for c in "ABCD"}
            return set("ABCD")
    m = re.search(rf"第?0*{n}題[^。；;]*?答([Ａ-ＤA-D](?:或([Ａ-ＤA-D]))?)(?:或([Ａ-ＤA-D]{{2,4}}))?者均給分", note)
    if m:
        raw = "".join(g or "" for g in m.groups())
        trans = str.maketrans("ＡＢＣＤ", "ABCD")
        return set(raw.translate(trans))
    m = re.search(rf"第?0*{n}題[^。；;]*?答([Ａ-ＤA-D])給分", note)
    if m:
        return {m.group(1).translate(str.maketrans("ＡＢＣＤ", "ABCD"))}
    # If a # appears but we cannot decode the note, leave it unresolved.
    return None

def main():
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    questions = bank["questions"]
    by = {}
    for q in questions:
        by[(f'{q["year"]}-{q.get("session","")}', q["subject"], q["number"])] = q

    report = {
        "checked_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "official_source": "考選部測驗式試題標準答案更正清冊",
        "papers": [],
        "mismatches": [],
        "unresolved": [],
        "totals": {"papers": 0, "subjects": 0, "questions": 0, "mismatches": 0, "unresolved": 0},
    }

    with tempfile.TemporaryDirectory() as td:
        for paper, code in PAPERS:
            url = BASE.format(code)
            pdf = Path(td) / f"{code}.pdf"
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            pdf.write_bytes(r.content)
            doc = fitz.open(pdf)
            text = "\n".join(page.get_text("text") for page in doc)
            p = {"paper": paper, "code": code, "url": url, "subjects": []}
            for subject in SUBJECTS:
                try:
                    official, note = parse_official(text, subject)
                except Exception as e:
                    p["subjects"].append({"subject": subject, "status": "parse_error", "error": str(e)})
                    continue
                s = {"subject": subject, "status": "checked", "official": official, "note": note, "mismatches": [], "unresolved": []}
                for i, ch in enumerate(official, 1):
                    q = by.get((paper, subject, i))
                    if q is None:
                        s["unresolved"].append({"number": i, "reason": "question missing from bank"})
                        continue
                    report["totals"]["questions"] += 1
                    bank_ans = "ABCD"[q["answer"]]
                    accepted = accepted_from_note(note, i, ch)
                    if ch == "#":
                        if accepted is None:
                            s["unresolved"].append({"number": i, "reason": "official correction marker # but note could not be decoded"})
                            report["unresolved"].append({"paper": paper, "subject": subject, "number": i, "note": note})
                            continue
                        bank_ok = bank_ans in accepted
                    else:
                        bank_ok = bank_ans == ch
                        accepted = {ch}
                    if not bank_ok:
                        item = {
                            "paper": paper, "subject": subject, "number": i,
                            "bank_answer": bank_ans, "official_answer": ch,
                            "accepted_answers": sorted(accepted) if accepted else None,
                            "note": note,
                            "id": q.get("id"),
                        }
                        s["mismatches"].append(item)
                        report["mismatches"].append(item)
                p["subjects"].append(s)
            report["papers"].append(p)

    report["totals"]["papers"] = len(PAPERS)
    report["totals"]["subjects"] = len(PAPERS) * len(SUBJECTS)
    report["totals"]["mismatches"] = len(report["mismatches"])
    report["totals"]["unresolved"] = len(report["unresolved"])
    Path("official_answer_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["totals"], ensure_ascii=False))
    for x in report["mismatches"][:100]:
        print(f'MISMATCH {x["paper"]} | {x["subject"]} | #{x["number"]}: bank={x["bank_answer"]} official={x["official_answer"]} accepted={x["accepted_answers"]}')
    for x in report["unresolved"][:50]:
        print(f'UNRESOLVED {x["paper"]} | {x["subject"]} | #{x["number"]}: {x["note"]}')
    # Do not fail merely because mismatches exist: the report is the input to a deliberate correction commit.
    if report["totals"]["unresolved"]:
        sys.exit(2)

if __name__ == "__main__":
    main()
