FROM metsi/ats:master-latest AS foundation

LABEL maintainer="Jupyter Project <jupyter@googlegroups.com>"
ARG NB_USER="jovyan"
ARG NB_UID="1000"
ARG NB_GID="100"

# Fix: https://github.com/hadolint/hadolint/wiki/DL4006
# Fix: https://github.com/koalaman/shellcheck/wiki/SC3014
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

# Install all OS dependencies for the Server that starts
# but lacks all features (e.g., download as all possible file formats)
ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update --yes && \
    # - `apt-get upgrade` is run to patch known vulnerabilities in apt-get packages as
    #   the Ubuntu base image is rebuilt too seldom sometimes (less than once a month)
    apt-get upgrade --yes && \
    apt-get install --yes --no-install-recommends \
    # - bzip2 is necessary to extract the micromamba executable.
    bzip2 \
    ca-certificates \
    locales \
    sudo \
    # - tini is installed as a helpful container entrypoint that reaps zombie
    #   processes and such of the actual executable we want to start, see
    #   https://github.com/krallin/tini#why-tini for details.
    tini \
    wget && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && \
    locale-gen

# Configure environment
ENV CONDA_DIR=/opt/conda \
    SHELL=/bin/bash \
    NB_USER="${NB_USER}" \
    NB_UID=${NB_UID} \
    NB_GID=${NB_GID} \
    LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8
ENV PATH="${CONDA_DIR}/bin:${PATH}" \
    HOME="/home/${NB_USER}"

# Copy a script that we will use to correct permissions after running certain commands
#COPY fix-permissions /usr/local/bin/fix-permissions
RUN cd /usr/local/bin/ \
    && wget https://raw.githubusercontent.com/jupyter/docker-stacks/main/images/docker-stacks-foundation/fix-permissions \
    && chmod a+rx /usr/local/bin/fix-permissions

# Enable prompt color in the skeleton .bashrc before creating the default NB_USER
# hadolint ignore=SC2016
RUN sed -i 's/^#force_color_prompt=yes/force_color_prompt=yes/' /etc/skel/.bashrc && \
   # Add call to conda init script see https://stackoverflow.com/a/58081608/4413446
   echo 'eval "$(command conda shell.bash hook 2> /dev/null)"' >> /etc/skel/.bashrc

# Create NB_USER with name jovyan user with UID=1000 and in the 'users' group
# and make sure these dirs are writable by the `users` group.
RUN echo "auth requisite pam_deny.so" >> /etc/pam.d/su && \
    sed -i.bak -e 's/^%admin/#%admin/' /etc/sudoers && \
    sed -i.bak -e 's/^%sudo/#%sudo/' /etc/sudoers && \
    useradd --no-log-init --create-home --shell /bin/bash --uid "${NB_UID}" --no-user-group "${NB_USER}" && \
    mkdir -p "${CONDA_DIR}" && \
    chown "${NB_USER}:${NB_GID}" "${CONDA_DIR}" && \
    chmod g+w /etc/passwd && \
    fix-permissions "${CONDA_DIR}" && \
    fix-permissions "/home/${NB_USER}"

USER ${NB_UID}

# Pin the Python version here, or set it to "default"
ARG PYTHON_VERSION=3.11

# Setup work directory for backward-compatibility
RUN mkdir "/home/${NB_USER}/work" && \
    fix-permissions "/home/${NB_USER}"

# Download and install Micromamba, and initialize the Conda prefix.
#   <https://github.com/mamba-org/mamba#micromamba>
#   Similar projects using Micromamba:
#     - Micromamba-Docker: <https://github.com/mamba-org/micromamba-docker>
#     - repo2docker: <https://github.com/jupyterhub/repo2docker>
# Install Python, Mamba, and jupyter_core
# Cleanup temporary files and remove Micromamba
# Correct permissions
# Do all this in a single RUN command to avoid duplicating all of the
# files across image layers when the permissions change
USER root
RUN cd / \
    && wget https://raw.githubusercontent.com/jupyter/docker-stacks/main/images/docker-stacks-foundation/initial-condarc \
    && mv initial-condarc ${CONDA_DIR}/.condarc \
    && chown ${NB_UID}:${NB_GID} ${CONDA_DIR}/.condarc
#COPY --chown="${NB_UID}:${NB_GID}" initial-condarc "${CONDA_DIR}/.condarc"
WORKDIR /tmp
RUN set -x && \
    arch=$(uname -m) && \
    if [ "${arch}" = "x86_64" ]; then \
        # Should be simpler, see <https://github.com/mamba-org/mamba/issues/1437>
        arch="64"; \
    fi && \
    wget --progress=dot:giga -O /tmp/micromamba.tar.bz2 \
        "https://micromamba.snakepit.net/api/micromamba/linux-${arch}/latest" && \
    tar -xvjf /tmp/micromamba.tar.bz2 --strip-components=1 bin/micromamba && \
    rm /tmp/micromamba.tar.bz2 && \
    PYTHON_SPECIFIER="python=${PYTHON_VERSION}" && \
    if [[ "${PYTHON_VERSION}" == "default" ]]; then PYTHON_SPECIFIER="python"; fi && \
    # Install the packages
    ./micromamba install \
        --root-prefix="${CONDA_DIR}" \
        --prefix="${CONDA_DIR}" \
        --yes \
        "${PYTHON_SPECIFIER}" \
        'mamba' \
        'jupyter_core' && \
    rm micromamba && \
    # Pin major.minor version of python
    mamba list python | grep '^python ' | tr -s ' ' | cut -d ' ' -f 1,2 >> "${CONDA_DIR}/conda-meta/pinned" && \
    mamba clean --all -f -y && \
    fix-permissions "${CONDA_DIR}" && \
    fix-permissions "/home/${NB_USER}"

# Configure container startup
ENTRYPOINT ["tini", "-g", "--"]
CMD ["start.sh"]

# Copy local files as late as possible to avoid cache busting
RUN cd /usr/local/bin \
    && wget https://raw.githubusercontent.com/jupyter/docker-stacks/main/images/docker-stacks-foundation/start.sh \
    && wget https://raw.githubusercontent.com/jupyter/docker-stacks/main/images/docker-stacks-foundation/run-hooks.sh

USER root

# Create dirs for startup hooks
RUN mkdir /usr/local/bin/start-notebook.d && \
    mkdir /usr/local/bin/before-notebook.d

# Switch back to jovyan to avoid accidental container runs as root
USER ${NB_UID}

WORKDIR "${HOME}"

FROM foundation as base_notebook

# set up jupyter notebook infrastructure

# Fix: https://github.com/hadolint/hadolint/wiki/DL4006
# Fix: https://github.com/koalaman/shellcheck/wiki/SC3014
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

# Install all OS dependencies for the Server that starts but lacks all
# features (e.g., download as all possible file formats)
RUN apt-get update --yes && \
    apt-get install --yes --no-install-recommends \
    fonts-liberation \
    # - pandoc is used to convert notebooks to html files
    #   it's not present in the aarch64 Ubuntu image, so we install it here
    pandoc \
    # - run-one - a wrapper script that runs no more
    #   than one unique  instance  of  some  command with a unique set of arguments,
    #   we use `run-one-constantly` to support the `RESTARTABLE` option
    run-one && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER ${NB_UID}

# Install JupyterLab, Jupyter Notebook, JupyterHub and NBClassic
# Generate a Jupyter Server config
# Cleanup temporary files
# Correct permissions
# Do all this in a single RUN command to avoid duplicating all of the
# files across image layers when the permissions change
WORKDIR /tmp
RUN mamba install --yes \
    'jupyterlab' \
    'notebook' \
    'jupyterhub' \
    'nbclassic' && \
    jupyter server --generate-config && \
    mamba clean --all -f -y && \
    npm cache clean --force && \
    jupyter lab clean && \
    rm -rf "/home/${NB_USER}/.cache/yarn" && \
    fix-permissions "${CONDA_DIR}" && \
    fix-permissions "/home/${NB_USER}"

ENV JUPYTER_PORT=8888
EXPOSE $JUPYTER_PORT

# Configure container startup
CMD ["start-notebook.py"]

# Copy local files as late as possible to avoid cache busting
USER root
RUN cd /usr/local/bin \
    && wget https://raw.githubusercontent.com/jupyter/docker-stacks/main/images/base-notebook/start-notebook.py \
    && wget https://raw.githubusercontent.com/jupyter/docker-stacks/main/images/base-notebook/start-notebook.sh \
    && wget https://raw.githubusercontent.com/jupyter/docker-stacks/main/images/base-notebook/start-singleuser.py \
    && wget https://raw.githubusercontent.com/jupyter/docker-stacks/main/images/base-notebook/start-singleuser.sh \
    && chown ${NB_UID}:${NB_GID} start* \
    && chmod u+x start* \
    && mkdir /etc/jupyter \
    && cd /etc/jupyter/ \
    && wget https://raw.githubusercontent.com/jupyter/docker-stacks/main/images/base-notebook/jupyter_server_config.py \
    && wget https://raw.githubusercontent.com/jupyter/docker-stacks/main/images/base-notebook/docker_healthcheck.py \
    && chown ${NB_UID}:${NB_GID} jupyter_server_config.py docker_healthcheck.py \
    && chmod u+x jupyter_server_config.py docker_healthcheck.py
#COPY start-notebook.py start-notebook.sh start-singleuser.py start-singleuser.sh /usr/local/bin/
#COPY jupyter_server_config.py docker_healthcheck.py /etc/jupyter/

# Fix permissions on /etc/jupyter as root
#USER root
RUN fix-permissions /etc/jupyter/

# HEALTHCHECK documentation: https://docs.docker.com/engine/reference/builder/#healthcheck
# This healtcheck works well for `lab`, `notebook`, `nbclassic`, `server`, and `retro` jupyter commands
# https://github.com/jupyter/docker-stacks/issues/915#issuecomment-1068528799
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \
    CMD /etc/jupyter/docker_healthcheck.py || exit 1

# Switch back to jovyan to avoid accidental container runs as root
USER ${NB_UID}

WORKDIR "${HOME}"

FROM base_notebook AS minimal_notebook

# Fix: https://github.com/hadolint/hadolint/wiki/DL4006
# Fix: https://github.com/koalaman/shellcheck/wiki/SC3014
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

# Install all OS dependencies for a fully functional Server
RUN apt-get update --yes && \
    apt-get install --yes --no-install-recommends \
    # Common useful utilities
    curl \
    git \
    nano-tiny \
    tzdata \
    unzip \
    vim-tiny \
    # git-over-ssh
    openssh-client \
    # less is needed to run help in R
    # see: https://github.com/jupyter/docker-stacks/issues/1588
    less \
    # nbconvert dependencies
    # https://nbconvert.readthedocs.io/en/latest/install.html#installing-tex
    texlive-xetex \
    texlive-fonts-recommended \
    texlive-plain-generic \
    # Enable clipboard on Linux host systems
    xclip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create alternative for nano -> nano-tiny
RUN update-alternatives --install /usr/bin/nano nano /bin/nano-tiny 10

# Switch back to jovyan to avoid accidental container runs as root
USER ${NB_UID}

# Add an R mimetype option to specify how the plot returns from R to the browser
# COPY --chown=${NB_UID}:${NB_GID} Rprofile.site /opt/conda/lib/R/etc/

#
# Stage 1 -- setup base CI environment
## okay, now build WW
FROM minimal_notebook AS ww_env_base_user
LABEL Description="Base env for CI of Watershed Workflow"

ARG env_name=watershed_workflow
ARG user=jovyan
ENV CONDA_BIN=mamba

USER ${user}

WORKDIR /home/${user}/tmp
RUN mkdir /home/${user}/environments

# # dump the environments to disk so they can be recovered if desired
# RUN ${CONDA_BIN} env export -n ${env_name} > /home/${user}/environments/environment-Linux.yml

#
# New approach, use the current environment.yml
#
# -- creates env: watershed_workflow
COPY environments/environment-Linux.yml /home/${user}/environments
RUN --mount=type=cache,uid=1000,gid=100,target=/opt/conda/pkgs \
    ${CONDA_BIN} env create -f /home/${user}/environments/environment-Linux.yml

# -- creates env: watershed_workflow_tools
COPY environments/environment-TOOLS-Linux.yml /home/${user}/environments
RUN --mount=type=cache,uid=1000,gid=100,target=/opt/conda/pkgs \
    ${CONDA_BIN} env create -f /home/${user}/environments/environment-TOOLS-Linux.yml

# shouldn't need default?
# -- creates env: default
#COPY environments/environment-USER-Linux.yml /home/${user}/environments
#RUN --mount=type=cache,uid=1000,gid=100,target=/opt/conda/pkgs \
#    ${CONDA_BIN} env create -f /home/${user}/environments/environment-USER-Linux.yml

# install the kernel on base's jupyterlab
USER root
RUN ${CONDA_BIN} run -n ${env_name} python -m ipykernel install \
        --name watershed_workflow --display-name "Python3 (watershed_workflow)"
USER ${user}

#
# Stage 2 -- add in the pip
#
FROM ww_env_base_user AS ww_env_pip_user

WORKDIR /home/${user}/tmp
COPY requirements.txt /home/${user}/tmp/requirements.txt
RUN ${CONDA_BIN} run -n ${env_name} python -m pip install -r requirements.txt


#
# Stage 3 -- add in Exodus
#
FROM ww_env_pip_user AS ww_env_user

ENV PATH="/opt/conda/envs/watershed_workflow_tools/bin:${PATH}"
ENV SEACAS_DIR="/opt/conda/envs/${env_name}"
ENV CONDA_PREFIX="/opt/conda/envs/${env_name}"

# get the source
WORKDIR /opt/conda/envs/${env_name}/src
COPY environments/exodus_py.patch /opt/conda/envs/${env_name}/src/exodus_py.patch
RUN git clone -b v2021-10-11 --depth=1 https://github.com/gsjaardema/seacas/ seacas
WORKDIR /opt/conda/envs/${env_name}/src/seacas
RUN git apply ../exodus_py.patch

# configure
WORKDIR /home/${user}/tmp
COPY --chown=${user}:${user} docker/configure-seacas.sh /home/${user}/tmp/configure-seacas.sh
RUN chmod +x  /home/${user}/tmp/configure-seacas.sh
WORKDIR /home/${user}/tmp/seacas-build
RUN ${CONDA_BIN} run -n watershed_workflow ../configure-seacas.sh \
    && make -j install

# exodus installs its wrappers in an invalid place for python...
RUN cp /opt/conda/envs/${env_name}/lib/exodus3.py \
       /opt/conda/envs/${env_name}/lib/python3.10/site-packages/


# clean up
RUN rm -rf /home/${user}/tmp

# unclear where this comes from, must be in the jupyter/minimal-notebook?
RUN rm -rf /home/${user}/work

#
# Stage 6 -- run tests!
#
FROM ww_env_user AS ww_user

WORKDIR /home/${user}/watershed_workflow

# copy over source code
COPY  --chown=${user}:${user} . /home/${user}/watershed_workflow
RUN ${CONDA_BIN} run -n watershed_workflow python -m pip install -e .

# run the tests
RUN ${CONDA_BIN} run -n watershed_workflow python -m pytest watershed_workflow/test/

# Set up the workspace.
#
# create a watershed_workflowrc that will be picked up
RUN cp watershed_workflowrc /home/${user}/.watershed_workflowrc

# create a directory for data -- NOTE, the user should mount a
# persistent volume at this location!
RUN mkdir /home/${user}/data

# create a working directory -- NOTE, the user should mount a
# persistent volume at this location!
RUN mkdir /home/${user}/workdir
WORKDIR /home/${user}/workdir

# note, don't set a command here, the entrypoint is set by the jupyter stack