# Third-party notices

Warframe Planner itself is MIT licensed; see `LICENSE`.

This file lists what it builds on. The runtime dependencies matter most when a
built executable is distributed, because the packaged binary embeds them.

## User interface

Two interface patterns are adapted from [Uiverse.io](https://uiverse.io),
whose elements are published under the MIT license.

| Element | Author | Used in |
|---|---|---|
| Cyberpunk checkbox | [adamgiebl](https://uiverse.io/adamgiebl) | `planner/static/css/controls.css` |
| Offset outline ring | [cohencoo](https://uiverse.io/cohencoo) | `planner/static/css/board.css` |

Both are reworked rather than copied verbatim: colours come from the
application's theme tokens, and the ring is drawn with `box-shadow` instead of
`outline-offset` so it can animate smoothly.

## Runtime dependencies

Embedded in the distributed executable.

| Package | License |
|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | MIT |
| [Starlette](https://github.com/encode/starlette) | BSD 3-Clause |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD 3-Clause |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT |
| [pydantic-core](https://github.com/pydantic/pydantic-core) | MIT |
| [python-multipart](https://github.com/Kludex/python-multipart) | Apache 2.0 |
| [anyio](https://github.com/agronholm/anyio) | MIT |
| [click](https://github.com/pallets/click) | BSD 3-Clause |
| [h11](https://github.com/python-hyper/h11) | MIT |
| [idna](https://github.com/kjd/idna) | BSD 3-Clause |
| [annotated-types](https://github.com/annotated-types/annotated-types) | MIT |
| [typing-extensions](https://github.com/python/typing_extensions) | PSF 2.0 |
| [CPython](https://github.com/python/cpython) | PSF 2.0 |

To regenerate the full licence texts from an installed environment:

```
pip install pip-licenses
pip-licenses --format=plain-vertical --with-license-file --no-license-path \
             --output-file THIRD-PARTY-LICENSES.txt
```

`pip-licenses` sees pip packages only, so the CPython notice has to be added by
hand.

## Build tooling

[PyInstaller](https://github.com/pyinstaller/pyinstaller) is GPL-2.0, but its
bootloader carries an exception that allows frozen applications to be
distributed under any terms, including closed ones. It is a build-time tool and
is not part of the distributed application.

## Trademarks

Warframe is a trademark of Digital Extremes Ltd. This project is an unofficial
fan-made tool, is not affiliated with or endorsed by Digital Extremes, and is
distributed free of charge.
