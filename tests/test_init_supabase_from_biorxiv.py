import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class InitSupabaseFromBioRxivTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module(
            "init_biorxiv_supabase_mod",
            src_dir / "maintain" / "init_biorxiv.py",
        )

    def test_resolve_date_token_long_range(self):
        token = self.mod.resolve_date_token("", 30)
        self.assertRegex(token, r"^\d{8}-\d{8}$")

    def test_resolve_date_token_manual(self):
        token = self.mod.resolve_date_token("20260301-20260310", 30)
        self.assertEqual(token, "20260301-20260310")

    def test_init_biorxiv_import_does_not_require_torch(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        real_import = __import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "torch":
                raise ModuleNotFoundError("No module named 'torch'")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=guarded_import):
            mod = _load_module(
                "init_biorxiv_without_torch_mod",
                root / "src" / "maintain" / "init_biorxiv.py",
            )

        self.assertIsNone(mod.torch)


if __name__ == "__main__":
    unittest.main()
