"""Minimal QR Code (byte mode, ECC M) as an SVG for order receipts."""
from __future__ import annotations

from typing import List

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for i in range(255):
    _EXP[i] = _x
    _LOG[_x] = i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for i in range(255, 512):
    _EXP[i] = _EXP[i - 255]


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(degree: int) -> List[int]:
    gen = [1]
    for i in range(degree):
        nxt = [0] * (len(gen) + 1)
        factor = _EXP[i]
        for idx, coef in enumerate(gen):
            nxt[idx] ^= _gf_mul(coef, factor)
            nxt[idx + 1] ^= coef
        gen = nxt
    return gen


def _rs_encode(data: List[int], ecc_len: int) -> List[int]:
    gen = _rs_generator(ecc_len)
    ecc = [0] * ecc_len
    for byte in data:
        factor = byte ^ ecc[0]
        ecc = ecc[1:] + [0]
        if factor:
            for i, coef in enumerate(gen[1:]):
                ecc[i] ^= _gf_mul(coef, factor)
    return ecc


# version -> (capacity bytes, ecc codewords, blocks, group2_blocks, group2_data)
_VERSIONS = {
    1: (14, 10, 1, 0, 0),
    2: (26, 16, 1, 0, 0),
    3: (42, 26, 1, 0, 0),
    4: (62, 18, 2, 0, 0),
    5: (84, 24, 2, 0, 0),
    6: (106, 16, 4, 0, 0),
}

_ALIGN = {
    2: (18,),
    3: (22,),
    4: (26,),
    5: (30,),
    6: (34,),
}


def _choose_version(payload: bytes) -> int:
    needed = 2 + len(payload)  # mode + length + data (v1-9 length is 1 byte)
    for version, (capacity, *_rest) in _VERSIONS.items():
        if needed <= capacity:
            return version
    raise ValueError('Receipt QR payload is too long.')


def _build_data(payload: bytes, version: int) -> List[int]:
    capacity, ecc_len, blocks, _g2, _g2d = _VERSIONS[version]
    bits: List[int] = []

    def put(value: int, width: int) -> None:
        for shift in range(width - 1, -1, -1):
            bits.append((value >> shift) & 1)

    put(0b0100, 4)
    put(len(payload), 8)
    for byte in payload:
        put(byte, 8)
    remaining = capacity * 8 - len(bits)
    put(0, min(4, remaining))
    while len(bits) % 8:
        bits.append(0)
    data = []
    for i in range(0, len(bits), 8):
        byte = 0
        for bit in bits[i:i + 8]:
            byte = (byte << 1) | bit
        data.append(byte)
    pad = (0xEC, 0x11)
    idx = 0
    while len(data) < capacity:
        data.append(pad[idx % 2])
        idx += 1
    data = data[:capacity]
    block_data = capacity // blocks
    ecc_each = ecc_len // blocks
    encoded: List[int] = []
    ecc_blocks: List[List[int]] = []
    for i in range(blocks):
        chunk = data[i * block_data:(i + 1) * block_data]
        encoded.extend(chunk)
        ecc_blocks.append(_rs_encode(chunk, ecc_each))
    # interleave if more than one block
    if blocks == 1:
        return encoded + ecc_blocks[0]
    interleaved = []
    for col in range(block_data):
        for block in range(blocks):
            interleaved.append(data[block * block_data + col])
    for col in range(ecc_each):
        for block in range(blocks):
            interleaved.append(ecc_blocks[block][col])
    return interleaved


def _reserved(size: int, version: int) -> List[List[bool]]:
    reserved = [[False] * size for _ in range(size)]

    def mark(r: int, c: int) -> None:
        if 0 <= r < size and 0 <= c < size:
            reserved[r][c] = True

    def finder(r: int, c: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                mark(r + dr, c + dc)

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)
    for i in range(size):
        mark(6, i)
        mark(i, 6)
    for pos in _ALIGN.get(version, ()):
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                mark(pos + dr, pos + dc)
    for i in range(9):
        mark(8, i)
        mark(i, 8)
        mark(8, size - 1 - i)
        mark(size - 1 - i, 8)
    mark(8, 8)
    return reserved


def _place_finders(grid: List[List[int]], size: int) -> None:
    def finder(r: int, c: int) -> None:
        for dr in range(7):
            for dc in range(7):
                edge = dr in (0, 6) or dc in (0, 6)
                inner = 2 <= dr <= 4 and 2 <= dc <= 4
                grid[r + dr][c + dc] = 1 if edge or inner else 0

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)


def _place_timing_and_align(grid: List[List[int]], size: int, version: int) -> None:
    for i in range(8, size - 8):
        grid[6][i] = 1 if i % 2 == 0 else 0
        grid[i][6] = 1 if i % 2 == 0 else 0
    for pos in _ALIGN.get(version, ()):
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                edge = abs(dr) == 2 or abs(dc) == 2
                grid[pos + dr][pos + dc] = 1 if edge or (dr == 0 and dc == 0) else 0


def _mask_bit(mask: int, r: int, c: int) -> bool:
    if mask == 0:
        return (r + c) % 2 == 0
    if mask == 1:
        return r % 2 == 0
    if mask == 2:
        return c % 3 == 0
    if mask == 3:
        return (r + c) % 3 == 0
    if mask == 4:
        return (r // 2 + c // 3) % 2 == 0
    if mask == 5:
        return (r * c) % 2 + (r * c) % 3 == 0
    if mask == 6:
        return ((r * c) % 2 + (r * c) % 3) % 2 == 0
    return ((r + c) % 2 + (r * c) % 3) % 2 == 0


_FORMAT_POLY = 0b10100110111
_FORMAT_MASK = 0b101010000010010


def _format_bits(mask: int) -> int:
    data = (0b00 << 3) | mask  # ECC M
    bits = data << 10
    for shift in range(14, 9, -1):
        if bits & (1 << shift):
            bits ^= _FORMAT_POLY << (shift - 10)
    return ((data << 10) | bits) ^ _FORMAT_MASK


def _place_format(grid: List[List[int]], size: int, mask: int) -> None:
    bits = _format_bits(mask)
    coords = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]
    copies = [
        (size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8),
        (size - 5, 8), (size - 6, 8), (size - 7, 8),
        (8, size - 8), (8, size - 7), (8, size - 6), (8, size - 5),
        (8, size - 4), (8, size - 3), (8, size - 2), (8, size - 1),
    ]
    for i, (r, c) in enumerate(coords):
        grid[r][c] = (bits >> (14 - i)) & 1
    for i, (r, c) in enumerate(copies):
        grid[r][c] = (bits >> (14 - i)) & 1
    grid[size - 8][8] = 1


def _place_data(grid: List[List[int]], reserved: List[List[bool]], data: List[int], mask: int) -> None:
    size = len(grid)
    bits: List[int] = []
    for byte in data:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    idx = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for dc in (0, -1):
                c = col + dc
                if reserved[row][c]:
                    continue
                bit = bits[idx] if idx < len(bits) else 0
                if _mask_bit(mask, row, c):
                    bit ^= 1
                grid[row][c] = bit
                idx += 1
        upward = not upward
        col -= 2


def _penalty(grid: List[List[int]]) -> int:
    size = len(grid)
    score = 0
    for r in range(size):
        run = 1
        for c in range(1, size):
            if grid[r][c] == grid[r][c - 1]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run = 1
        if run >= 5:
            score += 3 + (run - 5)
    for c in range(size):
        run = 1
        for r in range(1, size):
            if grid[r][c] == grid[r - 1][c]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run = 1
        if run >= 5:
            score += 3 + (run - 5)
    for r in range(size - 1):
        for c in range(size - 1):
            if grid[r][c] == grid[r][c + 1] == grid[r + 1][c] == grid[r + 1][c + 1]:
                score += 3
    dark = sum(sum(row) for row in grid)
    percent = (dark * 100) // (size * size)
    score += abs(percent - 50) // 5 * 10
    return score


def qr_modules(text: str) -> List[List[int]]:
    payload = (text or '').encode('utf-8')
    version = _choose_version(payload)
    size = 17 + 4 * version
    data = _build_data(payload, version)
    reserved = _reserved(size, version)
    best = None
    best_score = None
    for mask in range(8):
        grid = [[0] * size for _ in range(size)]
        _place_finders(grid, size)
        _place_timing_and_align(grid, size, version)
        _place_data(grid, reserved, data, mask)
        _place_format(grid, size, mask)
        score = _penalty(grid)
        if best_score is None or score < best_score:
            best = grid
            best_score = score
    return best or [[1]]


def qr_svg(text: str, *, size_px: int = 84) -> str:
    modules = qr_modules(text)
    n = len(modules)
    quiet = 2
    dim = n + quiet * 2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" width="{size_px}" height="{size_px}" shape-rendering="crispEdges" aria-hidden="true">'
        f'<rect width="{dim}" height="{dim}" fill="#fff"/>'
    ]
    for r, row in enumerate(modules):
        for c, bit in enumerate(row):
            if bit:
                parts.append(f'<rect x="{c + quiet}" y="{r + quiet}" width="1" height="1" fill="#111"/>')
    parts.append('</svg>')
    return ''.join(parts)
