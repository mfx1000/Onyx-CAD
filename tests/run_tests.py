import subprocess
import sys
import os

def run_tests():
    # List of test files to run in order
    test_files = [
        "tests/test_boot.py",
        "tests/test_xde_pipeline.py",
        "tests/test_geometry_db.py",
        "tests/test_three_strategies.py",
        "tests/test_thread.py",
        "tests/test_step_entities.py",
        "tests/test_meta_roundtrip.py",
        "tests/test_fuzzy_sw.py",
        "tests/test_db_restoration.py",
        "tests/test_hole_tolerance_suite.py",
        "tests/test_browser_flow.py",
    ]

    print("=" * 60)
    print("RUNNING FULL TEST SUITE")
    print("=" * 60)

    failed = []
    passed = 0

    # Ensure we are running from the project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    os.chdir(root_dir)
    print(f"Working directory: {os.getcwd()}")

    python_exe = sys.executable
    if "venv" in python_exe:
        pass # Already using venv python hopefully
    else:
        # Fallback to venv if easy to find, otherwise use current
        if os.path.exists("venv/Scripts/python.exe"):
            python_exe = "venv/Scripts/python.exe"

    for test_file in test_files:
        print(f"\n[RUN] {test_file}...")
        try:
            # Run as subprocess to ensure clean state for each test
            # Capture output to show it, but check return code
            result = subprocess.run(
                [python_exe, test_file],
                capture_output=False, # Let it stream to stdout
                text=True
            )
            
            if result.returncode == 0:
                print(f"[PASS] {test_file}")
                passed += 1
            else:
                print(f"[FAIL] {test_file} (Exit code: {result.returncode})")
                failed.append(test_file)
        except Exception as e:
            print(f"[ERR] Failed to execute {test_file}: {e}")
            failed.append(test_file)

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Passed: {passed}")
    print(f"Failed: {len(failed)}")
    
    if failed:
        print("\nFailed Tests:")
        for f in failed:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\nAll tests passed!")
        sys.exit(0)

if __name__ == "__main__":
    run_tests()
