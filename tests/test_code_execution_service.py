import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.code_execution_service import CodeExecutionService


class CodeExecutionServiceTests(unittest.TestCase):
    def test_resolve_workspace_path_blocks_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("services.code_execution_service.CODE_WORKSPACE_ROOT", temp_dir):
                service = CodeExecutionService()
                with self.assertRaises(ValueError):
                    service.resolve_workspace_path("../outside.py")

    def test_create_and_read_file_in_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("services.code_execution_service.CODE_WORKSPACE_ROOT", temp_dir):
                service = CodeExecutionService()
                created = service.create_file("sample.py", "print('hello')")
                self.assertEqual(created, "sample.py")
                self.assertEqual(service.read_file("sample.py"), "print('hello')")
                self.assertTrue((Path(temp_dir) / "sample.py").exists())


if __name__ == "__main__":
    unittest.main()
