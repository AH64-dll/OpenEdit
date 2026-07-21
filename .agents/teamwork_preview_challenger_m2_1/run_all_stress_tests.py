"""Runner for all Milestone 2 EditGraphStore stress test suites."""
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "open_edit"))

import stress_bulk_insertion
import stress_status_transitions
import stress_concurrency
import stress_reorder_edge_cases


def main():
    print("==================================================")
    print(" RUNNING MILESTONE 2 EDIT GRAPH STORE STRESS TESTS ")
    print("==================================================")
    
    print("\n--- 1. Bulk Insertion & Sequence Numbering ---")
    stress_bulk_insertion.test_bulk_insertion_1000()
    stress_bulk_insertion.test_custom_sequence_numbering()
    stress_bulk_insertion.test_duplicate_explicit_sequence_numbering()

    print("\n--- 2. Status Transitions & Status Filtering ---")
    stress_status_transitions.test_status_transitions()
    stress_status_transitions.test_invalid_status_value()
    stress_status_transitions.test_update_status_nonexistent_id()
    stress_status_transitions.test_status_filtering_in_load_all()

    print("\n--- 3. Concurrency & WAL Access ---")
    stress_concurrency.test_concurrent_threads_append()
    stress_concurrency.test_concurrent_processes_append()
    stress_concurrency.test_concurrent_read_write()

    print("\n--- 4. Reorder Edge Cases ---")
    stress_reorder_edge_cases.test_reorder_valid_swap()
    stress_reorder_edge_cases.test_reorder_same_edit_id()
    stress_reorder_edge_cases.test_reorder_invalid_edit_ids()
    stress_reorder_edge_cases.test_reorder_non_adjacent_sequence_numbers()
    stress_reorder_edge_cases.test_reorder_gapped_sequence_numbers()
    stress_reorder_edge_cases.test_reorder_duplicate_sequence_numbers()

    print("\n==================================================")
    print(" ALL STRESS SUITES COMPLETED SUCCESSFULLY ")
    print("==================================================")


if __name__ == "__main__":
    main()
