# Decision block 6 — draft (Session 4)

> Drafted in S4 for inclusion in `02_main.ipynb` (Cleaning & structuring section).
> The crosswalk it documents is built by `sudan_displacement.data.build_admin1_crosswalk()`
> and pinned to `data/processed/admin1_crosswalk.csv`. Paste the markdown and
> code cells below into the notebook; the prose is final.

---

### Decision: Admin-1 boundary reconciliation — one crosswalk for three naming systems

**Problem.** The violence layer (ACLED), the internal-displacement layer (IOM DTM)
and the polygon basemap (GADM 4.1) each label admin-1 units with a different
convention. ACLED uses spaced English names (`North Kordofan`, `Al Jazirah`);
DTM uses OCHA names plus pcodes (`Aj Jazirah`, `SD01`–`SD18`); GADM uses BGN/PCGN
romanisation with no spaces (`NorthKurdufan`, `AlQadarif`). Nothing downstream
works until these agree: the violence and displacement layers cannot be joined
to the same polygon, and neither can be drawn on the choropleth. A careless join
fails *silently* — ACLED's `Gedaref` simply never matching GADM's `AlQadarif`
would zero out an entire state rather than raise an error.

**Diagnostic.** Exact-string match rate against GADM `NAME_1`, then the rate
after normalisation (strip accents, spacing, casing; bridge the known
`Kurdufan`↔`Kordofan` and `Aj`↔`Al Jazirah` token splits).

```python
from sudan_displacement.data import build_admin1_crosswalk, crosswalk_unmatched_acled

crosswalk = build_admin1_crosswalk()
crosswalk.groupby(["country", "match_method"]).size().unstack(fill_value=0)
```

The diagnostic surfaced four things:

- **Sudan:** 4/18 match exactly, 17/18 after normalisation. Two real gaps —
  `Gedaref`/`AlQadarif` (genuinely different romanisations, no shared
  normalised form) and **Abyei**, which ACLED reports as a 19th Sudan admin-1
  unit but which has no GADM polygon and no DTM pcode (it is a disputed
  Sudan/South Sudan territory).
- **Neighbours:** Central African Republic 17/17 and Chad 21/21 reconcile on
  normalisation alone (the residue was pure diacritics); South Sudan needs a
  handful of romanisation overrides; **Ethiopia** reconciles only 10/14 because
  GADM 4.1 predates Ethiopia's 2020–2023 regional reorganisation (Sidama, South
  West, and the Central/South Ethiopia split from SNNPR did not yet exist);
  **Egypt** reconciles 2/27 — ACLED and GADM use entirely incompatible
  governorate romanisations.
- **GADM `HASC_1` is unusable as a key:** North Kurdufan and West Kurdufan both
  carry `SD.KN`. `GID_1` is the only unique GADM key.
- Abyei is **181 ACLED events (1.09 %) and 515 fatalities (1.15 %)** of Sudan's
  totals — small, but not nothing.

**Options considered.**
- (a) **Exact string join.** Rejected — only 4/18 in Sudan; would silently void
  14 states.
- (b) **Fuzzy / edit-distance matching.** Rejected — opaque, and unsafe here:
  `North Kordofan` and `South Kordofan` differ by a single token, so an
  edit-distance threshold loose enough to catch real variants is also loose
  enough to cross-wire neighbouring states.
- (c) **Normalisation + a small hand-audited override table, keyed on OCHA
  pcodes.** Chosen.

**Decision.** Build a deterministic crosswalk (`admin1_crosswalk.csv`, one row
per GADM polygon): normalise names, then resolve the few irreducible
romanisation gaps with an explicit, auditable override table. The canonical key
is the **OCHA pcode `SD01`–`SD18`** for Sudan — it is also DTM's key and the
humanitarian-sector standard — and GADM `GID_1` for the neighbours. **Abyei**'s
ACLED events are folded into **South Kordofan**, the Sudan state Abyei was
administratively carved out of and the one it most directly adjoins (merging
into a Darfur state, as a naïve alphabetical fallback might, would inflate a
state Abyei does not even border). **Egypt's** admin-1 units are deliberately
left unreconciled: Egypt's role in this analysis is a refugee *destination*,
joined at country level (Decision D3), and no deliverable uses its admin-1
violence detail — hand-romanising 27 governorates would be effort without
downstream value. Result: **Sudan reconciles 18/18**, every state carrying a
pcode, an ACLED name and a DTM name.

**Sensitivity.** The headline figures combine violence and displacement on
Sudan's 18 states, and that reconciliation is *exact* (18/18) — the main finding
rests on no judgement call in the join itself. The one judgement is the
Abyei → South Kordofan merge; at 1.1 % of Sudan events its effect on any state's
counts is marginal, and the merge is re-run against the drop-Abyei alternative
in `03_robustness.ipynb`. Ethiopia's 4 unmatched regions and Egypt's
unreconciled governorates touch only neighbour-side admin-1 detail, which never
enters a headline figure — neighbours appear only at country level (the
origin-destination chord diagram and the UNHCR cross-border layer).
