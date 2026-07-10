# Troubleshooting reference

## The fast path does not trigger

The FreeCAD AI chat must be in Act mode and the config must report
`tools_detected: true`. The parser intentionally ignores rich messages with
images/documents and question-style prompts. Verify the patch marker before
changing the parser.

## The bridge starts but Codex fails

The bridge is only a local protocol adapter. It does not create an API key or
perform a new login. Check that Codex Desktop has been opened and the user is
already signed in. Then inspect the bridge log and run `codex doctor` from a
normal terminal if needed.

## The upstream plugin changed

Do not use broad replacements. Find the worker's `run()` method and its existing
LLM import. Update the guarded anchor in `install.ps1`, add a regression test,
and preserve the backup/rollback contract.
