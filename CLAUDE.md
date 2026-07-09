# CLAUDE.md — ScheduleIQ operating rules

ScheduleIQ is Long International's Acumen Fuse replacement — schedule quality,
health, trend, forensic-delay, and risk analysis for P6/MSP.  At the start of a
session read `docs/HANDOFF.md`, then `docs/BACKLOG.md`; `docs/GOVERNANCE.md`
governs how checks and the scoring spec may change.

## Peer review from Codex / ChatGPT — evaluate, don't rubber-stamp

External LLM review (Codex, ChatGPT, or any other) is **input to be verified,
not fact to be accepted.**  Apply independent judgment to every finding, every
time:

- **Reproduce or check it** against the actual code/behavior before acting on
  it — the same "reproduce, don't trust" discipline we apply to our own audits.
- **Judge correctness AND scope.**  A reviewer can be wrong, out of scope,
  over-engineered, or propose a methodology change dressed up as a bug fix.
  Some requests deserve push-back.
- **Push back plainly when warranted.**  If a finding is wrong or a change is
  unwarranted, say so and explain why — do not implement it just to be
  agreeable.  Deferring or declining a suggestion with a clear rationale is a
  valid, expected outcome.
- The goal is **not** to be contrarian: legitimate findings should be adopted
  and credited.  The goal is to stop automatic acceptance and keep a human-
  auditable rationale for what we take, adapt, or reject.

This applies symmetrically — we hold our own conclusions to the same bar when
Codex reviews our work.

## Git

- Commit as `Claude <noreply@anthropic.com>`; end messages with the
  Co-Authored-By + Claude-Session trailers.  Never put a model identifier in
  committed artifacts.  Push early and often — the container is ephemeral.
- Canonical repo is `worktodo77/schedule-iq`; keep the expert-assist mirror
  subtree in sync until the migration is confirmed (per `docs/HANDOFF.md` §2).

## Governance

- A check changes only when matrix row + implementation + seeded fixture +
  tests change together (`docs/GOVERNANCE.md`), with a CHANGELOG note.
- Bespoke LI metric definitions (FCBI, LHL, FRB, PCI, RDI, BDI, CDI, IL, BWI,
  MML, and the provocative set) are **methodology decisions owned by the
  principal** — audit and propose, never silently revise.  Number-changing
  changes ship with the full governance quartet and a recorded ruling.
