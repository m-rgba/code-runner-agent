FROM quay.io/jupyter/datascience-notebook:latest

USER root

# Install Docker
RUN apt-get update && \
    apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    sudo && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd docker || true && \
    usermod -aG docker jovyan && \
    # Add jovyan to sudoers
    echo "jovyan ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/jovyan

# Create a startup script
COPY --chown=root:root <<-"EOF" /usr/local/bin/start.sh
#!/bin/bash
if [ -e /var/run/docker.sock ]; then
    # Get the GID of the docker socket
    DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
    
    # Add jovyan to the docker group with the correct GID
    sudo groupmod -g ${DOCKER_GID} docker || true
    sudo usermod -aG docker jovyan || true
    
    # Set permissions on docker socket
    sudo chmod 666 /var/run/docker.sock || true
fi

# Start Jupyter
exec jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root
EOF

RUN chmod +x /usr/local/bin/start.sh

USER jovyan
ENTRYPOINT ["/usr/local/bin/start.sh"]