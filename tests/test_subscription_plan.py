import unittest
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.subscription_plan import (
    build_pipeline_inputs,
    count_subscription_tags,
)


class SubscriptionPlanTest(unittest.TestCase):
    def test_build_pipeline_inputs_from_profiles(self):
        cfg = {
            'subscriptions': {
                'schema_migration': {'stage': 'A'},
                'intent_profiles': [
                    {
                        'id': 'p1',
                        'tag': 'SR',
                        'enabled': True,
                        'keywords': [
                            {
                                'keyword': 'A AND B',
                                'query': 'find papers about A and B',
                                'logic_cn': '语义补充',
                                'enabled': True,
                            },
                        ],
                    }
                ],
            }
        }

        plan = build_pipeline_inputs(cfg)
        self.assertEqual(plan['stage'], 'A')
        self.assertTrue(plan['bm25_queries'])
        self.assertTrue(plan['embedding_queries'])
        self.assertTrue(plan['context_keywords'])
        self.assertTrue(plan['context_queries'])

        kw_bm25 = [q for q in plan['bm25_queries'] if q.get('type') == 'keyword'][0]
        self.assertEqual(kw_bm25.get('boolean_expr'), '')
        self.assertEqual(kw_bm25.get('query_text'), 'A B')
        self.assertEqual(kw_bm25.get('paper_tag'), 'keyword:SR')
        self.assertEqual(kw_bm25.get('paper_sources'), ['arxiv'])

    def test_build_pipeline_inputs_without_profiles(self):
        plan = build_pipeline_inputs({'subscriptions': {'keyword_recall_mode': 'or'}})
        self.assertEqual(plan['stage'], 'A')
        self.assertEqual(plan['source'], 'intent_profiles_required_but_missing')
        self.assertEqual(plan['bm25_queries'], [])
        self.assertEqual(plan['embedding_queries'], [])
        self.assertEqual(plan['context_keywords'], [])
        self.assertEqual(plan['context_queries'], [])

    def test_build_pipeline_inputs_boolean_mixed_mode(self):
        cfg = {
            'subscriptions': {
                'keyword_recall_mode': 'boolean_mixed',
                'intent_profiles': [
                    {
                        'id': 'p1',
                        'tag': 'SR',
                        'enabled': True,
                        'keywords': [
                            'A AND B',
                        ],
                    }
                ],
            }
        }
        plan = build_pipeline_inputs(cfg)
        kw_bm25 = [q for q in plan['bm25_queries'] if q.get('type') == 'keyword'][0]
        self.assertEqual(kw_bm25.get('boolean_expr'), '')
        self.assertEqual(kw_bm25.get('query_text'), 'A B')

    def test_build_pipeline_inputs_accepts_query_strings(self):
        cfg = {
            'subscriptions': {
                'intent_profiles': [
                    {
                        'id': 'p1',
                        'tag': 'SR',
                        'enabled': True,
                        'keywords': ['legacy expr'],
                    }
                ],
            }
        }
        plan = build_pipeline_inputs(cfg)
        kw_bm25 = [q for q in plan['bm25_queries'] if q.get('type') == 'keyword'][0]
        self.assertEqual(kw_bm25.get('query_text'), 'legacy expr')
        emb = [q for q in plan['embedding_queries'] if q.get('type') == 'keyword'][0]
        self.assertEqual(emb.get('query_text'), 'legacy expr')
        self.assertEqual(emb.get('paper_sources'), ['arxiv'])

    def test_build_pipeline_inputs_with_intent_queries(self):
        cfg = {
            'subscriptions': {
                'intent_profiles': [
                    {
                        'id': 'p1',
                        'tag': 'SR',
                        'enabled': True,
                        'keywords': [
                            {
                                'keyword': 'Symbolic Regression',
                                'query': 'symbolic regression methods',
                                'enabled': True,
                            },
                        ],
                        'intent_queries': [
                            {'query': 'symbolic regression with reinforcement learning', 'enabled': True},
                            {'query': 'equation discovery for physical systems', 'enabled': True},
                        ],
                    }
                ],
            }
        }
        plan = build_pipeline_inputs(cfg)

        intent_bm25 = [q for q in plan['bm25_queries'] if q.get('type') == 'intent_query']
        intent_emb = [q for q in plan['embedding_queries'] if q.get('type') == 'intent_query']
        intent_context = [q for q in plan['context_queries'] if q.get('tag', '') == 'query:SR']

        self.assertEqual(len(intent_bm25), 2)
        self.assertEqual(len(intent_emb), 2)
        self.assertEqual(len(intent_context), 3)

        bm25_texts = [q.get('query_text') for q in intent_bm25]
        self.assertIn('symbolic regression with reinforcement learning', bm25_texts)
        self.assertIn('equation discovery for physical systems', bm25_texts)

        emb_texts = [q.get('query_text') for q in intent_emb]
        self.assertIn('symbolic regression with reinforcement learning', emb_texts)
        self.assertIn('equation discovery for physical systems', emb_texts)

        context_texts = [q.get('query') for q in intent_context]
        self.assertIn('symbolic regression methods', context_texts)
        self.assertIn('symbolic regression with reinforcement learning', context_texts)
        self.assertIn('equation discovery for physical systems', context_texts)

    def test_build_pipeline_inputs_keeps_explicit_paper_sources(self):
        cfg = {
            'source_backends': {
                'arxiv': {'enabled': True},
                'biorxiv': {'enabled': True},
            },
            'subscriptions': {
                'intent_profiles': [
                    {
                        'id': 'p1',
                        'tag': 'BIO',
                        'enabled': True,
                        'paper_sources': ['arxiv', 'biorxiv'],
                        'keywords': [
                            {'keyword': 'protein design', 'query': 'protein design with language models', 'enabled': True},
                        ],
                    }
                ],
            },
        }
        plan = build_pipeline_inputs(cfg)
        self.assertEqual(plan['profiles'][0].get('paper_sources'), ['arxiv', 'biorxiv'])
        self.assertEqual(plan['bm25_queries'][0].get('paper_sources'), ['arxiv', 'biorxiv'])

    def test_build_pipeline_inputs_rejects_empty_paper_sources(self):
        cfg = {
            'subscriptions': {
                'intent_profiles': [
                    {
                        'tag': 'BAD',
                        'enabled': True,
                        'paper_sources': [],
                        'keywords': [{'keyword': 'x', 'query': 'x'}],
                    }
                ],
            }
        }
        with self.assertRaises(ValueError):
            build_pipeline_inputs(cfg)

    def test_build_pipeline_inputs_rejects_unknown_paper_source(self):
        cfg = {
            'subscriptions': {
                'intent_profiles': [
                    {
                        'tag': 'BAD',
                        'enabled': True,
                        'paper_sources': ['unknown-source'],
                        'keywords': [{'keyword': 'x', 'query': 'x'}],
                    }
                ],
            }
        }
        with self.assertRaises(ValueError):
            build_pipeline_inputs(cfg)

    def test_build_pipeline_inputs_can_append_runtime_paper_sources(self):
        cfg = {
            'source_backends': {
                'arxiv': {'enabled': True},
                'biorxiv': {'enabled': True},
            },
            'subscriptions': {
                'intent_profiles': [
                    {
                        'tag': 'SR',
                        'enabled': True,
                        'paper_sources': ['arxiv'],
                        'keywords': [{'keyword': 'x', 'query': 'x'}],
                    }
                ],
            }
        }
        with patch.dict('os.environ', {'DPR_APPEND_PAPER_SOURCES': 'biorxiv'}, clear=False):
            plan = build_pipeline_inputs(cfg)
        self.assertEqual(plan['profiles'][0].get('paper_sources'), ['arxiv', 'biorxiv'])

    def test_build_pipeline_inputs_can_filter_runtime_profile_tag(self):
        cfg = {
            'source_backends': {
                'arxiv': {'enabled': True},
                'biorxiv': {'enabled': True},
            },
            'subscriptions': {
                'intent_profiles': [
                    {
                        'tag': 'AHD',
                        'enabled': True,
                        'keywords': [{'keyword': 'algo', 'query': 'algo'}],
                    },
                    {
                        'tag': 'GENE',
                        'enabled': True,
                        'paper_sources': ['biorxiv'],
                        'keywords': [{'keyword': 'genetics', 'query': 'genetics'}],
                    },
                ],
            },
        }
        with patch.dict('os.environ', {'DPR_FILTER_PROFILE_TAG': 'GENE'}, clear=False):
            plan = build_pipeline_inputs(cfg)
        self.assertEqual([item.get('tag') for item in plan['profiles']], ['GENE'])
        self.assertEqual([item.get('tag') for item in plan['bm25_queries']], ['GENE'])
        self.assertEqual(plan['bm25_queries'][0].get('paper_sources'), ['biorxiv'])

    def test_runtime_profile_tag_filter_can_run_paused_profile(self):
        cfg = {
            'subscriptions': {
                'intent_profiles': [
                    {
                        'tag': 'PausedOnly',
                        'enabled': True,
                        'paused': True,
                        'keywords': [{'keyword': 'paused keyword', 'query': 'paused keyword'}],
                    },
                ],
            },
        }
        with patch.dict('os.environ', {'DPR_FILTER_PROFILE_TAG': 'PausedOnly'}, clear=False):
            plan = build_pipeline_inputs(cfg)
        self.assertEqual([item.get('tag') for item in plan['profiles']], ['PausedOnly'])
        self.assertEqual([item.get('tag') for item in plan['bm25_queries']], ['PausedOnly'])

    def test_count_tags(self):
        cfg = {
            'subscriptions': {
                'intent_profiles': [
                    {'id': 'p1', 'tag': 'A', 'enabled': True},
                    {'id': 'p2', 'tag': 'B', 'enabled': True},
                ]
            }
        }
        cnt, tags = count_subscription_tags(cfg)
        self.assertEqual(cnt, 2)
        self.assertIn('A', tags)
        self.assertIn('B', tags)

    def test_paused_profile_skipped(self):
        cfg = {
            'subscriptions': {
                'intent_profiles': [
                    {
                        'id': 'p1',
                        'tag': 'Active',
                        'enabled': True,
                        'keywords': [
                            {'keyword': 'active keyword', 'query': 'active query', 'enabled': True},
                        ],
                        'intent_queries': [
                            {'query': 'active intent', 'enabled': True},
                        ],
                    },
                    {
                        'id': 'p2',
                        'tag': 'Paused',
                        'enabled': True,
                        'paused': True,
                        'keywords': [
                            {'keyword': 'paused keyword', 'query': 'paused query', 'enabled': True},
                        ],
                        'intent_queries': [
                            {'query': 'paused intent', 'enabled': True},
                        ],
                    },
                ],
            }
        }
        plan = build_pipeline_inputs(cfg)
        self.assertIn('Active', plan['tags'])
        self.assertNotIn('Paused', plan['tags'])

        bm25_tags = [q.get('tag') for q in plan['bm25_queries']]
        self.assertIn('Active', bm25_tags)
        self.assertNotIn('Paused', bm25_tags)

        emb_tags = [q.get('tag') for q in plan['embedding_queries']]
        self.assertIn('Active', emb_tags)
        self.assertNotIn('Paused', emb_tags)

    def test_paused_false_profile_not_skipped(self):
        cfg = {
            'subscriptions': {
                'intent_profiles': [
                    {
                        'id': 'p1',
                        'tag': 'NotPaused',
                        'enabled': True,
                        'paused': False,
                        'keywords': [
                            {'keyword': 'keyword A', 'query': 'query A', 'enabled': True},
                        ],
                    },
                ],
            }
        }
        plan = build_pipeline_inputs(cfg)
        self.assertIn('NotPaused', plan['tags'])
        self.assertTrue(plan['bm25_queries'])

    def test_no_paused_field_defaults_to_active(self):
        cfg = {
            'subscriptions': {
                'intent_profiles': [
                    {
                        'id': 'p1',
                        'tag': 'NoPausedField',
                        'enabled': True,
                        'keywords': [
                            {'keyword': 'keyword B', 'query': 'query B', 'enabled': True},
                        ],
                    },
                ],
            }
        }
        plan = build_pipeline_inputs(cfg)
        self.assertIn('NoPausedField', plan['tags'])
        self.assertTrue(plan['bm25_queries'])

    def test_paused_profile_preserved_in_profiles_list(self):
        cfg = {
            'subscriptions': {
                'intent_profiles': [
                    {
                        'id': 'p1',
                        'tag': 'PausedButKept',
                        'enabled': True,
                        'paused': True,
                        'keywords': [
                            {'keyword': 'keyword C', 'query': 'query C', 'enabled': True},
                        ],
                    },
                ],
            }
        }
        plan = build_pipeline_inputs(cfg)
        self.assertEqual(len(plan['profiles']), 1)
        self.assertTrue(plan['profiles'][0].get('paused'))
        self.assertNotIn('PausedButKept', plan['tags'])


if __name__ == '__main__':
    unittest.main()
