#!/bin/sh

cd src

alembic upgrade head
fastapi run main.py --proxy-headers

