# Contributing

## Repository layout

| Path | Contents |
| --- | --- |
| `bin/netcap` | The CLI (Python 3, standard library only) |
| `mac/` | The macOS device side (pf + dummynet). The agent and netcap-check are shared with Linux |
| `linux/` | The Linux device side (tc) |
| `win/` | The Windows device side (NetQosPolicy) |
| `examples/` | Templates for `hosts` and `profiles` |
| `Formula/netcap.rb` | The Homebrew formula (this repository is its own tap) |
| `scripts/measure.sh` | Measures how well the cap works |
| `tests/` | Tests that follow the behavior promised by the README and docs |
| `.github/workflows/ci.yml` | CI. E2E runs on a macOS / Linux / Windows matrix |

## Direction

[docs/vision.md](docs/vision.md) is the yardstick for changes. A change should move netcap toward it:

- Work on a gap starts from its issue (label [`vision-gap`](https://github.com/ken-ty/netcap/labels/vision-gap)).
  The PR that closes it updates the "Ideal and current" table
- A proposal that falls under the non-goals is declined, however useful it is on its own
- Changing the job, the principles, or the non-goals is a decision of its own: open an issue before the PR

## Tests

```bash
python3 -m unittest discover tests           # the CLI (with a fake ssh), and docs checked against the implementation
NETCAP_E2E=1 python3 -m unittest tests/test_e2e.py   # real machine: installs the device side here, applies a cap, and removes it at the end
```

E2E rewrites this machine's settings and needs sudo (Administrator on Windows). Normally leave it to CI.
When changing behavior written in the docs, fix the test first, confirm it fails, then implement.

## Language

**English is the source of truth.** Write everything in English: code, comments, CLI output,
commit messages, issues, pull requests, and the docs.

Other languages are translations of the English docs.

- A translation sits next to its source as `<name>.<lang>.md` (`README.ja.md`, `docs/design.ja.md`).
  To add a language, add files with a new `<lang>`; nothing else needs to change
- Each translation starts with the language switcher and a note saying the English version wins when they disagree
- If a translation disagrees with the English version, the English version is correct. Fix the translation
- Translations may lag behind. Change the English version first; a translation can follow in a later PR.
  Commands, versions, and paths are the exception: tests check that they match, so update them in the same PR

CLI messages for people (help and errors) can be translated too, in the same spirit:

- Write the message in English and pass it through `_()` in `bin/netcap`. Translations live in the
  `JA` table in the same file, keyed by the English text. A message with no translation is printed in English
- The language comes from `LC_ALL`, `LC_MESSAGES`, then `LANG`, as POSIX tools do. `LC_ALL=C` gives English
- Never translate what a machine reads: `--json`, the `key=value` line from devices, and the values in the
  table (`ok`, `no-sudo`, `on`, …). The column headers stay in English too, because the docs explain the table by them
- A test checks that every translation still has its English message and the same placeholders.
  When changing a message, update or remove its translation in the same PR

## Changelog

[CHANGELOG.md](CHANGELOG.md) tells people who use netcap what changed and what to do about it.

- A PR that changes what users see (commands, flags, output, the device side, behavior the docs promise) adds a
  line under `## [Unreleased]` in the same PR. Tests, CI, refactoring, and formula bumps do not
- Put the line under Added, Changed, Deprecated, Removed, Fixed, or Security, and end it with the PR number
- Start a change that can break a script, a habit, or a device's setup with **Breaking**, and say what to do instead
- CHANGELOG.md is English only; it has no translation

## Release

1. Decide the oldest agent the new CLI works with ([docs/compatibility.md](docs/compatibility.md) lists what raises it).
   If it goes up, say so in the tag message
2. In a PR, move the lines under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) to a new `## [X.Y.Z] - YYYY-MM-DD`
   section, and add its compare link at the bottom
3. After it merges, push an annotated tag `vX.Y.Z` on main. The message is a one-line summary, then that section
4. Point `tag` and `revision` in `Formula/netcap.rb` at that tag
5. Update the version in the curl and zip examples in [docs/host-setup.md](docs/host-setup.md) and its translations
6. Add a row for the version to [docs/compatibility.md](docs/compatibility.md) and its translations

The tag is the source of truth for the version. The formula fills `@VERSION@` in `bin/netcap`; a clone uses `git describe`.
