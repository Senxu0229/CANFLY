"""Offline RAG checks: python3 -m unittest backend.test_index -v.

Fixtures are deliberately bilingual; default lexical embeddings are tested as
lexical retrieval, not claimed to provide semantic translation.
"""
import dataclasses
import hashlib
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .config import Settings
from .index import CHUNK_OVERLAP, CHUNK_SIZE, Index, IndexUnavailable, chunk_text, documents, rebuild
from .vectors import cosine, embeddings, fit_tfidf


FIXTURES = {
    'location.md': '# Village location / 村庄位置\n\n'
        'Kalari Abdu village center: latitude 11.7367804 N, longitude 13.2846742 E. '
        'The study radius is 6 km. 村庄中心纬度 11.7367804，经度 13.2846742，研究范围半径6公里。',
    'methods/water.txt': '# Candidate water detection / 疑似新增水体判断\n\n'
        'Possible new water means HH sigma0 is above the shared threshold before and below it after. '
        'The threshold is -12.40234375 dB. Calibrated radar is smoothed on a 10 m grid. '
        '疑似新增水体根据两期雷达回波和共同阈值判断。浅蓝色不是已确认洪水，橙色是回波增强、原因待核查。',
    'satellite.md': '# Satellite acquisition / 卫星拍摄资料\n\n'
        'The satellite is RADARSAT-2. Acquisitions use XF0W2 beam mode, HH polarization, '
        'descending orbit. 拍摄卫星为RADARSAT-2，波束模式XF0W2，极化HH，降轨。',
    'unrelated.txt': '# Garden notes / 花园笔记\n\n'
        'Tomato seedlings need regular watering. 花园番茄幼苗需要浇水。 This document has no radar evidence.',
}


class ChunkingTests(unittest.TestCase):
    def assert_complete_bounded_chunks(self, text):
        chunks = list(chunk_text(text))
        self.assertTrue(chunks)
        covered = [False] * len(text)
        previous_start, previous_end = -1, 0
        for chunk in chunks:
            self.assertTrue(chunk.strip())
            self.assertLessEqual(len(chunk), CHUNK_SIZE)
            start = text.find(chunk, previous_start + 1)
            self.assertGreater(start, previous_start)
            end = start + len(chunk)
            if previous_start >= 0:
                self.assertLessEqual(max(0, previous_end - start), CHUNK_OVERLAP)
                self.assertFalse(text[previous_end:start].strip(), 'Only boundary whitespace may be omitted')
            covered[start:end] = [True] * len(chunk)
            previous_start, previous_end = start, end
        self.assertTrue(all(seen or character.isspace() for seen, character in zip(covered, text)))
        return chunks

    def test_long_lines_and_paragraphs_keep_content_with_bounded_overlap(self):
        long_line = ' '.join(f'point-{i:06d}' for i in range(1000))
        chunks = self.assert_complete_bounded_chunks(long_line)
        self.assertGreater(len(chunks), 5)
        paragraphs = '\n\n'.join(f'Section {i:04d}: ' + f'记录{i:04d}，' * 43 for i in range(30))
        self.assert_complete_bounded_chunks(paragraphs)

    def test_empty_and_short_documents(self):
        self.assertEqual(list(chunk_text(' \n\t ')), [])
        self.assertEqual(list(chunk_text('  One short passage.\n  ')), ['One short passage.'])


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.knowledge = self.root / 'knowledge'
        self.knowledge.mkdir()
        self.settings = Settings(root=self.root, knowledge_dir=self.knowledge, index_path=self.root/'index.sqlite3')
        for name, text in FIXTURES.items():
            path = self.knowledge / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')

    def test_bilingual_queries_retrieve_relevant_local_documents(self):
        summary = rebuild(self.settings)
        self.assertEqual(summary['documents'], len(FIXTURES))
        self.assertEqual(summary['embedding_provider'], 'tfidf')
        with Index(self.settings) as index:
            for query, expected in [
                ('village center latitude longitude', 'location.md'),
                ('村庄中心的经纬度和半径', 'location.md'),
                ('How is possible new water detected using the threshold?', 'methods/water.txt'),
                ('浅蓝色疑似新增水体怎么判断？', 'methods/water.txt'),
                ('Which satellite and beam mode acquired the radar?', 'satellite.md'),
                ('拍摄卫星和波束模式是什么？', 'satellite.md'),
            ]:
                with self.subTest(query=query):
                    results = index.retrieve(query)
                    self.assertTrue(results)
                    self.assertEqual(results[0]['name'], expected)
                    self.assertLessEqual(len(results), self.settings.top_k)
                    self.assertTrue(all('vector' not in result for result in results))
            self.assertEqual(index.retrieve('🦒'), [])

    def test_index_persists_and_reopens_without_embedding_service(self):
        with patch('backend.vectors.http_json', side_effect=AssertionError('Offline mode must not use HTTP')):
            rebuild(self.settings)
            self.assertTrue(self.settings.index_path.read_bytes().startswith(b'SQLite format 3\x00'))
            with Index(self.settings) as index:
                first = index.retrieve('Kalari Abdu village center')
            with Index(self.settings) as index:
                self.assertEqual(index.retrieve('Kalari Abdu village center'), first)
                self.assertGreater(index.metadata['chunk_count'], 0)

    def test_citation_identity_resolves_exact_indexed_document(self):
        rebuild(self.settings)
        with Index(self.settings) as index:
            hit = index.retrieve('浅蓝色疑似新增水体判断')[0]
            source = index.document(hit['doc_id'])
            self.assertIsNotNone(source)
            self.assertEqual(source['name'], hit['name'])
            self.assertEqual(source['title'], hit['title'])
            self.assertEqual(source['sha256'], hit['sha256'])
            self.assertIn(hit['text'], source['text'])
            expected = FIXTURES[source['name']]
            self.assertEqual(source['text'], expected)
            self.assertEqual(source['sha256'], hashlib.sha256(expected.encode()).hexdigest())
            self.assertIsNone(index.document('missing-source'))
            self.assertIsNone(index.document("' OR 1=1 --"))

    def test_edited_document_is_rejected_until_rebuild(self):
        rebuild(self.settings)
        with Index(self.settings) as index:
            before = index.retrieve('village center latitude')[0]['doc_id']
            original_snapshot = index.document(before)
            (self.knowledge/'location.md').write_text(FIXTURES['location.md'] + '\nUpdated observation note.')
            with self.assertRaises(IndexUnavailable):
                index.retrieve('village center latitude')
            # An existing citation still identifies the text used to generate it.
            self.assertEqual(index.document(before), original_snapshot)
        rebuild(self.settings)
        with Index(self.settings) as index:
            self.assertIn('Updated observation note.', index.retrieve('village center latitude')[0]['text'])

    def test_deleted_document_is_rejected_until_rebuild(self):
        rebuild(self.settings)
        (self.knowledge/'location.md').unlink()
        with Index(self.settings) as index:
            with self.assertRaises(IndexUnavailable):
                index.retrieve('village center latitude')
        rebuild(self.settings)
        with Index(self.settings) as index:
            self.assertFalse(any(hit['name'] == 'location.md' for hit in index.retrieve('village center latitude')))

    def test_added_document_is_rejected_until_rebuild(self):
        rebuild(self.settings)
        (self.knowledge/'new.txt').write_text('New observation notes.')
        with Index(self.settings) as index:
            with self.assertRaises(IndexUnavailable):
                index.retrieve('observation notes')
        self.assertEqual(rebuild(self.settings)['documents'], len(FIXTURES) + 1)

    def test_changed_embedding_settings_refuse_stale_index(self):
        rebuild(self.settings)
        for changes in [
            {'embedding_model': 'another-embedding'},
            {'embedding_provider': 'openai', 'embedding_base_url': 'http://127.0.0.1:9/v1'},
            {'embedding_base_url': 'http://127.0.0.1:9/v1'},
        ]:
            with self.subTest(changes=changes), patch('backend.vectors.http_json') as http:
                with Index(dataclasses.replace(self.settings, **changes)) as index:
                    with self.assertRaises(IndexUnavailable):
                        index.retrieve('water threshold')
                http.assert_not_called()

    def test_generation_model_settings_are_independent_of_embedding_index(self):
        rebuild(self.settings)
        changed = dataclasses.replace(self.settings, llm_model='different-generator', llm_base_url='http://127.0.0.1:9/v1')
        with Index(changed) as index:
            self.assertEqual(index.retrieve('village center latitude longitude')[0]['name'], 'location.md')

    def test_changed_project_classification_source_refuses_stale_index(self):
        shared = self.root/'shared'
        shared.mkdir()
        rules = shared/'water_classes.json'
        rules.write_text('{"orange": "stronger return"}')
        rebuild(self.settings)
        rules.write_text('{"orange": "revised interpretation"}')
        with Index(self.settings) as index:
            with self.assertRaises(IndexUnavailable):
                index.retrieve('orange')

    def test_escape_symlink_is_rejected(self):
        outside = self.root/'outside.txt'
        outside.write_text('This is not in the knowledge directory.')
        (self.knowledge/'escape.md').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            documents(self.knowledge)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            rebuild(self.settings)
        self.assertFalse(self.settings.index_path.exists())

    def test_empty_corpus_and_missing_index_fail_explicitly(self):
        empty = self.root/'empty'
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, 'No Markdown or TXT'):
            rebuild(dataclasses.replace(self.settings, knowledge_dir=empty))
        with self.assertRaises(IndexUnavailable):
            Index(self.settings)

    def test_non_documents_are_excluded_and_nested_paths_are_preserved(self):
        (self.knowledge/'ignored.json').write_text('{"water": "not a knowledge document"}')
        (self.knowledge/'empty.md').write_text(' \n')
        docs = documents(self.knowledge)
        self.assertEqual({doc['name'] for doc in docs}, set(FIXTURES))
        self.assertEqual(len({doc['id'] for doc in docs}), len(FIXTURES))


class VectorTests(unittest.TestCase):
    def test_lexical_embeddings_are_normalized_and_unknown_terms_have_no_evidence(self):
        settings = Settings()
        corpus = ['SAR threshold water 雷达 水体', 'Village coordinates 村庄 经纬度']
        idf = fit_tfidf(corpus)
        vectors = embeddings(settings, corpus + ['🦒'], idf)
        for vector in vectors[:2]:
            self.assertAlmostEqual(math.sqrt(sum(v*v for v in vector.values())), 1.0)
            self.assertAlmostEqual(cosine(vector, vector), 1.0)
        self.assertEqual(vectors[2], {})
        self.assertEqual(cosine(vectors[0], vectors[2]), 0)

    def test_external_embeddings_use_separate_model_and_order_vectors(self):
        settings = Settings(embedding_provider='openai', embedding_model='embedding-only',
                            embedding_base_url='http://127.0.0.1:1234/v1/', embedding_api_key='test-key',
                            llm_model='generation-only')
        with patch('backend.vectors.http_json', return_value={'data': [
            {'index': 1, 'embedding': [0, 2]}, {'index': 0, 'embedding': [3, 4]},
        ]}) as http:
            vectors = embeddings(settings, ['first', 'second'])
        http.assert_called_once_with('http://127.0.0.1:1234/v1/embeddings',
            {'model': 'embedding-only', 'input': ['first', 'second']}, 'test-key', settings.timeout_seconds)
        self.assertEqual(vectors, [{'0': .6, '1': .8}, {'0': 0, '1': 1}])

    def test_external_service_invalid_vectors_are_rejected(self):
        settings = Settings(embedding_provider='openai', embedding_model='embedding-only', embedding_base_url='http://127.0.0.1:1234/v1')
        for rows in [
            [],
            [{'index': 1, 'embedding': [1, 2]}],
            [{'index': 0, 'embedding': []}],
            [{'index': 0, 'embedding': [0, 0]}],
            [{'index': 0, 'embedding': [float('nan'), 1]}],
            [{'index': 0, 'embedding': [float('inf'), 1]}],
            [{'index': 0, 'embedding': ['bad', 1]}],
        ]:
            with self.subTest(rows=rows), patch('backend.vectors.http_json', return_value={'data': rows}):
                with self.assertRaises(ValueError):
                    embeddings(settings, ['first'])
        with patch('backend.vectors.http_json', return_value={'data': [
            {'index': 0, 'embedding': [1]}, {'index': 1, 'embedding': [1, 2]},
        ]}):
            with self.assertRaisesRegex(ValueError, 'dimensions'):
                embeddings(settings, ['first', 'second'])


if __name__ == '__main__':
    unittest.main()
