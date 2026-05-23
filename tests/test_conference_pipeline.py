import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


class ConferencePipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("conference_pipeline_mod", src_dir / "conference_pipeline.py")

    def test_load_count_counts_non_empty_queries(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as f:
            path = pathlib.Path(f.name)
            json.dump(
                {
                    "papers": [{"id": "a"}, {"id": "b"}],
                    "queries": [
                        {"sim_scores": {"a": {"rank": 1}}},
                        {"sim_scores": {}},
                    ],
                },
                f,
            )
        try:
            self.assertEqual(
                self.mod.load_count(path),
                {"papers": 2, "queries": 2, "non_empty_queries": 1},
            )
        finally:
            path.unlink(missing_ok=True)

    def test_write_manifest_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "manifest.json"
            self.mod.write_manifest(path, {"ok": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"ok": True})


if __name__ == "__main__":
    unittest.main()
