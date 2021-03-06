
# This source code is inspired by Yuxin Wu's repo(tensorpack/expamples/dorefanet.py)
import tensorflow as tf

from tensorpack.utils.argtools import graph_memoized
#from tensorpack.callbacks.base import Callback


__all__ = ['ternarize']


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


def quantize_odd(x, s):
    n = float((s - 1) / 2)

    @tf.custom_gradient
    def _quantize_odd(x):
        return tf.round(x * n) / n, lambda dy: dy

    return _quantize_odd(x)


def quantize_even(x, s):
    n = float(s / 2 - 0.5)

    @tf.custom_gradient
    def _qunatize_even(x):
        return (tf.floor(x * n) + 0.5) / n, lambda dy: dy

    return _qunatize_even(x)


'''
class GlobalStep(Callback):
    def get_global_step(self):
        return self.trainer.global_step
'''


def quantize_weight(bitW, name, opts, quantizer_config):
    # 1. Linear Quantization
    if name == 'linear':
        # 1-Level Quantization
        if eval(opts['centralized']) == False or eval(opts['centralized']) == True:
            def qw(x):
                if bitW == 32:

                    if quantizer_config['mulR'] in ['2R', 'R']:
                        if eval(opts['fix_max']):
                            param_name = x.op.name.split('/W')[0] + '/maxW'
                            max_x = tf.stop_gradient(tf.get_variable('maxW', initializer=1.0, dtype=tf.float32), name=param_name)
                            tf.add_to_collection('maxs', max_x)
                        else:
                            param_name = x.op.name.split('/W')[0] + '/maxW'
                            max_x = tf.stop_gradient(tf.reduce_max(tf.abs(x)), name=param_name)
                            tf.add_to_collection('maxs', max_x)
                    
                    return x

                if eval(opts['fix_max']):
                    #param_name = 'regularize_cost_internals/' + x.op.name.split('/W')[0] + '/maxW'
                    param_name = x.op.name.split('/W')[0] + '/maxW_stop_grad'
                    max_x = tf.stop_gradient(tf.get_variable('maxW', initializer=1.0, dtype=tf.float32))
                    max_x = tf.multiply(float(opts['max_scale']), max_x, name=param_name)
                    x = tf.clip_by_value(x, -max_x, max_x)
                else:
                    param_name = x.op.name.split('/W')[0] + '/maxW_stop_grad'
                    max_x = tf.stop_gradient(tf.reduce_max(tf.abs(x)), name=param_name)
                
                tf.add_to_collection('maxs', max_x)
                
                x = x / max_x

                if eval(opts['is_Lv']): # midtread
                    assert bitW != 1, '[ConfigError]Cannot quantize weight to 1-bit with midtread method'
                    if bitW == 3:
                        if eval(opts['fix_max']):
                            return ternarize_fixmax(x, max_x)
                        else:
                            return ternarize(x)
                    x = quantize_odd(x, bitW)
                else:  # midrise
                    x = quantize_midrise(x, bitW - 1)

                #w_s = tf.get_variable('scale_Ws', initializer=1.0, dtype=tf.float32)
                return tf.multiply(max_x, x)
            return qw

    # intervals quantization
    elif name == 'intQ':

        @tf.custom_gradient
        def qw(x): 
            if bitW == 32:
                if quantizer_config['mulR'] in ['2R', 'R']:
                    if eval(opts['fix_max']):
                        param_name = x.op.name.split('/W')[0] + '/maxW'
                        max_x = tf.stop_gradient(tf.get_variable('maxW', initializer=1.0, dtype=tf.float32), name=param_name)
                        tf.add_to_collection('maxs', max_x)
                    else:
                        param_name = x.op.name.split('/W')[0] + '/maxW'
                        max_x = tf.stop_gradient(tf.reduce_max(tf.abs(x)), name=param_name)
                        tf.add_to_collection('maxs', max_x)
                    
                return x

            if eval(opts['fix_max']):
                #param_name = 'regularize_cost_internals/' + x.op.name.split('/W')[0] + '/maxW'
                param_name = x.op.name.split('/W')[0] + '/maxW_stop_grad'
                max_x = tf.stop_gradient(tf.get_variable('maxW', initializer=1.0, dtype=tf.float32), name=param_name)
            else:
                param_name = x.op.name.split('/W')[0] + '/maxW_stop_grad'
                max_x = tf.stop_gradient(tf.reduce_max(tf.abs(x)), name=param_name)
                
            tf.add_to_collection('maxs', max_x)

            n = (bitW - 1) / 2

            x_abs = tf.abs(x)
            
            lower = max_x * 0.05
            upper = max_x * 0.95
            
            x_temp = tf.conf(x_abs < lower, tf.zeros_like(x_abs), tf.clip_by_value(x_abs, lower, upper*0.9999))
            x_temp = (n / 0.9 * max_x) * x_temp + (0.5 - (0.5 * n / 9))
            x_temp = tf.round(x_temp)

            x_temp = x_temp / n * upper

            x_temp = x_temp * tf.sign(x)
            
            return x_temp, lambda dy: dy
        return qw



    # 2. Centroid Quantization
    elif name == 'cent':

        if type(opts['threshold_bit']) == str:
            inBIT, exBIT = eval(opts['threshold_bit'])
        else:
            inBIT, exBIT = opts['threshold_bit']
        ratio = (1 / (1 + ((2 ** exBIT - 1) / (2 ** inBIT - 1))))
        
        def qw(x):
            if bitW == 32:
                return x

            if eval(opts['fix_max']):
                #param_name = 'regularize_cost_internals/' + x.op.name.split('/W')[0] + '/maxW'
                max_x = tf.stop_gradient(tf.get_variable('maxW', initializer=1.0, dtype=tf.float32))
                max_x *= float(opts['max_scale'])
                x = tf.clip_by_value(x, -max_x, max_x)
            else:
                max_x = tf.stop_gradient(tf.reduce_max(tf.abs(x)))

            thresh = ratio * max_x
            thresh2 = thresh * 0.999

            mask = tf.get_variable('maskW', shape=x.shape, initializer=tf.ones_initializer, dtype=tf.float32)
            
            x = tf.where(tf.equal(1.0, mask), tf.clip_by_value(x, -thresh2, thresh2), x)
                
            x = x / max_x

            if eval(opts['is_Lv']): # midtread
                assert bitW != 1, '[ConfigError]Cannot quantize weight to 1-bit with midtread method'
                x = quantize_odd(x, bitW)
            else:  # midrise
                x = quantize_midrise(x, bitW - 1)

            #w_s = tf.get_variable('scale_Ws', initializer=1.0, dtype=tf.float32)
            return tf.multiply(max_x, x)
        return qw

    # 3. Dynamic Network Surgery
    elif name == 'dns':

        if type(opts['threshold_bit']) == str:
            inBIT, exBIT = eval(opts['threshold_bit'])
        else:
            inBIT, exBIT = opts['threshold_bit']
        ratio = (1 / (1 + ((2 ** exBIT - 1) / (2 ** inBIT - 1))))

        def qw(x):
            if bitW == 32:
                return x

            if eval(opts['fix_max']):
                # param_name = 'regularize_cost_internals/' + x.op.name.split('/W')[0] + '/maxW'
                max_x = tf.stop_gradient(tf.get_variable('maxW', initializer=1.0, dtype=tf.float32))
                x = tf.clip_by_value(x, -max_x, max_x)
                max_x *= float(opts['max_scale'])
            else:
                max_x = tf.stop_gradient(tf.reduce_max(tf.abs(x)))
            x = x / max_x

            thresh = ratio * max_x * 0.999

            if eval(opts['is_Lv']):  # midtread
                assert bitW != 1, '[ConfigError]Cannot quantize weight to 1-bit with midtread method'
                if bitW == 3:
                    return ternarize(x)

                mask = tf.get_variable('maskW', shape=x.shape, initializer=tf.ones_initializer, dtype=tf.float32)

                @tf.custom_gradient
                def clip_with_STE(x):
                    return tf.clip_by_value(x, -thresh, thresh), lambda dy: dy

                x = tf.where(tf.equal(0.0, mask), clip_with_STE(x), x)
                x = quantize_odd(x, bitW)
            else:  # midrise
                x = quantize_midrise(x, bitW - 1)

            #w_s = tf.get_variable('scale_Ws', initializer=1.0, dtype=tf.float32)
            return tf.multiply(max_x, x)

        return qw


def quantize_activation(bitA, name, q_config):
    if name == 'intQ':
        @tf.custom_gradient        
        def qa(x):
            name = x.op.name
            ema_name = name + '_ema'
            
            c = tf.get_variable(ema_name, initializer=0.0, dtype=tf.float32)

            max_a = tf.max(x)

            temp_c = max_a

            new_c = tf.cond(tf.get_global_step() == 0, temp_c, c * 0.99 + temp_c * 0.01, name=ema_name + '_new')

            #op = tf.assign(c, new_c, use_locking=False).op

            tf.add_to_collection('new_cs', new_c)

            n = 2 ** bitA - 1
            
            lower = new_c * 0.05
            upper = new_c * 0.95
            
            x_temp = tf.conf(x < lower, tf.zeros_like(x), tf.clip_by_value(x, lower, upper*0.9999))
            x_temp = (n / 0.9 * new_c) * x_temp + (0.5 - (0.5 * n / 9))
            x_temp = tf.round(x_temp)

            x_temp = x_temp / n * upper
            
            return x_temp, lambda dy: dy

        return qa
        
    
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

    w1 = _sign_mask(x)

    w2 = tf.multiply(w1, mask_np, name='QW')

    #w_loss = 0.5 * tf.reduce_sum(tf.square(w1))
    #tf.add_to_collection('regularization_losses', w_loss)

    tf.summary.histogram(w2.name, w2)
    return w2


def ternarize_fixmax(x, max_x):

    thresh = 0.05
    
    shape = x.get_shape()

    thre_x = max_x * thresh

    w_s = tf.get_variable('Ws', initializer=1.0, dtype=tf.float32)

    tf.summary.scalar(w_s.op.name + '-summary', w_s)

    mask = tf.ones(shape)
    mask_s = tf.where(tf.logical_or(x > thre_x, x < -thresh), tf.ones(shape) * w_s, mask)
    mask_z = tf.where((x < thre_x) & (x > - thre_x), tf.zeros(shape), mask)

    @tf.custom_gradient
    def _sign_mask(x):
        return tf.sign(x) * mask_z, lambda dy: dy

    w1 = _sign_mask(x)

    w2 = tf.multiply(w1, mask_s, name='QW')

    #w_loss = 0.5 * tf.reduce_sum(tf.square(w1))
    #tf.add_to_collection('regularization_losses', w_loss)

    tf.summary.histogram(w2.name, w2)
    return w2
