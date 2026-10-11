# AGENTS.md: JEV file locations and dataclass/enum placement

## What and why

`AGENTS.md` never mentions JEV, though JEV now spans `vidbyte/agents/jev/`, `vidbyte/lib/jev/`, `jev.py` modules in `lib/dataclasses`, `lib/enums`, and `lib/constants`, a runner, a provider adapter, pricing, a prompt family, two skills, and tests. An agent working on JEV has to rediscover that layout every time.

The dataclass and enum rule exists only as one soft sentence at the end of each folder entry ("Adding a new typed shape here ... is the expected discipline"). New code keeps defining dataclasses and enums inline next to their consumers. `AGENTS.md` is also the input to the `AGENTS.md placement` workflow (`.github/prompts/agents-md-placement.md`), which moves PR code only when `AGENTS.md` *clearly* names a different home. The current wording is too soft for that bot to act on.

## How

Edit `AGENTS.md` only:

1. **Map preamble.** Add one sentence saying the new Placement Rules section is prescriptive and binding, unlike the rest of the Map (which is lossy and descriptive).
2. **New `## Placement Rules` section before `## File Index`.**
   - Dataclasses: every new dataclass goes in `vidbyte/lib/dataclasses/<domain>.py`, public or private. No `types.py`/`records.py`/`models.py`/`schemas.py` next to consumers. If a dataclass needs a higher-layer type, move the contract down rather than the dataclass up (matches lint rule A006's fix guidance). Two named exceptions: `*Settings` agent configuration objects, and JEV preflight question subclasses.
   - Enums: every new `Enum` subclass goes in `vidbyte/lib/enums/<domain>.py` and public ones are exported from `vidbyte/lib/enums/__init__.py`. No exceptions.
   - Existing code: out-of-place definitions on `main` predate the rule. They are not precedent, may be edited in place, and are moved only in their own PR. This keeps the placement bot from relocating untouched legacy classes when a PR merely edits them.
3. **New `## JEV File Locations` section.** A table from each JEV concern to its path, plus where new JEV pieces go (a new record, enum, constant, preset, or prompt).
4. **File Index.**
   - Add `##### vidbyte/agents/jev/` and `##### vidbyte/lib/jev/` entries in the existing prose style.
   - Point the `lib/dataclasses/` and `lib/enums/` entries at Placement Rules.
   - Correct the `lib/constants/` entry, which says the folder holds only runner identifiers; it also holds `jev.py`.

## Files changed

- `AGENTS.md`
- `docs/design/agents-md-jev-and-type-placement.md` (this doc)

## Risks and open questions

- **Private dataclasses.** The rule covers underscore-prefixed dataclasses too, for maximum clarity to the bot. If module-private state records should be allowed inline, the rule needs a third exception.
- **Bot behavior.** Stricter wording means the placement workflow will relocate new inline dataclasses and enums in future PRs. That is the intent, but it will produce bot commits on PRs that previously passed silently.
- **Drift.** The JEV table names files. It will drift as JEV grows, like the rest of the Map.

## Verification

- Every path and symbol in the JEV table checked against `origin/main` (`git ls-tree`, grep for class names).
- `python scripts/run_ci.py --stage source`, the same gate CI runs. `AGENTS.md` is not parsed by lint (S020 only scans `README.md`), but the full gate is still required.
- Draft PR CI green: CI (3.11, 3.12, Package), Static policy, actionlint, AGENTS.md placement.
