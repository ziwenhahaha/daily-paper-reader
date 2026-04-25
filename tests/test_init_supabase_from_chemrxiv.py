import importlib.util
import pathlib
import sys
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class InitSupabaseFromChemRxivTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module(
            "init_chemrxiv_supabase_mod",
            src_dir / "maintain" / "init_chemrxiv.py",
        )

    def test_default_date_token_uses_today(self):
        self.assertRegex(self.mod.TODAY_STR, r"^\d{8}$")


if __name__ == "__main__":
    unittest.main()
