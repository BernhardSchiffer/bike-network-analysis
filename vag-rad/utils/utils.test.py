# %%
from utils.utils import get_reversed_key, is_sublist, is_tuple, split_tuple

# test tuple validation
t = '(1, 2)'
assert is_tuple(t)

# test split tuplestring
s = '1360463310, (1360463310, 1360463309), 0'
assert split_tuple(s) == ['1360463310', '(1360463310, 1360463309)', '0']

# test reversing nested tuples
k1 = ('(1360463310, (1360463310, 1360463309, 0), 0)', '(1360463310, 1360463309, 0)', '0')
k2 = ('(1360463309, 1360463310, 0)', '((1360463309, 1360463310, 0), 1360463310, 0)', '0')

assert get_reversed_key(k1) == k2, f'expected {k2} but got {get_reversed_key(k1)}'

# test 
a = [5, 6, 3, 8, 2, 1, 7, 1]
b = [8, 2, 1, 7] # sublist

assert is_sublist(a, b)
# %%
