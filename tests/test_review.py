import unittest

from lean_prefix.review import _offer, _shared_depth


class ReviewSelectionTests(unittest.TestCase):
    def test_shared_depth_stops_at_first_unique_prefix(self):
        counts = {("a",): 3, ("a", "b"): 2, ("a", "b", "c"): 1}
        self.assertEqual(_shared_depth(["a", "b", "c"], counts), 2)

    def test_offer_retains_highest_rank(self):
        selected = {}
        _offer(selected, "case", (2,), {"proposal_id": "second"})
        _offer(selected, "case", (1,), {"proposal_id": "first"})
        self.assertEqual(selected["case"][1]["proposal_id"], "second")


if __name__ == "__main__":
    unittest.main()
