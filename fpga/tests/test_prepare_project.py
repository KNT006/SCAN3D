"""Integrity checks for reviewed comment-only source changes."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("prepare_project", Path(__file__).parents[1] / "prepare_project.py")
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


class CommentIntegrityTests(unittest.TestCase):
    def check(self, content, original_comment="// old\n", updated_comment="// new\n"):
        original = (original_comment + "module top; endmodule\n").encode()
        updated = (updated_comment + "module top; endmodule\n").encode()
        change = {"original_sha256": hashlib.sha256(original).hexdigest(),
                  "updated_sha256": hashlib.sha256(updated).hexdigest(),
                  "original_comment": original_comment, "updated_comment": updated_comment}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "source" / "top.v"
            path.parent.mkdir()
            path.write_bytes(content if content is not None else updated)
            with patch.object(PREPARE, "HERE", root):
                return PREPARE.verified_bytes(path, {"top.v": change})

    def test_comment_edit_restores_original(self):
        self.assertEqual(self.check(None), b"// old\nmodule top; endmodule\n")

    def test_logic_edit_rejected(self):
        with self.assertRaisesRegex(ValueError, "Edited source hash"):
            self.check(b"// new\nmodule changed; endmodule\n")

    def test_noncomment_override_rejected(self):
        with self.assertRaisesRegex(ValueError, "whole-line comments"):
            self.check(None, "module old;\n", "module new;\n")


if __name__ == "__main__":
    unittest.main()
