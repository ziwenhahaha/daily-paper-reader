import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"


CONFERENCE_SQL = {
    "neurips": {
        "table": "neurips_openreview_papers",
        "create": "create_neurips_openreview_papers_schema.sql",
        "match": "match_neurips_openreview_papers.sql",
        "exact": "match_neurips_openreview_papers_exact",
        "bm25": "match_neurips_openreview_papers_bm25",
    },
    "icml": {
        "table": "icml_openreview_papers",
        "create": "create_icml_openreview_papers_schema.sql",
        "match": "match_icml_openreview_papers.sql",
        "exact": "match_icml_openreview_papers_exact",
        "bm25": "match_icml_openreview_papers_bm25",
    },
    "iclr": {
        "table": "iclr_openreview_papers",
        "create": "create_iclr_openreview_papers_schema.sql",
        "match": "match_iclr_openreview_papers.sql",
        "exact": "match_iclr_openreview_papers_exact",
        "bm25": "match_iclr_openreview_papers_bm25",
    },
    "aaai": {
        "table": "aaai_papers",
        "create": "create_aaai_papers_schema.sql",
        "match": "match_aaai_papers.sql",
        "exact": "match_aaai_papers_exact",
        "bm25": "match_aaai_papers_bm25",
    },
    "acl": {
        "table": "acl_papers",
        "create": "create_acl_papers_schema.sql",
        "match": "match_acl_papers.sql",
        "exact": "match_acl_papers_exact",
        "bm25": "match_acl_papers_bm25",
    },
    "emnlp": {
        "table": "emnlp_papers",
        "create": "create_emnlp_papers_schema.sql",
        "match": "match_emnlp_papers.sql",
        "exact": "match_emnlp_papers_exact",
        "bm25": "match_emnlp_papers_bm25",
    },
    "cvpr": {
        "table": "cvpr_papers",
        "create": "create_cvpr_papers_schema.sql",
        "match": "match_cvpr_papers.sql",
        "exact": "match_cvpr_papers_exact",
        "bm25": "match_cvpr_papers_bm25",
    },
    "eccv": {
        "table": "eccv_papers",
        "create": "create_eccv_papers_schema.sql",
        "match": "match_eccv_papers.sql",
        "exact": "match_eccv_papers_exact",
        "bm25": "match_eccv_papers_bm25",
    },
    "ijcai": {
        "table": "ijcai_papers",
        "create": "create_ijcai_papers_schema.sql",
        "match": "match_ijcai_papers.sql",
        "exact": "match_ijcai_papers_exact",
        "bm25": "match_ijcai_papers_bm25",
    },
    "osdi": {
        "table": "osdi_papers",
        "create": "create_osdi_papers_schema.sql",
        "match": "match_osdi_papers.sql",
        "exact": "match_osdi_papers_exact",
        "bm25": "match_osdi_papers_bm25",
    },
    "sosp": {
        "table": "sosp_papers",
        "create": "create_sosp_papers_schema.sql",
        "match": "match_sosp_papers.sql",
        "exact": "match_sosp_papers_exact",
        "bm25": "match_sosp_papers_bm25",
    },
    "ieee_sp": {
        "table": "ieee_sp_papers",
        "create": "create_ieee_sp_papers_schema.sql",
        "match": "match_ieee_sp_papers.sql",
        "exact": "match_ieee_sp_papers_exact",
        "bm25": "match_ieee_sp_papers_bm25",
    },
    "ndss": {
        "table": "ndss_papers",
        "create": "create_ndss_papers_schema.sql",
        "match": "match_ndss_papers.sql",
        "exact": "match_ndss_papers_exact",
        "bm25": "match_ndss_papers_bm25",
    },
}


class ConferenceSupabaseSqlContractTest(unittest.TestCase):
    def test_unified_conference_view_and_rpcs_exist(self):
        path = SQL_DIR / "create_conference_papers_unified.sql"
        self.assertTrue(path.exists(), f"missing {path.name}")
        sql = path.read_text(encoding="utf-8").lower()

        self.assertIn("create or replace view public.conference_papers_unified", sql)
        for column in ["conference_key", "conference_year", "conference_pair", "source_table"]:
            self.assertIn(column, sql)
        for spec in CONFERENCE_SQL.values():
            self.assertIn(f"from public.{spec['table']}", sql)
        self.assertIn("create or replace function public.match_conference_papers_exact", sql)
        self.assertIn("create or replace function public.match_conference_papers_bm25", sql)
        self.assertRegex(sql, r"filter_pairs\s+text\[\]\s+default\s+null")
        self.assertIn("p.conference_pair = any(filter_pairs)", sql)
        self.assertIn("grant select on public.conference_papers_unified to anon, authenticated", sql)
        self.assertIn("grant execute on function public.match_conference_papers_exact", sql)
        self.assertIn("grant execute on function public.match_conference_papers_bm25", sql)

    def test_all_conference_schema_files_define_pdf_url(self):
        for conference, spec in CONFERENCE_SQL.items():
            with self.subTest(conference=conference):
                sql = (SQL_DIR / spec["create"]).read_text(encoding="utf-8").lower()
                self.assertRegex(sql, r"\bpdf_url\s+text\b")

    def test_all_conference_match_rpc_files_exist_and_return_pdf_url(self):
        for conference, spec in CONFERENCE_SQL.items():
            with self.subTest(conference=conference):
                path = SQL_DIR / spec["match"]
                self.assertTrue(path.exists(), f"missing {path.name}")
                sql = path.read_text(encoding="utf-8")
                self.assertIn(f"create or replace function {spec['exact']}(", sql)
                self.assertIn(f"create or replace function {spec['bm25']}(", sql)
                self.assertGreaterEqual(len(re.findall(r"\bpdf_url\s+text\b", sql.lower())), 2)
                self.assertGreaterEqual(len(re.findall(r"\bp\.pdf_url\b", sql.lower())), 2)

    def test_conference_anon_policy_covers_all_production_conference_tables(self):
        sql = (SQL_DIR / "enable_conference_anon_read_policies.sql").read_text(encoding="utf-8").lower()
        for conference, spec in CONFERENCE_SQL.items():
            with self.subTest(conference=conference):
                table = spec["table"]
                self.assertIn(f"alter table public.{table} enable row level security", sql)
                self.assertIn(f"grant select on table public.{table} to anon, authenticated", sql)
                self.assertIn(f"grant execute on function public.{spec['exact']}", sql)
                self.assertIn(f"grant execute on function public.{spec['bm25']}", sql)


if __name__ == "__main__":
    unittest.main()
