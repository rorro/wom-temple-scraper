#!/bin/bash
. .venv/bin/activate
python rate-dumper.py ehp ~/personal_projects/wise-old-man/server/src/api/modules/efficiency/configs/ehp
python rate-dumper.py ehb ~/personal_projects/wise-old-man/server/src/api/modules/efficiency/configs/ehb
pushd ~/personal_projects/wise-old-man/server/src/api/modules/efficiency/configs
npx prettier --write **/*.ts
popd
deactivate
