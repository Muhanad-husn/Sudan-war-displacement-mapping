# Notebook structure

Each project's main analysis notebook should read top-to-bottom **as a lab notebook / short paper**, not as a code dump. The audience is a recruiter or a fellow analyst who wants to see *how decisions were made*, not just what they were.

The brand is **balance practicality vs. perfectionism**. Every meaningful data-processing decision is *educated by analysis*, not chosen by convention.

## The decision discipline (core)

**Every meaningful data-processing decision** — cleaning, imputing, transforming, categorizing, feature engineering, outlier handling, threshold setting, aggregation, deduplication — must be presented in **five parts**:

1. **Problem / choice point.** What needs to be decided and why it matters for the analysis downstream.
2. **Diagnostic analysis.** Actual code that explores the data to inform the choice — distributions, missingness patterns, comparisons across candidate options. Use the helpers in `src/<project>/diagnostics.py`.
3. **Options considered.** At least 2–3 reasonable alternatives, named explicitly.
4. **Decision + rationale.** What we chose, and why this option, anchored in the diagnostic finding above (not in convention).
5. **Sensitivity** (where applicable). How much does the final result depend on this choice? Show a robustness check, or explicitly note that the question is not sensitive to this choice.

This block belongs **inline in the notebook**, in markdown, immediately preceding the code that implements the decision.

### Decision-block template

Copy-paste this as a markdown cell at every choice point:

```markdown
### Decision: <one-line name of the decision>

**Problem.** <Why is this a choice? What goes wrong if we pick badly?>

**Diagnostic.** <One sentence framing.>
```

```python
# Code cell — actual diagnostic analysis using diagnostics.py helpers
from sudan_displacement.diagnostics import missingness_summary
missingness_summary(df)
```

```markdown
**Options considered.**
- (a) <Option A — one line>
- (b) <Option B — one line>
- (c) <Option C — one line>

**Decision.** <The option we picked.> <One-sentence rationale anchored in the diagnostic.>

**Sensitivity.** <Either: result was robust to alternative X (see `03_robustness.ipynb`). Or: not sensitive — choice affects only intermediate counts, not the headline finding. Or: N/A — this is a definitional choice with no quantitative outcome.>
```

### What counts as a "meaningful" decision

Yes, document:
- Missing-value handling (drop / impute / flag)
- Outlier handling (drop / cap / keep)
- Categorical binning / regrouping
- Feature engineering (any constructed variable)
- Thresholds (event detection cutoffs, classification thresholds)
- Joins where keys don't perfectly align
- Deduplication rules
- Aggregation level choices (admin-1 vs. admin-2, weekly vs. monthly)
- Survey weight application
- Train/test/validation split strategy

No, don't document:
- Mechanical type conversions (`int → float` for arithmetic)
- Trivial renames or column selection
- Display formatting

When in doubt: document. The cost of an extra decision block is tiny; the cost of an undocumented load-bearing decision is catastrophic.

## Required sections, in order

### 1. Title + one-line hook
Markdown cell. Same as the README title. One sentence stating the question.

### 2. The question
Markdown cell, 2–4 sentences: why this question matters, what we're going to find out, what we're **not** trying to do.

### 3. Data
Markdown cell describing each dataset (URL, access date, granularity, time coverage, caveats). Code cell that loads everything via `src/<project>/data.py`.

### 4. Cleaning & structuring
**This is where the decision discipline lives most heavily.** Every cleaning / imputing / categorization step gets the five-part block above. Use `diagnostics.py` helpers for the diagnostic cells.

### 5. Feature engineering (where applicable)
Each engineered feature gets the five-part treatment: what is it, why this construction, what alternatives, what sensitivity.

### 6. Analysis
The actual analytical work. Break into subsections by analytical step. Each subsection: markdown framing → code → output → 1–2 sentence interpretation.

### 7. Hero figure
The single figure that, on its own, conveys the main finding. Saved via `viz.save_figure(fig, "hero")` to `figures/hero.png`.

### 8. Findings
3–5 bullets. Each one a **falsifiable statement** with a number where possible.

### 9. Limitations
Honest about: data gaps, methodological choices that could be defended differently, alternative explanations we couldn't rule out.

### 10. Decisions summary table
At the end, a single markdown table summarizing every decision made — for readers who want the methods overview without scrolling through every diagnostic:

```markdown
| Decision | Chose | Why (anchored in diagnostic) | Sensitivity |
|----------|-------|------------------------------|-------------|
| Missing 2020 imputation | Linear interp 2019↔2021 | Missingness pattern shows reporting gap, not data-quality issue | Carry-forward changes magnitude ±1.2pp; pattern unchanged |
| ... | ... | ... | ... |
```

### 11. Reproducibility
How long does the notebook take to run? Dependencies? Where does the data come from?

## Notebook file conventions

- `01_explore.ipynb` — first-pass EDA, ugly, exploratory. Lives in `notebooks/_scratch/` (gitignored).
- `02_main.ipynb` — the polished analysis notebook (THE deliverable). Lives in `notebooks/`.
- `03_robustness.ipynb` (optional) — sensitivity analyses for the major decisions, referenced from `02_main`.
- Specialized sub-analyses can be added: `04_pipeline_eval.ipynb`, etc.

## Output discipline

- Keep notebook outputs **committed** — they are part of the GitHub-rendered deliverable.
- Strip large/binary outputs (> 200 KB) by saving them as files in `figures/` and referencing with `![](figures/foo.png)` instead.
- Clear cell-execution-counts before the final commit (`Kernel → Restart & Run All`, then save).
