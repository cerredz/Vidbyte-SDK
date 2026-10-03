# Jev skill sources

`JevAlignmentSettings.skills` accepts inline text, a resolved `SkillDocument`, or a typed `SkillSource`. Plain strings always remain text; they are never treated as file paths or URLs. Source descriptors are resolved during preload for each run.

```python
import os

from vidbyte import (
    JevAgent,
    JevAgentSettings,
    JevAlignmentSettings,
    JevRuntimeSettings,
    ModelProvider,
    SkillSource,
    SkillSourceKind,
)

settings = JevAgentSettings(
    name="release-helper",
    system_prompt="Help with SDK release work.",
    provider=ModelProvider.ANTHROPIC,
    model_name="claude-sonnet-4-6",
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
    alignment=JevAlignmentSettings(
        skills=(
            "Follow our team's concise release-note style.",
            SkillSource(
                kind=SkillSourceKind.FILE,
                location="./skills/release-notes/SKILL.md",
            ),
            SkillSource(
                kind=SkillSourceKind.GITHUB,
                location="https://github.com/acme/skills",
                skill_name="release-review",
            ),
            SkillSource(
                kind=SkillSourceKind.SKILLS_SH,
                location="acme/skills/release-review",
            ),
            SkillSource(
                kind=SkillSourceKind.CLAUDE,
                location="skill_123",
                version="latest",
            ),
        ),
    ),
)
agent = JevAgent(settings, JevRuntimeSettings())
response = await agent.arun("Prepare notes for this release.")
```

The `FILE`, `GITHUB`, and `SKILLS_SH` adapters read the selected `SKILL.md` text and metadata. They do not install the skill, execute its scripts, or automatically load companion files. A text skill can refer to external assets, but those assets are not made available by source resolution.

`CLAUDE` sources resolve metadata and an opaque skill reference; they do not download the skill body. Jev scores these candidates using the available metadata only. Native references can be selected only for an Anthropic main model, and at most 20 selected references are mounted on a request. Claude-native skills are not supported for streaming calls. Pass a source-specific `api_key` when the agent's Anthropic key is not the intended credential; otherwise resolution uses the configured Anthropic agent key and then `ANTHROPIC_API_KEY`.

Each configured candidate retains its index in `agent.response.skills.results`. A source that cannot be resolved is reported as `UNAVAILABLE` with a safe explanation, while other candidates continue through selection. Selected text is added to the current run's prompt context. Native references are sent only with that run's Anthropic request.
