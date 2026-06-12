from app import vector_store
from app import embeddings


def test_vector_store_add_search_and_clear(tmp_path, monkeypatch):
    store_path = tmp_path / "vectors.sqlite3"
    monkeypatch.setattr(vector_store, "VECTOR_STORE_PATH", str(store_path))
    monkeypatch.setattr(
        embeddings,
        "embed_texts",
        lambda documents: [[1.0, 0.0], [0.0, 1.0]],
    )
    monkeypatch.setattr(vector_store, "embed_text", lambda query: [1.0, 0.0])

    vector_store.add_documents(
        ["blood pressure guidance", "glucose guidance"],
        [{"title": "BP"}, {"title": "Glucose"}],
        ["bp-1", "glucose-1"],
    )

    assert vector_store.get_document_count() == 2
    results = vector_store.search("blood pressure", top_k=1)
    assert results["documents"] == [["blood pressure guidance"]]
    assert results["metadatas"] == [[{"title": "BP"}]]
    assert results["distances"][0][0] == 0.0

    vector_store.clear_collection()
    assert vector_store.get_document_count() == 0


def test_vector_store_rejects_mismatched_input_lengths(tmp_path, monkeypatch):
    monkeypatch.setattr(
        vector_store,
        "VECTOR_STORE_PATH",
        str(tmp_path / "vectors.sqlite3"),
    )

    try:
        vector_store.add_documents(["one"], [], ["id-1"])
    except ValueError as error:
        assert "equal lengths" in str(error)
    else:
        raise AssertionError("mismatched vector-store inputs should fail")
