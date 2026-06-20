# Scoring audit — "Photo session July 6 2026" (318 photos)

**Question:** how well does our scorer actually *choose* the best frame in a burst? We went through
every multi-photo group, looked at the real images, judged the true best keeper by eye, and
critiqued the algorithm's pick.

**Method:** 46 groups with 2+ photos (40×2, 5×3, 1×4 = 99 photos). One visual judgment per group
(a vision model looking at the actual frames, prompted to judge as a portrait photographer and to
hunt for wrong picks), plus 3 groups hand-verified directly (grp 35, 96 = picks correct; grp 238 =
miss confirmed). Caveats: it's one shoot (a male model — lots of sunglasses + deliberate
look-away candids, a hard case for an eyes-first scorer); "best frame" is partly subjective;
judgments are at preview resolution; the judge itself is fallible.

## Headline

| Metric | Result |
|---|---|
| Groups where algo pick = human pick | **33 / 46 (72%)** |
| Misses (human would pick differently) | 13 / 46 |
| **Misses that are sunglasses portraits** | **11 / 13** |
| Misses with visible eyes | 2 / 13 (grp 60, 103 — both *close* expression calls, not blunders) |
| Clear, high-confidence blunders | 3 (grp 5, 235, 238) — **all sunglasses** |
| Picks the judge rated "close" or "toss-up" | **24 / 46 (52%)** |

The 72% is misleading on its own. The real story: **the scorer is reliable when it can see the
eyes, and falls apart when it can't.** Almost every miss is a sunglasses shot.

## Failure mode #1 — sunglasses break the scorer (the big one)

Eye signals carry ~half the score: **focus (0.26)** is driven mostly by eye/face sharpness, and
**subject (0.27)** is eyes-open + smile + gaze. When the subject wears sunglasses:
- `eyes_open`, `eye_sharpness`, `eye_contact` become **noise** — they measure the sunglass lens or
  default to 0.0/0.5. The scorer doesn't *know* the eyes are hidden, so it still uses them as
  tiebreakers.
- That routinely drives the wrong pick. Verified example — **grp 238**: the algorithm chose
  `3E4A9030` (subject **walking away, back to camera**) over `3E4A9035` (front-facing, hand in
  pocket, engaged) — because it gave the back-view a phantom `eye_sharpness` 0.31 vs 0.04 and
  `eyes_open` 0.5 vs 0.0 (it read the sunglasses on the *front* frame as a blink).
- **grp 5** (3-frame): picked the flat, disengaged frame (expression axis 0.05) and ranked the only
  genuinely smiling frame (expression 0.52) **last** — the classic "sharper-but-worse-expression"
  inversion, caused by eye-sharpness dominating on a shot where eyes aren't visible.
- Same pattern in grp 56, 80, 91, 174, 179, 189, 215, 235, 242.

**Fix (highest leverage — addresses 11/13 misses):** detect eye occlusion (sunglasses / closed /
not-found) per face, and when eyes aren't usable, **zero out the eye axes and re-weight the score
onto expression + pose/engagement + framing + sharpness-of-face.** Even a crude "no eyes detected
behind the glasses → drop eyes_open/eye_sharpness/eye_contact" gate would flip most of these.

## Failure mode #2 — the aesthetic head is erratic and grade-sensitive

The LAION aesthetic axis swings wildly (0.0 ↔ 0.9) and reacts to **color grade/warmth**, not
subject quality. It nearly flipped grp 0 (a warmer edit gave the worse-expression frame aesthetic
0.90 vs 0.63), and it *did* swing the wrong pick in grp 179 (0.915 vs 0.324) and grp 235
(0.554 vs 0.231). On near-ties it's effectively a random tiebreaker. **Fix:** down-weight it,
or recalibrate per-session, or only let it break ties beyond a margin.

## Failure mode #3 — reason labels are unreliable

"eye contact" / "smiling" fire on frames where the subject is looking **away or up**. Verified in
grp 35 (frame craned straight up at the sky tagged "smiling, eye contact") and grp 60 (the
look-away frame scored *higher* on eye-contact than the forward one). Even when the final pick is
right, wrong reasons erode trust. **Fix:** tighten the frontal/gaze thresholds behind these labels.

## Failure mode #4 — no confidence signal

**52% of picks (24/46)** are near-ties the judge called "close" or "toss-up" — overall gaps of
0.005–0.02. A 0.640-vs-0.634 "pick" is presented identically to a clear winner. **Fix:** surface a
confidence / "too close to call — you decide" flag when the top-2 gap is small, so the human knows
exactly where to spend attention. This also directly answers the photographer's trust concern.

## Where the scorer is genuinely good

When eyes are visible and there's a real expression difference, it picks well and resists the wrong
lure: grp 0/2/6/11/15 it correctly preferred genuine smiles over pursed/awkward mouths; it
correctly demoted looking-down/away frames (grp 96's `068A1011`, subject looking at his hands,
subj=0.09); the blink penalty works. The two non-sunglasses "misses" (grp 60, 103) are close
expression calls, not errors. So the core ranking logic is sound — it's specifically the
**eyes-not-visible** case and the **aesthetic-head noise on near-ties** that hurt.

## Context / honest caveats

- This shoot is unusually adversarial for an eyes-first scorer: a male model doing fashion/lifestyle
  poses, frequently in sunglasses and frequently looking away on purpose. The photographer's actual
  domain (family/portrait) will have **far fewer sunglasses**, so the headline 28% miss rate likely
  *overstates* the impact on her typical work — but the sunglasses blind spot is real and will bite.
- Notably, this contradicts the photographer's general prior ("AI only keeps sharp frames, discards
  atmospheric blur"): our scorer did **not** over-reject soft/blur frames here. Its real weaknesses
  are different and more fixable — eye-occlusion handling and a noisy aesthetic head.

## Recommendations (priority order)

1. **Eye-occlusion gate** (sunglasses/closed/not-found) → drop eye axes, re-weight to
   expression/pose/framing. Fixes 11/13 misses. *Biggest win.*
2. **Tame the aesthetic head** — down-weight / recalibrate; don't let it flip near-ties.
3. **Surface a confidence flag** on close calls (top-2 gap small) — half the picks are near-ties.
4. **Tighten reason-label thresholds** (eye-contact/smiling) for trust.
5. Re-run this audit after #1–#2 to measure the lift (the harness is reusable).

---

# Fixes applied + measured lift (2026-06-15)

Implemented all four, re-analyzed the full 318-photo gallery with the patched pipeline, and
compared the new picks against the human picks from the audit above (same bursts — grouping is
score-independent so membership is identical).

**Changes** (`pipeline/`): (1) CLIP zero-shot **sunglasses detector** (`models.py`/`analyze.py`,
`eyes_occluded` when score ≥ 0.6) → when eyes aren't visible, scoring drops eye-sharpness +
eyes-open and re-weights focus onto face-sharpness and subject onto smile + camera-facing
(`score.py`). (2) **Aesthetic head damped** (weight 0.10→0.06, values shrunk 0.6× toward 0.5) so it
can't flip near-ties. (3) **`close_call` flag** per burst when the top-2 gap < 0.04
(`pipeline_runner.py` → store/views). (4) **Tightened reason thresholds** + suppressed eye-based
reasons when occluded.

**Detector quality:** 0.95 / 0.85 on known sunglasses frames, 0.01–0.03 on bare eyes — clean
separation; flagged 19 bursts as eyes-occluded with no clear false positives.

**Result (read past the headline):**
- Raw agreement **33/46 → 34/46**. *This number is the wrong metric* — ~half the bursts are
  near-identical frames the human judge themselves called "close/toss-up", so flipping them is noise
  either way.
- **7 misses fixed to the human pick** — including the two most egregious from the audit:
  grp 238 (was picking the subject **walking away, back to camera** → now the front-facing frame)
  and grp 5 (was burying the only **smiling** frame → now picks it). Also grp 56, 80, 103, 179, 189.
- **6 previously-correct picks flipped — but ALL 6 are flagged `close_call`** (gaps ≤ 0.037, one a
  literal 0.000 tie; grp 136 verified by eye = near-identical walking frames). No clear,
  eyes-visible pick regressed.
- **`close_call` now fires on 28/46 bursts (61%)** — covering every "regression" and 4 of the 5
  remaining sunglasses misses. The cases where the scorer is unreliable are now **surfaced for the
  human** rather than presented as confident picks. This is the real win for assist-don't-decide.
- One genuine high-confidence residual: **grp 242** (wide architectural framing vs subject-as-hero)
  — a composition-philosophy call the human judge themselves called "defensible".

**Takeaway:** the eye-occlusion gate eliminates the corrupted-eye-signal failure mode (confident-
wrong on sunglasses → either correct or flagged), and the confidence flag catches the residual
ambiguity. Deliberately did **not** keep tuning thresholds to push raw agreement higher — that
would overfit a noisy 46-sample reference from one (sunglasses-heavy, male-model) shoot. Real
validation needs a **family/portrait shoot** (the photographer's actual domain, far fewer
sunglasses) — re-run the harness there.
