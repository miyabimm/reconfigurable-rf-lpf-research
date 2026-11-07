"""W2: protect the 2026-10-17 structural-search overlay and source SHA."""
import unittest

from scripts import build_phase2_topology_search as w2


class W2TopologyIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = w2.build()
        cls.by_id = {r["catalog_id"]: r for r in cls.rows}

    def test_all_24_are_represented_without_evidence_fabrication(self):
        self.assertEqual(24, len(self.rows))
        self.assertEqual(24, len(self.by_id))
        originals = w2.read_rows(w2.ROOT, w2.BASE_CATALOG)
        self.assertEqual([r["catalog_id"] for r in originals],
                         [r["catalog_id"] for r in self.rows])
        self.assertEqual(14, sum(r["structural_evidence_state"]
                                 == "historical_not_yet_normalized" for r in self.rows))

    def test_f003_and_t005_are_not_merged(self):
        recent = [x for x in self.rows
                  if x["structural_evidence_state"] != "historical_not_yet_normalized"]
        self.assertEqual(6, sum(x["constraint_id"] == "RF-T005" for x in recent))
        self.assertEqual(4, sum(x["constraint_id"] == "RF-F003" for x in recent))
        self.assertEqual({"formal", "trial"}, {x["constraint_class"] for x in recent})

    def test_signed_k_follows_original_vector_not_a_schematic_claim(self):
        x = self.by_id["T005_4L_A4p667_EXP042"]
        self.assertEqual("L0-L1:+;L1-L3:+;L3-L2:-", x["signed_coupling_pairs"])
        self.assertEqual("L0;L1;L3;L2", x["reported_physical_inductor_order"])
        self.assertEqual("related_EXP047_only_not_independently_confirmed",
                         x["electrical_edges_provenance"])
        self.assertTrue(x["additional_source_git_blob_sha1"])
        self.assertIn("NOT verified physical", x["caveat"])

    def test_three_inductor_structured_graph_and_signed_k(self):
        x = self.by_id["T005_3L_A3p667_EXP045"]
        self.assertEqual("L0:0-1;L1:1-2;Ls:1-3", x["electrical_inductor_edges"])
        self.assertEqual("L0;Ls;L1", x["reported_physical_inductor_order"])
        self.assertEqual("L0-Ls:+;Ls-L1:-", x["signed_coupling_pairs"])
        self.assertEqual("own_structured_edges", x["electrical_edges_provenance"])

    def test_nested_nonconverged_entry_is_selected_by_id(self):
        x = self.by_id["T005_4L_A6_EXP042"]
        self.assertEqual("L0-L1:+;L1-L3:+;L3-L2:-", x["signed_coupling_pairs"])
        catalog = w2.read_rows(w2.ROOT, w2.BASE_CATALOG)
        orig = next(r for r in catalog if r["catalog_id"] == x["catalog_id"])
        self.assertIn("nonconverged", orig["solver_convergence_status"])

    def test_sha_check_fails_closed(self):
        target = self.by_id["F003_4L_A6_EXP047"]["source_checkpoint"]
        with self.assertRaisesRegex(ValueError, "Git source blob mismatch"):
            w2.source_bytes(w2.ROOT, target, "0" * 40)

    def test_tracked_csv_matches_verified_sources(self):
        self.assertEqual((w2.ROOT / w2.OUT).read_text(encoding='utf-8'),
                         w2.as_csv(self.rows))

    def test_current_physical_claim_remains_unverified(self):
        self.assertEqual({"unknown"}, {r["physical_realization_verified"] for r in self.rows[:14]})
        self.assertEqual({"false"}, {r["physical_realization_verified"] for r in self.rows[14:]})
        self.assertEqual("unknown", self.by_id["LPF-007"]["electrical_inductor_edges"])


if __name__ == "__main__":
    unittest.main()
