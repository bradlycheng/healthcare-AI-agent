
import sys
import os
import json
from app.query_assistant import process_query

def debug_ckd():
    print("QUERY: Show list of patients with eGFR < 60")
    result = process_query("Show list of patients with eGFR < 60", [])
    
    print(f"SUCCESS: {result.get('success')}")
    print(f"SQL USED: {result.get('sql_used')}")
    print(f"ROW COUNT: {result.get('row_count')}")
    print(f"ANSWER: {result.get('answer')}")
    
    if result.get("success"):
        print("\nRESULTS (RAW):")
        # results are in result['answer'] usually if it's a summary, 
        # but process_query returns 'success', 'answer', 'sql_used', 'row_count'
        pass

if __name__ == "__main__":
    debug_ckd()
