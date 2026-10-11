# mdict-audio

Convert audio inside MDict dictionary families for better reader compatibility.
Original dictionary files are never modified.

## Why

Many MDict dictionaries store audio in `.mdd` files and reference it from `.mdx`
entries with `sound://...` links. Some readers cannot play formats such as
Speex, OGG, WAV, or M4A reliably.

`mdict-audio` converts embedded audio to a more compatible format, rewrites the
matching `sound://` references, and verifies the generated dictionary family.

## Requirements

- Python 3.10+
- PyAV is recommended for faster MP3 conversion and decode checks.
- ffmpeg is required for the ffmpeg backend and for OGG output.

## Install

Run directly with `uvx` from GitHub after the repository is published:

```bash
uvx --from "mdict-audio[pyav] @ git+https://github.com/kibaamor/mdict-audio" mdict-audio --help
```

Use the same pattern for normal commands:

```bash
uvx --from "mdict-audio[pyav] @ git+https://github.com/kibaamor/mdict-audio" mdict-audio convert path/to/dicts --family oaldpe --to mp3
```

`uvx` installs the Python package and dependencies in an isolated temporary
environment. It does not install system tools; ffmpeg must still be available on
`PATH` for OGG output or `--engine ffmpeg`.

For local development:

```bash
pip install -e ".[pyav]"
```

Basic install without PyAV:

```bash
pip install -e .
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

Verify the generated output:

```bash
mdict-audio verify path/to/dicts/converted --family oaldpe
```

Run a full audio decode check when you need stronger validation:

```bash
mdict-audio verify path/to/dicts/converted --family oaldpe --decode
```

## Safety

- Input `.mdx` and `.mdd` files are preserved.
- By default, output is written under `converted/` inside the input directory.
- Existing output files are not overwritten unless you use `--redo`.
- `--redo` overwrites existing output files directly and may leave partial new
  output if the run fails.
- Ctrl+C exits cleanly and removes temporary staging files when possible.
- Source dictionary problems are tracked separately from problems introduced by
  conversion.

## Options

| Option | Meaning |
| --- | --- |
| `--family NAME` | Process one dictionary family. Repeat to process more than one. |
| `--to mp3\|ogg` | Choose the target audio format. Defaults to `mp3`. |
| `--engine auto\|pyav\|ffmpeg` | Choose the transcode/decode backend. Defaults to `auto`. |
| `--quality speech\|standard\|high` | Use a bitrate preset: `64k`, `128k`, or `192k`. Defaults to `speech`. |
| `--bitrate 96k` | Override the quality preset with an explicit bitrate. |
| `--force` | Re-encode clips that are already in the target format. |
| `--on-collision rename\|overwrite\|skip` | Handle resource-name collisions. Defaults to `rename`. |
| `--inline-verify all\|sample\|off` | Decode-check transcoded clips during conversion. |
| `--decode` | Fully decode audio during `verify`. |
| `--redo` | Replace existing converted output directly. |

Use `mdict-audio <command> --help` for the complete option list.

## Verify

`verify` checks that generated containers can be read and that `sound://`
references resolve to resources. With `--decode`, it also decodes every audio
clip to catch broken or unsupported audio streams.

Exit codes:

- `0`: verification passed.
- `1`: verification completed and found problems.
- `2`: command usage or runtime failure.

A failed verification does not always mean conversion introduced new damage.
Check whether problems are reported as pre-existing or introduced.

## Output Files

A converted family contains rewritten dictionary files and a manifest:

```text
oaldpe.mdx
oaldpe.mdd
oaldpe.1.mdd
oaldpe.manifest.json
```

The `.mdx` contains updated `sound://` references, the `.mdd` files contain the
converted audio resources, and the manifest records conversion settings,
statistics, selected backend, and verification findings.

## Limitations

- OGG output requires ffmpeg.
- Common PyAV wheels may not be able to encode OGG.
- Some damaged or unusual Speex files may still fail to decode.
- The tool records broken source references but does not repair missing audio.
- Audio conversion improves compatibility, not source recording quality.

## Bug Reports

Report bugs on GitHub:

```text
https://github.com/kibaamor/mdict-audio/issues
```

When reporting a bug, include the command you ran, the error output, your
platform, and whether the input dictionary can be shared or reproduced with a
small sample.

## License

This project is licensed under the BSD 3-Clause License. See `LICENSE` for
details.

## Development

Run checks with:

```bash
python -m pytest tests -q
python -m ruff check mdict_audio/ tests/
```
