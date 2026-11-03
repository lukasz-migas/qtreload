# qtreload
Hot-reloads edited Python modules inside a running Qt application during development.

## Role in ecosystem
Standalone developer utility with no internal deps.
Internal deps: none
Depended on by: qtextra

## Key abstractions
- `install_hot_reload` — attach reloading to a running app
- `QtReloadWidget` — widget that watches modules and triggers reloads
- `QtDevPopup` — developer popup hosting the reload widget
- `pydevd_reload.Reload` — module-reloading engine

## Do not re-explain
When working in this repo, assume familiarity with: none (no internal deps)
