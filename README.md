# Rate dumper

Dump skilling, bossing and misc. rates.

## Install
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```
## Run
```
usage: rate-dumper.py [-h] {ehp,ehb,misc} path

dump temple rates

positional arguments:
  {ehp,ehb,misc}  the rate category to dump
  path            the path to the output folder

optional arguments:
  -h, --help      show this help message and exit
```