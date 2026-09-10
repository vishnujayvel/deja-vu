# Stage 9 — Learn

The rubric only improves if verdicts get checked against what actually happened. This stage is
not part of a normal hunt — it runs on its own cadence, invoked deliberately (e.g. `/deja-vu
debrief`, or a periodic `/loop`), not as step 10 of every trigger.

## The debrief loop

For each entry in `data/decisions-registry.jsonl` old enough to have an outcome:

1. **If DEPEND/FORK/VENDOR**: did the adopted dependency survive? Was it abandoned, did a CVE
   land that changed the health picture, did the license change on you (a real and recurring
   risk), did the fence-check assumption hold or get violated by an update?
2. **If BUILD**: did the custom build prove necessary — or did prior art surface later that
   would have obviated it? Did the reversibility bet (Stage 6, point 6) turn out to be priced
   right?
3. **If NOT-A-PROBLEM/DIFFERENT-PROBLEM**: did the null solution or reframed problem actually
   hold up, or did the original need resurface later in a way that shows Stage 0 mis-scoped it?

Score each reviewed entry and append — never overwrite — to a calibration file,
`data/calibration.jsonl`:

```json
{"registry_id": "adr-3", "reviewed_date": "2027-01-20", "original_verdict": "DEPEND",
 "outcome": "survived | abandoned | license-changed | proved-unnecessary | vindicated | ...",
 "correct_in_hindsight": true, "notes": "<one paragraph, specific>"}
```

## What future hunts do with this file

Future Judge stages (`references/judge.md`) load `data/calibration.jsonl` as worked examples —
the same case-law pattern used by taste-calibration systems: not a rule, but a precedent to weigh
against. A judge scoring a candidate against a maintainer who has, per the calibration file,
abandoned two prior adopted dependencies should weigh the health dimension accordingly.

## The one hard rule

**This stage never edits `SKILL.md`, or any file under `references/`, on its own.** The
calibration file is evidence; a human reads it and decides whether the doctrine itself should
change. If a debrief surfaces a pattern strong enough to justify changing how the skill hunts —
"we keep under-weighting license changes post-adoption" — write that up as a proposal and hand it
to the human explicitly. Do not fold it into the router quietly because it seemed obviously
correct; that is the same rubber-stamp failure mode the Gate (Stage 7) exists to prevent, one
level up.
