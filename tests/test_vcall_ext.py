import drjit as dr
import vcall_ext as m
import pytest
import re

def get_pkg(t):
    backend = dr.backend_v(t)
    if backend == dr.JitBackend.LLVM:
        return m.llvm
    elif backend == dr.JitBackend.CUDA:
        return m.cuda

def cleanup(s):
    """Remove memory addresses and backend names from a string """
    s = re.sub(r' at 0x[a-fA-F0-9]*',r'', s)
    s = re.sub(r'\.llvm\.',r'.', s)
    s = re.sub(r'\.cuda\.',r'.', s)
    return s

@pytest.test_arrays('float32,is_diff,shape=(*)')
def test01_array_operations(t):
    pkg = get_pkg(t)

    A, B, Base, BasePtr = pkg.A, pkg.B, pkg.Base, pkg.BasePtr
    a, b = A(), B()

    # Creating objects (scalar)
    BasePtr(A())
    BasePtr(None)

    # Creating objects (vectorial)
    c = dr.zeros(BasePtr, 2)
    assert(str(c) == '[None, None]')
    assert c[0] is None

    c = dr.full(BasePtr, a, 2)
    assert cleanup(str(c)) == '[<vcall_ext.A object>, <vcall_ext.A object>]'
    c = dr.full(BasePtr, b, 2)
    assert cleanup(str(c)) == '[<vcall_ext.B object>, <vcall_ext.B object>]'
    assert c[0] is b and c[1] is b
    c[0] = a
    assert cleanup(str(c)) == '[<vcall_ext.A object>, <vcall_ext.B object>]'

    c = BasePtr(a)
    assert cleanup(str(c)) == '[<vcall_ext.A object>]'
    assert c[0] is a

    c = BasePtr(a, b)
    assert cleanup(str(c)) == '[<vcall_ext.A object>, <vcall_ext.B object>]'
    assert c[0] is a and c[1] is b
    c[0] = b
    c[1] = a
    assert cleanup(str(c)) == '[<vcall_ext.B object>, <vcall_ext.A object>]'
    assert c[0] is b and c[1] is a

    with pytest.raises(TypeError, match=re.escape("unsupported operand type(s) for +: 'BasePtr' and 'BasePtr'")):
        c+c
    assert dr.all(c == c)
    assert dr.all((c == None) == [False, False])
    assert dr.all((c == b) == [True, False])


@pytest.mark.parametrize("recorded", [True, False])
@pytest.test_arrays('float32,is_diff,shape=(*)')
def test02_array_call(t, recorded):
    pkg = get_pkg(t)

    A, B, Base, BasePtr = pkg.A, pkg.B, pkg.Base, pkg.BasePtr
    a, b = A(), B()

    c = BasePtr(a, a, None, b, b)

    xi = t(1, 2, 8, 3, 4)
    yi = t(5, 6, 8, 7, 8)

    with dr.scoped_set_flag(dr.JitFlag.VCallRecord, recorded):
        xo, yo = c.f(xi, yi)
    assert dr.all(xo == t(10, 12, 0, 21, 24))
    assert dr.all(yo == t(-1, -2, 0, 3, 4))

@pytest.mark.parametrize("recorded", [True, False])
@pytest.test_arrays('float32,is_diff,shape=(*)')
def test03_array_call_masked(t, recorded):
    pkg = get_pkg(t)

    A, B, Base, BasePtr = pkg.A, pkg.B, pkg.Base, pkg.BasePtr
    a, b = A(), B()

    c = BasePtr(a, a, a, b, b)

    xi = t(1, 2, 8, 3, 4)
    yi = t(5, 6, 8, 7, 8)
    mi = dr.mask_t(t)(True, True, False, True, True)

    with dr.scoped_set_flag(dr.JitFlag.VCallRecord, recorded):
        xo, yo = c.f_masked((xi, yi), mi)

    assert dr.all(xo == t(10, 12, 0, 21, 24))
    assert dr.all(yo == t(-1, -2, 0, 3, 4))

    c.dummy()


@pytest.mark.parametrize("recorded", [True, False])
@pytest.mark.parametrize("use_mask", [True, False])
@pytest.test_arrays('float32,is_diff,shape=(*)')
def test04_forward_diff(t, recorded, use_mask):
    pkg = get_pkg(t)

    A, B, Base, BasePtr = pkg.A, pkg.B, pkg.Base, pkg.BasePtr
    Mask = dr.mask_t(t)
    a, b = A(), B()

    xi = t(1, 2, 8, 3, 4)
    yi = t(5, 6, 8, 7, 8)

    # Turn one element off, two different ways..
    if use_mask:
        mi = Mask(True, True, False, True, True)
        c = BasePtr(a, a, a, b, b)
    else:
        mi = dr.ones(Mask, 5)
        c = BasePtr(a, a, None, b, b)

    dr.enable_grad(xi)
    dr.enable_grad(yi)

    with dr.scoped_set_flag(dr.JitFlag.VCallRecord, recorded):
        xo, yo = c.f_masked((xi, yi), mi)

    assert dr.all(xo == t(10, 12, 0, 21, 24))
    assert dr.all(yo == t(-1, -2, 0, 3, 4))

    dr.set_grad(xi, dr.ones(t, 5))
    dr.set_grad(yi, dr.full(t, 2, 5))
    xg, yg = dr.forward_to(xo, yo)
    dr.schedule(xg, yg)
    assert dr.all(xg == t(4, 4, 0, 6, 6))
    assert dr.all(yg == t(-1, -1, 0, 1, 1))


@pytest.mark.parametrize("recorded", [True, False])
@pytest.mark.parametrize("use_mask", [True, False])
@pytest.test_arrays('float32,is_diff,shape=(*)')
def test05_backward_diff(t, recorded, use_mask):
    pkg = get_pkg(t)

    A, B, Base, BasePtr = pkg.A, pkg.B, pkg.Base, pkg.BasePtr
    Mask = dr.mask_t(t)
    a, b = A(), B()

    xi = t(1, 2, 8, 3, 4)
    yi = t(5, 6, 8, 7, 8)

    # Turn one element off, two different ways..
    if use_mask:
        mi = Mask(True, True, False, True, True)
        c = BasePtr(a, a, a, b, b)
    else:
        mi = dr.ones(Mask, 5)
        c = BasePtr(a, a, None, b, b)

    dr.enable_grad(xi)
    dr.enable_grad(yi)

    with dr.scoped_set_flag(dr.JitFlag.VCallRecord, recorded):
        xo, yo = c.f_masked((xi, yi), mi)

    dr.set_grad(xo, dr.ones(t, 5))
    dr.set_grad(yo, dr.full(t, 2, 5))
    xg, yg = dr.backward_to(xi, yi)
    assert dr.all(xg == [-2, -2, 0, 2, 2])
    assert dr.all(yg == [2, 2, 0, 3, 3])


@pytest.mark.parametrize("recorded", [True, False])
@pytest.mark.parametrize("use_mask", [True, False])
@pytest.test_arrays('float32,is_diff,shape=(*)')
def test06_forward_diff_implicit(t, recorded, use_mask):
    pkg = get_pkg(t)

    A, B, Base, BasePtr = pkg.A, pkg.B, pkg.Base, pkg.BasePtr
    Mask = dr.mask_t(t)
    a, b = A(), B()

    x = t(1, 2, 8, 3, 4)
    av = t(1)
    bv = t(1)
    dr.enable_grad(x, av, bv)

    # Turn one element off, two different ways..
    if use_mask:
        mi = Mask(True, True, False, True, True)
        c = BasePtr(a, a, a, b, b)
    else:
        mi = dr.ones(Mask, 5)
        c = BasePtr(a, a, None, b, b)

    a.value = av * 2
    b.value = bv * 4
    y = x*x

    with dr.scoped_set_flag(dr.JitFlag.VCallRecord, recorded):
        xo = c.g(y, mi)

    assert dr.all(xo == t(2, 2, 0, 4*9, 4*16))

    dr.set_grad(x, [1,2,3,4,5])
    dr.set_grad(av, 10)
    dr.set_grad(bv, 100)
    xg = dr.forward_to(xo)

    assert dr.all(xg == t([20, 20, 0, 9*400+24*4, 16*400+40*4]))


@pytest.mark.parametrize("recorded", [True, False])
@pytest.mark.parametrize("use_mask", [True, False])
@pytest.test_arrays('float32,is_diff,shape=(*)')
def test07_backward_diff_implicit(t, recorded, use_mask):
    pkg = get_pkg(t)

    A, B, Base, BasePtr = pkg.A, pkg.B, pkg.Base, pkg.BasePtr
    Mask = dr.mask_t(t)
    a, b = A(), B()

    x = t(1, 2, 8, 3, 4)
    av = t(1)
    bv = t(1)
    dr.enable_grad(x, av, bv)

    # Turn one element off, two different ways..
    if use_mask:
        mi = Mask(True, True, False, True, True)
        c = BasePtr(a, a, a, b, b)
    else:
        mi = dr.ones(Mask, 5)
        c = BasePtr(a, a, None, b, b)

    a.value = av * 2
    b.value = bv * 4
    y = x*x

    with dr.scoped_set_flag(dr.JitFlag.VCallRecord, recorded):
        xo = c.g(y, mi)

    assert dr.all(xo == t(2, 2, 0, 4*9, 4*16))

    dr.set_grad(xo, [1,2,3,4,5])
    dr.backward_from(xo)

    assert dr.all(dr.grad(x) == t([0, 0, 0, 24, 32]))
    assert dr.all(dr.grad(av) == t([4]))
    assert dr.all(dr.grad(bv) == t([100]))


@pytest.mark.parametrize("use_mask", [True, False])
@pytest.test_arrays('float32,is_diff,shape=(*)')
def test08_getters(t, use_mask):
    pkg = get_pkg(t)

    A, B, Base, BasePtr = pkg.A, pkg.B, pkg.Base, pkg.BasePtr
    Mask = dr.mask_t(t)
    a, b = A(), B()

    # Turn one element off, two different ways..
    if use_mask:
        mi = Mask(True, True, False, True, True)
        c = BasePtr(a, a, a, b, b)
    else:
        mi = dr.ones(Mask, 5)
        c = BasePtr(a, a, None, b, b)

    arr0 = c.scalar_getter(mi)
    assert dr.all(arr0 == t([1, 1, 0, 2, 2]))

    arr1 = c.opaque_getter(mi)
    assert dr.all(arr1 == t([1, 1, 0, 2, 2]))

    arr3_a, arr3_b = c.complex_getter(mi)
    assert dr.all(arr3_a == t([1, 1, 0, 4, 4]))
    assert dr.all(arr3_b == dr.uint32_array_t(t)([5, 5, 0, 3, 3]))


@pytest.test_arrays('float32,is_diff,shape=(*)')
def test09_constant_getter(t, drjit_verbose, capsys):
    pkg = get_pkg(t)

    A, B, Base, BasePtr = pkg.A, pkg.B, pkg.Base, pkg.BasePtr
    Mask = dr.mask_t(t)
    a, b = A(), B()

    c = BasePtr(a, a, a, b, b)
    d = c.constant_getter()
    transcript = capsys.readouterr().out
    assert d[0] == 123
    assert transcript.count('ad_vcall_getter') == 1
    assert transcript.count('jit_var_gather') == 1
    d = c.opaque_getter()
    transcript = capsys.readouterr().out
    assert transcript.count('ad_vcall_getter') == 1
    assert transcript.count('jit_var_gather') == 1



@pytest.test_arrays('float32,is_diff,shape=(*)')
def test11_getter_ad(t):
    pkg = get_pkg(t)

    A, B, Base, BasePtr = pkg.A, pkg.B, pkg.Base, pkg.BasePtr
    Mask = dr.mask_t(t)
    a, b = A(), B()

    c = BasePtr(a, a, None, b, b)
    dr.enable_grad(a.opaque)
    dr.enable_grad(b.opaque)
    dr.set_grad(a.opaque, 10)
    dr.set_grad(b.opaque, 20)

    arr1 = c.opaque_getter()
    assert dr.grad_enabled(arr1)
    assert dr.all(arr1 == t([1, 1, 0, 2, 2]))
    arr1_g = dr.forward_to(arr1)
    assert dr.all(arr1_g == t([10, 10, 0, 20, 20]))
