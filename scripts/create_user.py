import getpass
from db import create_user, ensure_login_table

def main() -> None:
    ensure_login_table()
    username = input('Username: ').strip()
    if not username:
        raise SystemExit('Username required.')
    password = getpass.getpass('Password: ')
    if not password:
        raise SystemExit('Password required.')
    employeecode = input('Employee Code: ').strip()
    if not employeecode:
        raise SystemExit('Employee Code required.')
    create_user(username, password, employeecode)
    print('User created.')
if __name__ == '__main__':
    main()
