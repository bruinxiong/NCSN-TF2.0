import argparse

def get_command_line_args():
    parser = argparse.ArgumentParser(description='I AM A HELP MESSAGE')
    parser.add_argument('--dataset', default='mnist',
                        help="tfds name of dataset. Default: 'mnist'")
    parser.add_argument('--num_L', default=10,
                        help="How many levels of noise to use. Default: 10")
    # TODO: add more command line arguments here!
    # possible: whether to use local data, where data is stored, checkpointing

    return parser.parse_args()