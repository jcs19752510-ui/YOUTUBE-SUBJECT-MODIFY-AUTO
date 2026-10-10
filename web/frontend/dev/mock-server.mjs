// 개발용 모의 서버: WEB_DESIGN §3 계약을 흉내 낸다(의존성 없음). 실제 서버가 아니며 데이터는 메모리에만 있다.
// 사용: npm run mock  (기본 127.0.0.1:8081)  /  npm run dev:mock (모의 서버 + Vite 개발 서버)
// 환경변수: MOCK_PORT, MOCK_PIN(설정하면 PIN 필요), MOCK_EMPTY=1(영상 0개로 시작), MOCK_STATIC=dist(빌드 결과 서빙)
import http from 'node:http';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const DAY = 86400000;
const iso = (d) => new Date(d).toISOString();
const ymd = (d, tz) => new Intl.DateTimeFormat('en-CA', { timeZone: tz }).format(new Date(d));
const kstDate = (d) => ymd(d, 'Asia/Seoul');
const ptDate = (d) => ymd(d, 'America/Los_Angeles');
const addDays = (dateStr, n) => {
  const t = new Date(`${dateStr}T00:00:00Z`).getTime() + n * DAY;
  return new Date(t).toISOString().slice(0, 10);
};

class Problem extends Error {
  constructor(status, code, title, detail = '', hint = '') {
    super(title);
    Object.assign(this, { status, code, title, detail, hint });
  }
}

// ---------- 상태 ----------
export function createState(opts = {}) {
  const st = {
    pin: opts.pin ?? null,
    sessions: new Map(),
    videos: [],
    suggestions: [],
    batches: [],
    changes: [],
    audit: [],
    jobs: new Map(),
    idem: new Map(),
    settings: { daily_apply_cap: 10, suggestions_per_video: 3, tone: ['친근하게'] },
    seq: { suggestion: 1, batch: 1, item: 1, change: 1, audit: 1 },
    quotaUsed: 1250,
    now: () => Date.now(),
  };
  if (!opts.empty) seedVideos(st);
  return st;
}

const TOPICS = ['생활', '요리', '건강', '금융', '여행', '정원', '취미', '뉴스'];
const HEAD = [
  '겨울철 전기요금 줄이는 방법',
  '냉장고 정리 이렇게 하세요',
  '무릎 건강 지키는 걷기 습관',
  '노후 자금 점검하는 순서',
  '봄 여행 코스 추천',
  '베란다 텃밭 가꾸기',
  '트로트 명곡 모음',
  '오늘의 주요 소식',
  '김치찌개 맛있게 끓이는 법',
  '스마트폰 사진 정리법',
];
const TAIL = ['', ' 2편', ' 완결판', ' 초보 편', ' 총정리', ' (실전)', ' 따라하기'];

function seedVideos(st) {
  const now = st.now();
  for (let i = 0; i < 200; i++) {
    const id = `demo${String(i + 1).padStart(7, '0')}`.slice(0, 11);
    const topic = TOPICS[i % TOPICS.length];
    const title = `${HEAD[i % HEAD.length]}${TAIL[Math.floor(i / HEAD.length) % TAIL.length]}`;
    const reasons = [];
    let privacy = 'public';
    if (i % 23 === 7) {
      privacy = 'private';
      reasons.push('비공개 영상');
    }
    if (i % 31 === 11) reasons.push('아동용으로 설정된 영상');
    if (i % 41 === 5) reasons.push('라이브 방송');
    st.videos.push({
      video_id: id,
      title,
      privacy_status: privacy,
      duration_sec: 120 + ((i * 97) % 1500),
      is_short: i % 9 === 4,
      excluded: reasons.length > 0,
      exclusion_reasons: reasons,
      description_excerpt: `${title}에 대한 설명입니다. 구독과 좋아요는 큰 힘이 됩니다. (데모 영상 ${i + 1})`,
      views: 800 + ((i * 7919) % 250000),
      topic,
      created: now - (400 - i) * DAY,
    });
  }
  // 이미 반영된 과거 기록 몇 건(이력·리포트 화면용)
  [3, 8, 14, 20, 26].forEach((idx, n) => {
    const v = st.videos[idx];
    if (!v || v.excluded) return;
    const at = now - (20 + n * 6) * DAY;
    const prev = v.title;
    v.title = `${prev} 한눈에 보기`;
    st.changes.push({
      id: st.seq.change++,
      video_id: v.video_id,
      change_type: 'apply',
      previous_title: prev,
      new_title: v.title,
      result: 'success',
      mode: 'demo',
      approver: '운영자',
      applied_at: iso(at),
      verified_at: iso(at + 60000),
      error_code: null,
      batch_id: null,
      created: at,
    });
  });
}

// ---------- 검증(모의) ----------
const BLOCK_WORDS = [
  ['100%', '근거 없는 100% 단정 표현'],
  ['무조건', '"무조건" 같은 단정 표현'],
  ['완치', '의료 효능을 단정하는 표현'],
];
const WARN_WORDS = [
  ['충격', '자극적인 표현("충격")'],
  ['큰일', '공포를 조장할 수 있는 표현("큰일")'],
  ['!', '느낌표 사용'],
];
export function validateTitle(title, video) {
  const reasons = [];
  let result = 'pass';
  const strict = ['건강', '금융'].includes(video.topic);
  const len = Array.from(title).length;
  if (len > 100) {
    reasons.push({
      code: 'too_long',
      severity: 'block',
      message: `제목이 100자를 넘습니다(${len}자).`,
    });
    result = 'block';
  }
  for (const [w, m] of BLOCK_WORDS) {
    if (title.includes(w)) {
      reasons.push({ code: 'banned_term', severity: 'block', message: m });
      result = 'block';
    }
  }
  for (const [w, m] of WARN_WORDS) {
    if (title.includes(w)) {
      reasons.push({
        code: 'risky_term',
        severity: strict ? 'block' : 'warn',
        message: strict ? `${m} — 건강·금융 주제는 엄격하게 차단합니다` : m,
      });
      if (strict) result = 'block';
      else if (result === 'pass') result = 'warn';
    }
  }
  const overlap =
    Array.from(video.title).filter((c) => c.trim() && title.includes(c)).length /
    Math.max(1, Array.from(video.title).filter((c) => c.trim()).length);
  if (overlap < 0.35) {
    reasons.push({
      code: 'low_match',
      severity: 'warn',
      message: '영상 내용과 제목의 일치율이 낮습니다.',
    });
    if (result === 'pass') result = 'warn';
  }
  return { result, reasons, strict, length: len, match_ratio: Math.round(overlap * 100) / 100 };
}

function makeCandidates(video, n) {
  const base = video.title.replace(/ 한눈에 보기$/, '');
  const pool = [
    `${base}, 이것만 알면 쉽습니다`,
    `${base} 5가지 핵심 정리`,
    `이거 모르면 큰일! ${base}`,
    `${base} 100% 해결하는 무조건 성공법`,
    `충격! ${base}의 진실`,
    `${base} — 초보도 따라 하는 순서`,
  ];
  const start = (video.title.length + n) % pool.length;
  return Array.from({ length: n }, (_, i) => pool[(start + i) % pool.length]);
}

// ---------- 직렬화 ----------
const suggestionDto = (st, s) => {
  const v = videoOf(st, s.video_id);
  const ver = validateTitle(s.title, v);
  return {
    id: s.id,
    video_id: s.video_id,
    title: s.title,
    evidence: s.evidence,
    source: s.source,
    topic: v.topic,
    strict: ver.strict,
    validation_result: ver.result,
    reasons: ver.reasons,
    length: ver.length,
    match_ratio: ver.match_ratio,
    status: effectiveStatus(st, s),
    plan_hash: s.plan_hash,
    approval: s.approval,
    created_at: iso(s.created),
  };
};
const effectiveStatus = (st, s) =>
  s.status === 'approved' && s.approval && Date.parse(s.approval.expires_at) < st.now()
    ? 'expired'
    : s.status;
const videoOf = (st, id) => st.videos.find((v) => v.video_id === id);
const mustVideo = (st, id) => {
  const v = videoOf(st, id);
  if (!v)
    throw new Problem(
      404,
      'video_not_found',
      '영상을 찾을 수 없습니다',
      `영상 ID ${id} 가 없습니다.`,
      '영상 목록에서 다시 선택해 주세요.',
    );
  return v;
};
function workflow(st, v) {
  const ch = st.changes
    .filter((c) => c.video_id === v.video_id)
    .sort((a, b) => b.created - a.created)[0];
  const sugs = st.suggestions.filter((s) => s.video_id === v.video_id);
  if (sugs.some((s) => s.status === 'queued')) return 'queued';
  if (sugs.some((s) => effectiveStatus(st, s) === 'approved')) return 'approved';
  if (ch) return ch.change_type === 'rollback' ? 'rolled_back' : 'applied';
  if (sugs.some((s) => s.status === 'candidate')) return 'suggested';
  return 'none';
}
const lastChange = (st, id) =>
  st.changes.filter((c) => c.video_id === id).sort((a, b) => b.created - a.created)[0];
const videoSummary = (st, v) => ({
  video_id: v.video_id,
  title: v.title,
  privacy_status: v.privacy_status,
  duration_sec: v.duration_sec,
  is_short: v.is_short,
  excluded: v.excluded,
  exclusion_reasons: v.exclusion_reasons,
  workflow_status: workflow(st, v),
  suggestion_count: st.suggestions.filter(
    (s) => s.video_id === v.video_id && s.status !== 'rejected',
  ).length,
  last_change_at: lastChange(st, v.video_id)?.applied_at ?? null,
  views: v.views,
});
const changeDto = (st, c) => {
  const latest = lastChange(st, c.video_id);
  return {
    id: c.id,
    video_id: c.video_id,
    video_title: videoOf(st, c.video_id)?.title ?? c.new_title,
    change_type: c.change_type,
    previous_title: c.previous_title,
    new_title: c.new_title,
    result: c.result,
    mode: c.mode,
    approver: c.approver,
    applied_at: c.applied_at,
    verified_at: c.verified_at,
    error_code: c.error_code,
    rollbackable: c.change_type === 'apply' && c.result === 'success' && latest?.id === c.id,
    batch_id: c.batch_id,
  };
};
const limitsFor = (st, id) => {
  const mine = st.changes
    .filter((c) => c.video_id === id && c.result === 'success')
    .sort((a, b) => b.created - a.created);
  const reasons = [];
  let next = null;
  if (mine.length >= 3) reasons.push('영상당 최대 3회까지만 바꿀 수 있습니다.');
  if (mine[0] && st.now() - mine[0].created < 72 * 3600 * 1000) {
    next = iso(mine[0].created + 72 * 3600 * 1000);
    reasons.push('같은 영상은 72시간 안에 다시 바꿀 수 없습니다.');
  }
  return { allowed: reasons.length === 0, reasons, next_allowed_at: next };
};
function batchDto(st, b) {
  const items = b.items.map((it) => ({
    id: it.id,
    suggestion_id: it.suggestion_id,
    video_id: it.video_id,
    video_title: videoOf(st, it.video_id)?.title ?? '',
    previous_title: it.previous_title,
    new_title: it.new_title,
    seq: it.seq,
    scheduled_date: it.scheduled_date,
    status: it.status,
    skip_reason: it.skip_reason,
    change_id: it.change_id,
  }));
  const counts = { pending: 0, running: 0, success: 0, failed: 0, skipped: 0, cancelled: 0 };
  items.forEach((i) => {
    counts[i.status] = (counts[i.status] ?? 0) + 1;
  });
  return {
    id: b.id,
    status: b.status,
    note: b.note,
    created_at: iso(b.created),
    executed_at: b.executed ? iso(b.executed) : null,
    counts,
    items,
    precheck: b.precheck,
  };
}
const jobDto = (j) => ({
  id: j.id,
  type: j.type,
  status: j.status,
  progress: j.progress,
  total: j.total,
  error: j.error,
  result: j.result,
});

// ---------- 도우미 ----------
function page(items, q, mapper) {
  const size = Math.min(Math.max(parseInt(q.get('page_size') ?? '50', 10) || 50, 1), 200);
  const p = Math.max(parseInt(q.get('page') ?? '1', 10) || 1, 1);
  return {
    items: items.slice((p - 1) * size, p * size).map(mapper),
    total: items.length,
    page: p,
    page_size: size,
  };
}
const audit = (st, action, targetType, targetId, detail = {}) =>
  st.audit.push({
    id: st.seq.audit++,
    ts: iso(st.now()),
    actor: 'local-user',
    action,
    target_type: targetType ?? null,
    target_id: targetId ?? null,
    detail,
  });
const todayApplied = (st) =>
  st.changes.filter(
    (c) =>
      c.change_type === 'apply' &&
      c.result === 'success' &&
      kstDate(c.created) === kstDate(st.now()),
  ).length;
function newJob(st, type, total) {
  const j = {
    id: crypto.randomUUID(),
    type,
    status: 'queued',
    progress: 0,
    total,
    error: null,
    result: null,
  };
  st.jobs.set(j.id, j);
  return j;
}
function runJob(st, j, step, delay = 250) {
  let i = 0;
  const tick = () => {
    j.status = 'running';
    if (i >= j.total) {
      j.status = 'succeeded';
      return;
    }
    try {
      step(i);
    } catch (e) {
      j.status = 'failed';
      j.error = String(e.message ?? e);
      return;
    }
    i++;
    j.progress = i;
    setTimeout(tick, delay);
  };
  setTimeout(tick, delay);
}

// ---------- 라우팅 ----------
async function handle(st, req, url, body, session) {
  const m = req.method;
  const p = url.pathname;
  const q = url.searchParams;
  let r;
  const route = (method, pattern) => {
    if (m !== method) return null;
    const re = new RegExp(`^${pattern.replace(/:[a-z_]+/g, '([^/]+)')}$`);
    const x = re.exec(p);
    return x ? x.slice(1).map(decodeURIComponent) : null;
  };

  if (p === '/api/healthz' || p === '/healthz') return [200, { status: 'ok' }];
  if (p === '/api/v1/auth/me' && m === 'GET') {
    return [
      200,
      {
        authenticated: !!session,
        pin_required: st.pin !== null && !session,
        csrf_token: session?.csrf ?? null,
      },
    ];
  }
  if (p === '/api/v1/auth/session' && m === 'POST') {
    if (st.pin !== null && body?.pin !== st.pin)
      throw new Problem(
        401,
        'pin_invalid',
        'PIN 이 맞지 않습니다',
        '',
        'PIN 을 다시 확인해 주세요.',
      );
    const sid = crypto.randomBytes(24).toString('hex');
    const s = { sid, csrf: crypto.randomBytes(24).toString('hex') };
    st.sessions.set(sid, s);
    audit(st, 'session.create', 'session', sid.slice(0, 8));
    return [
      200,
      { csrf_token: s.csrf },
      { 'Set-Cookie': `ytw_session=${sid}; HttpOnly; SameSite=Strict; Path=/api` },
    ];
  }
  if (!session)
    throw new Problem(
      401,
      'unauthenticated',
      '로그인이 필요합니다',
      '세션이 없거나 만료되었습니다.',
      '화면을 새로고침해 주세요.',
    );

  if (p === '/api/v1/auth/session' && m === 'DELETE') {
    st.sessions.delete(session.sid);
    return [
      204,
      null,
      { 'Set-Cookie': 'ytw_session=; Max-Age=0; Path=/api; HttpOnly; SameSite=Strict' },
    ];
  }

  if (p === '/api/v1/dashboard' && m === 'GET') {
    const pending = st.batches.flatMap((b) => b.items).filter((i) => i.status === 'pending');
    const dates = pending
      .map((i) => i.scheduled_date)
      .filter(Boolean)
      .sort();
    const active = [...st.jobs.values()].find(
      (j) => j.status === 'running' || j.status === 'queued',
    );
    const count = (s) => st.videos.filter((v) => workflow(st, v) === s).length;
    return [
      200,
      {
        mode: 'demo',
        live_enabled: false,
        google: { mode: 'demo', connected: false },
        counts: {
          videos: st.videos.length,
          excluded: st.videos.filter((v) => v.excluded).length,
          suggested: count('suggested'),
          approved: count('approved'),
          queued: count('queued'),
          applied: count('applied'),
        },
        today: { applied: todayApplied(st), cap: st.settings.daily_apply_cap },
        quota: {
          used: st.quotaUsed,
          limit: 6000,
          remaining: 6000 - st.quotaUsed,
          pt_date: ptDate(st.now()),
        },
        active_job: active
          ? {
              id: active.id,
              type: active.type,
              status: active.status,
              progress: active.progress,
              total: active.total,
            }
          : null,
        queue: { pending_items: pending.length, next_run_date: dates[0] ?? null },
      },
    ];
  }

  if (p === '/api/v1/videos' && m === 'GET') {
    let list = st.videos.map((v) => ({ v, s: videoSummary(st, v) }));
    const text = (q.get('q') ?? '').trim().toLowerCase();
    if (text)
      list = list.filter(
        ({ v }) => v.title.toLowerCase().includes(text) || v.video_id.toLowerCase().includes(text),
      );
    const status = q.get('status');
    if (status) list = list.filter(({ s }) => s.workflow_status === status);
    const ex = q.get('excluded');
    if (ex === 'true') list = list.filter(({ v }) => v.excluded);
    if (ex === 'false') list = list.filter(({ v }) => !v.excluded);
    const sort = q.get('sort') ?? 'last_change_at';
    const dir = q.get('order') === 'asc' ? 1 : -1;
    const key = {
      title: (x) => x.s.title,
      views: (x) => x.s.views ?? 0,
      duration_sec: (x) => x.s.duration_sec ?? 0,
      last_change_at: (x) => x.s.last_change_at ?? '',
    }[sort];
    if (!key)
      throw new Problem(
        422,
        'invalid_sort',
        '정렬 기준이 올바르지 않습니다',
        `sort=${sort}`,
        'title, views, duration_sec, last_change_at 중에서 고르세요.',
      );
    list.sort((a, b) => (key(a) > key(b) ? dir : key(a) < key(b) ? -dir : 0));
    return [200, page(list, q, (x) => x.s)];
  }
  if ((r = route('GET', '/api/v1/videos/:id'))) {
    const v = mustVideo(st, r[0]);
    return [
      200,
      {
        ...videoSummary(st, v),
        description_excerpt: v.description_excerpt,
        suggestions: st.suggestions
          .filter((s) => s.video_id === v.video_id)
          .sort((a, b) => b.id - a.id)
          .map((s) => suggestionDto(st, s)),
        changes: st.changes
          .filter((c) => c.video_id === v.video_id)
          .sort((a, b) => b.created - a.created)
          .map((c) => changeDto(st, c)),
        limits: limitsFor(st, v.video_id),
      },
    ];
  }
  if (p === '/api/v1/videos/sync' && m === 'POST') {
    const j = newJob(st, 'videos.sync', 4);
    if (st.videos.length === 0) seedVideos(st);
    runJob(st, j, () => {}, 300);
    return [202, jobDto(j)];
  }
  if ((r = route('POST', '/api/v1/videos/:id/suggestions'))) {
    const v = mustVideo(st, r[0]);
    if (v.excluded)
      throw new Problem(
        409,
        'video_excluded',
        '제외된 영상입니다',
        v.exclusion_reasons.join(', '),
        '제외되지 않은 영상을 선택해 주세요.',
      );
    const out = makeCandidates(v, body?.count ?? st.settings.suggestions_per_video).map((title) =>
      addSuggestion(st, v, title, 'ai:mock'),
    );
    audit(st, 'suggestion.generate', 'video', v.video_id, { count: out.length });
    return [201, out.map((s) => suggestionDto(st, s))];
  }
  if (p === '/api/v1/suggestions/generate' && m === 'POST') {
    const ids = body?.video_ids;
    if (!Array.isArray(ids) || ids.length === 0)
      throw new Problem(
        422,
        'validation_error',
        '입력값이 올바르지 않습니다',
        'video_ids 가 비어 있습니다.',
      );
    const vids = ids.map((id) => mustVideo(st, id));
    if (vids.some((v) => v.excluded))
      throw new Problem(
        409,
        'video_excluded',
        '제외된 영상이 포함되어 있습니다',
        '',
        '제외되지 않은 영상만 선택해 주세요.',
      );
    const j = newJob(st, 'suggestions.generate', vids.length);
    runJob(
      st,
      j,
      (i) => {
        makeCandidates(vids[i], st.settings.suggestions_per_video).forEach((t) =>
          addSuggestion(st, vids[i], t, 'ai:mock'),
        );
      },
      350,
    );
    audit(st, 'suggestion.generate_bulk', 'job', j.id, { videos: vids.length });
    return [202, jobDto(j)];
  }
  if (p === '/api/v1/suggestions' && m === 'GET') {
    let list = [...st.suggestions].sort((a, b) => b.id - a.id);
    if (q.get('video_id')) list = list.filter((s) => s.video_id === q.get('video_id'));
    if (q.get('status')) list = list.filter((s) => effectiveStatus(st, s) === q.get('status'));
    if (q.get('result'))
      list = list.filter(
        (s) => validateTitle(s.title, videoOf(st, s.video_id)).result === q.get('result'),
      );
    return [200, page(list, q, (s) => suggestionDto(st, s))];
  }
  if ((r = route('PATCH', '/api/v1/suggestions/:id'))) {
    const s = mustSuggestion(st, r[0]);
    const t = typeof body?.title === 'string' ? body.title.trim() : '';
    if (!t)
      throw new Problem(
        422,
        'validation_error',
        '입력값이 올바르지 않습니다',
        '제목이 비어 있습니다.',
      );
    s.title = t;
    s.source = 'manual';
    s.status = 'candidate';
    s.approval = null;
    s.plan_hash = null;
    audit(st, 'suggestion.edit', 'suggestion', s.id);
    return [200, suggestionDto(st, s)];
  }
  if ((r = route('POST', '/api/v1/suggestions/:id/approve'))) {
    const s = mustSuggestion(st, r[0]);
    const dto = suggestionDto(st, s);
    if (dto.validation_result === 'block')
      throw new Problem(
        409,
        'suggestion_blocked',
        '차단 판정이라 승인할 수 없습니다',
        dto.reasons.map((x) => x.message).join(' / '),
        '제목을 수정해 다시 검증해 보세요.',
      );
    if (!['candidate', 'expired'].includes(dto.status))
      throw new Problem(
        409,
        'invalid_state',
        '지금은 승인할 수 없는 상태입니다',
        `현재 상태: ${dto.status}`,
      );
    if (!body?.approver || !String(body.approver).trim())
      throw new Problem(
        422,
        'validation_error',
        '입력값이 올바르지 않습니다',
        '승인자 이름이 필요합니다.',
      );
    s.status = 'approved';
    s.plan_hash = crypto.randomBytes(16).toString('hex');
    s.approval = {
      approver: String(body.approver).trim(),
      approved_at: iso(st.now()),
      expires_at: iso(st.now() + 24 * 3600 * 1000),
    };
    audit(st, 'suggestion.approve', 'suggestion', s.id, { approver: s.approval.approver });
    return [200, suggestionDto(st, s)];
  }
  if ((r = route('POST', '/api/v1/suggestions/:id/reject'))) {
    const s = mustSuggestion(st, r[0]);
    if (['queued', 'applied'].includes(s.status))
      throw new Problem(
        409,
        'invalid_state',
        '이미 반영 대기 또는 반영된 제안은 반려할 수 없습니다',
      );
    s.status = 'rejected';
    s.approval = null;
    audit(st, 'suggestion.reject', 'suggestion', s.id);
    return [200, suggestionDto(st, s)];
  }

  if (p === '/api/v1/batches' && m === 'POST') {
    return idempotent(st, req, p, body, () => {
      const ids = body?.suggestion_ids;
      if (!Array.isArray(ids) || ids.length === 0)
        throw new Problem(
          422,
          'validation_error',
          '입력값이 올바르지 않습니다',
          'suggestion_ids 가 비어 있습니다.',
        );
      if (ids.length > 50)
        throw new Problem(
          422,
          'batch_too_large',
          '한 배치에는 최대 50건까지입니다',
          `${ids.length}건 선택됨`,
          '선택을 줄여 주세요.',
        );
      const blocked = [];
      const ok = [];
      for (const id of ids) {
        const s = st.suggestions.find((x) => x.id === id);
        if (!s) blocked.push({ suggestion_id: id, reason: '존재하지 않는 제안입니다.' });
        else if (effectiveStatus(st, s) !== 'approved')
          blocked.push({
            suggestion_id: id,
            reason: '승인 상태가 아니거나 승인이 만료되었습니다.',
          });
        else if (!limitsFor(st, s.video_id).allowed)
          blocked.push({ suggestion_id: id, reason: limitsFor(st, s.video_id).reasons[0] });
        else ok.push(s);
      }
      const cap = st.settings.daily_apply_cap;
      let left = Math.max(0, cap - todayApplied(st));
      let day = kstDate(st.now());
      const schedule = [];
      ok.forEach(() => {
        if (left === 0) {
          day = addDays(day, 1);
          left = cap;
        }
        const last = schedule[schedule.length - 1];
        if (last && last.date === day) last.count++;
        else schedule.push({ date: day, count: 1 });
        left--;
      });
      const warnings = [];
      if (ok.length > Math.max(0, cap - todayApplied(st)))
        warnings.push(`하루 상한(${cap}건)을 넘는 항목은 다음 날로 예약됩니다.`);
      if ((st.quotaUsed + ok.length * 50) / 6000 >= 0.8)
        warnings.push('API 사용량이 80%를 넘을 수 있습니다.');
      const b = {
        id: st.seq.batch++,
        status: 'draft',
        note: body?.note ?? null,
        created: st.now(),
        executed: null,
        items: [],
        precheck: null,
      };
      ok.forEach((s, i) => {
        b.items.push({
          id: st.seq.item++,
          suggestion_id: s.id,
          video_id: s.video_id,
          previous_title: videoOf(st, s.video_id).title,
          new_title: s.title,
          seq: i + 1,
          scheduled_date: null,
          status: 'pending',
          skip_reason: null,
          change_id: null,
        });
      });
      b.precheck = {
        item_count: ok.length,
        estimated_units: ok.length * 50,
        daily_cap: cap,
        quota_remaining_units: 6000 - st.quotaUsed,
        schedule,
        warnings,
        blocked,
        confirm_text: `실행 ${ok.length}건`,
      };
      st.batches.unshift(b);
      audit(st, 'batch.create', 'batch', b.id, { items: ok.length });
      return [201, { batch: batchDto(st, b), precheck: b.precheck }];
    });
  }
  if (p === '/api/v1/batches' && m === 'GET')
    return [200, page(st.batches, q, (b) => batchDto(st, b))];
  if ((r = route('GET', '/api/v1/batches/:id'))) return [200, batchDto(st, mustBatch(st, r[0]))];
  if ((r = route('POST', '/api/v1/batches/:id/execute'))) {
    const b = mustBatch(st, r[0]);
    return idempotent(st, req, p, body, () => {
      if (b.status !== 'draft')
        throw new Problem(
          409,
          'invalid_state',
          '이미 실행했거나 끝난 배치입니다',
          `현재 상태: ${b.status}`,
        );
      if (body?.confirm_text !== b.precheck.confirm_text)
        throw new Problem(
          422,
          'confirm_text_mismatch',
          '확인 문구가 맞지 않습니다',
          `"${b.precheck.confirm_text}" 를 그대로 입력해야 합니다.`,
        );
      let left = Math.max(0, st.settings.daily_apply_cap - todayApplied(st));
      let day = kstDate(st.now());
      b.items.forEach((it) => {
        if (left === 0) {
          day = addDays(day, 1);
          left = st.settings.daily_apply_cap;
        }
        it.scheduled_date = day;
        left--;
        const s = st.suggestions.find((x) => x.id === it.suggestion_id);
        s.status = 'queued';
      });
      b.status = 'running';
      b.executed = st.now();
      const job = newJob(st, 'batch.execute', b.items.length);
      job.status = 'running';
      audit(st, 'batch.execute', 'batch', b.id, { items: b.items.length });
      scheduleWorker(st);
      return [202, { batch: batchDto(st, b), job: jobDto(job) }];
    });
  }
  if ((r = route('POST', '/api/v1/batches/:id/cancel'))) {
    const b = mustBatch(st, r[0]);
    b.items
      .filter((i) => i.status === 'pending')
      .forEach((i) => {
        i.status = 'cancelled';
        const s = st.suggestions.find((x) => x.id === i.suggestion_id);
        if (s && s.status === 'queued') s.status = 'approved';
      });
    settleBatch(st, b, true);
    audit(st, 'batch.cancel', 'batch', b.id);
    return [200, batchDto(st, b)];
  }
  if ((r = route('GET', '/api/v1/jobs/:id'))) {
    const j = st.jobs.get(r[0]);
    if (!j) throw new Problem(404, 'job_not_found', '작업을 찾을 수 없습니다');
    return [200, jobDto(j)];
  }

  if (p === '/api/v1/changes' && m === 'GET') {
    let list = [...st.changes].sort((a, b) => b.created - a.created);
    if (q.get('video_id')) list = list.filter((c) => c.video_id === q.get('video_id'));
    if (q.get('batch_id')) list = list.filter((c) => String(c.batch_id) === q.get('batch_id'));
    if (q.get('result')) list = list.filter((c) => c.result === q.get('result'));
    return [200, page(list, q, (c) => changeDto(st, c))];
  }
  if ((r = route('POST', '/api/v1/changes/:id/rollback'))) {
    return idempotent(st, req, p, body, () => {
      const c = st.changes.find((x) => x.id === Number(r[0]));
      if (!c) throw new Problem(404, 'change_not_found', '변경 기록을 찾을 수 없습니다');
      if (body?.typed_video_id !== c.video_id)
        throw new Problem(
          422,
          'typed_video_id_mismatch',
          '영상 ID 가 일치하지 않습니다',
          '직접 입력한 영상 ID 가 대상과 다릅니다.',
          '영상 ID 를 그대로 입력해 주세요.',
        );
      if (!changeDto(st, c).rollbackable)
        throw new Problem(
          409,
          'not_rollbackable',
          '되돌릴 수 없는 변경입니다',
          '이후에 다른 변경이 있거나 이미 되돌려졌습니다.',
        );
      const v = mustVideo(st, c.video_id);
      v.title = c.previous_title;
      const rc = {
        id: st.seq.change++,
        video_id: c.video_id,
        change_type: 'rollback',
        previous_title: c.new_title,
        new_title: c.previous_title,
        result: 'success',
        mode: 'demo',
        approver: String(body.approver ?? ''),
        applied_at: iso(st.now()),
        verified_at: iso(st.now()),
        error_code: null,
        batch_id: null,
        created: st.now(),
      };
      st.changes.push(rc);
      audit(st, 'change.rollback', 'change', c.id, { video_id: c.video_id });
      return [201, changeDto(st, rc)];
    });
  }

  if (p === '/api/v1/reports/changes' && m === 'GET')
    return [200, buildReports(st, q.get('video_id'))];
  if (p === '/api/v1/reports/export.csv' && m === 'GET') {
    const rows = buildReports(st, null).items.flatMap((r2) =>
      r2.metrics.length
        ? r2.metrics.map((x) => [
            r2.video_id,
            r2.title,
            r2.status,
            x.label,
            x.before,
            x.after,
            x.pct,
          ])
        : [[r2.video_id, r2.title, r2.status, '', '', '', '']],
    );
    const csv = [
      'video_id,title,status,metric,before,after,pct',
      ...rows.map((x) => x.map((c) => `"${String(c ?? '').replaceAll('"', '""')}"`).join(',')),
    ].join('\n');
    return [
      200,
      csv,
      {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename="report.csv"',
      },
    ];
  }
  if (p === '/api/v1/audit' && m === 'GET')
    return [200, { ...page([...st.audit].reverse(), q, (a) => a), chain_ok: true }];
  if (p === '/api/v1/settings' && m === 'GET') return [200, settingsDto(st)];
  if (p === '/api/v1/settings' && m === 'PATCH') {
    const b = body ?? {};
    const bad = Object.keys(b).filter(
      (k) => !['daily_apply_cap', 'suggestions_per_video', 'tone', 'pin'].includes(k),
    );
    if (bad.length)
      throw new Problem(
        400,
        'setting_not_allowed',
        '이 화면에서는 바꿀 수 없는 설정입니다',
        `허용되지 않은 키: ${bad.join(', ')}`,
        '변경 가능한 항목: daily_apply_cap, suggestions_per_video, tone, pin',
      );
    if (
      'daily_apply_cap' in b &&
      !(Number.isInteger(b.daily_apply_cap) && b.daily_apply_cap >= 1 && b.daily_apply_cap <= 20)
    )
      throw new Problem(
        422,
        'validation_error',
        '입력값이 올바르지 않습니다',
        '하루 반영 상한은 1~20 입니다.',
      );
    if (
      'suggestions_per_video' in b &&
      !(
        Number.isInteger(b.suggestions_per_video) &&
        b.suggestions_per_video >= 1 &&
        b.suggestions_per_video <= 5
      )
    )
      throw new Problem(
        422,
        'validation_error',
        '입력값이 올바르지 않습니다',
        '영상당 제안 개수는 1~5 입니다.',
      );
    if (
      'tone' in b &&
      !(
        Array.isArray(b.tone) &&
        b.tone.length <= 5 &&
        b.tone.every((t) => typeof t === 'string' && t.length >= 1 && t.length <= 20)
      )
    )
      throw new Problem(
        422,
        'validation_error',
        '입력값이 올바르지 않습니다',
        '말투는 최대 5개, 각 1~20자입니다.',
      );
    if ('pin' in b) {
      const pn = b.pin;
      if (!pn || !['set', 'clear'].includes(pn.action))
        throw new Problem(
          422,
          'validation_error',
          'pin 은 {action: set|clear, new_pin?, current_pin?} 형식이어야 합니다.',
        );
      if (pn.action === 'set' && !/^\d{4,12}$/.test(String(pn.new_pin ?? '')))
        throw new Problem(422, 'validation_error', 'PIN 은 숫자 4~12자리여야 합니다.');
      if (st.pin !== null && pn.current_pin !== st.pin)
        throw new Problem(
          401,
          'pin_invalid',
          '현재 PIN 이 맞지 않습니다',
          '',
          'PIN 을 다시 확인해 주세요.',
        );
      if (pn.action === 'clear' && st.pin === null)
        throw new Problem(409, 'pin_not_set', '설정된 PIN 이 없습니다.');
      st.pin = pn.action === 'set' ? pn.new_pin : null;
    }
    for (const k of ['daily_apply_cap', 'suggestions_per_video', 'tone'])
      if (k in b) st.settings[k] = b[k];
    audit(st, 'settings.update', 'settings', null, {
      keys: Object.keys(b).filter((k) => k !== 'pin'),
    });
    return [200, settingsDto(st)];
  }
  if (p === '/api/v1/google/status' && m === 'GET')
    return [
      200,
      {
        mode: 'demo',
        connected: false,
        message:
          '데모 모드입니다. 구글 계정과 연결되어 있지 않고 유튜브에 아무것도 전송되지 않습니다.',
      },
    ];

  throw new Problem(404, 'not_found', '찾을 수 없는 주소입니다', `${m} ${p}`);
}

const settingsDto = (st) => ({
  ...st.settings,
  pin_set: st.pin !== null,
  live_enabled: false,
  allowed_video_ids: [],
});
function addSuggestion(st, v, title, source) {
  const s = {
    id: st.seq.suggestion++,
    video_id: v.video_id,
    title,
    evidence: '영상 제목·설명의 핵심 단어를 바탕으로 만든 모의 제안입니다.',
    source,
    status: 'candidate',
    approval: null,
    plan_hash: null,
    created: st.now(),
  };
  st.suggestions.push(s);
  return s;
}
function mustSuggestion(st, id) {
  const s = st.suggestions.find((x) => x.id === Number(id));
  if (!s) throw new Problem(404, 'suggestion_not_found', '제안을 찾을 수 없습니다');
  return s;
}
function mustBatch(st, id) {
  const b = st.batches.find((x) => x.id === Number(id));
  if (!b) throw new Problem(404, 'batch_not_found', '배치를 찾을 수 없습니다');
  return b;
}
function idempotent(st, req, route, body, handler) {
  const key = req.headers['idempotency-key'];
  if (!key)
    throw new Problem(
      400,
      'idempotency_key_required',
      '중복 요청 방지 키가 필요합니다',
      'Idempotency-Key 헤더가 없습니다.',
    );
  const fp = `${route}|${JSON.stringify(body ?? {})}`;
  const prev = st.idem.get(key);
  if (prev) {
    if (prev.fp !== fp)
      throw new Problem(422, 'idempotency_key_reuse', '같은 키로 다른 요청을 보낼 수 없습니다');
    return prev.res;
  }
  const res = handler();
  st.idem.set(key, { fp, res });
  return res;
}
function settleBatch(st, b, cancelled = false) {
  const open = b.items.some((i) => i.status === 'pending' || i.status === 'running');
  if (open) return;
  b.status =
    cancelled && b.items.every((i) => i.status === 'cancelled') ? 'cancelled' : 'completed';
}
let workerTimer = null;
function scheduleWorker(st) {
  if (workerTimer) return;
  workerTimer = setInterval(() => {
    const today = kstDate(st.now());
    let busy = false;
    for (const b of st.batches) {
      if (b.status !== 'running') continue;
      const running = b.items.find((i) => i.status === 'running');
      if (running) {
        finishItem(st, b, running);
        busy = true;
        continue;
      }
      const next = b.items.find((i) => i.status === 'pending' && i.scheduled_date <= today);
      if (next && todayApplied(st) < st.settings.daily_apply_cap) {
        next.status = 'running';
        busy = true;
      }
      settleBatch(st, b);
    }
    if (
      !busy &&
      !st.batches.some((b) => b.status === 'running' && b.items.some((i) => i.status === 'running'))
    ) {
      for (const j of st.jobs.values())
        if (j.type === 'batch.execute' && j.status === 'running') {
          j.status = 'succeeded';
          j.progress = j.total;
        }
    }
  }, 1200);
  workerTimer.unref?.();
}
function finishItem(st, b, it) {
  const v = videoOf(st, it.video_id);
  const s = st.suggestions.find((x) => x.id === it.suggestion_id);
  const lim = limitsFor(st, it.video_id);
  if (!lim.allowed) {
    it.status = 'skipped';
    it.skip_reason = lim.reasons[0];
    s.status = 'approved';
  } else {
    const c = {
      id: st.seq.change++,
      video_id: v.video_id,
      change_type: 'apply',
      previous_title: v.title,
      new_title: it.new_title,
      result: 'success',
      mode: 'demo',
      approver: s.approval?.approver ?? null,
      applied_at: iso(st.now()),
      verified_at: iso(st.now()),
      error_code: null,
      batch_id: b.id,
      created: st.now(),
    };
    st.changes.push(c);
    v.title = it.new_title;
    it.status = 'success';
    it.change_id = c.id;
    s.status = 'applied';
    st.quotaUsed += 50;
  }
  settleBatch(st, b);
}
function buildReports(st, onlyId) {
  const ids = [
    ...new Set(st.changes.filter((c) => c.change_type === 'apply').map((c) => c.video_id)),
  ].filter((id) => !onlyId || id === onlyId);
  const items = ids.map((id) => {
    const v = videoOf(st, id);
    const ch = st.changes
      .filter((c) => c.video_id === id && c.change_type === 'apply')
      .sort((a, b) => b.created - a.created)[0];
    const ageDays = (st.now() - ch.created) / DAY;
    const base = {
      video_id: id,
      title: v?.title ?? null,
      baseline_missing: false,
      notes: [],
      reasons: [],
      metrics: [],
      before: null,
      after: null,
      expected_after_date: null,
    };
    if (ageDays < 14)
      return {
        ...base,
        status: 'insufficient',
        reasons: ['변경 후 집계 기간이 14일에 못 미칩니다.'],
        expected_after_date: kstDate(ch.created + 14 * DAY),
      };
    const seed = id.charCodeAt(id.length - 1);
    const b = {
      impressions: 12000 + seed * 31,
      ctr: 0.041,
      views: 520 + seed,
      watch_minutes: 1800 + seed * 3,
    };
    const a = {
      impressions: 13100 + seed * 29,
      ctr: 0.046,
      views: 610 + seed,
      watch_minutes: 2100 + seed * 3,
    };
    const pct = (x, y) => Math.round(((y - x) / x) * 1000) / 10;
    const lab = {
      impressions: '노출수',
      ctr: '클릭률',
      views: '조회수',
      watch_minutes: '시청 시간(분)',
    };
    return {
      ...base,
      status: 'ok',
      before: {
        id: 1,
        taken_at: iso(ch.created - DAY),
        phase: 'before',
        source: 'demo',
        period_start: kstDate(ch.created - 15 * DAY),
        period_end: kstDate(ch.created - DAY),
        ...b,
      },
      after: {
        id: 2,
        taken_at: iso(ch.created + 15 * DAY),
        phase: 'after',
        source: 'demo',
        period_start: kstDate(ch.created + DAY),
        period_end: kstDate(ch.created + 15 * DAY),
        ...a,
      },
      metrics: Object.keys(lab).map((k) => ({
        key: k,
        label: lab[k],
        before: b[k],
        after: a[k],
        delta: Math.round((a[k] - b[k]) * 1000) / 1000,
        pct: pct(b[k], a[k]),
      })),
    };
  });
  return {
    items,
    notes: [
      '순차 비교는 다른 요인(시기·노출 차이)의 영향을 받아 원인을 단정할 수 없습니다.',
      '이 표는 변경 전과 후의 숫자를 나란히 놓은 것일 뿐, 제목 변경이 원인이라고 말하지 않습니다. 계절·시기, 노출 위치 변화, 썸네일, 외부 유입, 공식 A/B 테스트 같은 다른 요인이 섞여 있을 수 있습니다.',
    ],
  };
}

// ---------- HTTP ----------
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.json': 'application/json',
};

export function createServer(st, { staticDir } = {}) {
  return http.createServer((req, res) => {
    const url = new URL(req.url ?? '/', 'http://localhost');
    const send = (status, body, headers = {}) => {
      const isText = typeof body === 'string';
      const h = { 'Cache-Control': 'no-store', ...headers };
      if (!h['Content-Type'])
        h['Content-Type'] = isText
          ? 'text/plain; charset=utf-8'
          : 'application/json; charset=utf-8';
      res.writeHead(status, h);
      res.end(status === 204 || body === null ? undefined : isText ? body : JSON.stringify(body));
    };
    if (
      !url.pathname.startsWith('/api') &&
      !url.pathname.startsWith('/__mock') &&
      !url.pathname.startsWith('/healthz')
    ) {
      if (!staticDir) return send(404, '모의 서버입니다. 화면은 npm run dev:mock 으로 여세요.');
      let f = path.join(staticDir, path.normalize(url.pathname).replace(/^(\.\.[/\\])+/, ''));
      if (!f.startsWith(staticDir) || !fs.existsSync(f) || fs.statSync(f).isDirectory())
        f = path.join(staticDir, 'index.html');
      res.writeHead(200, { 'Content-Type': MIME[path.extname(f)] ?? 'application/octet-stream' });
      return fs.createReadStream(f).pipe(res);
    }
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', async () => {
      try {
        if (url.pathname === '/__mock/expire') {
          st.sessions.clear();
          return send(200, { ok: true });
        }
        let body;
        const raw = Buffer.concat(chunks).toString('utf8');
        if (raw) {
          try {
            body = JSON.parse(raw);
          } catch {
            throw new Problem(400, 'invalid_json', '요청 형식이 올바르지 않습니다');
          }
        }
        const cookie = Object.fromEntries(
          (req.headers.cookie ?? '')
            .split(';')
            .map((x) => x.trim().split('='))
            .filter((x) => x[0]),
        );
        const session = st.sessions.get(cookie.ytw_session) ?? null;
        const mutating = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(req.method ?? '');
        const origin = req.headers.origin;
        if (mutating && origin && new URL(origin).host !== req.headers.host)
          throw new Problem(403, 'origin_not_allowed', '허용되지 않은 출처입니다');
        const isSessionCreate = url.pathname === '/api/v1/auth/session' && req.method === 'POST';
        if (mutating && !isSessionCreate && session && req.headers['x-csrf-token'] !== session.csrf)
          throw new Problem(
            403,
            'csrf_invalid',
            '보안 토큰이 맞지 않습니다',
            '',
            '화면을 새로고침해 주세요.',
          );
        const [status, payload, headers] = await handle(st, req, url, body, session);
        return send(status, payload, headers);
      } catch (e) {
        if (e instanceof Problem) {
          return send(
            e.status,
            {
              type: `about:blank#${e.code}`,
              title: e.title,
              status: e.status,
              detail: e.detail,
              code: e.code,
              hint: e.hint,
            },
            { 'Content-Type': 'application/problem+json; charset=utf-8' },
          );
        }
        console.error(e);
        return send(
          500,
          {
            type: 'about:blank',
            title: '서버 안에서 오류가 났습니다',
            status: 500,
            detail: '',
            code: 'internal_error',
            hint: '잠시 뒤 다시 시도해 주세요.',
          },
          { 'Content-Type': 'application/problem+json' },
        );
      }
    });
  });
}

export function startMockServer({
  port = Number(process.env.MOCK_PORT ?? 8081),
  host = '127.0.0.1',
  pin = process.env.MOCK_PIN ?? null,
  empty = process.env.MOCK_EMPTY === '1',
  staticDir = process.env.MOCK_STATIC ? path.resolve(process.env.MOCK_STATIC) : null,
} = {}) {
  const st = createState({ pin, empty });
  const server = createServer(st, { staticDir });
  return new Promise((resolve) =>
    server.listen(port, host, () => resolve({ server, state: st, port, host })),
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { port, host } = await startMockServer();
  console.log(
    `모의 서버 실행 중: http://${host}:${port}  (PIN=${process.env.MOCK_PIN ? '사용' : '없음'})`,
  );
}
