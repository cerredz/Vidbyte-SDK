# Adding Prompts

Use this guide when adding prompt assets to the Vidbyte SDK.

## Prompt Assets

- Add prompt files under `vidbyte/prompts/prompts/`.
- Use one JSON file per prompt family.
- Each JSON file must include `name`, `description`, `key`, and `prompts`.
- The `key` must be stable and match the prompt class key used by `vidbyte/prompts/strategies/strategy_prompts.py`.
- Each prompt value should be 6-8 coherent sentences, not anonymous inline strings.

## Registry Flow

- Load prompt assets through `vidbyte.lib.prompts.PromptRegistry`.
- Strategy prompt classes should expose `export()` by reading from the registry.
- Do not hardcode strategy prompt bodies directly inside strategy classes.
- Keep prompt dictionaries inspectable so SDK users can reuse, audit, or override them.

## Verification

- Run `python -m compileall vidbyte`.
- Run the strategy tests that use the prompt family.
- Add or update tests when a prompt key changes.
