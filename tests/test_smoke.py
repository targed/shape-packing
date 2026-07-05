import unittest

class TestSmoke(unittest.TestCase):
    def test_imports(self):
        try:
            import shape_packing.problems
            import shape_packing.geometry
            import shape_packing.optimization
            import shape_packing.packing_config
            import shape_packing.agent_loop
            import shape_packing.solution_tools
        except ImportError as e:
            self.fail(f"Import failed: {e}")

if __name__ == "__main__":
    unittest.main()
