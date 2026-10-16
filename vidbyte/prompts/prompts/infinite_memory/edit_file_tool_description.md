## What it does

Replaces one passage of an existing workspace file with new text and leaves the rest of the file unchanged.

## When to use it

Use it to correct a file in place: a wrong figure, an outdated statement, a broken section, or a verifier's fix to a generator's output. Prefer it to appending a correction, because a reader who meets the old text first may never reach the fix.

## How it behaves

The old text must appear exactly once in the file, matched exactly, including spacing, line breaks, and letter case. The change takes effect at once and is not staged. The file must already exist, so create it with write_note first. Every reply ends with your quota line, and an edit never uses your new-file allowance.

## Rules and refusals

Seed files, run journals, and the bookkeeping files of memory cannot be edited. An old text that matches zero times or several times is refused with the number of matches found; include more of the surrounding text and try again. The file and workspace size limits still apply after the change, and an edit over a limit is refused with nothing changed.
