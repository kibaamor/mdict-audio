import struct

# Ported from mdict-utils (MIT) base/ripemd128.py, which itself derives
# from zhansliu/writemdict. NOTICE carries the attribution.


def _f(j, x, y, z):
    if j < 16:
        return x ^ y ^ z
    if j < 32:
        return (x & y) | (z & ~x)
    if j < 48:
        return (x | (0xffffffff & ~y)) ^ z
    return (x & z) | (y & ~z)


def _K(j):
    if j < 16:
        return 0x00000000
    if j < 32:
        return 0x5a827999
    if j < 48:
        return 0x6ed9eba1
    return 0x8f1bbcdc


def _Kp(j):
    if j < 16:
        return 0x50a28be6
    if j < 32:
        return 0x5c4dd124
    if j < 48:
        return 0x6d703ef3
    return 0x00000000


def _padandsplit(message):
    origlen = len(message)
    padlength = 64 - ((origlen - 56) % 64)
    message += b"\x80"
    message += b"\x00" * (padlength - 1)
    message += struct.pack("<Q", origlen * 8)
    return [
        [
            struct.unpack("<L", message[i + j:i + j + 4])[0]
            for j in range(0, 64, 4)
        ]
        for i in range(0, len(message), 64)
    ]


def _add(*args):
    return sum(args) & 0xffffffff


def _rol(s, x):
    return (x << s | x >> (32 - s)) & 0xffffffff


_R = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
      7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8,
      3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12,
      1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2]
_RP = [5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12,
       6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2,
       15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13,
       8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14]
_S = [11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8,
      7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12,
      11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5,
      11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12]
_SP = [8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6,
       9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11,
       9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5,
       15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8]


def ripemd128(message):
    h0 = 0x67452301
    h1 = 0xefcdab89
    h2 = 0x98badcfe
    h3 = 0x10325476
    X = _padandsplit(message)
    for i in range(len(X)):
        (A, B, C, D) = (h0, h1, h2, h3)
        (Ap, Bp, Cp, Dp) = (h0, h1, h2, h3)
        for j in range(64):
            T = _rol(_S[j], _add(A, _f(j, B, C, D), X[i][_R[j]], _K(j)))
            (A, D, C, B) = (D, C, B, T)
            T = _rol(_SP[j],
                     _add(Ap, _f(63 - j, Bp, Cp, Dp), X[i][_RP[j]], _Kp(j)))
            (Ap, Dp, Cp, Bp) = (Dp, Cp, Bp, T)
        T = _add(h1, C, Dp)
        h1 = _add(h2, D, Ap)
        h2 = _add(h3, A, Bp)
        h3 = _add(h0, B, Cp)
        h0 = T
    return struct.pack("<LLLL", h0, h1, h2, h3)


def fast_decrypt(data, key):
    b = bytearray(data)
    key = bytearray(key)
    previous = 0x36
    for i in range(len(b)):
        t = (b[i] >> 4 | b[i] << 4) & 0xff
        t = t ^ previous ^ (i & 0xff) ^ key[i % len(key)]
        previous = b[i]
        b[i] = t
    return bytes(b)


def decrypt_key_block_info(frame):
    key = ripemd128(frame[4:8] + struct.pack("<L", 0x3695))
    return frame[:8] + fast_decrypt(frame[8:], key)
