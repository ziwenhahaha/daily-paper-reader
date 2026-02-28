import unittest

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
        self.assertEqual(len(intent_context), 2)

        bm25_texts = [q.get('query_text') for q in intent_bm25]
        self.assertIn('symbolic regression with reinforcement learning', bm25_texts)
        self.assertIn('equation discovery for physical systems', bm25_texts)

        emb_texts = [q.get('query_text') for q in intent_emb]
        self.assertIn('symbolic regression with reinforcement learning', emb_texts)
        self.assertIn('equation discovery for physical systems', emb_texts)

        context_texts = [q.get('query') for q in intent_context]
        self.assertIn('symbolic regression with reinforcement learning', context_texts)
        self.assertIn('equation discovery for physical systems', context_texts)

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


if __name__ == '__main__':
    unittest.main()
