import tensorflow as tf
from overrides import overrides

from layers import losses
from trainers import gan_trainer
from utils import logging

SEED = 0
NUM_TEST_EXAMPLES = 4

logger = logging.get_logger(__name__)


class CycleGANTrainer(gan_trainer.GANTrainer):

    def __init__(
            self,
            batch_size,
            generator,
            discriminator,
            dataset_type,
            lr_generator,
            lr_discriminator,
            continue_training,
            save_images_every_n_steps,
            checkpoint_step=10,
    ):
        self.generator_optimizer_f = tf.keras.optimizers.Adam(lr_generator, beta_1=0.5)
        self.generator_optimizer_g = tf.keras.optimizers.Adam(lr_generator, beta_1=0.5)
        self.discriminator_optimizer_x = tf.keras.optimizers.Adam(lr_discriminator, beta_1=0.5)
        self.discriminator_optimizer_y = tf.keras.optimizers.Adam(lr_discriminator, beta_1=0.5)

        self.discriminator_x, self.discriminator_y = discriminator
        self.generator_f, self.generator_g = generator
        super().__init__(
            batch_size=batch_size,
            generators={
                'generator_f': self.generator_f,
                'generator_g': self.generator_g,
            },
            discriminators={
                'discriminator_x': self.discriminator_x,
                'discriminator_y': self.discriminator_y,
            },
            dataset_type=dataset_type,
            generators_optimizers={
                'generator_optimizer_f': self.generator_optimizer_f,
                'generator_optimizer_g': self.generator_optimizer_g,
            },
            discriminators_optimizers={
                'discriminator_optimizer_x': self.discriminator_optimizer_x,
                'discriminator_optimizer_y': self.discriminator_optimizer_y,
            },
            continue_training=continue_training,
            save_images_every_n_steps=save_images_every_n_steps,
            num_test_examples=NUM_TEST_EXAMPLES,
            checkpoint_step=checkpoint_step,
        )

    @tf.function
    @overrides
    def train_step(self, batch):
        real_x, real_y = batch

        with tf.GradientTape(persistent=True) as tape:
            fake_y = self.generator_g(real_x, training=True)
            cycled_x = self.generator_f(fake_y, training=True)

            fake_x = self.generator_f(real_y, training=True)
            cycled_y = self.generator_g(fake_x, training=True)

            # same_x and same_y are used for identity loss.
            same_x = self.generator_f(real_x, training=True)
            same_y = self.generator_g(real_y, training=True)

            disc_real_x = self.discriminator_x(real_x, training=True)
            disc_real_y = self.discriminator_y(real_y, training=True)

            disc_fake_x = self.discriminator_x(fake_x, training=True)
            disc_fake_y = self.discriminator_y(fake_y, training=True)

            # calculate the loss
            gen_g_loss = losses.generator_loss(disc_fake_y)
            gen_f_loss = losses.generator_loss(disc_fake_x)

            total_cycle_loss = losses.cycle_loss(real_x, cycled_x) + losses.cycle_loss(real_y, cycled_y)

            # Total generator loss = adversarial loss + cycle loss
            total_generator_g_loss = gen_g_loss + total_cycle_loss + losses.identity_loss(real_y, same_y)
            total_generator_f_loss = gen_f_loss + total_cycle_loss + losses.identity_loss(real_x, same_x)

            discriminator_x_loss = 0.5 * losses.discriminator_loss(disc_real_x, disc_fake_x)
            discriminator_y_loss = 0.5 * losses.discriminator_loss(disc_real_y, disc_fake_y)

        # Calculate the gradients for generator and discriminator
        generator_g_gradients = tape.gradient(
            total_generator_g_loss,
            self.generator_g.trainable_variables,
        )
        generator_f_gradients = tape.gradient(
            total_generator_f_loss,
            self.generator_f.trainable_variables,
        )

        discriminator_x_gradients = tape.gradient(
            discriminator_x_loss,
            self.discriminator_x.trainable_variables,
        )
        discriminator_y_gradients = tape.gradient(
            discriminator_y_loss,
            self.discriminator_y.trainable_variables,
        )

        # Apply the gradients to the optimizer
        self.generator_optimizer_g.apply_gradients(zip(generator_g_gradients, self.generator_g.trainable_variables))

        self.generator_optimizer_f.apply_gradients(zip(generator_f_gradients, self.generator_f.trainable_variables))

        self.discriminator_optimizer_x.apply_gradients(
            zip(discriminator_x_gradients, self.discriminator_x.trainable_variables)
        )

        self.discriminator_optimizer_y.apply_gradients(
            zip(discriminator_y_gradients, self.discriminator_y.trainable_variables)
        )
        return {
            'generator_g_loss':     total_generator_g_loss,
            'generator_f_loss':     total_generator_f_loss,
            'discriminator_x_loss': discriminator_x_loss,
            'discriminator_y_loss': discriminator_y_loss
        }

    @overrides
    def test_inputs(self, dataset):
        summer, _ = next(dataset.train_dataset)
        summer = summer[:NUM_TEST_EXAMPLES]
        return summer
