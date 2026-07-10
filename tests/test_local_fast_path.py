import unittest

from payload.freecad_ai.core.local_fast_path import plan_local_arguments


class LocalFastPathTests(unittest.TestCase):
    def test_box_dimensions(self):
        plan = plan_local_arguments("\u521b\u5efa\u4e00\u4e2a 40 x 30 x 20 mm \u7684\u76d2\u5b50")
        self.assertIsNotNone(plan)
        self.assertEqual(plan.arguments["length"], 40.0)
        self.assertEqual(plan.arguments["width"], 30.0)
        self.assertEqual(plan.arguments["height"], 20.0)

    def test_diameter_to_radius(self):
        plan = plan_local_arguments("create a cylinder diameter 20 mm height 35 mm")
        self.assertIsNotNone(plan)
        self.assertEqual(plan.arguments["radius"], 10.0)
        self.assertEqual(plan.arguments["height"], 35.0)

    def test_questions_stay_on_model_path(self):
        self.assertIsNone(plan_local_arguments("\u76d2\u5b50\u7684\u5927\u5c0f\u600e\u4e48\u8bbe\u7f6e\uff1f"))


if __name__ == "__main__":
    unittest.main()
