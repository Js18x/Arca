import duckdb

import run_imports


class FakeImporter:
    """Stands in for an importer module: counts how often it is run."""

    ACCOUNT = {"account_id": 99}

    def __init__(self, fail=False):
        self.runs = 0
        self.fail = fail

    def run(self, connection):
        self.runs += 1
        if self.fail:
            raise ValueError("bad row")
        return 5


def setup(tmp_path, fail=False):
    folder = tmp_path / "broker"
    folder.mkdir()
    importer = FakeImporter(fail)
    sources = {"broker": (importer, [folder])}
    return folder, importer, sources, tmp_path / "test.duckdb"


def test_imports_only_when_files_change(tmp_path):
    folder, importer, sources, db = setup(tmp_path)

    run_imports.import_changed(sources, db)
    assert importer.runs == 0  # no CSV files yet

    (folder / "a.csv").write_text("x\n1\n")
    assert run_imports.import_changed(sources, db) == {"broker": 5}
    assert importer.runs == 1

    run_imports.import_changed(sources, db)
    assert importer.runs == 1  # nothing changed

    (folder / "b.csv").write_text("x\n2\n")
    run_imports.import_changed(sources, db)
    assert importer.runs == 2  # new file

    (folder / "a.csv").write_text("x\n3\n")
    run_imports.import_changed(sources, db)
    assert importer.runs == 3  # edited file

    run_imports.import_changed(sources, db, force=True)
    assert importer.runs == 4


def test_failed_import_is_retried(tmp_path):
    folder, importer, sources, db = setup(tmp_path, fail=True)
    (folder / "a.csv").write_text("x\n1\n")

    assert run_imports.import_changed(sources, db) == {}
    run_imports.import_changed(sources, db)
    assert importer.runs == 2

    with duckdb.connect(str(db)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM import_runs").fetchone() == (0,)


def test_fingerprint_ignores_modification_time(tmp_path):
    folder = tmp_path / "broker"
    folder.mkdir()
    path = folder / "a.csv"
    path.write_text("x\n1\n")
    before = run_imports.fingerprint([folder])

    path.write_text("x\n1\n")  # same contents, new modification time
    assert run_imports.fingerprint([folder]) == before


def test_importer_code_change_triggers_reimport(tmp_path, capsys):
    folder, importer, sources, db = setup(tmp_path)
    (folder / "a.csv").write_text("x\n1\n")
    code = tmp_path / "fake_importer.py"
    code.write_text("# version 1\n")
    importer.__file__ = str(code)

    run_imports.import_changed(sources, db)
    run_imports.import_changed(sources, db)
    assert importer.runs == 1

    code.write_text("# version 2: a bug fix\n")
    run_imports.import_changed(sources, db)
    assert importer.runs == 2
    assert "broker: importer code changed, importing..." in capsys.readouterr().out


def test_import_reason():
    reason = run_imports.import_reason
    assert reason(("f", "c"), None, force=False) == "first import"
    assert reason(("f", "c"), ("f", "c"), force=False) is None
    assert reason(("f", "c"), ("f", "c"), force=True) == "forced"
    assert reason(("f2", "c"), ("f", "c"), force=False) == "files changed"
    assert reason(("f", "c2"), ("f", "c"), force=False) == "importer code changed"
    assert reason(("f2", "c2"), ("f", "c"), force=False) == "files and importer code changed"
