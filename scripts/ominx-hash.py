#!/usr/bin/env python3
"""sha512crypt ($6$) generation for build-time account provisioning.

This mirrors the algorithm musl's crypt(3) implements, so the guest login
service verifies these hashes with the source-built C library. It only seeds the
packaged account file; runtime verification always happens in musl.
"""
import hashlib
import re
import secrets
import sys

ALPHABET = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
SALT_PATTERN = re.compile(r'^[./0-9A-Za-z]{1,16}$')
DEFAULT_ROUNDS = 5000
PASSWORD_MAX = 128


def _b64_from_24bit(b2, b1, b0, count):
    """glibc's little-endian 6-bit grouping used by crypt sha512."""
    value = (b2 << 16) | (b1 << 8) | b0
    out = []
    for _ in range(count):
        out.append(ALPHABET[value & 0x3F])
        value >>= 6
    return ''.join(out)


def _digest(password, salt, rounds):
    """Raw 64-byte crypt sha512 digest, before the fixed regrouping."""
    if rounds < 1000 or rounds > 999_999_999:
        raise ValueError('rounds out of range')
    # Digest B: reused as a subinput to A and as the seed for P.
    digest_b = hashlib.sha512(password + salt + password).digest()
    # Digest A is a running context; it is never a concatenation of digests.
    context = hashlib.sha512(password + salt)
    remaining = len(password)
    while remaining > 0:
        context.update(digest_b[:min(64, remaining)])
        remaining -= 64
    # Fold the length's binary digits: set bits add digest B, clear bits the key.
    count = len(password)
    while count > 0:
        context.update(digest_b if count & 1 else password)
        count >>= 1
    digest_a = context.digest()
    # P: password-length bytes from H(password repeated password-length times).
    seed = hashlib.sha512(password * len(password)).digest()
    p = (seed * (len(password) // 64 + 1))[:len(password)]
    # S: salt-length bytes from H(salt repeated 16 + A[0] times).
    seed = hashlib.sha512(salt * (16 + digest_a[0])).digest()
    s = (seed * (len(salt) // 64 + 1))[:len(salt)]
    for i in range(rounds):
        block = p if i % 2 else digest_a
        if i % 3:
            block += s
        if i % 7:
            block += p
        block += digest_a if i % 2 else p
        digest_a = hashlib.sha512(block).digest()
    return digest_a


def _encode(digest):
    """The fixed byte regrouping of crypt sha512; not generic base64."""
    order = [(0, 21, 42), (22, 43, 1), (44, 2, 23), (3, 24, 45), (25, 46, 4),
             (47, 5, 26), (6, 27, 48), (28, 49, 7), (50, 8, 29), (9, 30, 51),
             (31, 52, 10), (53, 11, 32), (12, 33, 54), (34, 55, 13),
             (56, 14, 35), (15, 36, 57), (37, 58, 16), (59, 17, 38),
             (18, 39, 60), (40, 61, 19), (62, 20, 41)]
    text = ''.join(_b64_from_24bit(digest[x], digest[y], digest[z], 4)
                   for x, y, z in order)
    return text + _b64_from_24bit(0, 0, digest[63], 2)


def generate(password, salt=None, rounds=DEFAULT_ROUNDS):
    if isinstance(password, str):
        password = password.encode('utf-8')
    if not 1 <= len(password) <= PASSWORD_MAX:
        raise ValueError('password length out of range')
    if salt is None:
        salt = ''.join(secrets.choice(ALPHABET[2:]) for _ in range(16))
    if isinstance(salt, str):
        salt = salt.encode('ascii')
    if not SALT_PATTERN.fullmatch(salt.decode('ascii')):
        raise ValueError('invalid crypt salt')
    digest = _digest(password, salt, rounds)
    prefix = f'$6$rounds={rounds}$' if rounds != DEFAULT_ROUNDS else '$6$'
    return prefix + salt.decode('ascii') + '$' + _encode(digest)


def verify(password, stored):
    if isinstance(password, str):
        password = password.encode('utf-8')
    if isinstance(stored, str):
        stored = stored.encode('ascii')
    match = re.fullmatch(rb'\$6\$(?:rounds=(\d+)\$)?([./0-9A-Za-z]{1,16})\$(.+)', stored)
    if not match:
        return False
    rounds = int(match.group(1)) if match.group(1) else DEFAULT_ROUNDS
    encoded = _encode(_digest(password, match.group(2), rounds)).encode('ascii')
    if len(encoded) != len(match.group(3)):
        return False
    difference = 0
    for left, right in zip(encoded, match.group(3)):
        difference |= left ^ right
    return difference == 0


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'generate':
        print(generate(sys.argv[2]))
    elif len(sys.argv) == 3 and sys.argv[1] == 'verify':
        sys.exit(0 if verify(sys.argv[2], sys.stdin.readline().strip()) else 1)
    else:
        raise SystemExit('usage: ominx-hash.py generate PASSWORD | verify PASSWORD')
