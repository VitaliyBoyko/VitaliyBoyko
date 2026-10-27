import io
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from update_github_stats import additional_project_stars, install_card


CARD = '''<svg xmlns="http://www.w3.org/2000/svg">
<desc>Total Stars Earned: 15, Total Commits: 395</desc>
<text>Total Stars Earned:</text><text data-testid="stars">15</text>
<text data-testid="commits">395</text><text data-testid="prs">273</text>
<text data-testid="issues">99</text><text data-testid="contribs">5</text>
</svg>'''


def repository_response(repository_id, owner, stars):
    return io.BytesIO(json.dumps({
        "id": repository_id,
        "owner": {"login": owner},
        "stargazers_count": stars,
    }).encode())


class ProjectStarsTests(unittest.TestCase):
    def test_fetches_both_selected_projects(self):
        with patch("update_github_stats.urlopen", side_effect=[
            repository_response(1, "MageLens", 6),
            repository_response(2, "magento", 472),
        ]) as request:
            self.assertEqual(additional_project_stars("VitaliyBoyko"), 478)
        self.assertEqual([call.args[0].full_url for call in request.call_args_list], [
            "https://api.github.com/repos/MageLens/MageLens",
            "https://api.github.com/repos/magento/magento2-phpstorm-plugin",
        ])

    def test_repository_transferred_back_to_profile_is_not_added_twice(self):
        with patch("update_github_stats.urlopen", side_effect=[
            repository_response(1, "vitaliyboyko", 6),
            repository_response(2, "magento", 472),
        ]):
            self.assertEqual(additional_project_stars("VitaliyBoyko"), 472)

    def test_redirect_aliases_are_counted_once(self):
        with patch("update_github_stats.urlopen", side_effect=[
            repository_response(1, "MageLens", 6),
            repository_response(1, "MageLens", 6),
        ]):
            self.assertEqual(additional_project_stars("VitaliyBoyko"), 6)

    def test_invalid_api_data_is_rejected(self):
        for stars in (None, "6", -1, True):
            with self.subTest(stars=stars), patch("update_github_stats.urlopen", return_value=
                repository_response(1, "MageLens", stars)
            ), self.assertRaises(ValueError):
                additional_project_stars("VitaliyBoyko")


class PublishCardTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.previous_directory = Path.cwd()
        os.chdir(self.workspace.name)
        Path("profile").mkdir()
        self.old_card = Path("profile/stats-1.svg")
        self.old_card.write_text("previous card")
        self.original_readme = "![GitHub Stats](./profile/stats-1.svg)\n"
        Path("README.md").write_text(self.original_readme)
        self.candidate = Path("candidate.svg")
        self.candidate.write_text(CARD)
        self.destination = Path("profile/stats-2.svg")

    def tearDown(self):
        os.chdir(self.previous_directory)
        self.workspace.cleanup()

    def assert_previous_card_preserved(self):
        self.assertEqual(self.old_card.read_text(), "previous card")
        self.assertEqual(Path("README.md").read_text(), self.original_readme)
        self.assertFalse(self.destination.exists())

    def test_publishes_combined_total_and_accessible_label(self):
        with patch("update_github_stats.urlopen", side_effect=[
            repository_response(1, "MageLens", 6),
            repository_response(2, "magento", 472),
        ]):
            install_card(self.candidate, self.destination, "VitaliyBoyko")
        root = ET.fromstring(self.destination.read_bytes())
        self.assertEqual(root.find(".//*[@data-testid='stars']").text, "493")
        self.assertEqual(root.find(".//*[@data-testid='commits']").text, "395")
        self.assertIn("Stars across my projects: 493", "".join(root.itertext()))
        self.assertNotIn("Total Stars Earned", self.destination.read_text())
        self.assertIn("./profile/stats-2.svg", Path("README.md").read_text())
        self.assertFalse(self.old_card.exists())

    def test_partial_api_failure_preserves_published_files(self):
        with patch("update_github_stats.urlopen", side_effect=[
            repository_response(1, "MageLens", 6),
            URLError("unavailable"),
        ]), self.assertRaises(URLError):
            install_card(self.candidate, self.destination, "VitaliyBoyko")
        self.assert_previous_card_preserved()

    def test_rounded_base_count_is_rejected(self):
        self.candidate.write_text(CARD.replace('data-testid="stars">15', 'data-testid="stars">1.5k'))
        with self.assertRaisesRegex(ValueError, "exact integer"):
            install_card(self.candidate, self.destination, "VitaliyBoyko")
        self.assert_previous_card_preserved()

    def test_modified_card_cannot_receive_extra_stars_twice(self):
        self.candidate.write_text(CARD.replace("Total Stars Earned", "Stars across my projects"))
        with self.assertRaisesRegex(ValueError, "unmodified stats card"):
            install_card(self.candidate, self.destination, "VitaliyBoyko")
        self.assert_previous_card_preserved()

    def test_readme_validation_failure_preserves_previous_card(self):
        Path("README.md").write_text("no stats image")
        self.original_readme = "no stats image"
        with patch("update_github_stats.additional_project_stars", return_value=478), self.assertRaises(ValueError):
            install_card(self.candidate, self.destination, "VitaliyBoyko")
        self.assert_previous_card_preserved()

    def test_error_card_preserves_previous_card(self):
        self.candidate.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text data-testid="message">API error</text></svg>')
        with self.assertRaisesRegex(ValueError, "provider returned an error"):
            install_card(self.candidate, self.destination, "VitaliyBoyko")
        self.assert_previous_card_preserved()


if __name__ == "__main__":
    unittest.main()
