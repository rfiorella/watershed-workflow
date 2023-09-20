#!/bin/bash

# how to (re-)create the local environments
ENV_NAME="watershed_workflow-`date +%F`"
python environments/create_envs.py --manager=mamba --env-name=${ENV_NAME} --with-user-env --user-env-name watershed_workflow_user --with-tools-env OSX 
conda run -n ${ENV_NAME} python -m ipykernel install \
        --name ${ENV_NAME} --display-name "Python3 ${ENV_NAME}"
conda env export -n ${ENV_NAME} --from-history > environments/environment-OSX.yml

CI_ENV_NAME="watershed_workflow_CI-`date +%F`"
python environments/create_envs.py --manager=mamba --env-type=CI --env-name=${CI_ENV_NAME} --with-user-env --user-env-name watershed_workflow_user OSX
conda run -n ${CI_ENV_NAME} python -m ipykernel install \
        --name ${CI_ENV_NAME} --display-name "Python3 ${CI_ENV_NAME}"
conda env export -n ${CI_ENV_NAME} --from-history > environments/environment-CI-OSX.yml

DEV_ENV_NAME="watershed_workflow_DEV-`date +%F`"
python environments/create_envs.py --manager=mamba --env-type=DEV --env-name=${DEV_ENV_NAME} --with-user-env --user-env-name watershed_worfklow_user OSX
conda run -n ${DEV_ENV_NAME} python -m ipykernel install \
        --name ${DEV_ENV_NAME} --display-name "Python3 ${DEV_ENV_NAME}"
conda env export -n ${DEV_ENV_NAME} --from-history > environments/environment-DEV-OSX.yml

