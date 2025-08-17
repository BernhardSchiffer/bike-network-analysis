# %%
from utils.utils import *

#%%
# test tuple validation
t = '(1, 2)'
assert is_tuple(t) == True

# test split tuplestring
s = '1360463310, (1360463310, 1360463309), 0'
assert split_tuple(s) == ['1360463310', '(1360463310, 1360463309)', '0']

# test reversing nested tuples
k1 = ('(1360463310, (1360463310, 1360463309, 0), 0)', '(1360463310, 1360463309, 0)', '0')
k2 = ('(1360463309, 1360463310, 0)', '((1360463309, 1360463310, 0), 1360463310, 0)', '0')

assert get_reversed_key(k1) == k2, f'expected {k2} but got {get_reversed_key(k1)}'
# %%
