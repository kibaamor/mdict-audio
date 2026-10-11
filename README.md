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
- PyAV is recommended for MP3 conversion and decode checks.
- `ffmpeg` must be available on `PATH` for OGG output, `--engine ffmpeg`, or
  automatic fallback when PyAV is not installed.

## Install

Run directly with `uvx`:

```bash
uvx --from "mdict-audio[pyav] @ git+https://github.com/kibaamor/mdict-audio" mdict-audio --help
```

Use the same pattern for normal commands:

```bash
uvx --from "mdict-audio[pyav] @ git+https://github.com/kibaamor/mdict-audio" mdict-audio convert path/to/dicts --family oaldpe --to mp3
```

`uvx` installs the Python package and Python dependencies in an isolated
temporary environment. It does not install system tools, so install `ffmpeg`
separately when you need OGG output or the ffmpeg backend.

For local development:

```bash
python -m pip install -e ".[pyav,test]"
```

Basic local install without PyAV:

```bash
python -m pip install -e .
```

Check the CLI:

```bash
mdict-audio --help
```

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

A failed verification does not always mean conversion introduced new damage.
Check whether problems are reported as pre-existing or introduced.

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

## Development

Run checks with:

```bash
python -m pytest tests -q
python -m ruff check mdict_audio/ tests/
```

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
