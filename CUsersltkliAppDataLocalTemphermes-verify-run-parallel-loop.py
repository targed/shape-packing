import sys
import os
import json
from unittest.mock import patch

# Add the workspace directory to sys.path
workspace_dir = r"C:\Users\ltkli\Documents\GitHub\shape-packing"
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from run_parallel_loop import process_result

@patch('run_parallel_loop.log_result')
def test_process_result(mock_log_result):
    mock_result = {
        'problem': '5_3_3_test',
        'success': True,
        'stdout': json.dumps({'score': 99.5})
    }
    
    process_result(mock_result)
    
    mock_log_result.assert_called_once_with(
        None, '5_3_3_test', 99.5, 0.0, "Parallel run loop", commit="auto"
    )
    print("Success: process_result called log_result correctly.")

if __name__ == "__main__":
    test_process_result()
