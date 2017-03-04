import os
import time
import argparse
import importlib
import tensorflow as tf
import tensorflow.contrib as tc

from visualize import *

import matplotlib.pyplot as plt

logging = tf.logging
logging.set_verbosity(tf.logging.ERROR)

class WassersteinGAN(object):
    def __init__(self, g_net, d_net, data, model):
        self.model = model
        self.dataset = data
        self.data = self.dataset.name
        self.g_net = g_net
        self.d_net = d_net

        self.x_sampler = self.dataset.train_sampler[0]
        self.y_sampler = self.dataset.train_sampler[1]
        self.name_sampler = self.dataset.train_sampler[2]
        self.z_sampler = self.dataset.noise_sampler

        self.batch_size = self.dataset.config.batch_size
        self.z_dim = self.dataset.config.z_dim
        self.image_size = self.dataset.config.image_size


        self.x = tf.placeholder(tf.float32, self.x_sampler.get_shape(), name='x')
        self.z = tf.placeholder(tf.float32, [self.batch_size, self.z_dim], name='z')

        self.x_ = self.g_net(self.z)
        self.d = self.d_net(self.x, reuse=False)
        self.d_ = self.d_net(self.x_)

        self.g_loss = tf.reduce_mean(self.d_)
        self.d_loss = tf.reduce_mean(self.d) - tf.reduce_mean(self.d_)

        self.reg = tc.layers.apply_regularization(
            tc.layers.l1_regularizer(2.5e-5),
            weights_list=[var for var in tf.global_variables() if 'weights' in var.name]
        )
        self.g_loss_reg = self.g_loss + self.reg
        self.d_loss_reg = self.d_loss + self.reg

        self.d_rmsprop = tf.train.RMSPropOptimizer(learning_rate=5e-5)\
            .minimize(self.d_loss_reg, var_list=self.d_net.vars)
        self.g_rmsprop = tf.train.RMSPropOptimizer(learning_rate=5e-5)\
            .minimize(self.g_loss_reg, var_list=self.g_net.vars)

        self.d_clip = [v.assign(tf.clip_by_value(v, -0.01, 0.01)) for v in self.d_net.vars]
        gpu_options = tf.GPUOptions(allow_growth=True)
        self.sess = tf.Session(config=tf.ConfigProto(gpu_options=gpu_options))
        tf.train.start_queue_runners(sess=self.sess)


    def train(self, num_batches=1000000):
        plt.ion()
        self.sess.run(tf.global_variables_initializer())
        start_time = time.time()
        for t in range(0, num_batches):
            d_iters = 5
            if t % 500 == 0 or t < 25:
                 d_iters = 100

            for _ in range(0, d_iters):
                bx, by, names = self.sess.run([self.x_sampler, self.y_sampler, self.name_sampler])

                convert_op = tf.image.convert_image_dtype(bx, dtype=tf.uint8)
                bx = self.sess.run(convert_op) 
                fig = plt.figure(self.data + '.' + self.model)
                grid_show(fig, bx, [self.image_size, self.image_size, 3])
                path = 'logs/{}/'.format('test')
                if not os.path.exists(path):
                    os.makedirs(path)
                fig.savefig('logs/{}/{}.pdf'.format('test', t/100))

                bz = self.z_sampler(self.batch_size, self.z_dim)
                self.sess.run(self.d_clip)
                self.sess.run(self.d_rmsprop, feed_dict={self.x: bx, self.z: bz})

            bz = self.z_sampler(self.batch_size, self.z_dim)
            self.sess.run(self.g_rmsprop, feed_dict={self.z: bz})

            if t % 100 == 0 or t < 100:
                #bx = self.x_sampler(batch_size)
                bx = self.sess.run(self.x_sampler)
                bz = self.z_sampler(self.batch_size, self.z_dim)

                d_loss = self.sess.run(
                    self.d_loss, feed_dict={self.x: bx, self.z: bz}
                )
                g_loss = self.sess.run(
                    self.g_loss, feed_dict={self.z: bz}
                )
                print('Iter [%8d] Time [%5.4f] d_loss [%.4f] g_loss [%.4f]' %
                        (t + 1, time.time() - start_time, d_loss - g_loss, g_loss))

            if t % 100 == 0:
                bz = self.z_sampler(self.batch_size, self.z_dim)
                bx = self.sess.run(self.x_, feed_dict={self.z: bz})
                #bx = xs.data2img(bx)
                bx = (bx * 255).astype(np.uint8)
                fig = plt.figure(self.data + '.' + self.model)
                grid_show(fig, bx, [self.image_size, self.image_size, 3])
                path = 'logs/{}/'.format(self.data)
                if not os.path.exists(path):
                    os.makedirs(path)
                fig.savefig('logs/{}/{}.pdf'.format(self.data, t/100))


if __name__ == '__main__':
    parser = argparse.ArgumentParser('')
    parser.add_argument('--data', type=str, default='hico')
    parser.add_argument('--model', type=str, default='dcgan')
    parser.add_argument('--gpus', type=str, default='0')
    parser.add_argument('--batch_size', type=int, default=32)
    parser.add_argument('--image_size', type=int, default=64)
    args = parser.parse_args()

    os.environ['CUDA_VISIBLE_DEVICES'] = args.gpus

    model = importlib.import_module(args.data + '.' + args.model)
    config = importlib.import_module(args.data).config(
                batch_size = args.batch_size, image_size = args.image_size)

    data = importlib.import_module(args.data).dataset(config)

    d_net = model.Discriminator()
    g_net = model.Generator()
    wgan = WassersteinGAN(g_net, d_net, data, args.model)
    wgan.train()
