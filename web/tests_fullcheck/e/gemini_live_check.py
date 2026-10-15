"""Gemini 실서버 재확인(합성 영상 8편 x 2회). 키는 더미 문자열(프록시가 교체). 소스 비수정."""
import json, sys, time, hashlib, urllib.request, urllib.error
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "web/backend")]
from youtube_title.config import load_settings
from youtube_title.banned_terms import load_dictionary
from youtube_title.candidates import CandidateFile, Candidate
from youtube_title.validator import validate_file, match_ratio
from ytweb.ai.gemini import GeminiSuggester, ENDPOINT, DEFAULT_MODEL
from ytweb.ai.base import VideoBrief, TitleSuggestionError
from ytweb.ai.guard import sanitize_drafts, build_summary, _dedupe_key
from ytweb.domain.common import Env

OUT = ROOT / ".harness-tmp/results/e-gemini"
s = load_settings(ROOT)
env = Env(s, load_dictionary(s.config_dir / "banned_terms.yaml"), ROOT / "web/secrets")
V = [
 ("S01","[시니어 필수] 스마트폰 사진 정리","life","스마트폰에 쌓인 사진을 정리하는 방법을 알려드립니다.\n00:00 인사\n01:10 중복 사진 지우기\n03:40 앨범 만들기\n06:20 클라우드에 백업하기\n"),
 ("S02","무릎이 시큰거릴 때 집에서 하는 운동","health","무릎이 시큰거릴 때 의자에 앉아서 할 수 있는 가벼운 스트레칭을 소개합니다. 통증이 심하면 병원에서 진료를 받으세요.\n00:00 시작\n00:50 의자 다리 펴기\n02:30 발목 돌리기\n04:10 주의할 점\n"),
 ("S03","연금 수령 시기 정리","finance","국민연금을 언제부터 받을지 고민하는 분들을 위해 조기 수령과 연기 수령의 차이를 설명합니다. 개인 상황에 따라 다르므로 국민연금공단에 문의하세요."),
 ("S04","장보기 영수증 모으는 법","life","마트 영수증을 한곳에 모아 한 달 생활비를 확인하는 간단한 방법입니다.\n00:00 소개\n02:00 영수증 사진 찍기\n05:15 월말 합계 내기\n"),
 ("S05","혈압 재는 올바른 자세","health","집에서 혈압을 잴 때 앉는 자세, 팔 높이, 측정 시간을 차례대로 보여드립니다. 혈압약을 드시는 분은 의사와 상의하세요.\n00:00 소개\n01:20 앉는 자세\n03:00 팔 높이 맞추기\n05:30 기록하는 법\n"),
 ("S06","은행 앱으로 송금하는 방법","finance","은행 앱에서 가족에게 돈을 보내는 방법을 천천히 따라 해 봅니다. 보이스피싱을 조심하는 방법도 함께 설명합니다.\n00:00 인사\n01:40 앱 설치\n04:00 계좌 선택\n07:10 송금 확인 문자\n"),
 ("S07","제주도 2박3일 버스 여행","life","제주공항에서 출발해 버스로 돌아보는 2박 3일 여행 코스입니다. 버스 노선과 시간표, 점심 식당을 소개합니다."),
 ("S08","카카오톡 글자 크게 보기","life","카카오톡 글자 크기를 키우고 화면을 보기 편하게 바꾸는 방법입니다.\n00:00 시작\n00:45 설정 열기\n02:10 글자 크기 조절\n03:30 배경 바꾸기\n"),
]
sug = GeminiSuggester("dummy-not-a-key")
recs = []; errs = Counter(); rows = []
for vid, title, topic, desc in V:
    brief = VideoBrief(vid, title, build_summary(desc)); avoid = []; firsts = []
    for call in (1, 2):
        g = sug.with_avoid(set(avoid)) if avoid else sug
        payload = {"현재_제목": brief.title, "영상_설명": brief.summary, "후보_수": 3, "이미_만든_제목": list(g._avoid)}
        (OUT / f"{vid}-{call}-request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
        t0 = time.time(); err = None; drafts = []
        # 응답 원문 확보를 위해 같은 호출을 urllib 로 한 번만 한다(어댑터의 suggest 와 동일 본문: 어댑터 내부 함수 재사용 불가 -> 어댑터를 감싼다)
        orig = urllib.request.urlopen
        raw_box = {}
        def spy(req, timeout=None, _o=orig):
            try:
                r = _o(req, timeout=timeout)
                body = r.read(); raw_box["body"] = body.decode("utf-8", "replace"); raw_box["code"] = r.status
                import io
                class R(io.BytesIO):
                    status = r.status
                    def __enter__(s2): return s2
                    def __exit__(s2, *a): return False
                return R(body)
            except urllib.error.HTTPError as e:
                raw_box["code"] = e.code; raw_box["body"] = e.read().decode("utf-8", "replace"); raise
        urllib.request.urlopen = spy
        try:
            drafts = g.suggest(brief, count=3, tone="plain")
        except TitleSuggestionError as e:
            err = str(e)
        finally:
            urllib.request.urlopen = orig
        dt = time.time() - t0
        (OUT / f"{vid}-{call}-response.json").write_text(json.dumps({"http": raw_box.get("code"), "body": raw_box.get("body")}, ensure_ascii=False)[:20000], "utf-8")
        if err: errs[(raw_box.get("code"), err[:40])] += 1
        guarded = sanitize_drafts(drafts, max_count=3)
        for d in guarded.drafts:
            cf = CandidateFile(vid, title, d.topic, desc, "web", None, (Candidate(d.title, d.evidence),), hashlib.sha256(d.title.encode()).hexdigest(), vid + ".json")
            fr = validate_file(cf, env.dictionary, env.policy)
            r = fr.results[0]
            rows.append(dict(vid=vid, topic=topic, call=call, title=d.title, len=r.length, result=r.result, codes=[f.code for f in r.findings],
                             ratio=r.match_ratio, ev=r.evidence_found, dup=_dedupe_key(d.title) in {_dedupe_key(x) for x in firsts} if call == 2 else False))
        if call == 1: firsts = [d.title for d in guarded.drafts]
        avoid += [d.title for d in guarded.drafts]
        recs.append(dict(vid=vid, call=call, sec=round(dt, 2), http=raw_box.get("code"), err=err, n_raw=len(drafts), n_ok=len(guarded.drafts), dropped=[list(x) for x in guarded.dropped]))
        print(vid, call, round(dt, 1), raw_box.get("code"), err, len(drafts), flush=True)
json.dump({"calls": recs, "rows": rows, "model": sug.model}, open(OUT / "summary.json", "w"), ensure_ascii=False, indent=1)
n = len(rows)
if n:
    print("candidates", n, "len45-60", sum(45 <= r["len"] <= 60 for r in rows), "pass", sum(r["result"]=="pass" for r in rows), "warn", sum(r["result"]=="warn" for r in rows), "block", sum(r["result"]=="block" for r in rows), "evidence", sum(r["ev"] for r in rows))
    print("codes", Counter(c for r in rows for c in r["codes"]))
    print("dup2", sum(r["dup"] for r in rows if r["call"]==2), "of", sum(r["call"]==2 for r in rows))
    print("per-video approvable", {v: sum(r["result"]!="block" for r in rows if r["vid"]==v) for v,*_ in V})
    print("sec", sorted(c["sec"] for c in recs))
