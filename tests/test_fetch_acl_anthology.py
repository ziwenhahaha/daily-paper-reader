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


class FetchACLAnthologyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module(
            "fetch_acl_anthology_mod",
            src_dir / "maintain" / "fetchers" / "fetch_acl_anthology.py",
        )

    def test_iter_target_years(self):
        self.assertEqual(self.mod.iter_target_years(2025, 3), [2023, 2024, 2025])

    def test_paper_url(self):
        self.assertEqual(
            self.mod._paper_url("/2025.acl-long.1/"),
            "https://aclanthology.org/2025.acl-long.1/",
        )

    def test_strip_abstract_prefix(self):
        self.assertEqual(self.mod._strip_abstract_prefix("Abstract Hello"), "Hello")


if __name__ == "__main__":
    unittest.main()
