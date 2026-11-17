# Deliverables index

Everything here was written for the Open-Source Agentic Venture Builders hackathon, checked against the organizers' `TEAM_CLAUDE.md` and the Case Brief.

| File | What it is | Who needs it |
|---|---|---|
| `TEAM_PLAN.md` / `pdf/TEAM_PLAN.pdf` | Timeline to 23:59, roles, how this replaces a scrum master, sleep checklist, cut list, final checklist | All four members, read once |
| `MEMBER_1_PLATFORM.md` / `.pdf` | M1: step-by-step plus Prompts A, B1, W, C | M1 |
| `MEMBER_2_DISCOVERY.md` / `.pdf` | M2 (senior data scientist): step-by-step plus Prompts A, B1, B2, B3, C | M2 |
| `MEMBER_3_VALIDATE_BUILD.md` / `.pdf` | M3: step-by-step plus Prompts A, B1, B2, B3, C | M3 |
| `MEMBER_4_COMMERCE_SAFETY.md` / `.pdf` | M4: step-by-step plus Prompts A, B1, B2, B3, C | M4 |
| `CONTEXT.md` / `pdf/CONTEXT.pdf` | Shared contracts, ownership map, artifact names, gate metrics, testing and merge protocols | Copy the **`.md`** into each member's repo folder (untracked); Claude reads it |
| `ARCHITECTURE.md` / `pdf/ARCHITECTURE.pdf` | The repo-ready architecture in the organizers' required sections, with Mermaid diagrams | Copy the **`.md`** into the repo root |

**Copy prompts from the `.md` files, not from the PDFs.** The PDFs are for reading and for giving to Claude as context; copying from a PDF can break line breaks.

## Where each file goes
- Repo root (committed): `ARCHITECTURE.md`, and the organizers' `TEAM_CLAUDE.md` renamed to `CLAUDE.md`.
- Repo root (never committed, listed in `.git/info/exclude` and `.gitignore`): `CONTEXT.md`, `PROGRESS_M<N>.md`.
- Not in the repo: everything else in this folder.

## Start order
1. M1 sets up the repo (`MEMBER_1_PLATFORM.md`, steps 1 to 7) and runs Prompt A.
2. M2, M3, M4 clone the empty repo, branch, place `CONTEXT.md`, and run their Prompt A immediately (it begins with work that needs no code, then waits for the skeleton).
3. Everybody sleeps after confirming their session is running.
