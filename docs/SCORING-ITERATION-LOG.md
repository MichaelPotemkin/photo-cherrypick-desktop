# Scoring improvement — iteration log

Goal: iteratively improve the burst-pick quality of the scorer. Running log; newest iterations
appended at the bottom.

## Methodology (and its honest limits)

- **No real human ground truth exists yet** (the photographer hasn't rated our picks). So the
  reference is a **proxy**: a 3-lens judge panel (technical / expression / deliverable), independent
  agents per group, majority vote → `eval/reference_panel.json`. Diverse lenses reduce single-model
  bias, but this is still AI judging AI — treat agreements as a *signal*, not proof. Cross-checked
  with my own spot-checks on contested groups.
- **Fast offline harness** (`eval/rescore.py`): re-scores the cached per-photo metrics
  (`/tmp/eval_metas.json`, 318 photos / 46 multi-photo bursts) with no torch and no re-analysis, so
  a scoring-formula change is testable in milliseconds. Burst membership is fixed (score-independent),
  isolating *pick* quality. Verified to reproduce production picks 46/46.
- **Primary metric:** agreement with the panel on **consensus groups** (panel unanimous/majority),
  and separately on **panel-unanimous** groups (highest-confidence subset). Near-ties where the
  panel splits are excluded — flipping those is noise.
- **Anti-overfitting:** changes must be *principled* (a named failure mode), not threshold-fishing to
  match this one sunglasses-heavy male-model shoot. Real validation = a family/portrait shoot later.
- Formula-only changes use the harness (fast). New CLIP-probe features need a torch re-analysis
  (~3 min) — batched.

## Hypothesis queue (prioritized)

Fast (formula-only, harness):
1. **Burst-relative pick score** — decouple the in-burst pick from the cross-group `overall`. Within
   a near-identical burst, exposure/color/aesthetic are ~constant and only add noise; the
   decisive axes are eyes (open+sharp), expression, face sharpness, pose. Rank the pick on those.
2. **Subject-prominence guard** — penalize tiny-subject/background-dominant frames (grp 242 "scored
   the building, not the man") using `face_frac`.
3. **Drop aesthetic from the pick** entirely (keep for cross-group ordering) — it's the noisiest axis.
4. Weight/threshold sensitivity checks.

Needs re-analysis (new CLIP probes, batch):
5. **Facing-camera vs back-to-camera** probe (more reliable than geometric `frontal`; grp 238).
6. **Eyes open vs closed/squint** probe (replace noisy Haar eye count when eyes are visible).
7. **Awkward/mid-word mouth** negative probe (grp 2, 91 awkward-expression cases).

## Baseline (vs 3-lens panel, 46 groups: 26 unanimous / 20 majority / 0 split)
**28/46 (61%)** overall · 17/26 (65%) unanimous · 11/20 (55%) majority.
Most misses are near-ties (gap ≤0.02 — coin flips; matching the panel there is luck). The signal is
**confident misses** (algo gap ≥0.04, panel consensus, wrong): g196 (0.092, una), g91 (0.07, una),
g39 (0.068, maj), g97 (0.067, maj), g74 (0.046, una). These are the principled targets.

## Iterations

### Iter 1 — burst-relative pick score (REJECTED)
Decouple in-burst pick from cross-group `overall`, emphasizing eyes/expression/face-sharpness.
Result: 27/46 (−1). Fixed g35 but broke g42/g108/g140/g168/g204 (over-weights smile → picks
laughing-but-looking-away frames, e.g. g42 1198→1200). Kept behind `PICK_SCORE` flag, default OFF.

### Iter 2 — saturating sharpness (KEPT, now default) + subject-prominence (dropped)
Hypothesis (from confident misses g91/g39/g97): portrait sharpness has **diminishing returns** —
past "acceptably sharp," more sharpness shouldn't keep adding score, yet linear `eye_sharp/EYE_REF`
let a sharper-but-worse-moment frame win. Fix: `_sat = sqrt` compression on eye/face sharpness.
**Result: 28→30/46 (61%→65%)**, unanimous 17→18, and it shrank every confident-miss gap
(g91 .07→.05, g97 .067→.055, g39 .068→.05). One new near-tie miss (g38, gap .007). **Promoted to
default** (`SHARP_SAT=0` restores legacy).
Subject-prominence haircut (SUBJ_PROM, for g196 background-over-subject): +0 agreement, halved the
g196 gap but risks demoting legitimate wide shots in cross-group ordering → **left OFF**.
pick_score re-tested on top of sharp_sat: still −3 → confirmed rejected.

Remaining after iter 2: 16 misses, but **11 are flagged `close_call`** (gap <0.04 — human decides);
only **5 confident misses** (g39, g74, g91, g97, g196). g74 is occluded (panel wants the more
front-facing frame) → motivates a CLIP facing-camera probe (iter 3); g91/g39/g97 are very subtle
sharper-vs-moment calls (chasing them risks overfitting one shoot).

### Iter 3 — CLIP facing-camera probe (REJECTED, +0)
Added a CLIP front/back probe to replace the unreliable geometric `frontal` in the occluded
orientation term (geometric `frontal` alone tested −1: it reads a back-of-head as frontal). Result
**30/46 (+0)** — the eye-occlusion gate already handles the one back-of-head case (g238), so facing
is redundant on this shoot. Removed to keep the pipeline lean (it costs a CLIP probe per face).

### Iter 4 — CLIP eyes-open probe (REJECTED)
Continuous CLIP "eyes open vs blink" to replace the coarse Haar 0/1/2 count in the subject term.
Result: replace **27/46 (−3)**, blend **28/46 (−2)** — the CLIP probe is noisier than the Haar
count here. Removed.

### Iter 5 — calibrate the `close_call` confidence flag (KEPT)
Data-driven: pick reliability vs the panel by gap bucket — [0,.02)=58%, [.02,.04)=75%,
[.04,.06)=**56%**, [.06,1)=83% (non-monotonic: the subtle confident misses live in [.04,.06)).
Raising the flag threshold **0.04 → 0.05** cuts confidently-wrong *unflagged* picks from 5 → 2
(flag-rate 67%→78%). High flag-rate is honest on a shoot of near-identical bursts ("both are good,
you decide"). Locked in `desktop_core.pipeline_runner._CLOSE_GAP`.

### Independent validation of SHARP_SAT (guard vs reference-overfitting)
SHARP_SAT changed exactly 4 picks. A **fresh, independent** 3-judge head-to-head (different judges,
blind to scores, not the reference panel) on those 4: **g30, g35, g141 → confirmed improvements;
g38 → confirmed regression** — identical verdict to the reference panel. So the +2 is a real
quality gain, not fitting the panel I tuned against. g38 (the one regression) is a flagged
`close_call` near-tie (gap 0.007) → the human decides it regardless.

### ★ First REAL-human validation (not a proxy)
The user culled the gallery in the app. In the multi-photo groups where they favorited exactly one
frame (8 so far), the scorer's `suggested` pick **matched the user's actual favorite 7/8 (88%)** —
one mismatch (g70, a near-tie). Small sample, but this is the first non-AI ground truth, and it's
*higher* than the AI panel's 65%, implying the diverse panel was stricter on near-identical frames
than the real photographer. Re-run as more decisions accumulate:
`python3 -c "..."` over `decisions` vs `analyses.suggested` (see the validation query).

## Summary
**Net: one validated scoring win (saturating sharpness, +2 / +4pp vs the panel) on top of the
earlier eye-occlusion gate; plus a data-calibrated confidence flag.** Four other ideas
(burst-relative pick, subject-prominence, geometric/CLIP facing, CLIP eyes-open) were tested and
**rejected on the evidence** rather than shipped on intuition. Deliberately stopped formula-tuning
once changes stopped clearing the bar — further gains on this single sunglasses-heavy male-model
shoot would be overfitting. Final harness state: 30/46 (65%) panel agreement, but most residual
misses are flagged near-ties; ~2 genuinely confident errors remain (g91 subtle, g196 hard).
**Real next step is breadth, not depth: a family/portrait shoot + the photographer's own picks.**
Locked in with regression tests (`tests/test_scoring.py`); reusable harness (`eval/`).

---

## Scene grouping (second-pass mode) — 2026-06-18

Added a **second grouping mode** alongside the existing burst grouping. Burst answers "which frames
are near-duplicate shots of the same instant?" (tight time gate) — the first culling pass. **Scene**
answers "of the keepers I have left, which belong to the same look — same setting, same outfit?"
(no time gate) — the second pass, for assembling an Instagram/gallery set and picking the best per
look. `pipeline/scene_group.py`; exposed as `GET /api/sessions/{id}/groups?mode=scene`, computed
on demand from stored embeddings (no schema change, no re-analysis), trashed photos excluded.

### Why mean-centering is the load-bearing step
For a single-subject studio shoot, raw CLIP embeddings are crammed into a narrow high-cosine band
(audit shoot: pairwise cosine min 0.53 / **median 0.80** / p90 0.87) because the same person in the
same studio dominates every vector — a raw global threshold can't separate looks (T=0.82 lumps 228
of 318 photos into one cluster). Subtracting the session-mean embedding and re-normalizing strips
that shared component; the centered pairwise cosine spreads to **−0.25..0.28** and actually
discriminates scenes. Greedy nearest-centroid clustering (O(n·k), deterministic, no K) over the
centered vectors.

### Threshold calibrated with a vision-judge panel + the fragmentation knee
Swept T∈{0.35,0.45,0.55} on the real shoot; 8 sampled clusters/threshold judged by independent
vision agents for coherence ("is this one look?"), plus over-split checks on the closest cluster
pairs:

| T | scenes | coherentRate | avgOutlierRate |
|---|--------|--------------|----------------|
| 0.35 | 29 | 0.75 | 0.15 |
| 0.45 | 55 | 0.75 | 0.09 |
| **0.55** | **93–101** | **0.88** | **0.06** |

Coherence rises monotonically and peaks at **0.55** (over-split signal was flat/uninformative — it
only ever samples the closest pairs). 0.55 is **also the fragmentation knee**: past it singleton
scenes explode (~35→64 on the 253-keeper set) without buying coherence. Both lines of evidence
converge → default `SCENE_SIM=0.55` (centered space; env-tunable). **Caveat:** tiny audit sample
on one male-model/portrait shoot — re-validate on a family/portrait shoot, and probing T>0.55 is the
honest next step the panel flagged. Regression tests in `tests/test_grouping.py` (merge-across-time,
no-chaining) + e2e in `tests/test_server_e2e.py` (keepers-only, trash excluded, bad-mode 400).

### Robustness fix from adversarial review — `SCENE_CENTER=0.95` (mean shrinkage)
A 3-lens adversarial review (backend/frontend/UX, each finding then independently verified) caught a
degeneracy in **full** mean-centering: a frame at the set centroid — an exact/near-duplicate of the
average, or a duplicate group whose members *are* the mean — centers to the zero vector, whose
normalized direction is pure noise, so it never matches a centroid and is forced into a spurious
singleton. Fix: subtract **0.95×** the mean instead of 1.0×, leaving a tiny raw component so such
frames keep their direction and merge. An α-sweep confirmed this is the right knob: aggressive
shrinkage (α≤0.7) re-introduces the single-subject mega-cluster (top cluster 41 at α=0.6), but α=0.95
keeps the vision-validated distribution essentially identical (88 vs 91 scenes, same multi-scene
structure) while folding ~3 spurious centroid-singletons back in and merging exact/near duplicates
(`exact-dup4 → [4]`). Threshold stays 0.55. The review also fixed a **high-severity frontend bug**:
optimistic header counts were recomputed from the (keeper-only) scene cache, collapsing the trash
count to ~0 on the first decision — replaced with a mode-agnostic delta on the server's authoritative
counts + invalidate-on-settle (verified live: favoriting a maybe in scene mode keeps trash at 65).
Plus: `close_call` now computed for scenes (consistent with the shown best-frame pick), and the
singleton label is "unique look" (not the burst "single shot").

---

## Multi-face / group-aware subject scoring (2026-06-19)

Closed the two standing TODOs (`faces.py` single-largest-face; `score.py` subject-aware). Now:
`detect_faces` returns ALL prominent faces (bystanders below 0.15× the largest face's area dropped,
capped at 4); `analyze` computes per-face subject signals into `meta["faces"]` + `n_faces`;
`score.py` subject = **0.5·mean + 0.5·min** over per-face subject scores — a blinking/averted child
tanks the `min`. One face ⇒ mean==min, so **solo scoring is byte-identical** (existing tests pass,
plus new `test_group_subject_*`). Detection works: 124/186 family frames get ≥2 faces.

### Honest result: NET-ZERO on the proxy, and we now know why
Re-analyzed the family shoot and re-scored against the SAME 40 blind-judge picks (grouping is
unchanged — same 40 bursts). Agreement **55% → 55%**; the group fold flipped **8/40** picks but
**2 went right, 2 went wrong, 4 lateral** — a wash. The single-largest-face hypothesis was real but
NOT the binding constraint on this shoot. The actual blockers, diagnosed from the data:
1. **Face-detection misses — the #1 issue.** 21/186 frames detect ZERO faces (e.g. g100's judge pick
   068A0929 — a laughing child the detector missed → scored as faceless 0.247). Scoring can't pick a
   frame where it sees no subject.
2. **Eye-detection insensitive to a child's squint** — Haar `eye_open_count` returns eyes=2 for the
   child in both a squinted and an open frame, so the per-face blink signal never fires.
3. **Focus dominates subject in close calls** — e.g. g58 subject correctly favors the judge's frame
   (0.217 vs 0.204) but a focus gap (0.99 vs 0.73) keeps the old pick. Subject is 0.29 of the weight.
4. **The min-fold over-penalizes INTENTIONAL closed eyes** (parents kissing the child) — 2 of the
   regressions trace to this.

**Decision: KEPT the change** — it's correct, zero-regression for solo, the requested capability
("judged on all faces in the image"), mechanically proven by the unit test, and the right foundation
(`meta["faces"]` now exists). But it does NOT move the family metric yet. **The real next lever is
detection recall**, not aggregation — improving YuNet recall (higher-res detect, lower conf
threshold, full-res pass) so the child is actually found. Did NOT tune the fold to chase this one
shoot (overfitting). Still AI-proxy; her real picks remain the ground truth to get.

---

## Iteration A — face-detection recall (2026-06-19, /goal)

Diagnosis from the group-aware work: the binding constraint on family picks is DETECTION, not
aggregation (21/186 frames found 0 faces). Made both detector knobs env-tunable and bumped defaults:
`DETECT_MAX 1024→1920` (faces.py) + `YUNET_SCORE 0.7→0.6` (models.py). Swept first: resolution alone
(thr 0.7) recovered faces with ZERO control false-positives; 1920 beat 2560 (model degrades past it);
thr 0.6 added a little more recall. Re-analyzed the family shoot: zero-face 21→19, and 11 frames now
find the additional subject — **visually verified real** (mother-in-profile + child, incl. the
previously-faceless laughing-child 068A0929 that was a judge pick). No false positives observed.

**Honest result: detection is more correct, but agreement is STILL 55%.** Recovering the faces didn't
flip the picks because the *other* bottlenecks bind: focus (0.28) + composition (0.16) outweigh
subject (0.29) in near-identical family bursts, and Haar eye-open is insensitive to a child's squint.
KEPT it anyway — it's strictly-more-correct detection (verified), zero observed downside, and the
right foundation. But this is now TWO scoring/detection levers (multi-face, detection) that don't move
the family proxy → the metric is bottlenecked deeper, and the real unlock is the photographer's actual
labels, not more proxy-tuning on one shoot. Pivoting the remaining /goal iterations to other product
improvements (robustness, features) rather than overfitting this shoot.
