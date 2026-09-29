# Atom Integration Apply Notes

## On GitHub after this commit
- `services/__init__.py`
- `services/atom_appraisal_service.py` (main module)
- `services/atom_appraisal_core.py` (re-export)
- `test_atom_appraisal.py`
- `.env.example` Atom vars

## Local steps
```bash
git pull origin main
python3 -m pytest test_atom_appraisal.py -q
```

## Env
```
ATOM_ENABLED=true
ATOM_API_TOKEN=
ATOM_USER_ID=
ATOM_MAX_APPRAISALS_PER_RUN=25
ATOM_CACHE_TTL_HOURS=24
ATOM_RANK_WEIGHT=0.12
```

Pipeline position: after learning, before diversity in Stage 9.
Scheduler/UI patches may need a follow-up commit if not present.
