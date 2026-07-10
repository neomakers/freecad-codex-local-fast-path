# Reusable engineering knowledge

These are the invariants learned while making the route work on a real
FreeCAD 1.1.1 installation.

## Latency

Do not put a remote model call in the critical path for deterministic commands.
The useful target is local request and FreeCAD execution time, not end-to-end
model reasoning time. A localhost bridge can be fast after warm-up, but remote
Codex reasoning remains network-dependent.

## FreeCAD threading

FreeCAD document mutations must happen on the Qt main thread. The chat worker
can parse and wait, but tool execution must use its existing queued signal and
main-thread executor. Bypassing that rule can hang the GUI or corrupt the
document state.

## Tool capability

FreeCAD AI suppresses tools for a generic `custom` provider unless capability is
explicitly detected. The Codex bridge is OpenAI-compatible and supports the
tool schema, so the installer sets `tools_detected=true` in the user's config.
This is configuration, not an API key.

## Reproducibility

Keep one parser in the repository payload and copy that same file into the
FreeCAD AI installation. The bridge imports the repository payload too. This
prevents the plugin and bridge from learning different grammars over time.

Guard every upstream patch with an exact marker and a narrow source anchor.
Create a timestamped backup before editing. If the anchor disappears, fail
closed and ask for an upstream compatibility update.

Start the bridge from the workbench activation hook as well as from the manual
launcher. The hook must be idempotent, repair only the integration-owned
provider settings, and return quickly when the localhost port is already up.

## Safe evolution

Add a new fast-path command only when its grammar is unambiguous, its handler
already exists in FreeCAD AI, and a regression test covers both a valid command
and an ambiguous/question form. Images, documents, vague natural language,
and multi-step design intent should continue to the normal model path.
