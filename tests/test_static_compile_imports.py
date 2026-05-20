import compileall
import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_all_app_and_test_python_files_compile():
    assert compileall.compile_dir("app", quiet=1)
    assert compileall.compile_dir("tests", quiet=1)


def test_core_app_modules_import_cleanly():
    modules = [
        "app.agent",
        "app.api",
        "app.calculator_specs",
        "app.context_builder",
        "app.db",
        "app.fhir_builder",
        "app.grant_builder",
        "app.healthcare_agent",
        "app.hl7_guard",
        "app.hl7_parser",
        "app.llm_gateway",
        "app.patient_timeline",
        "app.query_assistant",
        "app.rag_guard",
        "app.safe_memory",
        "app.security_validation",
        "app.sql_guard",
        "app.token_guard",
        "app.warden",
    ]

    for module_name in modules:
        importlib.import_module(module_name)


def test_legacy_sqlalchemy_models_removed():
    assert not Path("app/models.py").exists()
    assert not Path("app/crud.py").exists()
