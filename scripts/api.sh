#!/bin/bash

cd src

alembic upgrade head
fastapi run api_svc.py --proxy-headers --host ::

