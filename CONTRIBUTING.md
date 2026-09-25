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

## Release

1. Push an annotated tag `vX.Y.Z` on main
2. Point `tag` and `revision` in `Formula/netcap.rb` at that tag
3. Update the version in the curl and zip examples in [docs/host-setup.md](docs/host-setup.md) and its translations

The tag is the source of truth for the version. The formula fills `@VERSION@` in `bin/netcap`; a clone uses `git describe`.
