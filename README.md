# mdict-audio

Convert audio embedded in MDict dictionary families for better playback
compatibility. The source `.mdx` and `.mdd` files are never modified.

`mdict-audio` is useful when a dictionary stores pronunciations or other audio in
formats that some MDict readers cannot play reliably, such as Speex-in-Ogg, WAV,
or M4A. It converts the audio resources, rewrites matching `sound://...`
references, and can verify the generated dictionary family.

## Features

- Discover MDict families from `.mdx` and `.mdd` files by filename stem.
- Convert embedded audio resources to MP3 or OGG.
- Rewrite `sound://` references in `.mdx` entries when resource names change.
- Preserve non-audio resources and audio that cannot be converted.
- Detect and handle resource-name collisions.
- Write a JSON manifest with inputs, settings, renames, warnings, and stats.
- Verify output containers, sound references, extension/content consistency, and
  optional full audio decoding.

## Requirements

- Python 3.10+
- PyAV is optional and recommended for MP3 conversion and decode checks.
- `ffmpeg` must be available on `PATH` for OGG output, `--engine ffmpeg`, or
  automatic fallback when PyAV is not installed.

## Install

There are two ways to use `mdict-audio`: install it with `pip`, or run it
directly from PyPI with `uvx`.

### Install with `pip`

Recommended install with PyAV support:

```bash
pip install "mdict-audio[pyav]"
```

Install without PyAV:

```bash
pip install mdict-audio
```

After installation:

```bash
mdict-audio --help
```

### Run with `uvx`

Recommended one-off run with PyAV support:

```bash
uvx --from "mdict-audio[pyav]" mdict-audio --help
```

Run without PyAV:

```bash
uvx mdict-audio --help
```

For normal commands with PyAV support, keep the same `uvx --from ...` prefix:

```bash
uvx --from "mdict-audio[pyav]" mdict-audio convert path/to/dicts --family oaldpe --to mp3
```

`pip` installs the CLI into your current Python environment. `uvx` uses an
isolated temporary environment for each run. Neither method installs system
tools, so install `ffmpeg` separately when you need OGG output or the ffmpeg
backend.

## Quick Start

Inspect a dictionary directory:

```bash
mdict-audio inspect path/to/dicts --family oaldpe
```

Convert one family to MP3:

```bash
mdict-audio convert path/to/dicts --family oaldpe --to mp3
```

The default output directory is `converted/` under the input directory. To choose
a different location:

```bash
mdict-audio convert path/to/dicts --family oaldpe --out-dir path/to/output
```

Verify the converted family:

```bash
mdict-audio verify path/to/dicts/converted --family oaldpe
```

Run a full decode check when you need stronger validation:

```bash
mdict-audio verify path/to/dicts/converted --family oaldpe --decode
```

If the input directory contains exactly one family, `--family` is optional. If
multiple families are present, the command asks you to select one or more family
stems with repeated `--family` options.

## Dictionary Families

A family is grouped by filename stem. These files are treated as one family named
`oaldpe`:

```text
oaldpe.mdx
oaldpe.mdd
oaldpe.1.mdd
```

Converted output keeps the same family filenames and adds a manifest:

```text
converted/
  oaldpe.mdx
  oaldpe.mdd
  oaldpe.1.mdd
  oaldpe.manifest.json
```

The `.mdx` contains rewritten `sound://` references, the `.mdd` files contain
converted and preserved resources, and the manifest records conversion settings,
selected backend, resource renames, warnings, and verification-related stats.

## Commands

### `inspect`

List discovered families, container support, and audio counts:

```bash
mdict-audio inspect path/to/dicts
mdict-audio inspect path/to/dicts --family oaldpe
```

### `convert`

Convert audio resources and write a new family:

```bash
mdict-audio convert path/to/dicts --family oaldpe --to mp3
```

Useful options:

| Option | Meaning |
| --- | --- |
| `--family NAME` | Process one dictionary family. Repeat to process more than one. |
| `--to mp3\|ogg` | Choose the target audio format. Defaults to `mp3`. |
| `--out-dir DIR` | Write output to this directory. Relative paths resolve under the input directory. Defaults to `converted`. |
| `--engine auto\|pyav\|ffmpeg` | Choose the transcode backend. Defaults to `auto`. |
| `--quality speech\|standard\|high` | Use a preset quality. For MP3 this maps to `64k`, `128k`, or `192k`; for OGG this maps to Vorbis quality `2`, `4`, or `6`. Defaults to `speech`. |
| `--bitrate 96k` | Override the MP3 quality preset with an explicit bitrate. |
| `--workers N` | Set parallel transcode workers. Defaults to CPU count. |
| `--force` | Re-encode clips that are already in the target format. |
| `--on-collision rename\|overwrite\|skip` | Handle resource-name collisions. Defaults to `rename`. |
| `--inline-verify all\|sample\|off` | Decode-check transcoded clips during conversion. Defaults to `sample`. |
| `--redo` | Replace existing converted output directly. |

### `verify`

Check generated containers and references:

```bash
mdict-audio verify path/to/dicts/converted --family oaldpe
```

Add `--decode` to decode every audio clip:

```bash
mdict-audio verify path/to/dicts/converted --family oaldpe --decode
```

Useful options:

| Option | Meaning |
| --- | --- |
| `--family NAME` | Verify one dictionary family. Repeat to verify more than one. |
| `--decode` | Fully decode audio clips instead of only checking extension/content consistency. |
| `--engine auto\|pyav\|ffmpeg` | Choose the decode backend when `--decode` is used. |
| `--workers N` | Set parallel decode-check workers. Defaults to CPU count. |

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Verification passed. |
| `1` | Verification completed and found problems. |
| `2` | Command usage or runtime failure. |

A failed verification can also reflect damage already present in the source
dictionary. Compare with the original input or manifest warnings when needed.

## Backends

The default engine is `auto`:

- MP3 output uses PyAV when available, otherwise falls back to `ffmpeg`.
- OGG output always uses `ffmpeg`.
- An explicit unavailable engine is reported as an error.

Common examples:

```bash
mdict-audio convert path/to/dicts --family oaldpe --engine pyav --to mp3
mdict-audio convert path/to/dicts --family oaldpe --engine ffmpeg --to mp3
mdict-audio convert path/to/dicts --family oaldpe --to ogg
```

## Safety

- Input `.mdx` and `.mdd` files are preserved.
- By default, output is written under `converted/` inside the input directory.
- Existing output files are not overwritten unless you use `--redo`.
- `--redo` overwrites existing output files directly and may leave partial new
  output if the run fails.
- Ctrl+C exits cleanly and removes temporary staging files when possible.
- Conversion failures for individual clips keep the original resource and record
  a warning.
- Source dictionary problems are tracked separately from problems introduced by
  conversion.

## Limitations

- OGG output requires `ffmpeg`.
- Common PyAV wheels may not be able to encode OGG, so `--engine pyav --to ogg`
  is rejected.
- Some damaged or unusual audio files may still fail to decode.
- Missing audio resources are reported but not repaired.
- Audio conversion improves playback compatibility, not source recording quality.

## Bug Reports

Report bugs on GitHub:

```text
https://github.com/kibaamor/mdict-audio/issues
```

Please include the command you ran, the error output, your platform, and whether
the input dictionary can be shared or reproduced with a small sample.

## License

This project is licensed under the BSD 3-Clause License. See [LICENSE](LICENSE) for
details.

Parts of this project include code derived from other open source projects. See
[NOTICE](NOTICE) for attribution and third-party license details.
