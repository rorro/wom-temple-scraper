#!/bin/bash
. .venv/bin/activate
python rate-dumper.py ehp /home/david/personal_projects/wise-old-man/server/src/api/modules/efficiency/configs/ehp
python rate-dumper.py ehb /home/david/personal_projects/wise-old-man/server/src/api/modules/efficiency/configs/ehb
pushd /home/david/personal_projects/wise-old-man/server/src/api/modules/efficiency/configs
npx prettier --write **/*.ts
popd

