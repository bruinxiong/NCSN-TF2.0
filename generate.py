import os
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from PIL import Image
from tqdm import tqdm

import configs
import utils
from datasets.dataset_loader import get_data_k_nearest

utils.manage_gpu_memory_usage()


def clamped(x):
    return tf.clip_by_value(x, 0, 1.0)


def plot_grayscale(image):
    plt.imshow(image, cmap=plt.get_cmap("gray"))
    plt.show()


def save_image(image, dir):
    plt.imshow(image, cmap=plt.get_cmap("gray"))
    plt.savefig(dir)


def save_as_grid(images, filename, spacing=2):
    """
    Partially from https://stackoverflow.com/questions/42040747/more-idiomatic-way-to-display-images-in-a-grid-with-numpy
    :param images:
    :return:
    """
    # Define grid dimensions
    n_images, height, width, channels = images.shape
    rows = np.floor(np.sqrt(n_images)).astype(int)
    cols = n_images // rows

    # Init image
    grid_cols = rows * height + (rows + 1) * spacing
    grid_rows = cols * width + (cols + 1) * spacing
    mode = 'L' if channels == 1 else "RGB"
    im = Image.new(mode, (grid_rows, grid_cols))
    for i in range(n_images):
        row = i // rows
        col = i % rows
        row_start = row * height + (1 + row) * spacing
        col_start = col * width + (1 + col) * spacing
        im.paste(tf.keras.preprocessing.image.array_to_img(images[i]), (row_start, col_start))
        # im.show()

    im.save(filename, format="PNG")


@tf.function
def sample_one_step(model, x, idx_sigmas, alpha_i):
    z_t = tf.random.normal(shape=x.get_shape(), mean=0, stddev=1.0)  # TODO: check if stddev is correct
    score = model([x, idx_sigmas])
    noise = tf.sqrt(alpha_i * 2) * z_t
    return x + alpha_i * score + noise


def sample_many(model, sigmas, batch_size=128, eps=2 * 1e-5, T=100, n_images=1):
    """
    Used for sampling big amount of images (e.g. 50000)
    :param model: model for sampling (RefineNet)
    :param sigmas: sigma levels of noise
    :param eps:
    :param T: iteration per sigma level
    :return: Tensor of dimensions (n_images, width, height, channels)
    """
    # Tuple for (n_images, width, height, channels)
    image_size = (n_images,) + utils.get_dataset_image_size(configs.config_values.dataset)
    batch_size = min(batch_size, n_images)

    with tf.device('CPU'):
        x = tf.random.uniform(shape=image_size)
    x = tf.data.Dataset.from_tensor_slices(x).batch(batch_size)
    x_processed = None

    n_processed_images = 0
    for i_batch, batch in enumerate(
            tqdm(x, total=tf.data.experimental.cardinality(x).numpy(), desc='Generating samples')):
        for i, sigma_i in enumerate(sigmas):
            alpha_i = eps * (sigma_i / sigmas[-1]) ** 2
            idx_sigmas = tf.ones(batch.get_shape()[0], dtype=tf.int32) * i
            for t in range(T):
                batch = sample_one_step(model, batch, idx_sigmas, alpha_i)

        with tf.device('CPU'):
            if x_processed is not None:
                x_processed = tf.concat([x_processed, batch], axis=0)
            else:
                x_processed = batch

        n_processed_images += batch_size

    return x_processed


@tf.function
def _preprocess_image_to_save(x):
    x = x * 255
    x = x + 0.5
    x = tf.clip_by_value(x, 0, 255)
    return x


def sample_many_and_save(model, sigmas, batch_size=128, eps=2 * 1e-5, T=100, n_images=1, save_directory=None):
    """
    Used for sampling big amount of images (e.g. 50000)
    :param model: model for sampling (RefineNet)
    :param sigmas: sigma levels of noise
    :param eps:
    :param T: iteration per sigma level
    :return: Tensor of dimensions (n_images, width, height, channels)
    """
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)

    # Tuple for (n_images, width, height, channels)
    image_size = (n_images,) + utils.get_dataset_image_size(configs.config_values.dataset)
    batch_size = min(batch_size, n_images)

    with tf.device('CPU'):
        x = tf.random.uniform(shape=image_size)
    x = tf.data.Dataset.from_tensor_slices(x).batch(batch_size)

    idx_image = 0
    for i_batch, batch in enumerate(
            tqdm(x, total=tf.data.experimental.cardinality(x).numpy(), desc='Generating samples')):
        for i, sigma_i in enumerate(sigmas):
            alpha_i = eps * (sigma_i / sigmas[-1]) ** 2
            idx_sigmas = tf.ones(batch.get_shape()[0], dtype=tf.int32) * i
            for t in range(T):
                batch = sample_one_step(model, batch, idx_sigmas, alpha_i)

        if save_directory is not None:
            batch = _preprocess_image_to_save(batch)
            for image in batch:
                im = Image.new('RGB', image_size[1:3])
                im.paste(tf.keras.preprocessing.image.array_to_img(tf.tile(image, [1, 1, 3])))
                im.save(save_directory + f'{idx_image}.png', format="PNG")
                idx_image += 1


def sample_and_save(model, sigmas, eps=2 * 1e-5, T=100, n_images=1, save_directory=None):
    """
    :param model:
    :param sigmas:
    :param eps:
    :param T:
    :return:
    """
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)

    image_size = (n_images,) + utils.get_dataset_image_size(configs.config_values.dataset)

    x = tf.random.uniform(shape=image_size)

    for i, sigma_i in enumerate(tqdm(sigmas, desc='Sampling for each sigma')):
        alpha_i = eps * (sigma_i / sigmas[-1]) ** 2
        idx_sigmas = tf.ones(n_images, dtype=tf.int32) * i
        for t in range(T):
            x = sample_one_step(model, x, idx_sigmas, alpha_i)

            if (t + 1) % 10 == 0:
                save_as_grid(x, save_directory + f'sigma{i + 1}_t{t + 1}.png')
    return x


if __name__ == '__main__':
    tf.random.set_seed(2019)

    tf.get_logger().setLevel('ERROR')
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

    args = utils.get_command_line_args()
    configs.config_values = args

    save_dir, complete_model_name = utils.get_savemodel_dir()
    model, optimizer, step = utils.try_load_model(save_dir, verbose=True)
    start_time = datetime.now().strftime("%y%m%d-%H%M%S")

    model_directory = './saved_models/'

    sigma_levels = tf.math.exp(tf.linspace(tf.math.log(configs.config_values.sigma_high),
                                           tf.math.log(configs.config_values.sigma_low),
                                           configs.config_values.num_L))

    samples_directory = './samples/' + f'{start_time}_{configs.config_values.dataset}' \
                                       f'_{step}steps_{configs.config_values.filters}filters' + "/"
    if not os.path.exists(samples_directory):
        os.makedirs(samples_directory)

    if configs.config_values.find_nearest:
        n_images = 10  # TODO make this not be hard-coded
        samples = tf.split(sample_many(model, sigma_levels, T=100, n_images=n_images), n_images)
        data_as_array = get_data_k_nearest(configs.config_values.dataset)
        data_as_array = data_as_array.batch(int(tf.data.experimental.cardinality(data_as_array)))
        data_as_array = tf.data.experimental.get_single_element(data_as_array)

        for i, sample in enumerate(samples):
            save_image(sample[0, :, :, 0], samples_directory + f'sample_{i}')
            k_closest_images = utils.find_k_closest(sample, configs.config_values.k, data_as_array)
            for j, img in enumerate(k_closest_images):
                save_image(img[0, :, :, 0], samples_directory + f'sample_{i}_closest_{j}')
    else:
        n_images = 100
        sample_and_save(model, sigma_levels, n_images=n_images, save_directory=samples_directory)
