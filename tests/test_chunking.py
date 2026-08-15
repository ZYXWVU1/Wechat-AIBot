import unittest

from nas_backend.app.chunking import chunk_text


class ChunkingTests(unittest.TestCase):
    def test_splits_chinese_sentences_without_empty_chunks(self):
        chunks = chunk_text("你好。今天怎么样？我刚刚在看书！", max_chars=8, max_chunks=3)
        self.assertEqual(chunks, ["你好。", "今天怎么样？", "我刚刚在看书！"])

    def test_hard_limit_and_chunk_count(self):
        chunks = chunk_text("a" * 50, max_chars=10, max_chunks=3)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(chunk) <= 10 for chunk in chunks))

    def test_empty_input(self):
        self.assertEqual(chunk_text("   \n ", 10, 3), [])


if __name__ == "__main__":
    unittest.main()
