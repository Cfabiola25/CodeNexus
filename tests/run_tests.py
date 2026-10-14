"""
Ejecutor de pruebas automatizadas y generador de reporte JUnit XML.
Compatible tanto con ejecucion directa en Python como dentro del contenedor Docker tests.
"""

import os
import sys
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
TEST_RESULTS_DIR = REPO_ROOT / "test-results"
JUNIT_REPORT_PATH = TEST_RESULTS_DIR / "junit.xml"

# Asegurar que la raiz este en sys.path
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def collect_tests(suite_item):
    """Recolecta todos los casos de prueba de forma recursiva antes de ejecutar."""
    all_tests = []
    for item in suite_item:
        if isinstance(item, unittest.TestSuite):
            all_tests.extend(collect_tests(item))
        elif item is not None and hasattr(item, "id"):
            all_tests.append(item)
    return all_tests


def run_and_report():
    TEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(HERE), pattern="test_*.py")

    # Recolectar lista de pruebas ANTES de suite.run (en Python 3.13+ suite vacia sus elementos durante run)
    all_cases = collect_tests(suite)

    start_time = time.time()
    result = unittest.TestResult()
    suite.run(result)
    duration = time.time() - start_time

    testsuite_elem = ET.Element("testsuite", {
        "name": "gateway-tests",
        "tests": str(len(all_cases)),
        "failures": str(len(result.failures)),
        "errors": str(len(result.errors)),
        "skipped": str(len(result.skipped)),
        "time": f"{duration:.3f}",
    })

    failure_dict = {test.id(): err for test, err in result.failures}
    error_dict = {test.id(): err for test, err in result.errors}
    skipped_dict = {test.id(): reason for test, reason in result.skipped}

    for test in all_cases:
        test_id = test.id()
        parts = test_id.split(".")
        classname = ".".join(parts[:-1]) if len(parts) > 1 else "tests"
        name = parts[-1]

        case_elem = ET.SubElement(testsuite_elem, "testcase", {
            "classname": classname,
            "name": name,
            "time": "0.010",
        })

        if test_id in failure_dict:
            fail_elem = ET.SubElement(case_elem, "failure", {"message": "Test assertion failed"})
            fail_elem.text = failure_dict[test_id]
        elif test_id in error_dict:
            err_elem = ET.SubElement(case_elem, "error", {"message": "Test execution error"})
            err_elem.text = error_dict[test_id]
        elif test_id in skipped_dict:
            skip_elem = ET.SubElement(case_elem, "skipped", {"message": skipped_dict[test_id]})

    tree = ET.ElementTree(testsuite_elem)
    ET.indent(tree, space="  ", level=0)
    tree.write(str(JUNIT_REPORT_PATH), encoding="utf-8", xml_declaration=True)

    print(f"============================================================")
    print(f"PRUEBAS AUTOMATIZADAS: {len(all_cases)} ejecutadas en {duration:.2f}s")
    print(f"Aprobadas: {len(all_cases) - len(result.failures) - len(result.errors)}")
    print(f"Fallidas:  {len(result.failures)}")
    print(f"Errores:   {len(result.errors)}")
    print(f"Reporte JUnit XML guardado en: {JUNIT_REPORT_PATH}")
    print(f"============================================================")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_and_report())
