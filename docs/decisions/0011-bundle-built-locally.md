# 0011 — The React bundle is built on the author's machine and committed

**Date:** 2026-09-15
**Status:** accepted

## Context

ADR 0008 adopted React for the interactive parts and left one thing open, which
§12 carried with a deadline of v0.4, before the first component: *how does the
bundle get built, and tested?*

A bundle is the single JavaScript file a browser downloads, produced by
compiling the component sources. Something has to run that compilation, and
there are two places it can happen.

§7.1 adds a constraint that is easy to miss here: everything a page needs is
served from this site, never a CDN, because the CDNs are unreliable in mainland
China. That applies to the bundle as much as to the fonts, and it rules out the
usual third option of loading React from somebody else's server.

## Decision

**The bundle is built on the author's machine, and the built file is committed
to the repository.** Render deploys it as a static file and never runs Node.

**Vite builds it.** It is the standard toolchain for a React project of this
shape, it emits one file that can be dropped into a Jinja template, and it is
the toolchain Vitest assumes.

**A check guards staleness.** The build writes a hash of its input sources
beside the bundle; the check recomputes that hash from the working tree and
fails if it disagrees. Editing a component and forgetting to rebuild then fails
a check instead of shipping a bundle that does not match its source.

**Component tests are Vitest, and they arrive at v0.7** with the rest of the
tests, as ADR 0008 already scheduled. The tool is decided now so the question is
closed; installing it is not v0.4 work, and there is no component to test until
there is a component.

## Alternatives

**Render builds on deploy.** The attraction is real: no generated code in the
repository, and pushing a source change is enough. Rejected on three counts.

- Render runs this as a Python service. Getting Node into its build means either
  a custom build command that downloads a Node toolchain on every deploy, or
  moving the whole service to Docker. That is a build system for a site with
  five pages.
- **A build failure takes the site down.** ADR 0003 already accepted a cold
  start of about a minute on the free instance; adding a second way for the
  whole site to be unavailable is the wrong direction, and it would fail at
  deploy time, away from the machine where the cause is visible.
- The deploy grows a dependency whose breakage looks nothing like a Python
  error, at a point in the project where every hour is meant to come out of §9.

**Commit the bundle with no staleness check.** This is the chosen option minus
its one defence, and the defect it leaves is the reason the alternative above is
attractive: a source edit that is never rebuilt produces a site that disagrees
with its own repository, silently, until someone notices the feature did not
change. The check costs a few lines and converts that into a failure at the
moment it happens.

**Rebuild in the check and compare the bundles byte for byte.** A stronger
guarantee, and the obvious first idea. Rejected because it makes the check
depend on the build being byte-reproducible across machines and tool versions,
so a harmless toolchain upgrade would fail a check for a reason that has nothing
to do with the code. Hashing the inputs is deterministic by construction and
needs no build to run.

**Skip the bundler and ship hand-written browser JavaScript.** That is option
(a) in ADR 0008, which was considered and rejected there. Not reopened.

## Consequences

- **Generated code lives in the repository.** Accepted deliberately. It is one
  file, it is named so that it is obviously generated, and the check above is
  what makes it safe.
- **Node and npm are required on the development machine**, not on the server.
  Installed 2026-09-15.
- **A rebuild is part of committing a component change**, the same way updating
  a document is part of a decision. The check is what enforces it.
- **`.gitignore` gains `node_modules/`** and the build's own scratch output. The
  bundle itself is deliberately not ignored.
- **The lockfile is committed**, so the same input builds the same bundle on a
  future machine. Without it, "rebuild from source" stops meaning one thing.
- **v0.7 inherits Vitest**, an installation and a first test, alongside the
  Python tests already scheduled there.
- **If the bundle ever needs to be built somewhere else** — a second developer,
  or a CI service — this decision is what has to be revisited, and the staleness
  check is what will notice the disagreement.
