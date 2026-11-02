import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_inputs import required_source


class SourceInputsTest(unittest.TestCase):
    def test_requires_explicit_input(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                required_source("SCAN3D_SAMPLE_ROOT", directory=True)

    def test_validates_file_and_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "mesh.stl"
            source.write_bytes(b"fixture")
            with patch.dict(os.environ, {"SOURCE": str(source), "ROOT": directory}):
                self.assertEqual(required_source("SOURCE"), source.resolve())
                self.assertEqual(required_source("ROOT", directory=True), Path(directory).resolve())
                with self.assertRaises(FileNotFoundError):
                    required_source("ROOT")
            self.assertEqual(source.read_bytes(), b"fixture")


if __name__ == "__main__":
    unittest.main()
