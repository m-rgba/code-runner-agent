FROM python:3.12

# Install necessary packages
RUN apt-get update && apt-get install -y wget

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
    
CMD ["sleep", "infinity"]