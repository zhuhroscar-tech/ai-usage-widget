import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "2.3.2"


class RepositoryContractTests(unittest.TestCase):
    def test_required_project_files_exist(self):
        for relative in [
            "README.md",
            "README.zh.md",
            "README.es.md",
            "CHANGELOG.md",
            "Token Telescope.spec",
            "app.py",
            ".github/workflows/ci.yml",
        ]:
            self.assertTrue((ROOT / relative).exists(), relative)

    def test_runtime_and_bundle_versions_match(self):
        app_tree = ast.parse((ROOT / "app.py").read_text())
        constants = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in app_tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {"APP_NAME", "APP_VERSION"}
        }
        self.assertEqual(constants["APP_NAME"], "Token Telescope")
        self.assertEqual(constants["APP_VERSION"], EXPECTED_VERSION)

        spec = (ROOT / "Token Telescope.spec").read_text()
        short_version = re.search(r"'CFBundleShortVersionString': '([^']+)'", spec)
        bundle_version = re.search(r"'CFBundleVersion': '([^']+)'", spec)
        self.assertIsNotNone(short_version)
        self.assertIsNotNone(bundle_version)
        assert short_version is not None
        assert bundle_version is not None
        self.assertEqual(short_version.group(1), EXPECTED_VERSION)
        self.assertEqual(bundle_version.group(1), EXPECTED_VERSION)

    def test_changelog_and_readme_track_current_release(self):
        changelog = (ROOT / "CHANGELOG.md").read_text()
        self.assertIn(f"## {EXPECTED_VERSION}", changelog)
        self.assertIn("bundle metadata", changelog.lower())

        readme = (ROOT / "README.md").read_text()
        self.assertIn("[Releases](../../releases/latest)", readme)
        self.assertIn("## License", readme)

    def test_ci_runs_repository_contract(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("Token Telescope.spec", workflow)


if __name__ == "__main__":
    unittest.main()
