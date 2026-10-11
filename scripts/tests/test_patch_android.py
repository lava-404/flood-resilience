import os, sys, unittest, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import patch_android as P

# SAMPLE templates approximating React Native's (not copied from a real generated project).
MANIFEST = '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n\n    <uses-permission android:name="android.permission.INTERNET" />\n\n    <application android:name=".MainApplication">\n    </application>\n</manifest>\n'
MAIN_KT = 'class MainApplication : Application(), ReactApplication {\n  override val reactNativeHost: ReactNativeHost =\n      object : DefaultReactNativeHost(this) {\n        override fun getPackages(): List<ReactPackage> =\n            PackageList(this).packages.apply {\n              // add(MyReactNativePackage())\n            }\n      }\n}\n'
MAIN_JAVA = 'public List<ReactPackage> getPackages() {\n  @SuppressWarnings("UnnecessaryLocalVariable")\n  List<ReactPackage> packages = new PackageList(this).getPackages();\n  return packages;\n}\n'
PERMS = '<uses-permission android:name="android.permission.NEARBY_WIFI_DEVICES" />\n<uses-feature android:name="android.hardware.wifi.direct" android:required="false" />'


class Patch(unittest.TestCase):
    def test_manifest_inserted_before_application_and_idempotent(self):
        out = P.patch_manifest(MANIFEST, PERMS)
        self.assertLess(out.index("NEARBY_WIFI_DEVICES"), out.index("<application"))
        self.assertIn("INTERNET", out); self.assertEqual(P.patch_manifest(out, PERMS), out)
        self.assertEqual(out.count("NEARBY_WIFI_DEVICES"), 1)

    def test_manifest_without_application_errors_clearly(self):
        with self.assertRaises(P.PatchError): P.patch_manifest("<manifest/>", PERMS)

    def test_main_application_kotlin_and_java(self):
        k = P.patch_main_application(MAIN_KT); self.assertIn("add(com.floodresilience.p2p.FloodP2pPackage())", k)
        self.assertEqual(P.patch_main_application(k), k)
        self.assertLess(k.index("FloodP2pPackage"), k.index("// add(MyReactNativePackage())"))
        j = P.patch_main_application(MAIN_JAVA); self.assertIn("packages.add(new com.floodresilience.p2p.FloodP2pPackage());", j)
        self.assertLess(j.index("packages.add"), j.index("return packages"))
        with self.assertRaises(P.PatchError): P.patch_main_application("class X")

    def test_tsconfig(self):
        out = json.loads(P.patch_tsconfig('{"extends": "@react-native/typescript-config"}'))
        self.assertTrue(out["compilerOptions"]["allowImportingTsExtensions"] and out["compilerOptions"]["noEmit"])
        self.assertEqual(out["extends"], "@react-native/typescript-config")
        with self.assertRaises(P.PatchError): P.patch_tsconfig('{ // comment\n}')


if __name__ == "__main__":
    unittest.main()
