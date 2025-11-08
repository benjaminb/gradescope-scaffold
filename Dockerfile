# syntax=docker/dockerfile:1.2
ARG BASE_REPO=gradescope/autograder-base
ARG TAG=latest
ARG ASSIGNMENT

FROM ${BASE_REPO}:${TAG}
ARG ASSIGNMENT
# Install software-properties-common and add deadsnakes PPA
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Python 3.13 and set it as the default python3
RUN apt-get update && \
    apt-get install -y python3.13 python3.13-venv python3.13-dev python3-distutils && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1 && \
    update-alternatives --set python3 /usr/bin/python3.13 && \
    # ln -sf /usr/bin/python3.13 /usr/local/bin/python3 && \
    ln -sf /usr/bin/python3.13 /usr/local/bin/python && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install pip for Python 3.13
RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    python3.13 get-pip.py && \
    rm get-pip.py

# Install dependencies (Copy requirements.txt separately to leverage caching)
COPY common/source/requirements.txt /autograder/source/requirements.txt
RUN python -m pip install --upgrade pip
RUN python -m pip install -v -r /autograder/source/requirements.txt
    
# Copy remaining source files
COPY common/source/* /autograder/source/

# Copy assignment-specific test files
COPY ${ASSIGNMENT}/ /autograder/source/tests/

# Copy common test files such as cs7helpers.py
COPY common/tests/* /autograder/source/tests/
RUN cp /autograder/source/run_autograder /autograder/run_autograder

# Add any secret API keys
RUN --mount=type=secret,id=.env \
    # Read the key and store in environment setup
    cat /run/secrets/.env >> /autograder/.env && \
    chmod 600 /autograder/.env 

# Ensure that scripts are Unix-friendly and executable
RUN chmod +x /autograder/run_autograder

RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*