import torch
import torch.optim as optim
import torch.nn as nn

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from .networks import FCNN
from .neurodiffeq import diff


class DirichletBVP2D:

    def __init__(self, x_min, x_min_val, x_max, x_max_val, y_min, y_min_val, y_max, y_max_val):
        self.x_min, self.x_min_val = x_min, x_min_val
        self.x_max, self.x_max_val = x_max, x_max_val
        self.y_min, self.y_min_val = y_min, y_min_val
        self.y_max, self.y_max_val = y_max, y_max_val

    def enforce(self, net, x, y):
        xys = torch.cat((x, y), 1)
        u = net(xys)
        x_tilde = (x-self.x_min) / (self.x_max-self.x_min)
        y_tilde = (y-self.y_min) / (self.y_max-self.y_min)
        Axy = (1-x_tilde)*self.x_min_val(y) + x_tilde*self.x_max_val(y) + \
              (1-y_tilde)*( self.y_min_val(x) - ((1-x_tilde)*self.y_min_val(self.x_min * torch.ones_like(x_tilde))
                                                  + x_tilde *self.y_min_val(self.x_max * torch.ones_like(x_tilde))) ) + \
                 y_tilde *( self.y_max_val(x) - ((1-x_tilde)*self.y_max_val(self.x_min * torch.ones_like(x_tilde))
                                                  + x_tilde *self.y_max_val(self.x_max * torch.ones_like(x_tilde))) )
        return Axy + x_tilde*(1-x_tilde)*y_tilde*(1-y_tilde)*u


class IBVP1D:

    def __init__(
            self, x_min, x_max, t_min,
            x_min_val=None, x_min_prime=None,
            x_max_val=None, x_max_prime=None,
            t_min_val=None
    ):
        self.x_min, self.x_min_val, self.x_min_prime = x_min, x_min_val, x_min_prime
        self.x_max, self.x_max_val, self.x_max_prime = x_max, x_max_val, x_max_prime
        self.t_min, self.t_min_val = t_min, t_min_val
        if self.x_min_val and self.x_max_val:
            if self.x_min_prime or self.x_max_prime:
                raise ValueError('Problem is over-conditioned.')
            self.enforce = self._enforce_dd
        elif self.x_min_val and self.x_max_prime:
            if self.x_min_prime or self.x_max_val:
                raise ValueError('Problem is over-conditioned.')
            self.enforce = self._enforce_dn
        elif self.x_min_prime and self.x_max_val:
            if self.x_min_val or self.x_max_prime:
                raise ValueError('Problem is over-conditioned.')
            self.enforce = self._enforce_nd
        elif self.x_min_prime and self.x_max_prime:
            if self.x_min_val or self.x_max_val:
                raise ValueError('Problem is over-conditioned.')
            self.enforce = self._enforce_nn

    def _enforce_dd(self, net, x, t):
        xts = torch.cat((x, t), 1)
        uxt = net(xts)

        t_ones = torch.ones_like(t, requires_grad=True)
        t_ones_min = self.t_min * t_ones

        x_tilde = (x - self.x_min) / (self.x_max - self.x_min)
        t_tilde = t - self.t_min

        Axt = self.t_min_val(x) + \
            x_tilde     * (self.x_max_val(t) - self.x_max_val(t_ones_min)) + \
            (1-x_tilde) * (self.x_min_val(t) - self.x_min_val(t_ones_min))
        return Axt + x_tilde * (1 - x_tilde) * (1 - torch.exp(-t_tilde)) * uxt

    def _enforce_dn(self, net, x, t):
        xts = torch.cat((x, t), 1)
        uxt = net(xts)

        x_ones = torch.ones_like(x, requires_grad=True)
        t_ones = torch.ones_like(t, requires_grad=True)
        x_ones_max = self.x_max * x_ones
        t_ones_min = self.t_min * t_ones
        xmaxts  = torch.cat((x_ones_max, t), 1)
        uxmaxt  = net(xmaxts)

        x_tilde = (x-self.x_min) / (self.x_max-self.x_min)
        t_tilde = t-self.t_min

        Axt = (self.x_min_val(t) - self.x_min_val(t_ones_min)) + self.t_min_val(x) + \
            x_tilde * (self.x_max-self.x_min) * (self.x_max_prime(t) - self.x_max_prime(t_ones_min))
        return Axt + x_tilde*(1-torch.exp(-t_tilde))*(
            uxt - (self.x_max-self.x_min)*diff(uxmaxt, x_ones_max) - uxmaxt
        )

    def _enforce_nd(self, net, x, t):
        xts = torch.cat((x, t), 1)
        uxt = net(xts)

        x_ones = torch.ones_like(x, requires_grad=True)
        t_ones = torch.ones_like(t, requires_grad=True)
        x_ones_min = self.x_min * x_ones
        t_ones_min = self.t_min * t_ones
        xmints = torch.cat((x_ones_min, t), 1)
        uxmint = net(xmints)

        x_tilde = (x - self.x_min) / (self.x_max - self.x_min)
        t_tilde = t - self.t_min

        Axt = (self.x_max_val(t) - self.x_max_val(t_ones_min)) + self.t_min_val(x) + \
              (x_tilde - 1) * (self.x_max - self.x_min) * (self.x_min_prime(t) - self.x_min_prime(t_ones_min))
        return Axt + (1 - x_tilde) * (1 - torch.exp(-t_tilde)) * (
                uxt + (self.x_max - self.x_min) * diff(uxmint, x_ones_min) - uxmint
        )

    def _enforce_nn(self, net, x, t):
        xts = torch.cat((x, t), 1)
        uxt = net(xts)

        x_ones = torch.ones_like(x, requires_grad=True)
        t_ones = torch.ones_like(t, requires_grad=True)
        x_ones_min = self.x_min * x_ones
        x_ones_max = self.x_max * x_ones
        t_ones_min = self.t_min * t_ones
        xmints = torch.cat((x_ones_min, t), 1)
        xmaxts = torch.cat((x_ones_max, t), 1)
        uxmint = net(xmints)
        uxmaxt = net(xmaxts)

        x_tilde = (x - self.x_min) / (self.x_max - self.x_min)
        t_tilde = t - self.t_min

        Axt = self.t_min_val(x) - 0.5 * (1 - x_tilde) ** 2 * (self.x_max - self.x_min) * (
                self.x_min_prime(t) - self.x_min_prime(t_ones_min)
        ) + 0.5 * x_tilde ** 2 * (self.x_max - self.x_min) * (
                      self.x_max_prime(t) - self.x_max_prime(t_ones_min)
              )
        return Axt + (1 - torch.exp(-t_tilde)) * (
                uxt - x_tilde * (self.x_max - self.x_min) * diff(uxmint, x_ones_min) \
                + 0.5 * x_tilde ** 2 * (self.x_max - self.x_min) * (
                        diff(uxmint, x_ones_min) - diff(uxmaxt, x_ones_max)
                ))


class ExampleGenerator2D:

    def __init__(self, grid=[10, 10], xy_min=[0.0, 0.0], xy_max=[1.0, 1.0], method='equally-spaced-noisy'):
        self.size = grid[0] * grid[1]

        if method == 'equally-spaced':
            x = torch.linspace(xy_min[0], xy_max[0], grid[0], requires_grad=True)
            y = torch.linspace(xy_min[1], xy_max[1], grid[1], requires_grad=True)
            grid_x, grid_y = torch.meshgrid(x, y)
            self.grid_x, self.grid_y = grid_x.flatten(), grid_y.flatten()

            self.get_examples = lambda: (self.grid_x, self.grid_y)

        elif method == 'equally-spaced-noisy':
            x = torch.linspace(xy_min[0], xy_max[0], grid[0], requires_grad=True)
            y = torch.linspace(xy_min[1], xy_max[1], grid[1], requires_grad=True)
            grid_x, grid_y = torch.meshgrid(x, y)
            self.grid_x, self.grid_y = grid_x.flatten(), grid_y.flatten()

            self.noise_xmean = torch.zeros(self.size)
            self.noise_ymean = torch.zeros(self.size)
            self.noise_xstd = torch.ones(self.size) * ((xy_max[0] - xy_min[0]) / grid[0]) / 4.0
            self.noise_ystd = torch.ones(self.size) * ((xy_max[1] - xy_min[1]) / grid[1]) / 4.0
            self.get_examples = lambda: (
                self.grid_x + torch.normal(mean=self.noise_xmean, std=self.noise_xstd),
                self.grid_y + torch.normal(mean=self.noise_ymean, std=self.noise_ystd)
            )
        else:
            raise ValueError(f'Unknown method: {method}')


class Monitor2D:
    def __init__(self, xy_min, xy_max, check_every=100):
        self.check_every = check_every
        self.fig = plt.figure(figsize=(20, 8))
        self.ax1 = self.fig.add_subplot(121)
        self.ax2 = self.fig.add_subplot(122)
        self.cb1 = None
        # input for neural network
        gen = ExampleGenerator2D([32, 32], xy_min, xy_max, method='equally-spaced')
        xs_ann, ys_ann = gen.get_examples()
        self.xs_ann, self.ys_ann = xs_ann.reshape(-1, 1), ys_ann.reshape(-1, 1)
        self.xy_ann = torch.cat((self.xs_ann, self.ys_ann), 1)

    def check(self, net, pde, condition, loss_history):
        us = condition.enforce(net, self.xs_ann, self.ys_ann)
        us = us.detach().numpy().flatten()

        self.ax1.clear()
        cax1 = self.ax1.matshow(us.reshape((32, 32)), cmap='hot', interpolation='nearest')
        if self.cb1: self.cb1.remove()
        self.cb1 = self.fig.colorbar(cax1, ax=self.ax1)
        self.ax1.set_title('u(x, y)')

        self.ax2.clear()
        self.ax2.plot(loss_history['train'], label='training loss')
        self.ax2.plot(loss_history['valid'], label='validation loss')
        self.ax2.set_title('loss during training')
        self.ax2.set_ylabel('loss')
        self.ax2.set_xlabel('epochs')
        self.ax2.set_yscale('log')
        self.ax2.legend()

        self.fig.canvas.draw()


def solve2D(
        pde, condition, xy_min, xy_max,
        net=None, train_generator=None, shuffle=True, valid_generator=None, optimizer=None, criterion=None, batch_size=32,
        max_epochs=1000,
        monitor=None, return_internal=False
):
    # default values
    if not net:
        net = FCNN(n_input_units=2, n_hidden_units=32, n_hidden_layers=1, actv=nn.Tanh)
    if not train_generator:
        train_generator = ExampleGenerator2D([32, 32], xy_min, xy_max, method='equally-spaced-noisy')
    if not valid_generator:
        valid_generator = ExampleGenerator2D([32, 32], xy_min, xy_max, method='equally-spaced')
    if not optimizer:
        optimizer = optim.Adam(net.parameters(), lr=0.001)
    if not criterion:
        criterion = nn.MSELoss()

    if return_internal:
        internal = {
            'net': net,
            'condition': condition,
            'train_generator': train_generator,
            'valid_generator': valid_generator,
            'optimizer': optimizer,
            'criterion': criterion
        }

    n_examples_train = train_generator.size
    n_examples_valid = valid_generator.size
    train_zeros = torch.zeros(batch_size)
    valid_zeros = torch.zeros(n_examples_valid)

    loss_history = {'train': [], 'valid': []}

    for epoch in range(max_epochs):
        train_loss_epoch = 0.0

        train_examples_x, train_examples_y = train_generator.get_examples()
        train_examples_x, train_examples_y = train_examples_x.reshape((-1, 1)), train_examples_y.reshape((-1, 1))
        idx = np.random.permutation(n_examples_train) if shuffle else np.arange(n_examples_train)
        batch_start, batch_end = 0, batch_size
        while batch_start < n_examples_train:

            if batch_end > n_examples_train:
                batch_end = n_examples_train
            batch_idx = idx[batch_start:batch_end]
            xs, ys = train_examples_x[batch_idx], train_examples_y[batch_idx]

            us = condition.enforce(net, xs, ys)

            Fuxy = pde(us, xs, ys)
            loss = criterion(Fuxy, train_zeros)
            train_loss_epoch += loss.item() * (batch_end-batch_start)/n_examples_train

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            batch_start += batch_size
            batch_end += batch_size

        loss_history['train'].append(train_loss_epoch)

        # calculate the validation loss
        valid_examples_x, valid_examples_y = valid_generator.get_examples()
        xs, ys = valid_examples_x.reshape((-1, 1)), valid_examples_y.reshape((-1, 1))
        us = condition.enforce(net, xs, ys)
        Fuxy = pde(us, xs, ys)
        valid_loss_epoch = criterion(Fuxy, valid_zeros).item()

        loss_history['valid'].append(valid_loss_epoch)

        if monitor and epoch % monitor.check_every == 0:
            monitor.check(net, pde, condition, loss_history)

    def solution(xs, ys, as_type='tf'):
        original_shape = xs.shape
        if not isinstance(xs, torch.Tensor): xs = torch.tensor([xs], dtype=torch.float32)
        if not isinstance(ys, torch.Tensor): ys = torch.tensor([ys], dtype=torch.float32)
        xs, ys = xs.reshape(-1, 1), ys.reshape(-1, 1)
        us = condition.enforce(net, xs, ys)
        if   as_type == 'tf':
            return us.reshape(original_shape)
        elif as_type == 'np':
            return us.detach().numpy().reshape(original_shape)
        else:
            raise ValueError("The valid return types are 'tf' and 'np'.")

    if return_internal:
        return solution, loss_history, internal
    else:
        return solution, loss_history


def make_animation(solution, xs, ts):
    xx, tt = np.meshgrid(xs, ts)
    sol_net = solution(xx, tt, as_type='np')

    def u_gen():
        for i in range( len(sol_net) ):
            yield sol_net[i]

    fig, ax = plt.subplots()
    line, = ax.plot([], [], lw=2)

    umin, umax = sol_net.min(), sol_net.max()
    scale = umax - umin
    ax.set_ylim(umin-scale*0.1, umax+scale*0.1)
    ax.set_xlim(xs.min(), xs.max())
    def run(data):
        line.set_data(xs, data)
        return line,

    return animation.FuncAnimation(
        fig, run, u_gen, blit=True, interval=50, repeat=False
    )