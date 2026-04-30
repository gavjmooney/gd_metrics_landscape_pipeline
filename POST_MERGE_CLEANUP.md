# Post-merge cleanup

Run these once the refactor lands and the new pipeline has reproduced
the corpus end-to-end. They live here (not as a phase-12 commit)
because the existing `graph_generation/` tree under
`G:/My Drive/PhD Stuff/Effects of structure on layout/` was
declared read-only for the migration.

## Files to delete

```
G:/My Drive/PhD Stuff/Effects of structure on layout/
├── REFACTOR_PLAN.md                       # plan delivered; superseded by this repo
├── graph_generation/scripts/migrate_*.py  # one-shot migrations; history is in git
└── graph_generation/src/graph_generation/sources.py.pre-citations-bak
```

```
C:/Users/Gavin/Desktop/Effects of structure/output/
├── manifest.csv.pre-category-bak
├── manifest.csv.pre-classic-removal-bak
├── manifest.csv.pre-cooccurrence-removal-bak
├── manifest.csv.pre-dagmar-drop-bak
├── manifest.csv.pre-dedup-bak
├── manifest.csv.pre-ktree-fix-bak
├── manifest.csv.pre-sampling-bak
├── manifest.csv.pre-small-cleanup-bak
├── manifest.csv.pre-social-obs-merge-bak
├── manifest.csv.pre-source-bak
├── manifest.csv.pre-tudataset-rename-bak
└── manifest.csv.archive-2026-04-25-pre-dedup
```

Keep `manifest.csv.pre-refactor-bak` (taken at the start of this
refactor) until the new pipeline has demonstrably reproduced the
corpus. Then it can go too.

## Sankey counts

After a full new-pipeline run lands the final corpus numbers, update
the placeholders in
`paper/visualisations/sankey_pipeline.py` to match:

- `COHORT_STAGED` totals
- `TOTAL_FILTERED`, `TOTAL_SAMPLED`, `TOTAL_DEDUPED`
- `LAYOUT_DRAWINGS` per-algorithm counts
- `SUBSOURCE_REAL` per-source counts

## Old graph_generation/ tree

Once the new repo is producing the canonical corpus and all paper
artefacts have been regenerated from it, the old `graph_generation/`
package under the Drive-synced project root can be archived (move to
`graph_generation_archive_2026/` or remove entirely if git history is
sufficient).

## Verifying before deleting backups

The new pipeline should reproduce the existing corpus end-to-end. A
sufficient pre-deletion check:

```bash
EFFECTS_OUT=/tmp/check_repro pipeline run all
diff <(sort < /tmp/check_repro/manifest.csv | cut -d, -f1) \
     <(sort < /c/Users/Gavin/Desktop/Effects\ of\ structure/output/manifest.csv | cut -d, -f1)
```

(Modulo external-source counts that aren't byte-pinned — see refactor
plan §6.)

## When this file goes away

Delete `POST_MERGE_CLEANUP.md` once you've worked through the lists
above. Its only purpose is to keep destructive cleanup separate from
the refactor commits so it can be reviewed independently.
