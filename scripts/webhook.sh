#!/bin/bash

cd src
fastapi run webhook_svc.py --proxy-headers --host ::

