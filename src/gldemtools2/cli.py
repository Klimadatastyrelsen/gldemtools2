import argparse
import sys

def parse_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=str)
    parser.add_argument('row', type=int)
    parser.add_argument('col', type=int)
    parser.add_argument('out_path', type=str)
    parsed_args = parser.parse_args(args)
    return parsed_args

def main():
    input_args = parse_args(sys.argv[1:])
