# Refactor Status

This checkout no longer keeps a live monolith compatibility layer. Runtime
ownership is now split across focused `modules/`, `ui/`, and `cogs/` files.

## Current Layout

- `cogs/` owns slash-command and event registration.
- `modules/` owns data, services, permission resolution, embeds, setup helpers,
  moderation, modmail, automod, roles, and branding logic.
- `ui/` owns Discord `View`, `Modal`, and select components.
- `modules/mbx_permission_engine.py` is the capability-based authorization
  system.
- `modules/mbx_templates.py` is the onboarding template registry.

## Active Refactor Work

- Finish the `/start` onboarding wizard.
- Migrate remaining legacy permission shims at call sites to explicit
  capabilities.
- Keep `cogs/dev.py` isolated from broad cleanup.
- Preserve existing MBX/MGXBot branding names.

## Verification

Use these checks after meaningful refactor steps:

```bash
python3 -m unittest discover tests
python3 -c "from cogs import automod, moderation, modmail, roles, system, dev"
```
