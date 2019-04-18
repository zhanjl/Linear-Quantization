import tensorflow as tf

def get_optimizer(config):
    lr = tf.get_variable('learning_rate', initializer=float(config['lr']), trainable=False)
        
    if config['name'] == 'SGD':
        opt = tf.train.GradientDescentOptimizer(lr)
    elif config['name'] == 'Momentum':
        opt = tf.train.MomentumOptimizer(lr, 0.9)
    return opt