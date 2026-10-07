#!/usr/bin/env python3
"""Generate a bcrypt password hash for seed data."""

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


def main() -> None:
    password = 'Admin@123'
    print(pwd_context.hash(password))


if __name__ == '__main__':
    main()
