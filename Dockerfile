#
# The base image that the build will extend
#
FROM alpine:latest

# Docker container labels
#
LABEL org.ioccc.image.name="ioccc-submit"
LABEL org.ioccc.image.description="IOCCC Submit Server"
LABEL org.ioccc.image.version="0.7.1 2024-11-24"
LABEL org.ioccc.image.author="IOCCC Judges"
LABEL org.ioccc.image.contact="https://www.ioccc.org/judges.html"

# Create, if needed the /app tree in the image
#
RUN mkdir -p /app

# Copy everything from . into /app except for things mentioned in .dockerignore
#
COPY . /app

# Set permissions for /app
#
RUN chown root:root /app

# Specifies the "working directory" in the image where files will
# be copied and commands will be executed.
#
WORKDIR /app

# Setup the python environment needed by this image
#
RUN apk add tzdata
RUN apk add python3 py3-cryptography py3-pip py3-werkzeug py3-flask py3-authlib
RUN apk add py3-flask-login
RUN apk add uwsgi uwsgi-http uwsgi-cgi uwsgi-python3
RUN python3 -m pip install --break-system-packages -r etc/requirements.txt

# Set permissions for a number of top level files
#
RUN chown root:root .dockerignore .gitignore Dockerfile LICENSE README.md uwsgi.ini

# Set the default ownership for files under bin
#
RUN chown -R root:root bin

# Set the default ownership for files under etc
#
RUN chown -R root:root etc

# Set etc/iocccpasswd.json permissions
#
RUN <<EOT
    if [[ ! -s etc/iocccpasswd.json ]]; then
        cp -f etc/init.iocccpasswd.json etc/iocccpasswd.json
    fi
EOT
RUN chmod 0664 etc/iocccpasswd.json
RUN chown uwsgi:uwsgi etc/iocccpasswd.json

# Set etc/iocccpasswd.lock permissions
#
RUN chmod 0664 etc/iocccpasswd.lock
RUN chown uwsgi:uwsgi etc/iocccpasswd.lock

# Set permissions for etc/state.json
#
RUN <<EOT
    if [[ ! -s etc/state.json ]]; then
        cp -f etc/init.state.json etc/state.json
    fi
EOT
RUN chmod 0664 etc/state.json
RUN chown uwsgi:uwsgi etc/state.json

# Set etc/state.lock permissions
#
RUN chmod 0664 etc/state.lock
RUN chown uwsgi:uwsgi etc/state.lock

# Generate etc/.secret if not found or if empty
#
RUN <<EOT
    if [[ ! -s etc/.secret ]]; then
        /bin/sh ./bin/genflaskkey.sh
    fi
EOT

# Set permissions for etc/.secret
#
RUN chmod 0440 etc/.secret
RUN chown uwsgi:uwsgi etc/.secret

# Set the default ownership for files under static
#
RUN chown -R root:root static

# Set the default ownership for files under templates
#
RUN chown -R root:root templates

# Create the IOCCC users directory with permissions
#
RUN mkdir -p users
RUN chmod 2775 users
RUN chown -R uwsgi:uwsgi users

# setup python path
#
ENV PYTHONPATH=".:bin"

# Indicate the TCP port that the docker image would like to make available
#
EXPOSE 8191/tcp

# Set the default user for all subsequent instructions
#
USER uwsgi:uwsgi

# What to run as an docker executable
#
ENTRYPOINT [ "uwsgi" ]

# Default args given to the ENTRYPOINT
#
CMD [ "--http-socket", ":8191", \
      "--plugin", "python", \
      "--uid", "uwsgi", \
      "--gid", "uwsgi", \
      "uwsgi.ini" ]
