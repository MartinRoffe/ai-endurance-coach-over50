# Public version plan

Planning only. This document does not publish anything, change repository visibility, or authorise copying this history into a public remote.

The private app stays the maintainer's athlete-specific system. A public version, if it is ever built, is a **new repository with a new first commit**. It is not a fork, a mirror, or a `git filter-repo` rewrite of this one.

## Recommendation

Publish only a repository whose first commit is written after a line-level review, on a machine that does not have this `.git` directory as its parent.

A fork is the wrong shape. GitHub forks expose every reachable commit, blob, note, and tag. This history already contains:

- clinical narrative in source, docs, and commit messages
- measured physiology and a body-mass goal compiled into modules and tests
- multi-day ride files (heart rate, GPS, cadence, estimated power) and a written post-mortem of those files
- power, weight, and activity-id archives, including generated narratives
- git author identities (a personal mailbox and two machine hostnames)
- a home-directory username and a real activity id in tests
- one household's training calendar, events, kit, and deployment notes

Secret scanners did not find a committed API key, password, token, or private key (see the audit that accompanies this plan). That result does not make the history safe to publish. Health data and identifiers are the problem. Rewriting history is brittle: one missed blob, an unpruned remote, or a commit message is enough. A clean first commit is a boundary that can be reviewed.

There is no `LICENSE` file in this repository today. Anything copied out is all-rights-reserved until the maintainer chooses a licence and puts it in that first public commit.

## How the two trees relate afterwards

```text
public repo (clean history)
  endurance-coach package
  generic dashboard, readiness, zones, connectors, plan generator
        ^
        │  version pin (install the package; do not copy its git history)
        │
private repo (this history, stays private)
  private overlay: clinical notes, dated plans, events, kit defaults,
  household recipes and shops, ride archives
  thin app that imports the public package and the overlay
```

Rules for the ongoing relationship:

- Generic bugfixes land in the public repo as new commits, then the private app bumps the pin. Do not cherry-pick from this history onto the public repo. Cherry-picks carry the original author, message, and any personal hunks.
- Personal changes stay in the overlay. They never move downstream.
- The overlay imports the public package. It does not vendor a second copy of the dashboard long-term, or the two UIs will drift.
- One athlete per install for the public v1. The private app is that pattern plus an overlay, not a second architecture.
- The private data directory (`ENDURANCE_COACH_HOME`, SQLite, `.env`, OAuth tokens, FIT uploads) is never part of either git tree. It is already outside this clone. Do not rsync it into a public artefact, image, or issue.

Suggested package split. Names are roles, not a promise to keep today's module layout.

| Role | Public package | Private overlay |
| --- | --- | --- |
| Garmin / Withings / FIT session | Connector interfaces and implementations. Credentials from the environment or the data dir. | Nothing personal beyond the local `.env`, which stays untracked. |
| Readiness, z-scores, HRV traffic light, illness abstain | Yes, once copy no longer names one athlete. | — |
| Heart-rate and power zones | Formulae only. Inputs are measured values on the profile. | Stored measurements in the private database. |
| Training plan | Generator from an onboarding spec (days available, event date, kit). | The dated calendars, camps, charity block, and qualification targets. |
| Nutrition | Targets from a stated energy equation and the day's session. | Clinical diet rules, named shops, and the household meal rotation. |
| Coach prompts | A generic coach, age band and kit read from the profile. | Identity, clinical history, and this year's goals. |
| Dashboard | Shell, tabs, auth, bind address from config. | Extra routes that only make sense for the overlay. |
| Archives, TCX, post-mortems, analysis dumps | Do not copy. Ship a tiny fictional sample instead. | Keep. |

## Architecture for a self-hosted install

v1 is **single-user self-host**. One process, one SQLite file, one set of credentials, on a machine the athlete controls. Multi-user hosting is a different product and is an open decision below, not a requirement of this plan.

### Config

- `.env.example` committed, with empty secrets and placeholders such as `you@example.com`. No real mailbox, no key material, no voice-provider account id that is easy to mistake for a credential.
- Bind address defaults to `127.0.0.1`. Listening beyond localhost is opt-in via `HOST`, and the docs say to set a password first. They do not name a computer, a tailnet, or a cloud VM.
- `ENDURANCE_COACH_HOME` (default a generic directory under the home folder, not this app's current private directory name) holds the database, tokens, and generated profile.
- Athlete profile in that data dir, produced by onboarding, gitignored. Example keys: display name, age band, measured max HR, resting HR, lactate-threshold HR, FTP watts, body mass, kit flags, event list. No compiled-in numbers.
- Feature flags for optional processors: Garmin, Withings, SMTP, cloud LLM, text-to-speech. Each defaults off when its credentials are absent.

### Physiology and zones

Zones are computed at runtime from the profile:

- percent of max HR, heart-rate reserve, and percent of lactate threshold, chosen from what was actually measured
- power zones from FTP when a test or a typed FTP exists
- readiness baselines from the rolling window in SQLite, not from constants in source

If a value is missing, the UI asks for it or hides that chart. It does not fall back to the private athlete's figures.

### Kit profile

Onboarding records equipment as data: indoor trainer yes/no, which ergometers or strength tools exist, whether running is in or out. Session builders read the profile. A missing tool removes those sessions. The public default is an empty kit, not one household's garage.

### Onboarding questionnaire

A short flow writes the profile and a first plan:

1. Name used in prose, age band, experience.
2. Measurements the athlete chooses to enter (the list above). Import from a file or a connector can fill the same fields later.
3. Week template: which days, long day, strength days, minutes available.
4. One goal event: name, date, discipline. More events can be added later.
5. Nutrition preferences: deficit or maintenance, dietary flags. A clinical diet is off unless the athlete turns that flag on and types the constraint. No condition is pre-selected.
6. Review screen shows the generated week and the day's energy target, then saves.

The plan engine accepts a spec (start date, weeks, week template, events, kit). It does not embed a year of tuples for one person. Nutrition scales plates from that day's target. A fixed household energy base does not ship.

### Data sources

A small interface, three implementations:

- **Garmin.** Email and password, or whatever the current library requires, from the environment. Tokens cached only in the data dir.
- **Withings.** Optional OAuth. Client id and secret from the environment. Tokens in the data dir. The app runs with Withings absent.
- **Files.** FIT or TCX upload so a new install works before any cloud account exists.

Each install uses that install's credentials. There is no shared developer account.

### Email

SMTP host, port, username, and password from the environment, plus a From and a To address. Gmail is one example in the docs, not the only sender. The message is a readiness note with the same not-medical-advice line as the UI.

### Machines and networks

Remove the assumption that the app lives on a particular PC and is reached over a particular overlay network. Document three setups:

- this machine, `127.0.0.1`
- Docker Compose, published only to localhost
- a password-protected bind on an address the operator chooses

A private-network overlay such as Tailscale can be mentioned as one optional way an operator might reach a home server. It is not a setup step, and no network name, address, or machine model is filled in. The private install's server and tailnet stay out of the public docs.

## Packaging and setup

The new repository's first useful commit contains:

- `LICENSE` and a short disclaimer at the top of `README`
- `README` with clone, copy `.env.example` to `.env`, `docker compose up`, open the local URL, complete onboarding
- `Dockerfile` and `docker-compose.yml`: one app service, one named volume for the data dir, no default password, port bound to localhost
- `sample/` with an obviously fictional athlete (a made-up name, round numbers that are labelled `SAMPLE`, a few synthetic daily rows, no real FIT or TCX)
- pytest using that sample, not fixtures copied from this repo's tests
- CI: tests, plus gitleaks and trufflehog on every push and pull request, failing the job on any finding

Do not publish a container image that was built from this private tree.

## Legal and safety

This section is an engineering checklist, not legal advice. Before anyone else can create an account on a server the maintainer runs, a solicitor who knows UK data protection should review it.

### Licence

Recommend **Apache-2.0** for a self-hosted tool other people will run and modify: permissive, explicit patent grant, compatible with a separate medical disclaimer (the licence is not the disclaimer).

**AGPL-3.0** is the alternative if the goal is that anyone who hosts a modified copy and lets other people use it must publish their source. It is a poorer fit if the private overlay must stay unpublished while linking the public package. Confirm that combination with a solicitor before choosing AGPL. The private overlay can stay private either way, because it is never distributed.

Put the chosen licence in commit 1. Do not start public history and add a licence later.

There is no licence on this private repo. Choosing one here does not by itself publish it.

### Not a medical device

README, first-run screen, and email footer state, in plain language:

- the software is a training log and planning aid
- it is not a medical device and not medical advice
- it does not diagnose, clear an athlete to train, or replace a clinician
- stop and seek urgent care for generic red flags (for example chest pain, fainting, sudden severe shortness of breath). Do not encode one person's history as those rules
- cloud coach text, if enabled, is unverified prose

Safety rules that belong in code, with tests:

- ramp limits and a rest day, configurable, with conservative defaults
- missing readiness data abstains instead of inventing a score
- the model is not asked to clear someone after illness or a procedure
- uploaded files are parsed as workouts, not trusted as HTML

### UK GDPR and special-category data

Heart rate, heart-rate variability, weight, symptoms, and training data tied to health are health data. Under UK GDPR that is special-category data (Article 9), which needs a lawful basis and a separate Article 9 condition.

**Self-host, one person, their own machine.** The household exemption can apply to purely personal processing. It is narrow. Sending the same data to a coach API, an email provider, Garmin, or Withings is a disclosure to another organisation. The public app should default those integrations off, list each processor in the README, and send a field only when that integration is on. Tokens and the database stay in the volume on that machine.

**Hosted by the maintainer for other people.** The household exemption does not apply. The maintainer is a controller of special-category data and would need, at least, a privacy notice, an Article 9 condition (explicit consent is the realistic one), security, retention and deletion, a record of processing, a DPIA, and a transfer tool for any processor outside the UK. That is out of scope for v1. Do not add accounts, sign-up, or a shared server as part of the public launch.

**This repository and the new one.** A public git history must not contain anyone's real health data, including the maintainer's. Issues and pull requests need the same rule. Sample data is fictional and obviously so.

### Secret scanning in CI

On the new repository, from the first commit:

- gitleaks and trufflehog in GitHub Actions, full history of that repo, job fails on a finding
- an allowlist only for a specific rule and path, after a human checks the match is not a credential (cache-key constants can trip a generic key rule)
- `.env` gitignored; `.env.example` has empty or clearly fake values
- the same workflow is worth adding to this private repo in a separate change, so a later mistake is caught before it is pushed. That workflow is not part of the documentation-only change that adds this plan.

## Phased checklist

Build size is relative scope (which parts move), not a calendar estimate.

### Phase 0 — Boundary

Size: **S**. Decisions and a deny-list. No code leaves this repo.

- [ ] Maintainer answers the open decisions below.
- [ ] Write a deny-list for the copy step: clinical modules and prompts, dated personal plans, ride files, power and weight archives, post-mortems, tests that assert this athlete, deploy notes that name household machines, git history itself.
- [ ] Leave this repository private. Do not run a history rewrite here.

### Phase 1 — Empty public repository

Size: **S**. A new remote and a first commit that could be shown to a stranger.

- [ ] Create the new repository only when the maintainer is ready. Not part of this plan's change.
- [ ] First commit: `LICENSE`, disclaimer, README, `.env.example`, gitignore, CI secret scan, Compose file that serves a placeholder page.
- [ ] Confirm the commit author is a publishable identity, not a machine hostname or a personal mailbox that should stay quiet.

### Phase 2 — Generic core

Size: **L**. Most modules need a line-level pass. This is where personal data would leak if the copy is careless.

- [ ] Copy only modules that compute or display, after reading them against the deny-list.
- [ ] Replace compiled physiology with the profile. Delete fallbacks that use a real athlete's numbers.
- [ ] Strip names from prompts. Age band and kit come from the profile.
- [ ] Keep zone maths, readiness, alerts, and the SQLite schema. Drop personal routes and event tables.
- [ ] Tests use the fictional sample only. CI secret scan still green.

### Phase 3 — Onboarding, plans, nutrition

Size: **L**. New behaviour, not a move.

- [ ] Questionnaire writes the profile.
- [ ] Plan generator builds weeks from the spec.
- [ ] Nutrition targets come from the day's session and the profile. Plates scale from that target.
- [ ] Clinical diet flags exist and default off.

### Phase 4 — Connectors and email

Size: **M**. The private app already talks to these services. The work is boundaries and defaults.

- [ ] Garmin, Withings, and file import behind one interface. Each install's own credentials.
- [ ] Generic SMTP. App starts with email unset.
- [ ] Cloud coach and speech stay off without keys.

### Phase 5 — Private app consumes the package

Size: **L**. The private dashboard must keep today's behaviour.

- [ ] Pin the public package from a release, not from a copy of its git objects.
- [ ] Move clinical text, dated plans, events, and household nutrition into the overlay.
- [ ] Run the private test suite against the overlay. Compare a week of plan output and a readiness page with the pre-split app.
- [ ] Generic fixes go to the public repo first, then a version bump here.

### Phase 6 — Release hygiene

Size: **S**, after Phases 2–5. This is the gate before the new repository is made public.

- [ ] Second person clones the new repo, starts Compose, finishes onboarding with fictional answers, and sees no name, event, or measurement from this household.
- [ ] Repo search for mailboxes, home paths, machine names, and the deny-list terms.
- [ ] Secret scan clean on the full public history (it should still be one or a few commits).
- [ ] Only then change visibility of the **new** repository. This repository stays private.

## Open decisions

1. Public repository name and Python package name. They should not match this private repository's name.
2. Licence: Apache-2.0 (recommended for self-host) or AGPL-3.0 (if hosted forks must publish source). Needs a check against the private overlay.
3. Confirm v1 is single-user self-host only, with no accounts on a server the maintainer operates.
4. Does the cloud coach ship in v1, or is file-and-Garmin coaching enough until the disclaimer and processor list are comfortable?
5. Is Garmin required to finish onboarding, or is FIT upload enough?
6. Do any recipes ship in public v1, or only energy and macro targets?
7. Does the product stay framed for over-50 athletes, or is age a profile field with copy that changes?
8. How the private app takes the dependency: a tagged release on a package index, or a git URL pinned to a tag. Not a branch, and not a fork remote.
9. Whether a solicitor reviews the hosted case before any later multi-user work. v1 should not wait on that, because v1 does not host other people.
10. Whether to add the same secret-scanning workflow to this private repo in a follow-up. Recommended, and separate from this document.

## Non-goals

- Changing this repository's visibility, rewriting its history, or deleting its data files.
- Creating the public remote, cutting a release, or pushing this branch anywhere except as the review vehicle for this document.
- A multi-tenant service, logins for other athletes, or a medical-device claim.
