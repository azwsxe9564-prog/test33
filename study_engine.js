/* Study engine: unique-question cycling, balanced interleaving, and resumable local state.
 * Cloud sync is intentionally handled by cloud_sync.js; this module exposes a small API
 * so the UI can connect it without coupling quiz logic to a storage provider.
 */
(function (root) {
  'use strict';

  const VERSION = 1;
  const STORAGE_KEY = 'sw_study_engine_v1';
  const SUBJECT_ORDER = [
    '社會工作研究方法',
    '人類行為與社會環境',
    '社會工作',
    '社會工作直接服務',
    '社會政策與社會立法'
  ];

  function shuffle(items, random) {
    const out = items.slice();
    const rng = typeof random === 'function' ? random : Math.random;
    for (let i = out.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  }

  function interleaveBySubject(questions, random) {
    const buckets = new Map();
    SUBJECT_ORDER.forEach(subject => buckets.set(subject, []));
    questions.forEach(q => {
      if (!q || !q.id || !q.subject) return;
      if (!buckets.has(q.subject)) buckets.set(q.subject, []);
      buckets.get(q.subject).push(q);
    });
    buckets.forEach((items, subject) => buckets.set(subject, shuffle(items, random)));

    const order = Array.from(buckets.keys());
    const result = [];
    let remaining = true;
    while (remaining) {
      remaining = false;
      order.forEach(subject => {
        const bucket = buckets.get(subject);
        if (bucket.length) {
          result.push(bucket.pop());
          remaining = true;
        }
      });
    }
    return result;
  }

  function uniqueQuestions(questions) {
    const seen = new Set();
    return questions.filter(q => {
      if (!q || q.id == null || seen.has(String(q.id))) return false;
      seen.add(String(q.id));
      return true;
    });
  }

  function createState() {
    return { version: VERSION, pools: {}, active: null, updatedAt: null };
  }

  function readState(storage) {
    try {
      const raw = (storage || root.localStorage).getItem(STORAGE_KEY);
      if (!raw) return createState();
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.version !== VERSION || !parsed.pools) return createState();
      return parsed;
    } catch (_) {
      return createState();
    }
  }

  function writeState(state, storage) {
    state.updatedAt = new Date().toISOString();
    try {
      (storage || root.localStorage).setItem(STORAGE_KEY, JSON.stringify(state));
      return true;
    } catch (_) {
      return false;
    }
  }

  function poolKey(filters) {
    const f = filters || {};
    return JSON.stringify({ year: f.year || 'all', subject: f.subject || 'all' });
  }

  function beginCycle(questions, filters, state, random) {
    const clean = uniqueQuestions(questions);
    const key = poolKey(filters);
    const prior = state.pools[key] || {};
    const priorSeen = new Set(Array.isArray(prior.seenIds) ? prior.seenIds.map(String) : []);
    const unseen = clean.filter(q => !priorSeen.has(String(q.id)));

    // A new cycle begins only after every eligible unique question has been seen.
    const cycle = unseen.length ? (prior.cycle || 1) : (prior.cycle || 0) + 1;
    const source = unseen.length ? unseen : clean;
    const queue = interleaveBySubject(source, random).map(q => String(q.id));
    const next = {
      cycle,
      eligibleCount: clean.length,
      seenIds: unseen.length ? Array.from(priorSeen) : [],
      queue,
      position: 0,
      startedAt: new Date().toISOString()
    };
    state.pools[key] = next;
    state.active = key;
    return next;
  }

  function nextQuestion(questions, filters, state, random) {
    const clean = uniqueQuestions(questions);
    const key = poolKey(filters);
    let pool = state.pools[key];
    if (!pool || !Array.isArray(pool.queue) || pool.position >= pool.queue.length) {
      pool = beginCycle(clean, filters, state, random);
    }
    const id = pool.queue[pool.position++];
    pool.seenIds = Array.from(new Set((pool.seenIds || []).concat(id)));
    const byId = new Map(clean.map(q => [String(q.id), q]));
    return { question: byId.get(String(id)) || null, pool, state };
  }

  function resume(questions, filters, state) {
    const key = poolKey(filters);
    const pool = state.pools[key];
    if (!pool || !Array.isArray(pool.queue)) return null;
    const byId = new Map(uniqueQuestions(questions).map(q => [String(q.id), q]));
    const id = pool.queue[pool.position];
    return id == null ? null : (byId.get(String(id)) || null);
  }

  function snapshot(state) {
    return JSON.parse(JSON.stringify(state));
  }

  root.SWStudyEngine = {
    version: VERSION,
    subjectOrder: SUBJECT_ORDER.slice(),
    shuffle,
    interleaveBySubject,
    uniqueQuestions,
    createState,
    readState,
    writeState,
    poolKey,
    beginCycle,
    nextQuestion,
    resume,
    snapshot
  };
})(window);
