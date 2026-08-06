import tempfile
import unittest
from pathlib import Path

from insta_bot.scraper import Scraper


class TestScraperSave(unittest.TestCase):
    def setUp(self):
        self.scraper = Scraper.__new__(Scraper)  # __init__ atla; sadece _save test edilecek

    def test_csv_from_single_dict(self):
        # Regresyon: 'user' tipi tek sozluk dondurur; CSV kaydinda data[0] KeyError
        # atiyordu. Artik sozluk listeye sarilir.
        out = Path(tempfile.mkdtemp()) / "user.csv"
        self.scraper._save(str(out), {"pk": "1", "username": "ali"})
        content = out.read_text(encoding="utf-8")
        self.assertIn("pk", content)
        self.assertIn("ali", content)

    def test_csv_from_list(self):
        out = Path(tempfile.mkdtemp()) / "list.csv"
        self.scraper._save(str(out), [{"pk": "1"}, {"pk": "2"}])
        lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln]
        self.assertEqual(len(lines), 3)  # baslik + 2 satir

    def test_csv_empty(self):
        out = Path(tempfile.mkdtemp()) / "empty.csv"
        self.scraper._save(str(out), [])
        self.assertEqual(out.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
