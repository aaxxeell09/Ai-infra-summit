import unittest
from turbo.action_codec import ActionCodec


class ActionCodecTests(unittest.TestCase):
    def setUp(self):
        self.codec = ActionCodec.from_files(['notes/do-not-delete.txt', 'inbox/report.txt'])

    def test_expands_exact_path(self):
        self.assertEqual(self.codec.decode('{"r":1}', snapshot_digest=self.codec.digest),
                         ('read_file', {'path': 'notes/do-not-delete.txt'}))

    def test_rejects_stale_symbols_and_invalid_types(self):
        for text, digest in [('{"r":1}', 'old'), ('{"r":-1}', self.codec.digest),
                             ('{"r":true}', self.codec.digest), ('{"r":9}', self.codec.digest),
                             ('{"r":1,"s":"x"}', self.codec.digest)]:
            with self.assertRaises(ValueError):
                self.codec.decode(text, snapshot_digest=digest)

    def test_move_expands_without_guessing_destination(self):
        self.assertEqual(self.codec.decode('{"m":[0,"archive/report.txt"]}', snapshot_digest=self.codec.digest),
            ('move_file', {'source': 'inbox/report.txt', 'destination': 'archive/report.txt'}))


if __name__ == '__main__':
    unittest.main()
