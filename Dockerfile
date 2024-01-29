FROM python:3.11.6-alpine
LABEL authors="Miguel Afonso <mafonso@gmail.com>"

# Install requirements
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Copy source code
COPY src /opt/src
WORKDIR /opt/src

# Run application
CMD ["python", "main.py"]

# Expose port
EXPOSE 3000
