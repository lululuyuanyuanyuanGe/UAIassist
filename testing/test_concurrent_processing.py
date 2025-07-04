#!/usr/bin/env python3
"""Test concurrent processing functionality"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from agents.filloutTable import FilloutTableAgent

def test_concurrent_processing():
    """Test the concurrent processing method"""
    
    # Create test state with multiple chunks
    test_state = {
        'combined_data_array': [
            'Test chunk 1 - CSV data here\nName,Age\nJohn,25\nJane,30',
            'Test chunk 2 - More CSV data\nName,Salary\nBob,50000\nAlice,60000', 
            'Test chunk 3 - Even more data\nName,Department\nCharlie,Engineering\nDiana,Marketing'
        ],
        'headers_mapping': 'Column mapping example: Name->姓名, Age->年龄, Salary->工资'
    }

    # Create agent instance
    agent = FilloutTableAgent()

    print('🚀 Testing concurrent processing...')
    print(f'📊 Input: {len(test_state["combined_data_array"])} chunks')
    
    try:
        # Test the concurrent processing method
        result = agent._generate_CSV_based_on_combined_data(test_state)
        
        print(f'✅ Success! Processed {len(result["combined_data_array"])} chunks')
        print(f'📋 Results preview:')
        
        for i, response in enumerate(result['combined_data_array']):
            print(f'  Chunk {i+1} response length: {len(response)} characters')
            print(f'  Preview: {response[:150]}...')
            print()
            
    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_concurrent_processing() 