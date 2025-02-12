FROM python:3.12

# Install necessary packages
RUN apt-get update && apt-get install -y \
    firefox-esr \
    wget

# Download and install geckodriver for ARM64
RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-linux-aarch64.tar.gz \
    && tar -xvzf geckodriver-v0.33.0-linux-aarch64.tar.gz \
    && chmod +x geckodriver \
    && mv geckodriver /usr/local/bin/ \
    && rm geckodriver-v0.33.0-linux-aarch64.tar.gz

# Install Python packages in the virtual environment
RUN pip install --no-cache-dir \
    beautifulsoup4 \
    requests \
    pandas \
    numpy \
    matplotlib \
    scikit-image \
    scikit-learn \
    scipy \
    selenium \
    seaborn

# Set environment variable for geckodriver
ENV GECKODRIVER_PATH=/usr/local/bin/geckodriver

CMD ["sleep", "infinity"]