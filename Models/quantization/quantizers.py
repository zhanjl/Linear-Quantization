
# This source code is inspired by Yuxin Wu's repo(tensorpack/expamples/dorefanet.py)
import tensorflow as tf

from tensorpack.utils.argtools import graph_memoized


def quantize_midtread(x, k):
    n = float(2 ** k - 1)

    @tf.custom_gradient
    def _quantize_midtread(x):
        return tf.round(x * n) / n, lambda dy: dy

    return _quantize_midtread(x)


def quantize_midrise(x, k):
    n = float(2 ** k - 0.5)

    @tf.custom_gradient
    def _quantize_midrise(x):
        return (tf.floor(x * n) + 0.5) / n, lambda dy: dy

    return _quantize_midrise(x)


def quantize_weight(name, bitW, midtread):
    if name == 'linear':
        def qw(x):
            if bitW == 32:
                return x

            if midtread:
                assert bitW != 1, '[ConfigError]Cannot quantize weight to 1-bit with midtread method'
                max_val = tf.reduce_max(tf.abs(x))
                x = x / max_val
                x = quantize_midtread(x, bitW - 1) * max_val
                return x
            else:
                max_val = tf.reduce_max(tf.abs(x))
                x = x / max_val
                x = quantize_midrise(x, bitW - 1) * max_val
                return x

        return qw

    elif name == 'nonlinear':
        return None

def quantize_activation(bitA):
    def qa(x):
        if bitA == 32:
            return x
        return quantize_midtread(x, bitA)
    return qa

def quantize_gradient(bitG):
    def qg(x):
        if bitG == 32:
            return x

        @tf.custom_gradient
        def _identity(input):
            def grad_fg(x):
                rank = x.get_shape().ndims
                assert rank is not None
                maxx = tf.reduce_max(tf.abs(x), list(range(1, rank)), keep_dims=True)
                x = x / maxx
                n = float(2**bitG - 1)
                x = x * 0.5 + 0.5 + tf.random_uniform(
                    tf.shape(x), minval=-0.5 / n, maxval=0.5 / n)
                x = tf.clip_by_value(x, 0.0, 1.0)
                x = quantize_midtread(x, bitG) - 0.5
                return x * maxx * 2
            return input, grad_fg
        return _identity(x)
    return qg


def ternarize(x, thresh=0.05):
    """
    Implemented Trained Ternary Quantization:
    https://arxiv.org/abs/1612.01064
    Code modified from the authors' at:
    https://github.com/czhu95/ternarynet/blob/master/examples/Ternary-Net/ternary.py
    """
    shape = x.get_shape()

    thre_x = tf.stop_gradient(tf.reduce_max(tf.abs(x)) * thresh)

    w_p = tf.get_variable('Wp', initializer=1.0, dtype=tf.float32)
    w_n = tf.get_variable('Wn', initializer=1.0, dtype=tf.float32)

    tf.summary.scalar(w_p.op.name + '-summary', w_p)
    tf.summary.scalar(w_n.op.name + '-summary', w_n)

    mask = tf.ones(shape)
    mask_p = tf.where(x > thre_x, tf.ones(shape) * w_p, mask)
    mask_np = tf.where(x < -thre_x, tf.ones(shape) * w_n, mask_p)
    mask_z = tf.where((x < thre_x) & (x > - thre_x), tf.zeros(shape), mask)

    @tf.custom_gradient
    def _sign_mask(x):
        return tf.sign(x) * mask_z, lambda dy: dy

    w = _sign_mask(x)

    w = w * mask_np

    tf.summary.histogram(w.name, w)
    return w