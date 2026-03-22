# Final Decision After External Review
Date: 2026-03-21
Reviewers: Grok 4.1 Fast Reasoning (A), GPT-5.1 Codex Mini (B), ChatGPT Web (C — pending)

---

## 1. Reviewer Summaries

### Reviewer A — Grok 4.1 Fast Reasoning
**Strong on**: Specific line-level observations, concrete fixes, performance estimates.
**Key findings**:
- Protobuf builders duplicated across files → centralize in entities.py
- Playwright OOM risk on Railway hobby plan (~40% crash probability)
- Google rate limits triggered after ~20-30 pages (no stealth, detectable webdriver flag)
- Negative stopover deltas are **real** (airline stopover pricing mechanics, KE/ANA discount positioning fares)
- Missing `wait_for_selector` with `state='visible'` before clicks
- Race condition if scanner writes JSON while drill reads a different JSON simultaneously
- Date parsing `parse_dates()` misses non-standard formats

### Reviewer B — GPT-5.1 Codex Mini
**Strong on**: Architecture-level concerns, JSON schema validation, Railway symlink edge cases.
**Key findings**:
- No centralized state: malformed JSON from one stage crashes all downstream stages
- Railway symlinks create broken paths on first run (no empty file placeholders)
- Archive copy to GitHub grows unboundedly — will blow up git clone over time
- Stopover negative deltas likely **artifacts** (wrong passenger mix: base=2.75x, multi-city=1x)
- `PROOF_DIR` never created → screenshot saves crash
- No `Retry-After` handling for Google 429s

---

## 2. Critical Comparison

| Topic | Grok says | GPT says | Agreement? |
|-------|-----------|---------|------------|
| Negative stopover deltas | Real opportunities (airline pricing quirks) | Artifacts (passenger count mismatch) | **CONFLICT** |
| Top reliability risk | Playwright OOM (~40%) | Railway symlink broken on first run | Both valid, different angle |
| Protobuf duplication | Fix immediately, ~50 LOC saved | Not flagged | Grok correct |
| Selector fragility | High — needs `wait_for_selector` | High — needs data-testid targets | **Full agreement** |
| Archive growth | Not flagged | Critical — will break GitHub push | GPT correct, verify this |
| Parallelization | 8-12 workers with jitter OK | 3-4 workers + randomized delay | Both say add jitter |
| Passenger normalization | Mentioned briefly | Flagged as root cause of delta bug | GPT more thorough here |

---

## 3. Independent Judgment

### Stopover negative deltas — Grok vs GPT conflict
**Verdict: Both partially right.**
- GPT is correct that `build_multicity_url` does not encode passenger count → price shown is 1-adult rate → that alone explains most negative deltas.
- Grok is also correct that Korean Air / ANA have genuine stopover fare discounts that can produce real savings.
- **Action**: Fix passenger encoding first. After that, remaining negative deltas can be trusted.

### Railway symlinks on first run (GPT)
**Verdict: Valid, but lower priority.** The `os.path.ismount()` check already falls through to ephemeral mode when `/data` isn't mounted (which is always the case on Railway Hobby without a volume). The symlink code doesn't execute in our deployment. Not urgent, but worth a defensive comment.

### Archive growth (GPT)
**Verdict: Real risk, needs a cap.** We copy all archive/ subdirs to GitHub on every push. After 100+ runs, this will be hundreds of MB. Need a max-N-runs cap or push only current + last 10.

### Protobuf duplication (Grok)
**Verdict: Valid cleanup, not urgent.** Won't fix bugs but reduces maintenance burden. Defer.

### Selector fragility (both agree)
**Verdict: Accept.** `find_flight_li` using `$` and time regex is genuinely brittle. However, Google Flights has no stable `data-testid` attributes either — they obfuscate aggressively. The current heuristic (`30 < len(text) < 600`) has been working. Modest improvement: add `wait_for_selector('li', state='visible')` before scanning.

### Playwright OOM (Grok)
**Verdict: Needs verification.** We've not seen OOM crashes in Railway logs yet. The scanner is sequential (1 page at a time) so peak RAM is low. Deep verify uses 5 workers with separate pages. Monitor Railway memory metrics before acting.

---

## 4. Decision Table

| Suggestion | Source | Accept? | Reason | Risk | Difficulty |
|-----------|--------|---------|--------|------|------------|
| Fix passenger count in multi-city URL | B | ✅ Accept | Root cause of misleading deltas | Low | Easy |
| Cap archive/ to last 10 runs in GitHub push | B | ✅ Accept | Will break GitHub push over time | Low | Easy |
| Add `wait_for_selector` before li scanning | Both | ✅ Accept | Reduces false NO_FLIGHTS | Low | Easy |
| Add jitter (1-3s) between Playwright requests | Both | ✅ Accept | Reduces rate limit risk | Low | Easy |
| Centralize protobuf builders in entities.py | A | ⏸ Defer | Cleanup, not a bug | Low | Medium |
| Proxy rotation to avoid Google blocks | A | ❌ Reject | Adds complexity, cost, Railway config; not proven needed yet | Medium | Hard |
| SQLite for trend data | A | ❌ Reject | Overkill for current scale; JSON + archive works | Low | Medium |
| DataTables.js for HTML pagination | A | ⏸ Defer | Nice to have; HTML truncation is the priority | Low | Medium |
| Raise MAX_WORKERS to 8-12 | A | ❌ Reject | 5 workers already risks rate limits; don't increase without proxies | High | Easy |
| Validate JSON between pipeline stages | B | ⏸ Defer | Good idea, not currently causing failures | Low | Medium |
| Create PROOF_DIR in scanner | B | ✅ Accept | Trivial fix, prevents crash if screenshots enabled | Low | Trivial |
| Screenshot failed verifications | B | ⏸ Defer | Good for debug but adds disk/time cost | Low | Medium |

---

## 5. Final Recommendation — Prioritized Action List

### Do Now (high impact, low effort)
1. **Fix passenger count in `build_multicity_url`** — encode 2 adults + 1 child same as base scanner. This makes stopover deltas trustworthy.
2. **Cap archive push to last 10 runs** — in `railway_entrypoint.push_to_github()`, only copy 10 most recent archive subdirs.
3. **Add jitter** — `await asyncio.sleep(random.uniform(1, 3))` between each page load in scanner and deep verify.
4. **Add `PROOF_DIR` mkdir** — one-liner in `bug_fare_scanner.py`.

### Do Soon (medium impact, medium effort)
5. **HTML truncation fix** — investigate file size limit on GitHub Pages; likely need to split large fare table into separate JS-loaded file or paginate.
6. **`wait_for_selector` before li scan** — modest robustness gain in `deep_verify_all.py`.

### Defer / Monitor
7. Protobuf centralization — cleanup when touching entities.py for another reason.
8. Playwright OOM — monitor Railway logs; only act if crashes observed.
9. JSON schema validation between stages — add when a schema bug actually occurs.

---

## 6. Notes on What to Send Reviewer C (ChatGPT Web)
Send the zip + this doc. Ask specifically:
- Do you agree stopover negative deltas are passenger-count artifacts or genuine airline pricing?
- Review the `push_to_github()` archive growth issue — what's the right cap strategy for a GitHub Pages repo?
- Is there a way to make `find_flight_li` more robust without relying on `data-testid` (since Google obfuscates them)?

---

*Reviewer C (ChatGPT Web) response pending — to be added after user uploads zip to new chat.*
