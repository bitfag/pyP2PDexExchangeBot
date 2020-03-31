FROM python:3

ENV APPDIR=/opt/code
ENV USERNAME=_bot

COPY Pipfile* $APPDIR/

RUN set -xe ; \
    cd $APPDIR ;\
    pip install pipenv ;\
    pipenv install --system --deploy ;\
    useradd -m $USERNAME

# copy our files
COPY *.py $APPDIR/
COPY database/ $APPDIR/database/

WORKDIR $APPDIR

VOLUME $APPDIR/database

USER $USERNAME

CMD $APPDIR/bot.py
