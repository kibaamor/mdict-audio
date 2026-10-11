from mdict_audio.cli import build_parser, main


def test_help_lists_all_commands():
    parser = build_parser()
    assert "inspect" in parser.format_help()
    assert "convert" in parser.format_help()
    assert "verify" in parser.format_help()


def test_subcommand_help_exits_zero(capsys):
    import pytest

    with pytest.raises(SystemExit) as exc:
        main(["inspect", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--family" in out


def test_convert_help_documents_redo_overwrite(capsys):
    import pytest

    with pytest.raises(SystemExit) as exc:
        main(["convert", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--redo" in out
    assert "overwrite" in out
    assert "partial" in out


def test_keyboard_interrupt_is_friendly(capsys, monkeypatch):
    from mdict_audio.commands import inspect as inspect_cmd

    def interrupted(args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(inspect_cmd, "run", interrupted)
    rc = main(["inspect", "whatever"])
    err = capsys.readouterr().err
    assert rc == 130
    assert "interrupted" in err
