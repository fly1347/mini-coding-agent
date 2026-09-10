import unittest

from slugify import slugify


class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_punctuation_and_repeated_whitespace(self):
        self.assertEqual(slugify("  Hello, WORLD!!  "), "hello-world")

    def test_underscores(self):
        self.assertEqual(slugify("A___B"), "a-b")


if __name__ == "__main__":
    unittest.main()
