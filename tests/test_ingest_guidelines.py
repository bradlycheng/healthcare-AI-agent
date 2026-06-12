import ingest_guidelines


def test_ingest_guidelines_reports_empty_index_as_failure(monkeypatch):
    monkeypatch.setattr(
        ingest_guidelines,
        "index_directory",
        lambda path: {"guidelines.txt": 0},
    )
    assert ingest_guidelines.main() == 1


def test_ingest_guidelines_succeeds_when_chunks_are_created(monkeypatch):
    monkeypatch.setattr(
        ingest_guidelines,
        "index_directory",
        lambda path: {"guidelines.txt": 3},
    )
    assert ingest_guidelines.main() == 0
