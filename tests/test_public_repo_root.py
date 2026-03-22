import unittest
from pathlib import Path

from task_dashboard.helpers import _repo_root


class PublicRepoRootResolutionTests(unittest.TestCase):
    def test_public_repo_prefers_repo_root(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        self.assertEqual(_repo_root().resolve(), repo_root.resolve())


if __name__ == "__main__":
    unittest.main()
