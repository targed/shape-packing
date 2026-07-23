import subprocess
import sys

def verify():
    try:
        result = subprocess.run([sys.executable, 'C:\Users\ltkli\Documents\GitHub\shape-packing\run_parallel_loop.py'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("Verification passed: run_parallel_loop.py executes successfully.")
            return 0
        else:
            print("Verification failed.")
            print(result.stderr)
            return 1
    except Exception as e:
        print(f"Error during verification: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(verify())
