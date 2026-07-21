# MLT Python bindings — availability check

## Goal
Determine whether the `mlt` Python module is installable on this machine,
so Phase 2 of the PyAgent guide knows whether to use it or fall back to
plain `lxml` for MLT XML construction.

## Commands run

```sh
# Direct import
$ python3 -c "import mlt; print(mlt.__file__)"
ModuleNotFoundError: No module named 'mlt'

# Official Arch repos
$ pacman -Ss mlt
extra/kdenlive 26.04.3-1 ... [installed]
extra/mlt 7.40.0-2 ... [installed]
extra/mlton 20241230-1 ...           # unrelated (Standard ML compiler)
extra/python-xmltodict 1.0.4-1 ...    # unrelated (XML/JSON helper)
extra/qmltermwidget 2.0.0.git1-1 ...  # unrelated

$ pacman -Ss python-mlt
(no matches)

# AUR
$ yay -Ss mlt-python
(no matches)

$ yay -Ss python-mlt
(no matches)
```

## Result

**Not available.** The `mlt` Python module is not in the official Arch
repositories and no AUR package named `mlt-python` / `python-mlt` exists
under this account.

## Implications for Phase 2

Use **`lxml`** (or the stdlib `xml.etree.ElementTree` if we want zero
installs) for MLT XML construction, exactly as the `mlt-pipeline` Go code
already does (string-templated, but tree-edited with `lxml` will be more
robust to unknown elements that Kdenlive adds on top of vanilla MLT).
This matches the `01_FINDINGS_AND_ARCHITECTURE.md` fallback.

## Optional follow-up (out of scope for Phase 0)

If we ever want the bindings, the only practical path is building them
from source against the system `mlt` package — `mlt` upstream ships
`src/swig/python/` and the build requires `swig` and the same `mlt`
headers the system package installs. This is a half-day detour, not
worth it until we know plain XML is hitting a real ceiling.
