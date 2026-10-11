import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_mobile_static as C


class MobileStatic(unittest.TestCase):
    def test_no_static_problems(self):
        self.assertEqual(C.check(), [])

    def test_checker_detects_a_missing_native_method(self):      # the check must be able to fail
        real = C.read
        try:
            C.read = lambda p: real(p).replace("fun setOutbox", "fun setOutboxX") if p.endswith("FloodP2pModule.kt") else real(p)
            self.assertTrue(any("setOutbox" in p for p in C.check()))
        finally: C.read = real


if __name__ == "__main__":
    unittest.main()
