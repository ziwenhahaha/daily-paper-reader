import importlib.util
import pathlib
import sys
import unittest
from unittest import mock


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


class FetchSystemsSecurityConferencesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module(
            "fetch_systems_security_conferences_mod",
            src_dir / "maintain" / "fetchers" / "fetch_systems_security_conferences.py",
        )

    def test_parse_osdi_paper_page_uses_citation_pdf_url(self):
        html = """
        <meta name="citation_title" content="A Real OSDI Paper">
        <meta name="citation_author" content="Ada Lovelace">
        <meta name="citation_author" content="Grace Hopper">
        <meta name="citation_publication_date" content="2025/07/07">
        <meta name="citation_pdf_url" content="https://www.usenix.org/system/files/osdi25-demo.pdf">
        <div class="field-name-field-paper-description"><p>Abstract text.</p></div>
        """
        paper = self.mod.parse_osdi_paper_page(html, year=2025, page_url="https://www.usenix.org/conference/osdi25/presentation/demo")
        self.assertEqual(paper["source"], "OSDI-2025-USENIX")
        self.assertEqual(paper["title"], "A Real OSDI Paper")
        self.assertEqual(paper["authors"], ["Ada Lovelace", "Grace Hopper"])
        self.assertEqual(paper["published"], "2025-07-07T00:00:00Z")
        self.assertEqual(paper["pdf_url"], "https://www.usenix.org/system/files/osdi25-demo.pdf")

    def test_parse_ndss_paper_page_finds_official_paper_pdf(self):
        html = """
        <h1>NDSS Paper Title</h1>
        <a class="pdf-button" href="https://www.ndss-symposium.org/wp-content/uploads/2026-f797-paper.pdf">Paper</a>
        <strong>Authors:</strong> Alice, Bob
        <h3>Abstract:</h3><p>NDSS abstract.</p>
        """
        paper = self.mod.parse_ndss_paper_page(html, year=2026, page_url="https://www.ndss-symposium.org/ndss-paper/demo/")
        self.assertEqual(paper["source"], "NDSS-2026-Accepted")
        self.assertEqual(paper["title"], "NDSS Paper Title")
        self.assertEqual(paper["pdf_url"], "https://www.ndss-symposium.org/wp-content/uploads/2026-f797-paper.pdf")

    def test_parse_ndss_paper_page_reads_paper_data_abstract(self):
        html = """
        <h1>NDSS Paper Title</h1>
        <a href="https://www.ndss-symposium.org/wp-content/uploads/2026-f797-paper.pdf">Paper</a>
        <div class="paper-data">
          <p><strong><p>Alice (Example University), Bob (Example Lab)</p></strong></p>
          <p><p>This is the real abstract from the NDSS paper page.</p></p>
        </div>
        """
        paper = self.mod.parse_ndss_paper_page(html, year=2026, page_url="https://www.ndss-symposium.org/ndss-paper/demo/")
        self.assertEqual(paper["authors"], ["Alice", "Bob"])
        self.assertEqual(paper["abstract"], "This is the real abstract from the NDSS paper page.")

    def test_parse_sosp_accepted_page_pairs_titles_and_authors(self):
        html = """
        <ul class="paperlist">
          <li><b>Rearchitecting the Thread Model</b><br><em>Ada Lovelace, Grace Hopper</em></li>
          <li><b>Device-Assisted Live Migration</b><br><em>Barbara Liskov</em></li>
        </ul>
        """
        papers = self.mod.parse_sosp_accepted_page(html, year=2025)
        self.assertEqual([p["title"] for p in papers], ["Rearchitecting the Thread Model", "Device-Assisted Live Migration"])
        self.assertEqual(papers[0]["authors"], ["Ada Lovelace", "Grace Hopper"])
        self.assertEqual(papers[0]["source"], "SOSP-2025-ACM")

    def test_build_acm_pdf_url_from_doi(self):
        self.assertEqual(
            self.mod.build_acm_pdf_url("10.1145/3731569.3764794"),
            "https://dl.acm.org/doi/pdf/10.1145/3731569.3764794",
        )

    def test_enrich_sosp_with_crossref_queries_unmatched_title(self):
        papers = [
            {
                "title": "Efficient File-Lifetime Redundancy Management for Cluster File Systems",
                "link": "https://sigops.org/s/conferences/sosp/2024/accepted.html",
                "pdf_url": "",
                "published": "2024-01-01T00:00:00Z",
            }
        ]

        def fake_get(_url, params=None, **_kwargs):
            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    if params and params.get("query.title"):
                        return {
                            "message": {
                                "items": [
                                    {
                                        "DOI": "10.1145/3694715.3695981",
                                        "title": ["Morph: Efficient File-Lifetime Redundancy Management for Cluster File Systems"],
                                        "container-title": ["Proceedings of the ACM SIGOPS 30th Symposium on Operating Systems Principles"],
                                        "published": {"date-parts": [[2024, 11, 4]]},
                                    }
                                ]
                            }
                        }
                    return {"message": {"items": []}}

            return Resp()

        with mock.patch.object(self.mod.requests, "get", side_effect=fake_get):
            out = self.mod.enrich_sosp_with_crossref(papers, year=2024)

        self.assertEqual(out[0]["doi"], "10.1145/3694715.3695981")
        self.assertEqual(out[0]["pdf_url"], "https://dl.acm.org/doi/pdf/10.1145/3694715.3695981")
        self.assertEqual(out[0]["published"], "2024-11-04T00:00:00Z")

    def test_apply_semantic_scholar_abstracts_only_fills_missing_sosp_abstracts(self):
        papers = [
            {"doi": "10.1145/1", "abstract": ""},
            {"doi": "10.1145/2", "abstract": "Keep official abstract."},
        ]
        items = [
            {"externalIds": {"DOI": "10.1145/1"}, "abstract": "Semantic Scholar abstract."},
            {"externalIds": {"DOI": "10.1145/2"}, "abstract": "Should not overwrite."},
        ]
        out = self.mod.apply_semantic_scholar_abstracts(papers, items)
        self.assertEqual(out[0]["abstract"], "Semantic Scholar abstract.")
        self.assertEqual(out[1]["abstract"], "Keep official abstract.")

    def test_parse_arxiv_feed_and_apply_public_pdf_candidate(self):
        feed = """
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>https://arxiv.org/abs/2505.07239v1</id>
            <title>Comet: Accelerating Private Inference for Large Language Model by Predicting Activation Sparsity</title>
            <summary>ArXiv abstract.</summary>
            <published>2025-05-11T00:00:00Z</published>
            <author><name>Ada Lovelace</name></author>
            <author><name>Grace Hopper</name></author>
          </entry>
        </feed>
        """
        papers = [
            {
                "title": "Comet: Accelerating Private Inference for Large Language Model by Predicting Activation Sparsity",
                "abstract": "",
                "authors": [],
                "link": "https://sp2025.ieee-security.org/accepted-papers.html",
                "pdf_url": "",
            }
        ]

        entries = self.mod.parse_arxiv_feed_entries(feed)
        out = self.mod.apply_arxiv_pdf_candidates(papers, entries)

        self.assertEqual(out[0]["pdf_url"], "https://arxiv.org/pdf/2505.07239v1")
        self.assertEqual(out[0]["link"], "https://arxiv.org/abs/2505.07239v1")
        self.assertEqual(out[0]["abstract"], "ArXiv abstract.")
        self.assertEqual(out[0]["authors"], ["Ada Lovelace", "Grace Hopper"])

    def test_fetch_arxiv_title_matches_retries_rate_limit(self):
        feed = """
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>https://arxiv.org/abs/2604.09558v1</id>
            <title>VTC: DNN Compilation with Virtual Tensors for Data Movement Elimination</title>
            <summary>VTC abstract.</summary>
          </entry>
        </feed>
        """
        calls = []

        class Resp:
            def __init__(self, status_code, text=""):
                self.status_code = status_code
                self.text = text

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise self.mod.requests.HTTPError("rate limited")

        def fake_get(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                resp = Resp(429)
            else:
                resp = Resp(200, feed)
            resp.mod = self.mod
            return resp

        with mock.patch.object(self.mod.requests, "get", side_effect=fake_get), mock.patch.object(self.mod.time, "sleep"):
            entries = self.mod.fetch_arxiv_title_matches(
                [{"title": "VTC: DNN Compilation with Virtual Tensors for Data Movement Elimination"}],
                request_delay=0,
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(entries[0]["pdf_url"], "https://arxiv.org/pdf/2604.09558v1")

    def test_apply_arxiv_pdf_candidates_keeps_existing_pdf(self):
        papers = [
            {
                "title": "Open CSDL Paper",
                "abstract": "Official abstract.",
                "authors": ["Ada"],
                "link": "https://www.computer.org/csdl/example",
                "pdf_url": "https://www.computer.org/csdl/pds/api/csdl/proceedings/download-article/open/pdf",
            }
        ]
        entries = [
            {
                "title": "Open CSDL Paper",
                "abstract": "ArXiv abstract.",
                "authors": ["Grace"],
                "abs_url": "https://arxiv.org/abs/2501.00001",
                "pdf_url": "https://arxiv.org/pdf/2501.00001",
            }
        ]

        out = self.mod.apply_arxiv_pdf_candidates(papers, entries)

        self.assertEqual(out[0]["pdf_url"], "https://www.computer.org/csdl/pds/api/csdl/proceedings/download-article/open/pdf")
        self.assertEqual(out[0]["link"], "https://www.computer.org/csdl/example")
        self.assertEqual(out[0]["abstract"], "Official abstract.")
        self.assertEqual(out[0]["authors"], ["Ada"])

    def test_ieee_sp_keeps_only_public_pdf_articles(self):
        articles = [
            {"id": "open", "title": "Open Paper", "abstract": "Escaped &#x2019; abstract.", "normalizedAbstract": "Readable abstract.", "authors": [{"fullName": "Ada"}], "isOpenAccess": True, "hasPdf": True, "fno": "313000a001", "doi": "10.1109/SP.1", "year": "2024"},
            {"id": "locked", "title": "Locked Paper", "authors": [{"fullName": "Bob"}], "isOpenAccess": False, "hasPdf": True, "fno": "223600a001", "doi": "10.1109/SP.2", "year": "2025"},
            {"id": "front", "title": "Title Page", "authors": [], "isOpenAccess": True, "hasPdf": True, "fno": "223600z001", "doi": "10.1109/SP.3", "year": "2025"},
        ]
        papers = self.mod.normalize_ieee_sp_articles(articles, year=2025, require_public_pdf=True)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["id"], "ieee-sp-2025-open-paper")
        self.assertEqual(
            papers[0]["pdf_url"],
            "https://www.computer.org/csdl/pds/api/csdl/proceedings/download-article/open/pdf",
        )
        self.assertEqual(papers[0]["abstract"], "Readable abstract.")

    def test_parse_ieee_sp_accepted_page_extracts_titles_and_authors(self):
        html = """
        <div class="list-group-item">
          <a data-toggle="collapse" href="#collapse-0">Bridge: High-Order Taint Vulnerabilities Detection in Linux-based IoT Firmware</a>
        </div>
        <div class="collapse authorlist" id="collapse-0">
          Alice<sup>1</sup>, Bob<sup>2,3</sup>, Carol<sup>1</sup><br>
          <sup>1</sup>: Example University, <sup>2</sup>: Example Lab
        </div>
        """

        papers = self.mod.parse_ieee_sp_accepted_page(html, year=2026, page_url="https://sp2026.ieee-security.org/accepted-papers.html")

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["title"], "Bridge: High-Order Taint Vulnerabilities Detection in Linux-based IoT Firmware")
        self.assertEqual(papers[0]["authors"], ["Alice", "Bob", "Carol"])
        self.assertEqual(papers[0]["source"], "IEEE-SP-2026-Accepted")
        self.assertEqual(papers[0]["pdf_url"], "")


if __name__ == "__main__":
    unittest.main()
