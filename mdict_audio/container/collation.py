import functools
import re
import string

_PUNCT_STRIP = re.compile("[%s ]+" % string.punctuation)


def mdict_key_cmp(is_mdd):
    def cmp(key1, key2):
        k1 = key1.lower()
        k2 = key2.lower()
        if not is_mdd:
            k1 = _PUNCT_STRIP.sub("", k1)
            k2 = _PUNCT_STRIP.sub("", k2)
        if k1 > k2:
            return 1
        if k1 < k2:
            return -1
        if len(k1) > len(k2):
            return -1
        if len(k1) < len(k2):
            return 1
        k1 = k1.rstrip(string.punctuation)
        k2 = k2.rstrip(string.punctuation)
        if k1 > k2:
            return -1
        if k1 < k2:
            return 1
        return 0

    return cmp


def key_sort_key(is_mdd):
    return functools.cmp_to_key(mdict_key_cmp(is_mdd))


def check_key_order(keys, is_mdd):
    cmp = mdict_key_cmp(is_mdd)
    prev = None
    for key in keys:
        if prev is not None and cmp(prev, key) > 0:
            return False
        prev = key
    return True
