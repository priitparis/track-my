# CLAUDE.md

## Language

All code (identifiers, comments, commit messages) and all instructions to
AI models must be in English, unless explicitly stated otherwise.

## Working style

- Keep changes minimal — do not refactor, restructure, or touch unrelated
  code beyond what the task requires.
- Stay in the loop with the user throughout a task, unless told
  otherwise:
  - Before starting, ask clarifying questions if the request is
    ambiguous or a decision could go multiple ways.
  - When working from a plan, break it into small parts, implement each
    part separately, and pause after each part to discuss and align
    with the user before continuing.
  - At the end, explain in your own words how you understood the task,
    so the user can confirm the intent matched before relying on the
    result.
- Whenever a widget is about to undergo a major rewrite, ask whether to
  build a new widget alongside the existing one instead of rewriting it
  in place.

## Architecture

- Write code in small, reusable, loosely-coupled pieces (services,
  components, modules) rather than large monolithic classes or
  controllers.
- Keep clear boundaries between domains/modules, and avoid unnecessary
  coupling between them, so that a piece could in principle be
  extracted into a separate microservice later without a rewrite.
- Communicate between modules through well-defined interfaces (e.g.
  service classes, DTOs, events) rather than reaching directly into
  another module's internals.

## Testing

- Every change must be covered by tests. Add or update tests for any new
  or modified behavior as part of the same change.
- Prefer the project's existing test framework and conventions whenever
  possible. Writing a custom test setup is a last resort, only when the
  existing testing approach does not fit the case.

## Personal / local instructions

If a file `.claude/CLAUDE.local.md` exists, read it and follow the
instructions there in addition to this file. `.claude/CLAUDE.local.md`
is git-ignored and meant for each developer's own personal, unshared
instructions (e.g. personal tooling, local environment quirks). See
`.claude/CLAUDE.local.md.example` for a template.

If a file `.claude/PLAN.md` exists, read it and follow the instructions
there when planning work (e.g. in Plan Mode). `.claude/PLAN.md` is
git-ignored and meant for each developer's own personal planning
preferences (e.g. how detailed plans should be, when to ask for
confirmation). See `.claude/PLAN.md.example` for a template.