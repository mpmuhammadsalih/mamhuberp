"""Script to add location entries to LOCATIONMASTER table for each dbkey"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.settings import get_db_config
from db import _get_connection, _get_table_columns_with_key

def setup_locations():
    """Add location entries to LOCATIONMASTER table (single database)."""
    config = get_db_config()
    if not config.get('user') or not config.get('dsn'):
        print('ERROR: Database not configured. Set DB_USERNAME, DB_PASSWORD, DB_DSN in .env')
        return
    print(f"Connecting to database: {config['user']}@{config['dsn']}")
    print('=' * 80)
    cols = _get_table_columns_with_key('LOCATIONMASTER', None)
    if not cols:
        print('ERROR: LOCATIONMASTER table not found!')
        return
    print(f"LOCATIONMASTER columns: {', '.join(cols)}")
    print('=' * 80)
    if 'LOCATIONCODE' not in cols or 'LOCATIONNAME' not in cols:
        print('ERROR: LOCATIONCODE or LOCATIONNAME column not found!')
        return
    conn = _get_connection()
    cursor = conn.cursor()
    location_mappings = {'1': 'Default Location'}
    dbkey_to_code = {'1': 1}
    try:
        cursor.execute("\n            SELECT DATA_TYPE, DATA_LENGTH \n            FROM USER_TAB_COLUMNS \n            WHERE TABLE_NAME = 'LOCATIONMASTER' AND COLUMN_NAME = 'LOCATIONCODE'\n        ")
        col_info = cursor.fetchone()
        if col_info:
            data_type, data_length = col_info
            print(f'\nLOCATIONCODE data type: {data_type} (length: {data_length})')
            is_numeric = data_type in ('NUMBER', 'INTEGER', 'FLOAT', 'DECIMAL')
            print(f'Is numeric: {is_numeric}')
        else:
            is_numeric = False
        print('=' * 80)
        cursor.execute('SELECT LOCATIONCODE, LOCATIONNAME FROM LOCATIONMASTER')
        existing = cursor.fetchall()
        print(f'\nExisting locations in LOCATIONMASTER:')
        for row in existing:
            print(f'  LOCATIONCODE: {row[0]} (type: {type(row[0]).__name__}), LOCATIONNAME: {row[1]}')
        print('=' * 80)
        print('\nAdding/Updating locations for each dbkey:')
        print('-' * 80)
        for dbkey, location_name in location_mappings.items():
            if is_numeric:
                location_code = dbkey_to_code.get(dbkey, None)
                if location_code is None:
                    print(f"[SKIP] No numeric code mapping for dbkey '{dbkey}'")
                    continue
            else:
                location_code = dbkey
            if is_numeric:
                cursor.execute('SELECT COUNT(*) FROM LOCATIONMASTER WHERE LOCATIONCODE = :code', {'code': location_code})
            else:
                cursor.execute('SELECT COUNT(*) FROM LOCATIONMASTER WHERE TO_CHAR(LOCATIONCODE) = :code OR LOCATIONCODE = :code', {'code': str(location_code)})
            exists = cursor.fetchone()[0] > 0
            if exists:
                if is_numeric:
                    update_sql = '\n                        UPDATE LOCATIONMASTER \n                        SET LOCATIONNAME = :name\n                        WHERE LOCATIONCODE = :code\n                    '
                    cursor.execute(update_sql, {'name': location_name, 'code': location_code})
                else:
                    update_sql = '\n                        UPDATE LOCATIONMASTER \n                        SET LOCATIONNAME = :name\n                        WHERE TO_CHAR(LOCATIONCODE) = :code OR LOCATIONCODE = :code\n                    '
                    cursor.execute(update_sql, {'name': location_name, 'code': str(location_code)})
                print(f"[UPDATED] LOCATIONCODE = {location_code} (dbkey: {dbkey}) -> LOCATIONNAME = '{location_name}'")
            else:
                if 'BASELOCATIONFLAG' in cols:
                    insert_sql = '\n                        INSERT INTO LOCATIONMASTER (LOCATIONCODE, LOCATIONNAME, BASELOCATIONFLAG)\n                        VALUES (:code, :name, :flag)\n                    '
                    flag = 'Y' if dbkey == 'HO' else 'N'
                    cursor.execute(insert_sql, {'code': location_code, 'name': location_name, 'flag': flag})
                else:
                    insert_sql = '\n                        INSERT INTO LOCATIONMASTER (LOCATIONCODE, LOCATIONNAME)\n                        VALUES (:code, :name)\n                    '
                    cursor.execute(insert_sql, {'code': location_code, 'name': location_name})
                print(f"[INSERTED] LOCATIONCODE = {location_code} (dbkey: {dbkey}) -> LOCATIONNAME = '{location_name}'")
        conn.commit()
        print('\n' + '=' * 80)
        print('[SUCCESS] All locations added/updated successfully!')
        print('=' * 80)
        print('\nVerifying locations:')
        print('-' * 80)
        cursor.execute('SELECT LOCATIONCODE, LOCATIONNAME, BASELOCATIONFLAG FROM LOCATIONMASTER ORDER BY LOCATIONCODE')
        rows = cursor.fetchall()
        for row in rows:
            code, name, flag = (row[0], row[1], row[2] if len(row) > 2 else None)
            flag_str = f', BASELOCATIONFLAG = {flag}' if flag else ''
            print(f'  LOCATIONCODE: {code}, LOCATIONNAME: {name}{flag_str}')
    except Exception as e:
        conn.rollback()
        print(f'\n[ERROR] {e}')
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()
if __name__ == '__main__':
    setup_locations()
