#!/bin/bash
. .venv/bin/activate
python rate-dumper.py ehp ~/personal-projects/wise-old-man/server/src/api/modules/efficiency/configs/ehp
python rate-dumper.py ehb ~/personal-projects/wise-old-man/server/src/api/modules/efficiency/configs/ehb
pushd ~/personal-projects/wise-old-man/server/src/api/modules/efficiency/configs
npx prettier --write **/*.ts
popd
deactivate
