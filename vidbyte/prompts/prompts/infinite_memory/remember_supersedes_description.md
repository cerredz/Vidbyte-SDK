## Purpose

The id of a live entry that this new entry replaces, because the old one is outdated or wrong.

## How it behaves

Once the new entry is saved, the old one moves out of live memory into the record of replaced entries, so searches stop finding it and no reader meets two conflicting versions. For a generator or verifier, the replacement happens only when the pair's verdict saves the new entry.

## Rules

Give the id as a whole number, without the hash sign. The old entry must still be live when the new one is saved, and an id that is unknown or already replaced is refused. Leave it out when the entry adds new knowledge instead of correcting old knowledge.
