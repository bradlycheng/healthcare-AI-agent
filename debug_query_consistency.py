
import json
import os
import sys
from app.query_assistant import process_query

def debug_query(question):
    print(f"\nQUERY: {question}")
    result = process_query(question)
    
    print(f"SUCCESS: {result.get('success')}")
    print(f"SQL USED: {result.get('sql_used')}")
    print(f"ROW COUNT: {result.get('row_count')}")
    print(f"ANSWER: {result.get('answer')}")
    print("\nRESULTS (RAW):")
    # For privacy we only show headers and count in real life, but for debug we show row 1
    # print(json.dumps(result.get('sources', []), indent=2))

if __name__ == "__main__":
    debug_query("Which patients should I be worried about?")
