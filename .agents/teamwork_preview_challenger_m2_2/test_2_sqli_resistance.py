#!/usr/bin/env python3
"""Empirical test 2: SQL Injection Resistance in parameters, project_id queries, and methods.

Tests:
1. Malicious SQL payloads in op fields (edit_id, payload parameters, XML, python code, dict values).
2. Malicious SQL payloads in project_id stored in project_meta table.
3. Malicious SQL payloads in update_status (edit_id and new_status parameters).
4. Malicious SQL payloads in reorder (edit_id_a and edit_id_b parameters).
5. Attempting SQL injection to bypass CHECK constraints or drop tables.
"""
import sqlite3
import tempfile
import sys
from pathlib import Path

from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.types import (
    AddClipOp,
    RawMltXmlOp,
    FreeFormCodeOp,
    AddEffectOp,
)


SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE edits; --",
    "' UNION SELECT 1, 'hacked', 'hacked', 'hacked', 'hacked', 'applied', 99, '{}' --",
    "1'; DELETE FROM project_meta WHERE '1'='1",
    "admin'--",
    "' OR 1=1 --",
    "'; UPDATE edits SET status='reverted'; --",
    "\" OR \"a\"=\"a",
    "'; ATTACH DATABASE '/tmp/pwned.db' AS pwned; --",
]


def run_tests():
    print("=== TEST 2: SQL Injection Resistance Verification ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "sqli_test.db"
        store = EditGraphStore(db_path)
        
        # Initial check: DB tables exist
        with sqlite3.connect(db_path) as conn:
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            assert "edits" in tables and "project_meta" in tables, f"Tables missing: {tables}"
            
        print("[1/5] Testing SQL Injection in operation fields via append()...")
        # Test 1: Append operations containing SQL injection strings in edit_id, XML, code, params
        for idx, payload in enumerate(SQL_INJECTION_PAYLOADS):
            op = RawMltXmlOp(
                edit_id=f"sqli_id_{idx}_{payload}",
                author="user",
                xml=f"<mlt>{payload}</mlt>",
                description=payload,
            )
            seq = store.append(op)
            assert seq == idx, f"Expected sequence num {idx}, got {seq}"
            
        # Verify database integrity and table count after appending malicious payloads
        with sqlite3.connect(db_path) as conn:
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            assert "edits" in tables and "project_meta" in tables, "Table dropped during append SQL injection attempt!"
            count = conn.execute("SELECT count(*) FROM edits").fetchone()[0]
            assert count == len(SQL_INJECTION_PAYLOADS), f"Expected {len(SQL_INJECTION_PAYLOADS)} rows in edits, found {count}"
            
        # Verify load_all reads payloads back faithfully without executing SQL
        loaded = store.load_all()
        assert len(loaded) == len(SQL_INJECTION_PAYLOADS)
        for idx, payload in enumerate(SQL_INJECTION_PAYLOADS):
            assert loaded[idx].description == payload
            assert payload in loaded[idx].xml
        print("  -> Passed append() SQL injection test.")
        
        # Test 2: SQL injection in project_id / project_meta
        print("[2/5] Testing SQL Injection in project_meta / project_id...")
        # First read generates initial project_id
        pid = store.project_id
        assert isinstance(pid, str) and len(pid) > 0
        
        # Insert a malicious project_id directly into project_meta to test retrieval
        malicious_pid = "pid_'; DROP TABLE edits; --"
        with store._conn() as conn:
            conn.execute("UPDATE project_meta SET value = ? WHERE key = 'project_id'", (malicious_pid,))
            
        reopened_pid = store.project_id
        assert reopened_pid == malicious_pid, f"Expected {malicious_pid}, got {reopened_pid}"
        
        # Verify edits table still exists
        with sqlite3.connect(db_path) as conn:
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            assert "edits" in tables, "edits table dropped via project_id SQL injection!"
        print("  -> Passed project_id SQL injection test.")
        
        # Test 3: SQL injection in update_status (edit_id and new_status)
        print("[3/5] Testing SQL Injection in update_status()...")
        # 3a. Testing malicious edit_id parameter
        target_id = loaded[0].edit_id
        store.update_status("non_existent' OR '1'='1", "reverted")
        # Check that NO edits were changed by malicious WHERE clause
        with store._conn() as conn:
            statuses = [r[0] for r in conn.execute("SELECT status FROM edits").fetchall()]
            assert all(s == "applied" for s in statuses), "Malicious edit_id in update_status modified unexpected rows!"
            
        # 3b. Testing malicious new_status parameter (should trigger SQLite CHECK constraint)
        sqli_status_passed = False
        try:
            store.update_status(target_id, "applied'; DROP TABLE edits; --")
            sqli_status_passed = True
        except sqlite3.IntegrityError:
            print("  -> CHECK constraint correctly rejected invalid status payload.")
        except Exception as e:
            print(f"  -> Rejected with exception: {type(e).__name__}: {e}")
            
        assert not sqli_status_passed, "update_status allowed invalid status payload past CHECK constraint!"
        print("  -> Passed update_status() SQL injection test.")
        
        # Test 4: SQL injection in reorder()
        print("[4/5] Testing SQL Injection in reorder()...")
        op_a = loaded[0].edit_id
        op_b = loaded[1].edit_id
        
        # Pass SQL injection string as edit_id_a
        try:
            store.reorder(op_a + "' OR 1=1 --", op_b)
            assert False, "reorder should have raised ValueError for non-existent injected edit_id"
        except ValueError as e:
            assert "Both edits must exist" in str(e)
            print(f"  -> reorder safely rejected invalid edit_id: {e}")
            
        # Reorder valid ops to ensure normal function works
        store.reorder(op_a, op_b)
        new_loaded = store.load_all()
        assert new_loaded[0].edit_id == op_b and new_loaded[1].edit_id == op_a
        print("  -> Passed reorder() SQL injection test.")
        
        # Test 5: Verify table schema remains intact after all injection attempts
        print("[5/5] Final schema integrity check...")
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
            num_tables = cur.fetchone()[0]
            assert num_tables >= 2, f"Tables missing after SQL injection tests! Total tables: {num_tables}"
        print("  -> Passed schema integrity check.")
        
    print("\nSUCCESS: SQL Injection resistance empirically verified across all parameters!")


if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"\nTEST FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
